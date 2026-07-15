"""Serialization + input-normalization helpers for playbook views.

Extracted from server_playbooks.py to keep modules under the size limit.
"""
from __future__ import annotations

from typing import Any

from django.db.models import Q

from servers.models import Playbook, PlaybookRun
from servers.services.playbook_runner import normalize_tasks


def _playbooks_for_user(user):
    return Playbook.objects.filter(Q(user=user) | Q(visibility=Playbook.VISIBILITY_SHARED))


def _serialize_playbook(pb: Playbook, *, include_tasks: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": pb.id,
        "name": pb.name,
        "description": pb.description,
        "kind": pb.kind,
        "category": pb.category,
        "visibility": pb.visibility,
        "tags": pb.tags if isinstance(pb.tags, list) else [],
        "fidelity": pb.fidelity if isinstance(pb.fidelity, dict) else {},
        "task_count": pb.task_count,
        "is_template_clone": pb.is_template_clone,
        "template_slug": pb.template_slug,
        "last_run_at": pb.last_run_at.isoformat() if pb.last_run_at else None,
        "last_run_status": pb.last_run_status or "",
        "created_at": pb.created_at.isoformat() if pb.created_at else None,
        "updated_at": pb.updated_at.isoformat() if pb.updated_at else None,
        "owner_id": pb.user_id,
    }
    if include_tasks:
        data["tasks"] = pb.tasks if isinstance(pb.tasks, list) else []
        data["source_yaml"] = pb.source_yaml or ""
    return data


def _serialize_run(run: PlaybookRun, *, include_hosts: bool = True) -> dict[str, Any]:
    snapshot = run.playbook_snapshot if isinstance(run.playbook_snapshot, dict) else {}
    data: dict[str, Any] = {
        "id": run.id,
        "playbook_id": run.playbook_id,
        "status": run.status,
        "playbook_name": snapshot.get("name") or (run.playbook.name if run.playbook_id else "Playbook"),
        "target_server_ids": run.target_server_ids or [],
        "target_group_ids": run.target_group_ids or [],
        "options": run.options if isinstance(run.options, dict) else {},
        "summary": run.summary if isinstance(run.summary, dict) else {},
        "progress": run.progress if isinstance(run.progress, dict) else {},
        "inventory_preview": run.inventory_preview or "",
        "error_message": run.error_message or "",
        "cancel_requested": bool(run.cancel_requested),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }
    if include_hosts:
        data["host_results"] = run.host_results if isinstance(run.host_results, list) else []
        data["playbook_snapshot"] = snapshot
        data["live_log"] = (run.live_log or "")[-120_000:]
    return data


def _normalize_incoming_tasks(raw: Any) -> list[dict[str, Any]]:
    tasks = normalize_tasks(raw)
    # re-map keys for storage with snake_case
    return [
        {
            "id": t["id"],
            "command": t["command"],
            "description": t.get("description") or "",
            "continue_on_error": bool(t.get("continue_on_error")),
        }
        for t in tasks
        if not t.get("skipped_module") or t.get("command")
    ]
