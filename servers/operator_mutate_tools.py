"""Operator mutate tools: run_command, fanout, playbooks, runbooks, alerts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from asgiref.sync import async_to_sync
from django.utils import timezone
from loguru import logger

from app.assistant_actions import (
    AssistantActionContext,
    AssistantActionError,
    AssistantActionSpec,
    register_action,
)
from app.tools.safety import evaluate_command_safety
from servers.views.server_helpers import (
    _accessible_servers_queryset,
    _require_ssh_server,
    _resolve_server_secret,
    _server_has_capability,
)


def _int_arg(ctx: AssistantActionContext, key: str, *, required: bool = True) -> int | None:
    value = ctx.input_payload.get(key)
    if value is None or value == "":
        if required:
            raise AssistantActionError(f"{key} is required")
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AssistantActionError(f"{key} must be an integer") from exc
    if parsed <= 0:
        raise AssistantActionError(f"{key} must be positive")
    return parsed


def _server_for_user(user, server_id: int):
    server = _accessible_servers_queryset(user).filter(pk=server_id).first()
    if server is None:
        raise AssistantActionError("Server not found or not accessible", status=404)
    return server


def _resolve_secret(ctx: AssistantActionContext, server) -> str:
    """Resolve SSH password/passphrase even without HTTP request (Operator WS).

    Order:
    1) request-aware path (session MASTER_PASSWORD / payload)
    2) managed secrets + legacy decrypt with env MASTER_PASSWORD
    3) empty string for pure key auth
    """
    payload = ctx.input_payload if isinstance(ctx.input_payload, dict) else {}
    if ctx.request is not None:
        try:
            secret = _resolve_server_secret(server, ctx.request, payload)
            if secret:
                return secret
        except Exception as exc:  # noqa: BLE001
            # Fall through to request-less path before failing hard
            logger.warning("request secret resolve failed for {}: {}", server.name, exc)

    # WebSocket / background: no Django request.session — still decrypt stored secrets.
    try:
        from servers.secret_utils import get_server_auth_secret

        direct = str(payload.get("password") or "").strip()
        secret = get_server_auth_secret(server, master_password="", fallback_plain=direct)
        if secret:
            return secret
    except Exception as exc:  # noqa: BLE001
        raise AssistantActionError(f"Cannot resolve credentials: {exc}") from exc

    # key-only hosts legitimately have no password
    if getattr(server, "auth_method", "") in {"key", "key_password"}:
        return ""
    # password auth without a resolvable secret is a hard error (avoid silent Permission denied)
    if getattr(server, "auth_method", "") in {"password", "key_password"}:
        raise AssistantActionError(
            "Не удалось получить пароль сервера. "
            "Сохрани credentials в Managed Secret или задай MASTER_PASSWORD для legacy-шифрования."
        )
    return ""


def _execute_on_server(ctx: AssistantActionContext, server, command: str, *, allow_destructive: bool) -> dict[str, Any]:
    risk = evaluate_command_safety(command)
    if risk.is_dangerous and not allow_destructive:
        return {
            "ok": False,
            "server_id": server.id,
            "server_name": server.name,
            "blocked": True,
            "error": "Dangerous command requires allow_destructive=true after confirmation",
            "risk_categories": list(risk.categories),
        }
    if getattr(server, "ai_read_only", False) and not command.strip().startswith(
        ("ls", "cat ", "df", "free", "uptime", "ps ", "systemctl status", "journalctl", "uname", "hostname", "whoami", "id", "pwd", "echo ")
    ):
        # Soft guard: ai_read_only blocks non-read-ish commands unless clearly status-like
        if risk.is_dangerous or any(tok in command for tok in ("rm ", "mv ", "chmod", "chown", "systemctl restart", "systemctl stop", "apt ", "yum ", "dnf ")):
            return {
                "ok": False,
                "server_id": server.id,
                "server_name": server.name,
                "blocked": True,
                "error": "Server is ai_read_only — mutating command blocked",
            }

    _require_ssh_server(server)
    if not _server_has_capability(server, ctx.user, "connect_terminal"):
        return {
            "ok": False,
            "server_id": server.id,
            "server_name": server.name,
            "error": "Missing capability: connect_terminal",
        }

    secret = _resolve_secret(ctx, server)
    try:
        from servers.linux_ui_runtime import _run_command_result

        result = async_to_sync(_run_command_result)(server, secret=secret, command=command)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)[:500]
        # Auth/connect failures are expected operator outcomes — no full traceback spam
        if "Permission denied" in msg or "Authentication" in msg or "timed out" in msg.lower():
            logger.warning("operator run_command failed on {}: {}", server.name, msg)
        else:
            logger.exception("operator run_command failed on %s", server.name)
        return {
            "ok": False,
            "server_id": server.id,
            "server_name": server.name,
            "error": msg,
            "output": msg,
        }

    stdout = str(result.get("stdout") or "")
    stderr = str(result.get("stderr") or "")
    code = result.get("exit_status", result.get("exit_code", -1))
    out = (stdout + ("\n" + stderr if stderr else "")).strip()
    return {
        "ok": code in (0, "0", None),
        "server_id": server.id,
        "server_name": server.name,
        "exit_code": code,
        "output": out[:8000],
        "risk_categories": list(risk.categories),
    }


def run_command(ctx: AssistantActionContext) -> dict[str, Any]:
    server_id = _int_arg(ctx, "server_id")
    assert server_id is not None
    command = str(ctx.input_payload.get("command") or ctx.input_payload.get("cmd") or "").strip()
    if not command:
        raise AssistantActionError("command is required")
    allow_destructive = bool(ctx.input_payload.get("allow_destructive"))
    server = _server_for_user(ctx.user, server_id)
    result = _execute_on_server(ctx, server, command, allow_destructive=allow_destructive)
    result["target_url"] = f"/servers/{server.id}/terminal"
    result["blast_radius"] = {"server_ids": [server.id], "server_names": [server.name]}
    result["dry_run_preview"] = {"command": command, "server": server.name}
    # Simple undo heuristics
    undo = _guess_undo(command)
    if undo:
        result["undo_payload"] = {"server_id": server.id, "command": undo}
    return result


def run_fanout(ctx: AssistantActionContext) -> dict[str, Any]:
    command = str(ctx.input_payload.get("command") or ctx.input_payload.get("cmd") or "").strip()
    if not command:
        raise AssistantActionError("command is required")
    allow_destructive = bool(ctx.input_payload.get("allow_destructive"))
    raw_ids = ctx.input_payload.get("server_ids") or []
    if not isinstance(raw_ids, list) or not raw_ids:
        # Resolve by tags/group name optional
        tag = str(ctx.input_payload.get("tag") or "").strip()
        qs = _accessible_servers_queryset(ctx.user)
        if tag:
            qs = qs.filter(tags__icontains=tag)
        servers = list(qs.order_by("name")[:30])
    else:
        ids = []
        for item in raw_ids:
            try:
                ids.append(int(item))
            except (TypeError, ValueError):
                continue
        servers = list(_accessible_servers_queryset(ctx.user).filter(id__in=ids).order_by("name")[:40])

    if not servers:
        raise AssistantActionError("No accessible servers matched")

    concurrency = max(1, min(int(ctx.input_payload.get("concurrency") or 4), 8))
    matrix: list[dict[str, Any]] = []

    def _one(server):
        return _execute_on_server(ctx, server, command, allow_destructive=allow_destructive)

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(_one, s): s for s in servers}
        for fut in as_completed(futures):
            try:
                matrix.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                s = futures[fut]
                matrix.append({"ok": False, "server_id": s.id, "server_name": s.name, "error": str(exc)[:300]})

    matrix.sort(key=lambda row: (not row.get("ok"), str(row.get("server_name") or "")))
    ok_count = sum(1 for row in matrix if row.get("ok"))
    return {
        "ok": ok_count == len(matrix),
        "command": command,
        "matrix": matrix,
        "ok_count": ok_count,
        "fail_count": len(matrix) - ok_count,
        "blast_radius": {
            "server_ids": [s.id for s in servers],
            "server_names": [s.name for s in servers],
            "count": len(servers),
        },
        "dry_run_preview": {"command": command, "hosts": len(servers)},
        "target_url": "/servers",
    }


def _guess_undo(command: str) -> str | None:
    cmd = command.strip()
    # Very small heuristic set — honesty over false undo
    if cmd.startswith("systemctl start "):
        unit = cmd.split(None, 2)[-1]
        return f"systemctl stop {unit}"
    if cmd.startswith("systemctl stop "):
        unit = cmd.split(None, 2)[-1]
        return f"systemctl start {unit}"
    if cmd.startswith("systemctl enable "):
        unit = cmd.split(None, 2)[-1]
        return f"systemctl disable {unit}"
    if cmd.startswith("systemctl disable "):
        unit = cmd.split(None, 2)[-1]
        return f"systemctl enable {unit}"
    return None


def _steps_to_runbook_tasks(steps: Any) -> list[dict[str, Any]]:
    """Convert a list of command steps into runbook tasks.

    Accepts either bare command strings or dicts using any of the keys models
    commonly emit (``command``/``cmd``). Steps without a command are skipped.
    """
    if not isinstance(steps, list):
        return []
    tasks: list[dict[str, Any]] = []
    for idx, step in enumerate(steps):
        if isinstance(step, str):
            command = step.strip()
            if not command:
                continue
            tasks.append(
                {"id": f"step_{idx + 1}", "command": command, "description": "", "continue_on_error": False}
            )
        elif isinstance(step, dict):
            command = str(step.get("command") or step.get("cmd") or "").strip()
            if not command:
                continue
            tasks.append(
                {
                    "id": str(step.get("id") or f"step_{idx + 1}"),
                    "command": command,
                    "description": str(step.get("description") or "")[:500],
                    "continue_on_error": bool(
                        step.get("continue_on_error")
                        if "continue_on_error" in step
                        else step.get("continueOnError")
                    ),
                }
            )
    return tasks


def create_playbook(ctx: AssistantActionContext) -> dict[str, Any]:
    from servers.models import Playbook

    name = str(ctx.input_payload.get("name") or ctx.input_payload.get("title") or "Operator playbook").strip()[:200]
    yaml_text = str(ctx.input_payload.get("yaml") or ctx.input_payload.get("source_yaml") or "").strip()
    raw_tasks = ctx.input_payload.get("tasks") if isinstance(ctx.input_payload.get("tasks"), list) else []
    # Models represent a runbook as a step/command list under various keys — accept them all.
    raw_steps = ctx.input_payload.get("steps") or ctx.input_payload.get("commands") or []
    runbook_tasks = _steps_to_runbook_tasks(raw_tasks or raw_steps)
    if not yaml_text and not runbook_tasks:
        raise AssistantActionError(
            "Provide yaml, or steps/tasks as a list of {command, description}."
        )
    kind = Playbook.KIND_ANSIBLE if yaml_text else Playbook.KIND_RUNBOOK
    pb = Playbook.objects.create(
        user=ctx.user,
        name=name,
        description=str(ctx.input_payload.get("description") or "Created from Operator chat")[:2000],
        kind=kind,
        source_yaml=yaml_text,
        tasks=raw_tasks if yaml_text else runbook_tasks,
        category=str(ctx.input_payload.get("category") or Playbook.CATEGORY_CUSTOM)[:30],
    )
    return {
        "ok": True,
        "playbook": {"id": pb.id, "name": pb.name, "kind": pb.kind, "task_count": len(pb.tasks or [])},
        "target_url": f"/playbooks/{pb.id}",
    }


def run_playbook(ctx: AssistantActionContext) -> dict[str, Any]:
    from servers.models import Playbook, PlaybookRun
    from servers.services.playbook_runner import (
        build_inventory_for_servers,
        normalize_tasks,
        resolve_target_servers,
        start_playbook_run_async,
    )

    playbook_id = _int_arg(ctx, "playbook_id")
    assert playbook_id is not None
    pb = Playbook.objects.filter(pk=playbook_id, user=ctx.user).first()
    if pb is None:
        # shared
        pb = Playbook.objects.filter(pk=playbook_id, visibility=Playbook.VISIBILITY_SHARED).first()
    if pb is None:
        raise AssistantActionError("Playbook not found", status=404)

    raw_ids = ctx.input_payload.get("server_ids") or []
    server_ids = []
    for item in raw_ids if isinstance(raw_ids, list) else []:
        try:
            server_ids.append(int(item))
        except (TypeError, ValueError):
            continue
    servers = resolve_target_servers(ctx.user, server_ids=server_ids, group_ids=[])
    if not servers:
        raise AssistantActionError("Select at least one accessible server_ids")

    dry_run = bool(ctx.input_payload.get("check_mode") or ctx.input_payload.get("dry_run"))
    tasks = normalize_tasks(pb.tasks)
    snapshot = {
        "id": pb.id,
        "name": pb.name,
        "description": pb.description,
        "kind": pb.kind,
        "category": pb.category,
        "source_yaml": pb.source_yaml or "",
        "tasks": tasks,
    }
    options = {
        "concurrency": max(1, min(int(ctx.input_payload.get("concurrency") or 4), 12)),
        "dry_run": dry_run,
        "engine": str(ctx.input_payload.get("engine") or "auto"),
        "become": bool(ctx.input_payload.get("become", True)),
    }
    run = PlaybookRun.objects.create(
        playbook=pb,
        user=ctx.user,
        status=PlaybookRun.STATUS_PENDING,
        playbook_snapshot=snapshot,
        target_server_ids=[s.id for s in servers],
        options=options,
        host_results=[],
        summary={},
        inventory_preview=build_inventory_for_servers(servers),
    )
    master = ""
    if ctx.request is not None:
        try:
            from servers.views.server_helpers import _effective_master_password

            master = _effective_master_password(ctx.request, ctx.input_payload) or ""
        except Exception:  # noqa: BLE001
            master = ""
    start_playbook_run_async(run.id, master_password=master)
    return {
        "ok": True,
        "async": True,
        "async_kind": "playbook_run",
        "run_id": run.id,
        "status": run.status,
        "dry_run": dry_run,
        "blast_radius": {
            "server_ids": [s.id for s in servers],
            "server_names": [s.name for s in servers],
            "count": len(servers),
        },
        "target_url": f"/playbooks/runs/{run.id}",
    }


def save_runbook(ctx: AssistantActionContext) -> dict[str, Any]:
    from servers.models import Playbook

    title = str(ctx.input_payload.get("title") or ctx.input_payload.get("name") or "Saved runbook").strip()[:200]
    steps = ctx.input_payload.get("steps") or ctx.input_payload.get("tasks") or ctx.input_payload.get("commands") or []
    tasks = _steps_to_runbook_tasks(steps)
    if not tasks:
        raise AssistantActionError("steps is required (list of {command, description})")
    pb = Playbook.objects.create(
        user=ctx.user,
        name=title,
        description=str(ctx.input_payload.get("description") or "Saved from Operator chat")[:2000],
        kind=Playbook.KIND_RUNBOOK,
        tasks=tasks,
        category=Playbook.CATEGORY_MAINTENANCE,
        tags=["operator", "runbook"],
    )
    return {
        "ok": True,
        "playbook": {"id": pb.id, "name": pb.name, "kind": pb.kind, "task_count": len(tasks)},
        "target_url": f"/playbooks/{pb.id}",
    }


def resolve_alert(ctx: AssistantActionContext) -> dict[str, Any]:
    from servers.models import ServerAlert

    alert_id = _int_arg(ctx, "alert_id")
    assert alert_id is not None
    accessible = _accessible_servers_queryset(ctx.user).values_list("id", flat=True)
    alert = ServerAlert.objects.filter(pk=alert_id, server_id__in=accessible).first()
    if alert is None:
        raise AssistantActionError("Alert not found", status=404)
    alert.is_resolved = True
    alert.resolved_at = timezone.now()
    alert.resolved_by = ctx.user
    alert.save(update_fields=["is_resolved", "resolved_at", "resolved_by"])
    return {
        "ok": True,
        "alert_id": alert.id,
        "title": alert.title,
        "target_url": "/monitoring",
    }


def _hhmm_or_none(value: Any) -> str | None:
    """Return a normalized HH:MM string, or None when the input isn't a valid time."""
    text = str(value or "").strip()
    if not text or ":" not in text:
        return None
    try:
        hour, minute = (int(part) for part in text.split(":", 1))
    except (TypeError, ValueError):
        return None
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return f"{hour:02d}:{minute:02d}"
    return None


def _cron_to_schedule_config(cron: str) -> dict[str, Any]:
    """Map a simple 5-field cron (m h dom mon dow) to normalize_schedule_config keys.

    Handles the common daily/weekly forms; returns {} when it can't parse cleanly.
    """
    parts = cron.split()
    if len(parts) != 5:
        return {}
    minute, hour, dom, _mon, dow = parts
    if not (minute.isdigit() and hour.isdigit()):
        return {}
    time_str = f"{int(hour):02d}:{int(minute):02d}"
    if dow not in ("*", "?"):
        weekdays: list[int] = []
        for token in dow.split(","):
            # cron dow: 0/7 = Sunday; normalize uses Mon=0..Sun=6.
            if token.isdigit():
                cron_dow = int(token) % 7
                weekdays.append((cron_dow + 6) % 7)
        if weekdays:
            return {"mode": "weekly", "time": time_str, "weekdays": sorted(set(weekdays))}
    if dom.isdigit():
        return {"mode": "monthly", "time": time_str, "day_of_month": int(dom)}
    return {"mode": "daily", "time": time_str}


def schedule_agent(ctx: AssistantActionContext) -> dict[str, Any]:
    """Attach a schedule to an existing agent (phrase → cron-ish config)."""
    from servers.agent_schedule import normalize_schedule_config, schedule_minutes_for_config
    from servers.models import ServerAgent

    agent_id = _int_arg(ctx, "agent_id")
    assert agent_id is not None
    agent = ServerAgent.objects.filter(pk=agent_id, user=ctx.user).first()
    if agent is None:
        raise AssistantActionError("Agent not found", status=404)

    schedule_minutes = 0
    try:
        schedule_minutes = int(ctx.input_payload.get("schedule_minutes") or 0)
    except (TypeError, ValueError):
        schedule_minutes = 0

    raw_config = ctx.input_payload.get("schedule_config")
    raw_config = dict(raw_config) if isinstance(raw_config, dict) else {}

    # Friendly inputs → the canonical keys normalize_schedule_config actually reads
    # (mode / time / interval_minutes / weekdays). The previous mapping used type/
    # minutes/hour, which normalize ignored — every schedule silently became "manual".
    cron = str(ctx.input_payload.get("cron") or "").strip()
    daily_hour = ctx.input_payload.get("daily_hour")
    daily_time = _hhmm_or_none(ctx.input_payload.get("daily_time"))
    weekdays_in = ctx.input_payload.get("weekdays")

    if daily_time is None and daily_hour is not None:
        try:
            daily_time = f"{max(0, min(23, int(daily_hour))):02d}:00"
        except (TypeError, ValueError):
            daily_time = None

    if isinstance(weekdays_in, list) and weekdays_in:
        raw_config["mode"] = "weekly"
        raw_config["weekdays"] = weekdays_in
        if daily_time:
            raw_config["time"] = daily_time
    elif daily_time:
        raw_config.setdefault("mode", "daily")
        raw_config["time"] = daily_time
    elif cron:
        raw_config.update(_cron_to_schedule_config(cron))
    elif schedule_minutes > 0 and not raw_config.get("mode"):
        raw_config["mode"] = "interval"
        raw_config["interval_minutes"] = schedule_minutes

    config = normalize_schedule_config(raw_config, fallback_minutes=schedule_minutes)
    minutes = schedule_minutes_for_config(config, schedule_minutes)
    agent.schedule_config = config
    agent.schedule_minutes = minutes
    agent.is_enabled = True
    agent.save(update_fields=["schedule_config", "schedule_minutes", "is_enabled", "updated_at"])

    deliver_to_chat = bool(ctx.input_payload.get("deliver_to_chat"))
    if deliver_to_chat:
        delivery = agent.report_delivery if isinstance(agent.report_delivery, dict) else {}
        delivery = {
            **delivery,
            "chat": {"enabled": True, "note": "Deliver report summary to operator chat when available"},
        }
        agent.report_delivery = delivery
        agent.save(update_fields=["report_delivery", "updated_at"])

    return {
        "ok": True,
        "agent": {"id": agent.id, "name": agent.name},
        "schedule_config": config,
        "schedule_minutes": minutes,
        "deliver_to_chat": deliver_to_chat,
        "target_url": "/agents",
    }


def undo_last_action(ctx: AssistantActionContext) -> dict[str, Any]:
    """Execute reverse command from a prior action's undo_payload."""
    from core_ui.models import AssistantAction

    action_id = _int_arg(ctx, "action_id", required=False)
    if action_id:
        action = AssistantAction.objects.filter(pk=action_id, user=ctx.user).first()
    else:
        action = (
            AssistantAction.objects.filter(user=ctx.user, status=AssistantAction.STATUS_COMPLETED)
            .exclude(undo_payload={})
            .order_by("-completed_at", "-id")
            .first()
        )
    if action is None or not action.undo_payload:
        raise AssistantActionError("No undoable action found")
    undo = action.undo_payload if isinstance(action.undo_payload, dict) else {}
    server_id = undo.get("server_id")
    command = str(undo.get("command") or "").strip()
    if not server_id or not command:
        raise AssistantActionError("Undo payload incomplete")
    # Reuse run_command path
    nested = AssistantActionContext(
        user=ctx.user,
        input_payload={"server_id": server_id, "command": command, "allow_destructive": True},
        request=ctx.request,
        source=ctx.source,
    )
    result = run_command(nested)
    result["undid_action_id"] = action.pk
    return result


def register_operator_mutate_tools() -> None:
    specs = [
        AssistantActionSpec(
            action_type="operator.run_command",
            label="Run command",
            description="Execute a shell command on one accessible SSH server (confirm required).",
            required_feature="servers",
            risk="mutating",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "server_id": {"type": "integer"},
                    "command": {"type": "string"},
                    "allow_destructive": {"type": "boolean"},
                },
                "required": ["server_id", "command"],
            },
            handler=run_command,
        ),
        AssistantActionSpec(
            action_type="operator.run_fanout",
            label="Fan-out command",
            description="Run the same command on many servers; returns a result matrix.",
            required_feature="servers",
            risk="mutating",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "server_ids": {"type": "array", "items": {"type": "integer"}},
                    "tag": {"type": "string"},
                    "command": {"type": "string"},
                    "concurrency": {"type": "integer"},
                    "allow_destructive": {"type": "boolean"},
                },
                "required": ["command"],
            },
            handler=run_fanout,
        ),
        AssistantActionSpec(
            action_type="operator.create_playbook",
            label="Create playbook",
            description=(
                "Create a playbook. For ansible pass yaml. For a command runbook pass "
                "steps as a list of {command, description}."
            ),
            required_feature="servers",
            risk="internal_write",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "yaml": {"type": "string"},
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "command": {"type": "string"},
                                "description": {"type": "string"},
                            },
                            "required": ["command"],
                        },
                    },
                    "tasks": {"type": "array"},
                    "description": {"type": "string"},
                },
            },
            handler=create_playbook,
        ),
        AssistantActionSpec(
            action_type="operator.run_playbook",
            label="Run playbook",
            description="Start a playbook run (async). Use check_mode for dry-run.",
            required_feature="servers",
            risk="mutating",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "playbook_id": {"type": "integer"},
                    "server_ids": {"type": "array", "items": {"type": "integer"}},
                    "check_mode": {"type": "boolean"},
                    "concurrency": {"type": "integer"},
                },
                "required": ["playbook_id", "server_ids"],
            },
            handler=run_playbook,
        ),
        AssistantActionSpec(
            action_type="operator.save_runbook",
            label="Save runbook",
            description="Save a successful command chain as a reusable runbook playbook.",
            required_feature="servers",
            risk="internal_write",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "steps": {"type": "array"},
                    "description": {"type": "string"},
                },
                "required": ["title", "steps"],
            },
            handler=save_runbook,
        ),
        AssistantActionSpec(
            action_type="operator.resolve_alert",
            label="Resolve alert",
            description="Mark a monitoring alert as resolved.",
            required_feature="servers",
            risk="internal_write",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {"alert_id": {"type": "integer"}},
                "required": ["alert_id"],
            },
            handler=resolve_alert,
        ),
        AssistantActionSpec(
            action_type="operator.undo_last",
            label="Undo last action",
            description="Reverse the last undoable operator action when undo_payload is available.",
            required_feature="servers",
            risk="mutating",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {"action_id": {"type": "integer"}},
            },
            handler=undo_last_action,
        ),
        AssistantActionSpec(
            action_type="operator.schedule_agent",
            label="Schedule agent",
            description=(
                "Schedule an existing agent to run recurrently. Use daily_time 'HH:MM' "
                "for a daily run, weekdays [0-6] (Mon=0) for weekly, schedule_minutes for "
                "an interval, or cron. Optional deliver_to_chat posts the report here."
            ),
            required_feature="agents",
            risk="internal_write",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "agent_id": {"type": "integer"},
                    "schedule_minutes": {"type": "integer"},
                    "daily_hour": {"type": "integer"},
                    "daily_time": {"type": "string", "description": "HH:MM local time"},
                    "weekdays": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "0=Mon … 6=Sun for weekly schedules",
                    },
                    "cron": {"type": "string"},
                    "deliver_to_chat": {"type": "boolean"},
                },
                "required": ["agent_id"],
            },
            handler=schedule_agent,
        ),
    ]
    for spec in specs:
        try:
            register_action(spec)
        except ValueError:
            pass
