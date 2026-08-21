from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction
from django.utils import timezone

from app.agent_kernel.memory.compaction import compact_text
from app.agent_kernel.memory.snapshot_utils import content_delta
from app.agent_kernel.memory.trust import (
    TRUST_LLM_DISTILLED,
    VERIFICATION_NEEDS_REVALIDATION,
    enrich_metadata_with_trust,
    metadata_can_promote_to_canonical,
)
from app.agent_kernel.memory.types import AUTOMATION_CANDIDATE_PREFIX, PATTERN_CANDIDATE_PREFIX, SKILL_DRAFT_PREFIX
from servers.adapters.django_memory_serializers import describe_snapshot_rewrite


def upsert_snapshot(
    *,
    server_id: int,
    memory_key: str,
    title: str,
    content: str,
    source_kind: str,
    source_ref: str = "",
    importance_score: float = 0.5,
    stability_score: float = 0.5,
    confidence: float = 0.7,
    verified_at=None,
    metadata: dict[str, Any] | None = None,
    created_by_id: int | None = None,
    version_group_id: str | None = None,
    force_version: bool = False,
    layer: str | None = None,
    enforce_trust_gate: bool = True,
    generation_log=None,
):
    from servers.models import ServerMemorySnapshot

    clean_content = compact_text(content, limit=3200)
    metadata = dict(metadata or {})
    if memory_key.startswith((PATTERN_CANDIDATE_PREFIX, AUTOMATION_CANDIDATE_PREFIX, SKILL_DRAFT_PREFIX)):
        layer = layer or ServerMemorySnapshot.LAYER_CANDIDATE
        metadata.setdefault("candidate_requires_review", True)
        metadata.setdefault("trust_level", TRUST_LLM_DISTILLED)
        metadata.setdefault("verification_status", VERIFICATION_NEEDS_REVALIDATION)
    else:
        layer = layer or ServerMemorySnapshot.LAYER_CANONICAL
    metadata = enrich_metadata_with_trust(
        metadata,
        source_kind=source_kind,
        actor_kind=str(metadata.get("source_actor_kind") or ""),
        source_ref=source_ref,
        fallback_trust_level=str(metadata.get("trust_level") or ""),
        fallback_verification_status=str(metadata.get("verification_status") or ""),
    )

    with transaction.atomic():
        existing = (
            ServerMemorySnapshot.objects.select_for_update()
            .filter(server_id=server_id, memory_key=memory_key, is_active=True)
            .order_by("-version", "-updated_at")
            .first()
        )
        if (
            enforce_trust_gate
            and layer == ServerMemorySnapshot.LAYER_CANONICAL
            and not metadata_can_promote_to_canonical(metadata)
        ):
            ensure_revalidation(
                server_id,
                memory_key=memory_key,
                title=title,
                reason=(
                    "Snapshot candidate was not promoted to canonical memory because its "
                    "source trust requires verification."
                ),
                payload={
                    "memory_key": memory_key,
                    "source_kind": source_kind,
                    "source_ref": source_ref,
                    "trust_level": metadata.get("trust_level"),
                    "verification_status": metadata.get("verification_status"),
                    "candidate_content": clean_content,
                },
                source_snapshot=existing,
            )
            return existing, False
        if existing:
            delta = content_delta(existing.content, clean_content)
            confidence_shift = float(confidence or 0.0) - float(existing.confidence or 0.0)
            significant = force_version or delta >= 0.2 or abs(confidence_shift) >= 0.15
            if not significant:
                dirty_fields: list[str] = []
                if clean_content and clean_content != existing.content:
                    existing.content = clean_content
                    dirty_fields.append("content")
                if generation_log is not None and generation_log.pk != existing.generation_log_id:
                    existing.generation_log = generation_log
                    dirty_fields.append("generation_log")
                if abs(float(existing.confidence or 0.0) - float(confidence or 0.0)) >= 0.03:
                    existing.confidence = confidence
                    dirty_fields.append("confidence")
                if abs(float(existing.importance_score or 0.0) - float(importance_score or 0.0)) >= 0.03:
                    existing.importance_score = importance_score
                    dirty_fields.append("importance_score")
                if abs(float(existing.stability_score or 0.0) - float(stability_score or 0.0)) >= 0.03:
                    existing.stability_score = stability_score
                    dirty_fields.append("stability_score")
                if verified_at and verified_at != existing.last_verified_at:
                    existing.last_verified_at = verified_at
                    dirty_fields.append("last_verified_at")
                if metadata and metadata != (existing.metadata or {}):
                    existing.metadata = metadata
                    dirty_fields.append("metadata")
                if title and title != existing.title:
                    existing.title = title[:200]
                    dirty_fields.append("title")
                if source_kind and source_kind != existing.source_kind:
                    existing.source_kind = source_kind
                    dirty_fields.append("source_kind")
                if source_ref and source_ref != existing.source_ref:
                    existing.source_ref = source_ref[:255]
                    dirty_fields.append("source_ref")
                if layer and layer != existing.layer:
                    existing.layer = layer
                    dirty_fields.append("layer")
                if dirty_fields:
                    dirty_fields.append("updated_at")
                    existing.save(update_fields=dirty_fields)
                return existing, False

        version_group = version_group_id or getattr(existing, "version_group_id", "") or uuid.uuid4().hex
        version = (int(existing.version) + 1) if existing else 1
        next_metadata = dict(metadata)
        rewrite_reason = ""
        if existing:
            rewrite_reason = describe_snapshot_rewrite(
                memory_key=memory_key,
                delta=delta,
                confidence_shift=confidence_shift,
                force_version=force_version,
            )
            next_metadata.update(
                {
                    "rewrite_reason": rewrite_reason,
                    "rewrite_delta": round(delta, 3),
                    "prior_snapshot_id": existing.id,
                    "prior_version": int(existing.version or 0),
                }
            )
            if abs(confidence_shift) >= 0.01:
                next_metadata["confidence_shift"] = round(confidence_shift, 3)
            existing_metadata = dict(existing.metadata or {})
            if rewrite_reason:
                existing_metadata["superseded_reason"] = rewrite_reason
            existing.is_active = False
            existing.layer = ServerMemorySnapshot.LAYER_ARCHIVE
            existing.archived_at = timezone.now()
            existing.metadata = existing_metadata
            existing.save(update_fields=["is_active", "layer", "archived_at", "metadata", "updated_at"])
        snapshot = ServerMemorySnapshot.objects.create(
            server_id=server_id,
            created_by_id=created_by_id,
            memory_key=memory_key,
            layer=layer,
            title=title[:200],
            content=clean_content,
            source_kind=source_kind[:30],
            source_ref=source_ref[:255],
            version_group_id=version_group,
            version=version,
            is_active=True,
            importance_score=importance_score,
            stability_score=stability_score,
            confidence=confidence,
            last_verified_at=verified_at,
            metadata=next_metadata,
            generation_log=generation_log,
        )
        if existing:
            existing.superseded_by = snapshot
            existing.save(update_fields=["superseded_by", "updated_at"])
    return snapshot, True


def ensure_revalidation(
    server_id: int,
    *,
    memory_key: str,
    title: str,
    reason: str,
    payload: dict[str, Any] | None = None,
    source_snapshot=None,
):
    from servers.models import ServerMemoryRevalidation

    return ServerMemoryRevalidation.objects.get_or_create(
        server_id=server_id,
        memory_key=memory_key,
        title=title[:200],
        status=ServerMemoryRevalidation.STATUS_OPEN,
        defaults={
            "source_snapshot": source_snapshot,
            "reason": compact_text(reason, limit=1200),
            "payload": payload or {},
            "confidence": 0.45,
        },
    )


def archive_missing_candidate_snapshots(server_id: int, *, active_keys: set[str]) -> int:
    from servers.models import ServerMemorySnapshot

    now = timezone.now()
    filters = ServerMemorySnapshot.objects.filter(server_id=server_id, is_active=True)
    archived = 0
    for snapshot in filters:
        memory_key = str(snapshot.memory_key or "")
        if not memory_key.startswith((PATTERN_CANDIDATE_PREFIX, AUTOMATION_CANDIDATE_PREFIX, SKILL_DRAFT_PREFIX)):
            continue
        if memory_key in active_keys:
            continue
        snapshot.is_active = False
        snapshot.layer = ServerMemorySnapshot.LAYER_ARCHIVE
        snapshot.archived_at = now
        snapshot.save(update_fields=["is_active", "layer", "archived_at", "updated_at"])
        archived += 1
    return archived
