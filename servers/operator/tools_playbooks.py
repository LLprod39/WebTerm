"""Read-only Operator tools for resolving accessible playbooks."""

from __future__ import annotations

from typing import Any

from django.db.models import Q

from app.assistant_actions import AssistantActionContext, AssistantActionError
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
