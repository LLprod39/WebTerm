from __future__ import annotations

from typing import Any

from app.agent_kernel.memory.compaction import compact_text


def serialize_snapshot(item, *, history_items: list[Any] | None = None) -> dict[str, Any]:
    metadata = item.metadata or {}
    return {
        "id": item.id,
        "memory_key": item.memory_key,
        "title": item.title,
        "content": item.content,
        "content_hash": getattr(item, "content_hash", "") or "",
        "generation_log_id": getattr(item, "generation_log_id", None),
        "source_kind": item.source_kind,
        "source_ref": item.source_ref,
        "layer": item.layer,
        "version": item.version,
        "is_active": item.is_active,
        "version_group_id": getattr(item, "version_group_id", "") or "",
        "superseded_by_id": getattr(item, "superseded_by_id", None),
        "importance_score": float(item.importance_score or 0.0),
        "stability_score": float(item.stability_score or 0.0),
        "confidence": float(item.confidence or 0.0),
        "last_verified_at": item.last_verified_at.isoformat() if item.last_verified_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "archived_at": item.archived_at.isoformat() if item.archived_at else None,
        "metadata": metadata,
        "rewrite_reason": snapshot_rewrite_reason(item),
        "prior_snapshot_id": metadata.get("prior_snapshot_id"),
        "prior_version": metadata.get("prior_version"),
        "action_summary": snapshot_action_summary(item),
        "created_by_username": getattr(getattr(item, "created_by", None), "username", None),
        "history": [serialize_snapshot_history_item(history_item) for history_item in (history_items or [])[:6]],
    }


def serialize_episode(item) -> dict[str, Any]:
    return {
        "id": item.id,
        "episode_kind": item.episode_kind,
        "title": item.title,
        "summary": item.summary,
        "event_count": item.event_count,
        "importance_score": float(item.importance_score or 0.0),
        "confidence": float(item.confidence or 0.0),
        "is_active": item.is_active,
        "first_event_at": item.first_event_at.isoformat() if item.first_event_at else None,
        "last_event_at": item.last_event_at.isoformat() if item.last_event_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "metadata": item.metadata or {},
    }


def serialize_revalidation(item) -> dict[str, Any]:
    return {
        "id": item.id,
        "memory_key": item.memory_key,
        "title": item.title,
        "reason": item.reason,
        "status": item.status,
        "confidence": float(item.confidence or 0.0),
        "payload": item.payload or {},
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        "decided_by_id": getattr(item, "decided_by_id", None),
        "decided_at": item.decided_at.isoformat() if getattr(item, "decided_at", None) else None,
        "decision_reason": getattr(item, "decision_reason", "") or "",
    }


def serialize_snapshot_history_item(item) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "version": item.version,
        "is_active": item.is_active,
        "source_kind": item.source_kind,
        "source_ref": item.source_ref,
        "layer": item.layer,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "archived_at": item.archived_at.isoformat() if item.archived_at else None,
        "rewrite_reason": snapshot_rewrite_reason(item),
        "action_summary": snapshot_action_summary(item),
        "created_by_username": getattr(getattr(item, "created_by", None), "username", None),
        "content_preview": compact_text(item.content, limit=220) if getattr(item, "content", "") else None,
    }


def snapshot_rewrite_reason(item) -> str | None:
    metadata = getattr(item, "metadata", None) or {}
    reason = str(metadata.get("rewrite_reason") or metadata.get("superseded_reason") or "").strip()
    return reason or None


def snapshot_action_summary(item) -> str | None:
    metadata = getattr(item, "metadata", None) or {}
    promoted_skill_slug = str(metadata.get("promoted_skill_slug") or "").strip()
    promoted_knowledge_id = metadata.get("promoted_knowledge_id")
    archived_reason = str(metadata.get("archived_reason") or "").strip()
    promoted_to_skill_at = str(metadata.get("promoted_to_skill_at") or "").strip()
    promoted_to_manual_at = str(metadata.get("promoted_to_manual_at") or "").strip()
    rewrite_reason = snapshot_rewrite_reason(item)
    if promoted_skill_slug:
        return f"Promoted to skill `{promoted_skill_slug}`"
    if promoted_knowledge_id:
        return f"Promoted to note #{promoted_knowledge_id}"
    if archived_reason:
        normalized = archived_reason.replace("_", " ").strip()
        return f"Archived: {normalized}"
    if promoted_to_skill_at:
        return "Skill promotion recorded"
    if promoted_to_manual_at:
        return "Manual note promotion recorded"
    if getattr(item, "superseded_by_id", None):
        if rewrite_reason:
            return f"Superseded: {rewrite_reason}"
        return f"Superseded by v{int(getattr(item, 'version', 0)) + 1}"
    if rewrite_reason:
        return f"Updated: {rewrite_reason}"
    return None


def describe_snapshot_rewrite(
    *,
    memory_key: str,
    delta: float,
    confidence_shift: float,
    force_version: bool,
) -> str:
    if force_version:
        return "Versioned refresh requested"
    if memory_key == "risks" and delta >= 0.2:
        return "Risk state changed"
    if memory_key == "recent_changes" and delta >= 0.2:
        return "Recent change set updated"
    if memory_key == "runbook" and delta >= 0.2:
        return "Operational recipe updated"
    if memory_key == "human_habits" and delta >= 0.2:
        return "Human workflow pattern updated"
    if abs(confidence_shift) >= 0.15:
        return "Confidence recalibrated"
    if delta >= 0.45:
        return "Major content update"
    return "Canonical snapshot refreshed"
