"""Operator mutate tools: playbooks, runbooks, alert resolution (F-08a split)."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from app.assistant_actions import AssistantActionContext, AssistantActionError
from servers.operator_tools_common import _int_arg
from servers.views.server_helpers import _accessible_servers_queryset


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
            tasks.append({"id": f"step_{idx + 1}", "command": command, "description": "", "continue_on_error": False})
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
                        step.get("continue_on_error") if "continue_on_error" in step else step.get("continueOnError")
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
        raise AssistantActionError("Provide yaml, or steps/tasks as a list of {command, description}.")
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
