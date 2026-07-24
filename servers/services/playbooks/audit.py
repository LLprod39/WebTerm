"""Small append-only audit helper for playbook object changes."""

from __future__ import annotations

from typing import Any

from servers.models import PlaybookAuditEvent


def record_playbook_event(
    *,
    playbook,
    actor,
    event_type: str,
    entity_type: str = "playbook",
    entity_id: int | str | None = None,
    metadata: dict[str, Any] | None = None,
) -> PlaybookAuditEvent:
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    return PlaybookAuditEvent.objects.create(
        playbook=playbook,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        event_type=event_type[:80],
        entity_type=(entity_type or "playbook")[:40],
        entity_id=str(entity_id or "")[:80],
        metadata=safe_metadata,
    )
