"""Persistence and review helpers for exhausted pipeline node attempts."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from studio.pipeline.pipeline_secrets import serialize_pipeline_node_state
from studio.retry_models import PipelineNodeDeadLetter


def record_node_dead_letter(
    *,
    run: Any,
    node: dict,
    state: dict,
    attempt_count: int,
    max_attempts: int,
) -> PipelineNodeDeadLetter:
    node_id = str(node.get("id") or "")
    item, _created = PipelineNodeDeadLetter.objects.update_or_create(
        run=run,
        node_id=node_id,
        defaults={
            "node_type": str(node.get("type") or ""),
            "status": PipelineNodeDeadLetter.STATUS_OPEN,
            "attempt_count": max(1, int(attempt_count)),
            "max_attempts": max(1, int(max_attempts)),
            "last_error": str(state.get("error") or "")[:4000],
            "node_state": serialize_pipeline_node_state(state),
            "resolved_at": None,
            "resolved_by": None,
            "resolution_note": "",
        },
    )
    return item


def dead_letter_to_dict(item: PipelineNodeDeadLetter) -> dict:
    return {
        "id": item.pk,
        "run_id": item.run_id,
        "pipeline_id": item.run.pipeline_id,
        "pipeline_name": item.run.pipeline.name,
        "node_id": item.node_id,
        "node_type": item.node_type,
        "status": item.status,
        "attempt_count": item.attempt_count,
        "max_attempts": item.max_attempts,
        "last_error": item.last_error,
        "node_state": item.node_state,
        "created_at": item.created_at.isoformat(),
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        "resolved_by": item.resolved_by.username if item.resolved_by else None,
        "resolution_note": item.resolution_note,
    }


@transaction.atomic
def resolve_node_dead_letter(item_id: int, *, actor, note: str = "") -> PipelineNodeDeadLetter:
    item = PipelineNodeDeadLetter.objects.select_for_update().get(pk=item_id)
    item.status = PipelineNodeDeadLetter.STATUS_RESOLVED
    item.resolved_at = timezone.now()
    item.resolved_by = actor
    item.resolution_note = str(note or "")[:4000]
    item.save(update_fields=["status", "resolved_at", "resolved_by", "resolution_note", "updated_at"])
    return item
