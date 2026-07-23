from __future__ import annotations

import logging

from django.utils import timezone

from app.agent_kernel.memory.compaction import compact_text
from app.agent_kernel.memory.repair import detect_fact_conflicts, resolve_winning_fact
from app.agent_kernel.memory.snapshot_utils import guess_memory_key
from app.agent_kernel.memory.trust import TRUST_AGENT_REPORTED, VERIFICATION_NEEDS_REVALIDATION

logger = logging.getLogger(__name__)


def append_run_summary(store, run_id: int, summary: dict) -> str:
    from servers.models import AgentRun
    from servers.tasks import run_dream_cycle_task

    run = AgentRun.objects.select_related("server", "user", "agent").filter(pk=run_id).first()
    if not run or not run.server_id:
        return ""
    policy = store._get_or_create_policy_sync(user_id=run.user_id)
    if not bool(getattr(policy, "is_enabled", True)):
        return ""

    source_ref = f"agent-run:{run_id}"
    status = str(summary.get("status") or run.status or "completed")
    raw_text = "\n\n".join(
        part
        for part in [
            str(summary.get("summary_text") or "").strip(),
            str(summary.get("verification_summary") or "").strip(),
            str(run.final_report or "").strip(),
        ]
        if part
    )
    event_id = store._ingest_event_sync(
        run.server_id,
        source_kind="agent_run",
        actor_kind="agent",
        source_ref=source_ref,
        session_id=source_ref,
        event_type=f"run_{status}",
        raw_text=raw_text,
        structured_payload={
            "run_id": run_id,
            "status": status,
            "agent_name": getattr(run.agent, "name", "") if run.agent_id else "",
            "facts": summary.get("facts") or [],
            "changes": summary.get("changes") or [],
            "incidents": summary.get("incidents") or [],
            "canonical_notes": summary.get("canonical_notes") or [],
            "tool_calls": summary.get("tool_calls") or [],
            "verification_summary": summary.get("verification_summary") or "",
        },
        importance_hint=0.92 if status in {"failed", "stopped"} else 0.8,
        actor_user_id=run.user_id,
        force_compact=True,
    )
    for note in summary.get("canonical_notes") or []:
        record_canonical_note_candidate(store, run, note, source_ref=source_ref)
    for fact in summary.get("facts") or []:
        store._upsert_server_fact_sync(run.server_id, fact, source_ref=source_ref, session_id=source_ref)
    for change in summary.get("changes") or []:
        store._record_change_sync(run.server_id, change, source_ref=source_ref, session_id=source_ref)
    for incident in summary.get("incidents") or []:
        store._record_incident_sync(run.server_id, incident, source_ref=source_ref, session_id=source_ref)
    run_dream_cycle_task.delay(run.server_id, job_kind="nearline")
    return event_id


def record_canonical_note_candidate(store, run, note: dict, *, source_ref: str) -> None:
    if not isinstance(note, dict):
        return
    title = compact_text(str(note.get("title") or "Agent memory candidate"), limit=200)
    content = compact_text(str(note.get("content") or ""), limit=2400)
    if not content:
        return
    category = str(note.get("category") or "other")
    memory_key = store._preferred_memory_key_for_note(
        title=title, category=category, content=content
    ) or guess_memory_key(
        title=title,
        category=category,
        content=content,
    )
    payload = {
        "title": title,
        "category": category,
        "memory_key": memory_key,
        "source": note.get("source") or "agent_summary",
        "verified": bool(note.get("verified")),
        "trust_level": TRUST_AGENT_REPORTED,
        "verification_status": VERIFICATION_NEEDS_REVALIDATION,
    }
    event_id = store._ingest_event_sync(
        run.server_id,
        source_kind="agent_run",
        actor_kind="agent",
        source_ref=source_ref,
        session_id=source_ref,
        event_type="canonical_note_candidate",
        raw_text=f"{title}\n{content}",
        structured_payload=payload,
        importance_hint=float(note.get("confidence") or 0.62),
        actor_user_id=run.user_id,
        force_compact=True,
    )
    store._ensure_revalidation_sync(
        run.server_id,
        memory_key=memory_key,
        title=title,
        reason="Agent-generated canonical note candidate requires independent verification before promotion.",
        payload={
            **payload,
            "event_id": event_id,
            "content": content,
        },
    )


def upsert_server_fact(
    store,
    server_id: int,
    fact: dict,
    *,
    source_ref: str = "",
    session_id: str = "",
) -> str:
    title = (fact.get("title") or "Ops fact").strip()[:200]
    content = compact_text(fact.get("content") or "", limit=2400)
    memory_key = guess_memory_key(title=title, category=fact.get("category"), content=content)
    raw_category = str(fact.get("category") or "").strip()
    new_fact_variants = [{"title": title, "category": memory_key, "content": content}]
    if raw_category and raw_category.lower() != memory_key.lower():
        new_fact_variants.append({"title": title, "category": raw_category, "content": content})
    conflicts = store._detect_conflicts_sync(server_id, new_fact_variants)
    if conflicts:
        from servers.models import ServerMemorySnapshot

        conflict_info = conflicts[0]
        existing_snapshot = (
            ServerMemorySnapshot.objects.filter(
                server_id=server_id, title=conflict_info.get("title", ""), is_active=True
            )
            .order_by("-updated_at")
            .first()
        )
        verdict = resolve_winning_fact(
            existing_updated_at=getattr(existing_snapshot, "updated_at", None),
            existing_confidence=float(getattr(existing_snapshot, "confidence", 0.7) or 0.7),
            incoming_updated_at=timezone.now(),
            incoming_confidence=float(fact.get("confidence") or 0.78),
        )
        if verdict == "existing":
            logger.info("fact conflict: existing wins for %s on server %s", title, server_id)
            return ""
        if verdict == "revalidate":
            store._ensure_revalidation_sync(
                server_id,
                memory_key=memory_key,
                title=title,
                reason="Новый факт противоречит активной памяти сервера (требуется ручная проверка).",
                payload=conflict_info,
            )
    return store._ingest_event_sync(
        server_id,
        source_kind="agent_run",
        actor_kind="agent",
        source_ref=source_ref,
        session_id=session_id,
        event_type="fact_discovered",
        raw_text=f"{title}\n{content}",
        structured_payload={
            "title": title,
            "category": fact.get("category") or "other",
            "memory_key": memory_key,
            "confidence": float(fact.get("confidence") or 0.78),
            "verified": bool(fact.get("verified")),
        },
        importance_hint=float(fact.get("confidence") or 0.72),
    )


def record_change(
    store,
    server_id: int,
    change: dict,
    *,
    source_ref: str = "",
    session_id: str = "",
) -> str:
    title = change.get("title") or "Изменение состояния сервера"
    content = compact_text(change.get("content") or "", limit=1800)
    return store._ingest_event_sync(
        server_id,
        source_kind="agent_run",
        actor_kind="agent",
        source_ref=source_ref,
        session_id=session_id,
        event_type="server_change",
        raw_text=f"{title}\n{content}",
        structured_payload={
            "title": title,
            "category": change.get("category") or "config",
            "verified": bool(change.get("verified")),
            "memory_key": "recent_changes",
        },
        importance_hint=float(change.get("confidence") or 0.82),
    )


def record_incident(
    store,
    server_id: int,
    incident: dict,
    *,
    source_ref: str = "",
    session_id: str = "",
) -> str:
    title = incident.get("title") or "Инцидент"
    content = compact_text(incident.get("content") or "", limit=1800)
    event_id = store._ingest_event_sync(
        server_id,
        source_kind="agent_run",
        actor_kind="agent",
        source_ref=source_ref,
        session_id=session_id,
        event_type="incident",
        raw_text=f"{title}\n{content}",
        structured_payload={
            "title": title,
            "category": incident.get("category") or "issues",
            "memory_key": "risks",
        },
        importance_hint=float(incident.get("confidence") or 0.86),
    )
    store._ensure_revalidation_sync(
        server_id,
        memory_key="risks",
        title=title[:200],
        reason="Новый инцидент требует перепроверки и учёта в risk profile.",
        payload={"content": content},
    )
    return event_id


def detect_conflicts(server_id: int, new_facts: list[dict]) -> list[dict]:
    from servers.models import ServerMemorySnapshot

    existing = list(
        ServerMemorySnapshot.objects.filter(server_id=server_id, is_active=True).values(
            "title", "memory_key", "content", "metadata"
        )
    )
    normalized_existing = []
    for item in existing:
        memory_key = str(item.get("memory_key") or "")
        metadata = item.get("metadata") or {}
        category = str(metadata.get("category") or memory_key or "").strip()
        if memory_key.startswith(("manual_note:", "knowledge_note:")):
            category = category or guess_memory_key(
                title=str(item.get("title") or ""),
                category=None,
                content=str(item.get("content") or ""),
            )
        normalized_existing.append(
            {
                "title": item["title"],
                "category": category,
                "content": item["content"],
            }
        )
    return detect_fact_conflicts(normalized_existing, new_facts)
