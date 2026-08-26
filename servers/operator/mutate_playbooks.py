"""Operator mutate tools: playbooks, runbooks, alert resolution (F-08a split)."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from app.assistant_actions import AssistantActionContext, AssistantActionError
from servers.operator.tools_common import _int_arg
from servers.services.playbook_run_preparation import (
    PlaybookRunPreparationError,
    prepare_playbook_run,
)
from servers.services.playbook_runner import start_playbook_run_async
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
    from servers.models import Playbook, PlaybookRevision
    from servers.services.playbooks.revisions import initialize_created_playbook
    from servers.services.playbooks.source_guard import PlaybookSourceSafetyError, validate_ansible_source

    name = str(ctx.input_payload.get("name") or ctx.input_payload.get("title") or "Operator playbook").strip()[:200]
    yaml_text = str(ctx.input_payload.get("yaml") or ctx.input_payload.get("source_yaml") or "")
    raw_tasks = ctx.input_payload.get("tasks") if isinstance(ctx.input_payload.get("tasks"), list) else []
    # Models represent a runbook as a step/command list under various keys — accept them all.
    raw_steps = ctx.input_payload.get("steps") or ctx.input_payload.get("commands") or []
    runbook_tasks = _steps_to_runbook_tasks(raw_tasks or raw_steps)
    has_yaml = bool(yaml_text.strip())
    if not has_yaml and not runbook_tasks:
        raise AssistantActionError("Provide yaml, or steps/tasks as a list of {command, description}.")
    if has_yaml:
        try:
            yaml_text = validate_ansible_source(yaml_text).source_yaml
        except PlaybookSourceSafetyError as exc:
            raise AssistantActionError(
                "Playbook YAML failed safety validation",
                status=exc.status_code,
                details={"code": exc.code},
            ) from exc
    else:
        yaml_text = ""
    kind = Playbook.KIND_ANSIBLE if has_yaml else Playbook.KIND_RUNBOOK
    pb = Playbook.objects.create(
        user=ctx.user,
        name=name,
        description=str(ctx.input_payload.get("description") or "Created from Operator chat")[:2000],
        kind=kind,
        source_yaml=yaml_text,
        tasks=raw_tasks if yaml_text else runbook_tasks,
        category=str(ctx.input_payload.get("category") or Playbook.CATEGORY_CUSTOM)[:30],
    )
    initialize_created_playbook(pb, actor=ctx.user, origin_type=PlaybookRevision.ORIGIN_MANUAL)
    return {
        "ok": True,
        "playbook": {"id": pb.id, "name": pb.name, "kind": pb.kind, "task_count": len(pb.tasks or [])},
        "target_url": f"/automation/playbooks/{pb.id}",
    }


def run_playbook(ctx: AssistantActionContext) -> dict[str, Any]:
    from servers.services.playbooks.access import playbooks_visible_to

    playbook_id = _int_arg(ctx, "playbook_id")
    assert playbook_id is not None
    pb = playbooks_visible_to(ctx.user).filter(pk=playbook_id).first()
    if pb is None:
        raise AssistantActionError("Playbook not found", status=404)

    master = ""
    if ctx.request is not None:
        try:
            from servers.views.server_helpers import _effective_master_password

            master = _effective_master_password(ctx.request, ctx.input_payload) or ""
        except Exception:  # noqa: BLE001
            master = ""

    try:
        prepared = prepare_playbook_run(
            user=ctx.user,
            playbook=pb,
            payload=ctx.input_payload,
            enqueue_master_password=master,
        )
    except PlaybookRunPreparationError as exc:
        details = {"compatibility": exc.compatibility} if exc.compatibility else None
        raise AssistantActionError(exc.message, status=exc.status, details=details) from exc

    run = prepared.run
    servers = prepared.servers
    dry_run = bool((run.options or {}).get("dry_run"))
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
        "target_url": f"/automation/runs/{run.id}",
    }


def save_runbook(ctx: AssistantActionContext) -> dict[str, Any]:
    from servers.models import Playbook, PlaybookRevision
    from servers.services.playbooks.revisions import initialize_created_playbook

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
    initialize_created_playbook(pb, actor=ctx.user, origin_type=PlaybookRevision.ORIGIN_MANUAL)
    return {
        "ok": True,
        "playbook": {"id": pb.id, "name": pb.name, "kind": pb.kind, "task_count": len(tasks)},
        "target_url": f"/automation/playbooks/{pb.id}",
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
