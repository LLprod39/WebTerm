from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from app.agent_kernel.memory.repair import (
    compute_freshness_score,
    decay_confidence,
    needs_revalidation,
)


def repair_server_memory(store, server_id: int, *, stale_after_days: int = 30, create_notes: bool = True) -> dict:
    from servers.models import ServerMemoryRevalidation, ServerMemorySnapshot

    now = timezone.now()
    updated = 0
    notes = 0
    for snapshot in ServerMemorySnapshot.objects.filter(server_id=server_id, is_active=True).order_by(
        "memory_key", "-updated_at"
    ):
        should_revalidate = create_notes and needs_revalidation(
            snapshot.updated_at,
            snapshot.last_verified_at,
            max_age_days=stale_after_days,
        )
        freshness = compute_freshness_score(snapshot.updated_at, snapshot.last_verified_at)
        target_confidence = decay_confidence(snapshot.confidence or 0.8, freshness)
        dirty_fields: list[str] = []
        if abs(target_confidence - float(snapshot.confidence or 0.0)) >= 0.05:
            snapshot.confidence = target_confidence
            dirty_fields.append("confidence")
        snapshot.stability_score = min(1.0, max(0.05, float(snapshot.stability_score or 0.5) * freshness))
        dirty_fields.append("stability_score")
        if dirty_fields:
            dirty_fields.append("updated_at")
            snapshot.save(update_fields=dirty_fields)
            updated += 1
        if should_revalidate:
            _item, created = ServerMemoryRevalidation.objects.get_or_create(
                server_id=server_id,
                memory_key=snapshot.memory_key,
                title=f"Перепроверить {snapshot.title}"[:200],
                status=ServerMemoryRevalidation.STATUS_OPEN,
                defaults={
                    "source_snapshot": snapshot,
                    "reason": "Снимок памяти устарел и должен быть перепроверен по свежим данным.",
                    "payload": {"snapshot_id": snapshot.id},
                    "confidence": min(snapshot.confidence, 0.45),
                },
            )
            if created:
                notes += 1

    archived_records = store._archive_old_events_sync(server_id, now=now) + store._archive_old_episodes_sync(
        server_id, now=now
    )
    return {
        "server_id": server_id,
        "updated_records": updated,
        "created_notes": notes,
        "archived_records": archived_records,
    }


def auto_resolve_stale_revalidations(server_id: int, *, max_age_days: int = 60) -> int:
    """
    Close stale open revalidation records at the end of a dream cycle.

    Rules:
    - Records older than ``max_age_days`` expire as unverified.
    - Records whose source snapshot was superseded become superseded when a
      newer active snapshot exists for the same memory key.
    """
    from servers.models import ServerMemoryRevalidation, ServerMemorySnapshot

    now = timezone.now()
    cutoff = now - timedelta(days=max_age_days)
    resolved = 0

    open_items = list(
        ServerMemoryRevalidation.objects.filter(
            server_id=server_id,
            status=ServerMemoryRevalidation.STATUS_OPEN,
        ).select_related("source_snapshot")
    )

    for item in open_items:
        if item.created_at < cutoff:
            item.status = ServerMemoryRevalidation.STATUS_EXPIRED_UNVERIFIED
            item.resolved_at = now
            item.save(update_fields=["status", "resolved_at", "updated_at"])
            resolved += 1
            continue

        source = getattr(item, "source_snapshot", None)
        if source is not None and not source.is_active:
            newer_exists = ServerMemorySnapshot.objects.filter(
                server_id=server_id,
                memory_key=item.memory_key,
                is_active=True,
            ).exists()
            if newer_exists:
                item.status = ServerMemoryRevalidation.STATUS_SUPERSEDED
                item.resolved_at = now
                item.save(update_fields=["status", "resolved_at", "updated_at"])
                resolved += 1

    return resolved
