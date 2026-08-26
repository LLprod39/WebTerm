"""Read-only Operator tools for playbooks, their runs, reports, and logs."""

from __future__ import annotations

from typing import Any

from django.db.models import Q

from app.assistant_actions import AssistantActionContext, AssistantActionError
from servers.models import PlaybookRun
from servers.services.playbooks.access import playbooks_visible_to


def _playbook_summary(playbook) -> dict[str, Any]:
    published = playbook.published_revision
    tasks = (
        published.tasks
        if published and isinstance(published.tasks, list)
        else playbook.tasks
        if isinstance(playbook.tasks, list)
        else []
    )
    source_yaml = published.source_yaml if published else playbook.source_yaml or ""
    outline: list[dict[str, str]] = []
    for task in tasks[:80]:
        if not isinstance(task, dict):
            continue
        outline.append(
            {
                "description": str(task.get("description") or task.get("name") or "")[:300],
                "command": str(task.get("command") or task.get("action") or "")[:500],
            }
        )
    return {
        "id": int(playbook.id),
        "name": str(playbook.name),
        "description": str(playbook.description or "")[:4000],
        "kind": str(playbook.kind),
        "category": str(playbook.category),
        "tags": [str(tag) for tag in (playbook.tags or [])[:20]],
        "task_count": len(tasks),
        "task_outline": outline,
        # The normal egress redactor still runs before this reaches the model.
        # Keep the same viewer boundary as the existing playbook detail API.
        "source_yaml": str(source_yaml)[:40_000],
        "published_revision_id": playbook.published_revision_id,
        "target_url": f"/automation/playbooks/{playbook.id}",
    }


def _match_rows(queryset, query: str):
    exact = list(queryset.filter(name__iexact=query).order_by("name", "id")[:20])
    if exact:
        return exact, True
    partial = list(
        queryset.filter(Q(name__icontains=query) | Q(description__icontains=query)).order_by("name", "id")[:20]
    )
    return partial, False


def _catalog_row(playbook) -> dict[str, Any]:
    return {
        "id": int(playbook.id),
        "name": str(playbook.name),
        "description": str(playbook.description or "")[:500],
        "kind": str(playbook.kind),
        "category": str(playbook.category),
        "tags": [str(tag) for tag in (playbook.tags or [])[:20]],
        "task_count": int(playbook.task_count),
        "last_run_at": playbook.last_run_at.isoformat() if playbook.last_run_at else None,
        "last_run_status": str(playbook.last_run_status or ""),
        "target_url": f"/automation/playbooks/{playbook.id}",
    }


def list_playbooks(ctx: AssistantActionContext) -> dict[str, Any]:
    """List the authenticated user's accessible playbook catalog without YAML bodies."""
    payload = ctx.input_payload if isinstance(ctx.input_payload, dict) else {}
    query = str(payload.get("q") or payload.get("name") or "").strip()
    try:
        limit = min(50, max(1, int(payload.get("limit") or 20)))
    except (TypeError, ValueError) as exc:
        raise AssistantActionError("limit must be an integer") from exc

    queryset = playbooks_visible_to(ctx.user).order_by("name", "id")
    if query:
        queryset = queryset.filter(Q(name__icontains=query) | Q(description__icontains=query))
    rows = [_catalog_row(playbook) for playbook in queryset[:limit]]
    return {
        "count": len(rows),
        "query": query,
        "playbooks": rows,
        "reply_hint": "Summarize the accessible catalog or ask which playbook to inspect. Use operator.resolve_playbook for full details.",
    }


def _run_row(run: PlaybookRun, *, include_detail: bool, log_tail_chars: int = 0) -> dict[str, Any]:
    snapshot = run.playbook_snapshot if isinstance(run.playbook_snapshot, dict) else {}
    row: dict[str, Any] = {
        "id": int(run.id),
        "playbook_id": run.playbook_id,
        "playbook_name": str(snapshot.get("name") or (run.playbook.name if run.playbook_id else "Playbook")),
        "status": str(run.status),
        "target_server_ids": [int(value) for value in (run.target_server_ids or [])[:50]],
        "options": dict(run.options) if isinstance(run.options, dict) else {},
        "summary": dict(run.summary) if isinstance(run.summary, dict) else {},
        "progress": dict(run.progress) if isinstance(run.progress, dict) else {},
        "error_message": str(run.error_message or "")[:4000],
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "target_url": f"/automation/runs/{run.id}",
    }
    if include_detail:
        host_results = run.host_results if isinstance(run.host_results, list) else []
        row["host_results"] = host_results[-30:]
        row["live_log_tail"] = str(run.live_log or "")[-log_tail_chars:] if log_tail_chars else ""
        row["execution_fingerprint"] = (
            dict(run.execution_fingerprint) if isinstance(run.execution_fingerprint, dict) else {}
        )
    return row


def playbook_runs(ctx: AssistantActionContext) -> dict[str, Any]:
    """List playbook runs or return one bounded report with a redacted log tail."""
    payload = ctx.input_payload if isinstance(ctx.input_payload, dict) else {}
    queryset = PlaybookRun.objects.filter(user=ctx.user).select_related("playbook").order_by("-created_at", "-id")

    raw_run_id = payload.get("run_id") or payload.get("id")
    if raw_run_id not in (None, ""):
        try:
            run_id = int(raw_run_id)
        except (TypeError, ValueError) as exc:
            raise AssistantActionError("run_id must be an integer") from exc
        run = queryset.filter(pk=run_id).first()
        if run is None:
            raise AssistantActionError("Playbook run not found", status=404)
        try:
            tail_chars = min(20_000, max(0, int(payload.get("log_tail_chars") or 8_000)))
        except (TypeError, ValueError) as exc:
            raise AssistantActionError("log_tail_chars must be an integer") from exc
        return {
            "found": True,
            "run": _run_row(run, include_detail=True, log_tail_chars=tail_chars),
            "reply_hint": "Report status, key summary/error, affected hosts, and the important end of the log. Do not dump the full raw log.",
        }

    raw_playbook_id = payload.get("playbook_id")
    if raw_playbook_id not in (None, ""):
        try:
            playbook_id = int(raw_playbook_id)
        except (TypeError, ValueError) as exc:
            raise AssistantActionError("playbook_id must be an integer") from exc
        queryset = queryset.filter(playbook_id=playbook_id)

    query = str(payload.get("q") or payload.get("playbook_name") or "").strip()
    if query:
        queryset = queryset.filter(playbook__name__icontains=query)

    status = str(payload.get("status") or "").strip().lower()
    valid_statuses = {choice[0] for choice in PlaybookRun.STATUS_CHOICES}
    if status:
        if status not in valid_statuses:
            raise AssistantActionError(f"status must be one of: {', '.join(sorted(valid_statuses))}")
        queryset = queryset.filter(status=status)

    try:
        limit = min(50, max(1, int(payload.get("limit") or 20)))
    except (TypeError, ValueError) as exc:
        raise AssistantActionError("limit must be an integer") from exc
    rows = [_run_row(run, include_detail=False) for run in queryset[:limit]]
    return {
        "count": len(rows),
        "query": query,
        "status": status,
        "runs": rows,
        "reply_hint": "Summarize recent run statuses. For logs or a full report, call this tool again with run_id.",
    }


def resolve_playbook(ctx: AssistantActionContext) -> dict[str, Any]:
    """Resolve and read one playbook inside the authenticated user's object boundary."""
    payload = ctx.input_payload if isinstance(ctx.input_payload, dict) else {}
    queryset = playbooks_visible_to(ctx.user)
    raw_id = payload.get("playbook_id") or payload.get("id")
    query = str(payload.get("q") or payload.get("name") or payload.get("title") or "").strip()

    if raw_id not in (None, ""):
        try:
            playbook_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise AssistantActionError("playbook_id must be an integer") from exc
        if playbook_id <= 0:
            raise AssistantActionError("playbook_id must be positive")
        playbook = queryset.filter(pk=playbook_id).first()
        if playbook is None:
            # Deliberately do not reveal whether the object exists for another user/project.
            raise AssistantActionError("Playbook not found or not accessible", status=404)
        return {
            "found": True,
            "ambiguous": False,
            "query": str(playbook_id),
            "playbook": _playbook_summary(playbook),
            "reply_hint": "Summarize what this playbook does, important effects/risks, and prerequisites. Do not ask for its ID or YAML.",
        }

    if not query:
        matches = list(queryset.order_by("name", "id")[:20])
    else:
        matches, _exact = _match_rows(queryset, query)

    if len(matches) == 1:
        return {
            "found": True,
            "ambiguous": False,
            "query": query,
            "playbook": _playbook_summary(matches[0]),
            "reply_hint": "Summarize what this playbook does, important effects/risks, and prerequisites. Do not ask for its ID or YAML.",
        }

    safe_matches = [
        {
            "id": int(playbook.id),
            "name": str(playbook.name),
            "description": str(playbook.description or "")[:240],
            "kind": str(playbook.kind),
        }
        for playbook in matches
    ]
    return {
        "found": False,
        "ambiguous": len(safe_matches) > 1,
        "query": query,
        "count": len(safe_matches),
        "matches": safe_matches,
        "error": (
            "Multiple accessible playbooks match; ask the user to choose one of these names."
            if len(safe_matches) > 1
            else "No accessible playbook matches this name."
        ),
    }
