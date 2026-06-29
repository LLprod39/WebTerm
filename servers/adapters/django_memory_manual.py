from __future__ import annotations

from typing import Any

from django.utils import timezone

from app.agent_kernel.memory.snapshot_utils import guess_memory_key
from app.agent_kernel.memory.trust import TRUST_MANUAL_VERIFIED, VERIFICATION_VERIFIED


def preferred_memory_key_for_note(*, title: str, category: str | None, content: str) -> str | None:
    normalized_title = str(title or "").strip().lower()
    normalized_category = str(category or "").strip().lower()
    normalized_content = str(content or "").strip().lower()

    if any(term in normalized_title for term in ("профиль", "summary", "сводка", "overview")):
        return "profile"
    if any(term in normalized_title for term in ("риск", "risk", "issue", "incident", "alert", "замечан")):
        return "risks"
    if any(term in normalized_title for term in ("доступ", "access", "network", "ssh", "vpn", "порт")):
        return "access"
    if any(term in normalized_title for term in ("runbook", "playbook", "инструк", "workflow", "skill", "checklist", "чеклист")):
        return "runbook"
    if any(term in normalized_title for term in ("изменен", "change", "deploy", "release", "migration", "rollout", "обновл")):
        return "recent_changes"

    if normalized_category in {"issues", "performance", "storage"}:
        return "risks"
    if normalized_category in {"network", "security"}:
        return "access"
    if normalized_category == "solutions":
        return "runbook"
    if normalized_category in {"system", "config", "services", "packages", "other"}:
        return "profile"

    if normalized_content.startswith("обновлено:") and "факты:" in normalized_content:
        return "profile"
    if normalized_content.startswith("риски/замечания:"):
        return "risks"
    return None


def canonical_key_for_snapshot(snapshot: Any) -> str:
    metadata = getattr(snapshot, "metadata", None) or {}
    category = metadata.get("category")
    title = str(getattr(snapshot, "title", "") or "")
    content = str(getattr(snapshot, "content", "") or "")
    preferred = preferred_memory_key_for_note(
        title=title,
        category=str(category or ""),
        content=content,
    )
    if preferred:
        return preferred
    return guess_memory_key(
        title=title,
        category=str(category or ""),
        content=content,
    )


def sync_manual_knowledge_snapshot(store: Any, knowledge_id: int) -> str:
    from servers.models import ServerKnowledge

    knowledge = ServerKnowledge.objects.select_related("server").filter(pk=knowledge_id).first()
    if knowledge is None:
        return ""
    prefix = "manual_note" if knowledge.source == "manual" else "knowledge_note"
    memory_key = f"{prefix}:{knowledge.id}"
    if not knowledge.is_active:
        archive_manual_knowledge_snapshot(knowledge.id)
        store._ingest_event_sync(
            knowledge.server_id,
            source_kind="manual_knowledge",
            actor_kind="human",
            source_ref=f"knowledge:{knowledge.id}",
            session_id="",
            event_type="manual_note_disabled",
            raw_text=f"{knowledge.title}\n{knowledge.content}",
            structured_payload={
                "knowledge_id": knowledge.id,
                "category": knowledge.category,
                "memory_key": memory_key,
                "is_active": False,
            },
            importance_hint=0.55,
            actor_user_id=knowledge.created_by_id,
        )
        return ""
    snapshot, _created = store._upsert_snapshot_sync(
        server_id=knowledge.server_id,
        created_by_id=knowledge.created_by_id,
        memory_key=memory_key,
        title=knowledge.title,
        content=knowledge.content,
        source_kind="manual_knowledge",
        source_ref=f"knowledge:{knowledge.id}",
        importance_score=0.88,
        stability_score=0.75,
        confidence=float(knowledge.confidence or 1.0),
        verified_at=knowledge.verified_at,
        metadata={
            "category": knowledge.category,
            "knowledge_id": knowledge.id,
            "trust_level": TRUST_MANUAL_VERIFIED,
            "verification_status": VERIFICATION_VERIFIED,
            "source_actor_kind": "human",
            "source_confidence": float(knowledge.confidence or 1.0),
            "evidence_refs": [f"knowledge:{knowledge.id}"],
        },
        version_group_id=f"{prefix.replace('_', '-')}-{knowledge.id}",
        force_version=True,
    )
    store._ingest_event_sync(
        knowledge.server_id,
        source_kind="manual_knowledge",
        actor_kind="human",
        source_ref=f"knowledge:{knowledge.id}",
        session_id="",
        event_type="manual_note_updated",
        raw_text=f"{knowledge.title}\n{knowledge.content}",
        structured_payload={
            "knowledge_id": knowledge.id,
            "category": knowledge.category,
            "memory_key": memory_key,
            "is_active": knowledge.is_active,
        },
        importance_hint=0.82,
        actor_user_id=knowledge.created_by_id,
    )
    from servers.tasks import run_dream_cycle_task

    run_dream_cycle_task.delay(knowledge.server_id, job_kind="nearline")
    return str(snapshot.pk)


def archive_manual_knowledge_snapshot(knowledge_id: int) -> int:
    from servers.models import ServerMemorySnapshot

    return ServerMemorySnapshot.objects.filter(
        memory_key__in=[f"manual_note:{knowledge_id}", f"knowledge_note:{knowledge_id}"],
        is_active=True,
    ).update(
        is_active=False,
        layer=ServerMemorySnapshot.LAYER_ARCHIVE,
        archived_at=timezone.now(),
    )


def is_manual_bridge_memory_key(memory_key: str) -> bool:
    return str(memory_key or "").startswith(("manual_note:", "knowledge_note:"))
