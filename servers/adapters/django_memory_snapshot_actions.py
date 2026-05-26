from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from app.agent_kernel import skill_promotion_registry
from app.agent_kernel.domain.specs import SkillPromotionRequest
from app.agent_kernel.memory.compaction import compact_text
from app.agent_kernel.memory.pattern_utils import looks_mutating_command
from app.agent_kernel.memory.types import AUTOMATION_CANDIDATE_PREFIX, PATTERN_CANDIDATE_PREFIX, SKILL_DRAFT_PREFIX
from servers.adapters.django_memory_serializers import serialize_snapshot


def parse_trailing_int(value: Any, *, prefix: str | None = None) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if prefix:
        if not text.startswith(prefix):
            return None
        text = text[len(prefix) :]
    try:
        parsed = int(text)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def snapshot_linked_knowledge_id(snapshot: Any) -> int | None:
    metadata = getattr(snapshot, "metadata", None) or {}
    for key in ("knowledge_id", "promoted_knowledge_id"):
        parsed = parse_trailing_int(metadata.get(key))
        if parsed:
            return parsed

    source_ref = str(getattr(snapshot, "source_ref", "") or "").strip()
    parsed = parse_trailing_int(source_ref, prefix="knowledge:")
    if parsed:
        return parsed

    memory_key = str(getattr(snapshot, "memory_key", "") or "")
    for prefix in ("manual_note:", "knowledge_note:"):
        parsed = parse_trailing_int(memory_key, prefix=prefix)
        if parsed:
            return parsed
    return None


def has_active_user_ai_snapshots(server_id: int) -> bool:
    from servers.models import ServerMemorySnapshot

    return (
        ServerMemorySnapshot.objects.filter(server_id=server_id, is_active=True, archived_at__isnull=True)
        .exclude(memory_key__startswith="manual_note:")
        .exclude(memory_key__startswith="knowledge_note:")
        .exists()
    )


def hard_delete_snapshot(
    server_id: int,
    snapshot_id: int,
    *,
    actor_user_id: int | None = None,
) -> dict[str, Any]:
    from servers.models import ServerKnowledge, ServerMemoryRevalidation, ServerMemorySnapshot

    snapshot = ServerMemorySnapshot.objects.select_related("server").filter(pk=snapshot_id, server_id=server_id).first()
    if snapshot is None:
        raise ValueError("Memory snapshot not found")

    version_group_id = str(snapshot.version_group_id or "").strip()
    snapshot_group_qs = ServerMemorySnapshot.objects.filter(server_id=server_id)
    if version_group_id:
        snapshot_group_qs = snapshot_group_qs.filter(version_group_id=version_group_id)
    else:
        snapshot_group_qs = snapshot_group_qs.filter(pk=snapshot.pk)

    snapshot_ids = list(snapshot_group_qs.values_list("id", flat=True))
    memory_keys = list(snapshot_group_qs.values_list("memory_key", flat=True).distinct())
    linked_knowledge_id = snapshot_linked_knowledge_id(snapshot)
    linked_bridge_keys: list[str] = []
    if linked_knowledge_id:
        linked_bridge_keys = [f"manual_note:{linked_knowledge_id}", f"knowledge_note:{linked_knowledge_id}"]

    deleted_revalidations = 0
    deleted_snapshots = 0
    deleted_knowledge = 0

    with transaction.atomic():
        if snapshot_ids:
            deleted_revalidations += ServerMemoryRevalidation.objects.filter(
                server_id=server_id,
                source_snapshot_id__in=snapshot_ids,
            ).delete()[0]
        if memory_keys:
            deleted_revalidations += ServerMemoryRevalidation.objects.filter(
                server_id=server_id,
                memory_key__in=memory_keys,
            ).delete()[0]
        if linked_bridge_keys:
            deleted_revalidations += ServerMemoryRevalidation.objects.filter(
                server_id=server_id,
                memory_key__in=linked_bridge_keys,
            ).delete()[0]
            deleted_snapshots += (
                ServerMemorySnapshot.objects.filter(server_id=server_id, memory_key__in=linked_bridge_keys)
                .exclude(id__in=snapshot_ids)
                .delete()[0]
            )
        deleted_snapshots += snapshot_group_qs.delete()[0]

        if linked_knowledge_id:
            knowledge = ServerKnowledge.objects.filter(pk=linked_knowledge_id, server_id=server_id).first()
            if knowledge and knowledge.source in {"ai_auto", "ai_task"}:
                deleted_knowledge = knowledge.delete()[0]

    return {
        "snapshot_id": snapshot_id,
        "version_group_id": version_group_id,
        "deleted": {
            "snapshots": deleted_snapshots,
            "revalidations": deleted_revalidations,
            "knowledge": deleted_knowledge,
        },
        "actor_user_id": actor_user_id,
    }


def purge_server_ai_memory(store: Any, server_id: int, *, actor_user_id: int | None = None) -> dict[str, Any]:
    from servers.models import (
        ServerKnowledge,
        ServerMemoryEpisode,
        ServerMemoryEvent,
        ServerMemoryRevalidation,
        ServerMemorySnapshot,
    )

    ai_knowledge_ids = list(
        ServerKnowledge.objects.filter(server_id=server_id, source__in=["ai_auto", "ai_task"]).values_list("id", flat=True)
    )
    ai_bridge_keys: list[str] = []
    for knowledge_id in ai_knowledge_ids:
        ai_bridge_keys.append(f"manual_note:{knowledge_id}")
        ai_bridge_keys.append(f"knowledge_note:{knowledge_id}")

    deleted_bridge_snapshots = 0
    deleted_snapshots = 0
    deleted_revalidations = 0
    deleted_episodes = 0
    deleted_events = 0
    deleted_knowledge = 0

    with transaction.atomic():
        deleted_revalidations = ServerMemoryRevalidation.objects.filter(server_id=server_id).delete()[0]
        if ai_bridge_keys:
            deleted_bridge_snapshots = ServerMemorySnapshot.objects.filter(
                server_id=server_id,
                memory_key__in=ai_bridge_keys,
            ).delete()[0]
        deleted_snapshots = (
            ServerMemorySnapshot.objects.filter(server_id=server_id)
            .exclude(memory_key__startswith="manual_note:")
            .exclude(memory_key__startswith="knowledge_note:")
            .delete()[0]
        )
        deleted_episodes = ServerMemoryEpisode.objects.filter(server_id=server_id).delete()[0]
        deleted_events = ServerMemoryEvent.objects.filter(server_id=server_id).delete()[0]
        if ai_knowledge_ids:
            deleted_knowledge = ServerKnowledge.objects.filter(pk__in=ai_knowledge_ids, server_id=server_id).delete()[0]

    return {
        "deleted": {
            "snapshots": deleted_snapshots + deleted_bridge_snapshots,
            "revalidations": deleted_revalidations,
            "episodes": deleted_episodes,
            "events": deleted_events,
            "knowledge": deleted_knowledge,
        },
        "actor_user_id": actor_user_id,
        "overview": store._get_memory_overview_sync(server_id),
    }


def archive_snapshot(
    store: Any,
    server_id: int,
    snapshot_id: int,
    *,
    actor_user_id: int | None = None,
    reason: str = "manual_archive",
) -> dict[str, Any]:
    from servers.models import ServerMemorySnapshot

    snapshot = ServerMemorySnapshot.objects.select_related("server").filter(pk=snapshot_id, server_id=server_id).first()
    if snapshot is None:
        raise ValueError("Memory snapshot not found")

    if snapshot.is_active or snapshot.layer != ServerMemorySnapshot.LAYER_ARCHIVE:
        metadata = dict(snapshot.metadata or {})
        metadata.update(
            {
                "archived_reason": reason,
                "archived_by_user_id": actor_user_id,
                "archived_action_at": timezone.now().isoformat(),
            }
        )
        snapshot.is_active = False
        snapshot.layer = ServerMemorySnapshot.LAYER_ARCHIVE
        snapshot.archived_at = timezone.now()
        snapshot.metadata = metadata
        snapshot.save(update_fields=["is_active", "layer", "archived_at", "metadata", "updated_at"])
        store._ingest_event_sync(
            server_id,
            source_kind="system",
            actor_kind="human" if actor_user_id else "system",
            source_ref=f"snapshot:{snapshot.id}",
            session_id="",
            event_type="memory_snapshot_archived",
            raw_text=f"{snapshot.title}\n{snapshot.content}",
            structured_payload={
                "snapshot_id": snapshot.id,
                "memory_key": snapshot.memory_key,
                "reason": reason,
            },
            importance_hint=0.45,
            actor_user_id=actor_user_id,
        )
    return serialize_snapshot(snapshot)


def promote_snapshot_to_manual_knowledge(
    store: Any,
    server_id: int,
    snapshot_id: int,
    *,
    actor_user_id: int,
) -> dict[str, Any]:
    from servers.models import ServerKnowledge, ServerMemorySnapshot

    snapshot = ServerMemorySnapshot.objects.select_related("server").filter(pk=snapshot_id, server_id=server_id).first()
    if snapshot is None:
        raise ValueError("Memory snapshot not found")

    metadata = dict(snapshot.metadata or {})
    promoted_knowledge_id = metadata.get("promoted_knowledge_id")
    knowledge = None
    if promoted_knowledge_id:
        knowledge = ServerKnowledge.objects.filter(pk=promoted_knowledge_id, server_id=server_id).first()

    if knowledge is None:
        knowledge = ServerKnowledge.objects.create(
            server_id=server_id,
            category=knowledge_category_for_snapshot(snapshot),
            title=compact_text(snapshot.title, limit=180),
            content=compact_text(snapshot.content, limit=8000),
            source="manual",
            confidence=max(0.55, float(snapshot.confidence or 0.0)),
            is_active=True,
            created_by_id=actor_user_id,
            verified_at=snapshot.last_verified_at,
        )
        metadata["promoted_knowledge_id"] = knowledge.id
        metadata["promoted_to_manual_at"] = timezone.now().isoformat()
        snapshot.metadata = metadata
        snapshot.save(update_fields=["metadata", "updated_at"])
        store._sync_manual_knowledge_snapshot_sync(knowledge.id)
        store._ingest_event_sync(
            server_id,
            source_kind="manual_knowledge",
            actor_kind="human",
            source_ref=f"snapshot:{snapshot.id}",
            session_id="",
            event_type="memory_snapshot_promoted_to_manual",
            raw_text=f"{snapshot.title}\n{snapshot.content}",
            structured_payload={
                "snapshot_id": snapshot.id,
                "memory_key": snapshot.memory_key,
                "knowledge_id": knowledge.id,
            },
            importance_hint=0.72,
            actor_user_id=actor_user_id,
        )

    archived_snapshot = archive_snapshot(
        store,
        server_id,
        snapshot_id,
        actor_user_id=actor_user_id,
        reason="promoted_to_manual_note",
    )
    return {
        "knowledge_id": knowledge.id,
        "knowledge_title": knowledge.title,
        "snapshot": archived_snapshot,
        "overview": store._get_memory_overview_sync(server_id),
    }


def promote_skill_draft_to_skill(
    store: Any,
    server_id: int,
    snapshot_id: int,
    *,
    actor_user_id: int,
) -> dict[str, Any]:
    from servers.models import ServerKnowledge, ServerMemorySnapshot

    snapshot = ServerMemorySnapshot.objects.select_related("server").filter(pk=snapshot_id, server_id=server_id).first()
    if snapshot is None:
        raise ValueError("Memory snapshot not found")
    if not str(snapshot.memory_key or "").startswith(SKILL_DRAFT_PREFIX):
        raise ValueError("Selected snapshot is not a skill draft")

    metadata = dict(snapshot.metadata or {})
    gateway = skill_promotion_registry.get()
    if gateway is None:
        raise ValueError("Skill promotion gateway is not configured")

    promotion = gateway.promote_skill_draft(
        SkillPromotionRequest(
            server_name=snapshot.server.name,
            server_host=snapshot.server.host,
            snapshot_title=snapshot.title,
            snapshot_content=snapshot.content,
            memory_key=snapshot.memory_key,
            metadata=metadata,
            actor_user_id=actor_user_id,
            is_mutating=looks_mutating_command(str(metadata.get("display_command") or snapshot.content)),
        )
    )
    skill = promotion.skill
    metadata = dict(promotion.metadata or {})
    validation_payload = promotion.validation

    if promotion.created:
        snapshot.metadata = metadata
        snapshot.save(update_fields=["metadata", "updated_at"])
        store._ingest_event_sync(
            server_id,
            source_kind="system",
            actor_kind="human",
            source_ref=f"snapshot:{snapshot.id}",
            session_id="",
            event_type="memory_skill_draft_promoted",
            raw_text=f"{snapshot.title}\n{snapshot.content}",
            structured_payload={
                "snapshot_id": snapshot.id,
                "memory_key": snapshot.memory_key,
                "skill_slug": skill.slug,
            },
            importance_hint=0.8,
            actor_user_id=actor_user_id,
        )

    promoted_knowledge_id = metadata.get("promoted_knowledge_id")
    knowledge = None
    if promoted_knowledge_id:
        knowledge = ServerKnowledge.objects.filter(pk=promoted_knowledge_id, server_id=server_id).first()
    knowledge_title = f"Operational Skill: {skill.name}"
    knowledge_content = build_skill_memory_note_content(snapshot, metadata, skill)
    if knowledge is None:
        knowledge = ServerKnowledge.objects.create(
            server_id=server_id,
            category="solutions",
            title=knowledge_title[:200],
            content=knowledge_content,
            source="manual",
            confidence=max(0.62, float(snapshot.confidence or 0.0)),
            is_active=True,
            created_by_id=actor_user_id,
            verified_at=snapshot.last_verified_at,
        )
    else:
        dirty_fields: list[str] = []
        if knowledge.title != knowledge_title[:200]:
            knowledge.title = knowledge_title[:200]
            dirty_fields.append("title")
        if knowledge.content != knowledge_content:
            knowledge.content = knowledge_content
            dirty_fields.append("content")
        new_confidence = max(0.62, float(snapshot.confidence or 0.0))
        if abs(float(knowledge.confidence or 0.0) - new_confidence) >= 0.03:
            knowledge.confidence = new_confidence
            dirty_fields.append("confidence")
        if knowledge.verified_at != snapshot.last_verified_at:
            knowledge.verified_at = snapshot.last_verified_at
            dirty_fields.append("verified_at")
        if not knowledge.is_active:
            knowledge.is_active = True
            dirty_fields.append("is_active")
        if dirty_fields:
            dirty_fields.append("updated_at")
            knowledge.save(update_fields=dirty_fields)
    metadata["promoted_knowledge_id"] = knowledge.id
    snapshot.metadata = metadata
    snapshot.save(update_fields=["metadata", "updated_at"])
    store._sync_manual_knowledge_snapshot_sync(knowledge.id)

    archived_snapshot = archive_snapshot(
        store,
        server_id,
        snapshot_id,
        actor_user_id=actor_user_id,
        reason="promoted_to_skill",
    )
    return {
        "snapshot": archived_snapshot,
        "skill": {
            **skill.to_detail_dict(),
            "path": skill.path,
        },
        "knowledge_id": knowledge.id,
        "validation": validation_payload,
        "overview": store._get_memory_overview_sync(server_id),
    }


def knowledge_category_for_snapshot(snapshot: Any) -> str:
    memory_key = str(getattr(snapshot, "memory_key", "") or "")
    metadata = getattr(snapshot, "metadata", None) or {}
    intent = str(metadata.get("intent") or "").strip().lower()
    if memory_key.startswith(("manual_note:", "knowledge_note:")):
        category = str(metadata.get("category") or "").strip().lower()
        return category or "other"
    if memory_key.startswith((PATTERN_CANDIDATE_PREFIX, AUTOMATION_CANDIDATE_PREFIX, SKILL_DRAFT_PREFIX)):
        if intent == "service":
            return "services"
        if intent in {"docker", "kubernetes", "web"}:
            return "solutions"
        if intent == "diagnostics":
            return "performance"
        if intent == "inspection":
            return "config"
        return "solutions"
    if memory_key == "profile":
        return "system"
    if memory_key == "access":
        return "network"
    if memory_key == "risks":
        return "issues"
    if memory_key == "runbook":
        return "solutions"
    if memory_key == "recent_changes":
        return "config"
    if memory_key == "human_habits":
        return "solutions"
    return "other"


def build_skill_memory_note_content(snapshot: Any, metadata: dict[str, Any], skill: Any) -> str:
    commands = [str(item).strip() for item in (metadata.get("commands") or []) if str(item).strip()]
    sample_outputs = [str(item).strip() for item in (metadata.get("sample_outputs") or []) if str(item).strip()]
    common_cwds = [str(item).strip() for item in (metadata.get("common_cwds") or []) if str(item).strip()]
    lines = [
        f"Связанный skill: {skill.slug}",
        f"Когда использовать: {compact_text(str(metadata.get('intent') or snapshot.title), limit=180)}",
    ]
    if commands:
        lines.append("Workflow: " + " -> ".join(compact_text(item, limit=120) for item in commands[:4]))
    else:
        lines.append("Команда: " + compact_text(str(metadata.get("display_command") or snapshot.title), limit=180))
    if sample_outputs:
        lines.append("Сигналы успеха: " + " | ".join(compact_text(item, limit=140) for item in sample_outputs[:2]))
    if common_cwds:
        lines.append("Типовой cwd: " + ", ".join(compact_text(item, limit=120) for item in common_cwds[:2]))
    if metadata.get("playbook_summary"):
        lines.append("Playbook: " + compact_text(str(metadata.get("playbook_summary") or ""), limit=180))
    if metadata.get("verification"):
        lines.append("Verification: " + compact_text(str(metadata.get("verification") or ""), limit=180))
    if metadata.get("rollback_hint"):
        lines.append("Rollback: " + compact_text(str(metadata.get("rollback_hint") or ""), limit=180))
    lines.append("Открыть/редактировать skill в Studio при следующем изменении operational playbook.")
    return "\n".join(f"- {line}" for line in lines[:6])
