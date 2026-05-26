from __future__ import annotations

from typing import Any

from channels.db import database_sync_to_async

from app.agent_kernel.domain.specs import ServerMemoryCard
from app.agent_kernel.memory.dream_candidates import build_snapshot_candidates
from app.agent_kernel.memory.line_filters import (
    filter_memory_lines,
    sanitize_canonical_content,
)
from app.agent_kernel.memory.ports import MemoryStore  # noqa: F401
from app.agent_kernel.memory.types import (
    OperationalPattern,
    SnapshotCandidate,
)
from servers.adapters.django_memory_cards import (
    get_server_card as perform_get_server_card,
)
from servers.adapters.django_memory_cards import (
    get_server_cards_batch as perform_get_server_cards_batch,
)
from servers.adapters.django_memory_dreams import (
    archive_old_episodes as perform_archive_old_episodes,
)
from servers.adapters.django_memory_dreams import (
    archive_old_events as perform_archive_old_events,
)
from servers.adapters.django_memory_dreams import (
    dream_server_memory as perform_dream_server_memory,
)
from servers.adapters.django_memory_dreams import (
    is_sleep_window_open,
    server_recently_busy,
    should_skip_scheduled_dream,
)
from servers.adapters.django_memory_dreams import (
    run_dream_cycle as perform_run_dream_cycle,
)
from servers.adapters.django_memory_ingestion import (
    compact_group as perform_compact_group,
)
from servers.adapters.django_memory_ingestion import (
    compact_open_groups as perform_compact_open_groups,
)
from servers.adapters.django_memory_ingestion import (
    event_group_filters,
    maybe_compact_event_group,
)
from servers.adapters.django_memory_ingestion import (
    ingest_event as perform_ingest_event,
)
from servers.adapters.django_memory_llm import (
    build_memory_warmup_prompt,
    distill_with_llm,
    llm_enhance_patterns,
    should_distill_with_llm,
)
from servers.adapters.django_memory_manual import (
    archive_manual_knowledge_snapshot as perform_archive_manual_knowledge_snapshot,
)
from servers.adapters.django_memory_manual import (
    canonical_key_for_snapshot,
    is_manual_bridge_memory_key,
    preferred_memory_key_for_note,
)
from servers.adapters.django_memory_manual import (
    sync_manual_knowledge_snapshot as perform_sync_manual_knowledge_snapshot,
)
from servers.adapters.django_memory_overview import build_memory_overview_payload
from servers.adapters.django_memory_patterns import (
    derive_operational_patterns as perform_derive_operational_patterns,
)
from servers.adapters.django_memory_patterns import (
    promote_pattern_candidates as perform_promote_pattern_candidates,
)
from servers.adapters.django_memory_recording import (
    append_run_summary as perform_append_run_summary,
)
from servers.adapters.django_memory_recording import (
    detect_conflicts as perform_detect_conflicts,
)
from servers.adapters.django_memory_recording import (
    record_change as perform_record_change,
)
from servers.adapters.django_memory_recording import (
    record_incident as perform_record_incident,
)
from servers.adapters.django_memory_recording import (
    upsert_server_fact as perform_upsert_server_fact,
)
from servers.adapters.django_memory_repair import repair_server_memory as perform_repair_server_memory
from servers.adapters.django_memory_runbooks import build_operational_recipes_prompt, search_runbooks
from servers.adapters.django_memory_snapshot_actions import (
    archive_snapshot as perform_archive_snapshot,
)
from servers.adapters.django_memory_snapshot_actions import (
    hard_delete_snapshot as perform_hard_delete_snapshot,
)
from servers.adapters.django_memory_snapshot_actions import (
    has_active_user_ai_snapshots,
)
from servers.adapters.django_memory_snapshot_actions import (
    promote_skill_draft_to_skill as perform_promote_skill_draft_to_skill,
)
from servers.adapters.django_memory_snapshot_actions import (
    promote_snapshot_to_manual_knowledge as perform_promote_snapshot_to_manual_knowledge,
)
from servers.adapters.django_memory_snapshot_actions import (
    purge_server_ai_memory as perform_purge_server_ai_memory,
)
from servers.adapters.django_memory_snapshots import (
    archive_missing_candidate_snapshots as perform_archive_missing_candidate_snapshots,
)
from servers.adapters.django_memory_snapshots import (
    ensure_revalidation as perform_ensure_revalidation,
)
from servers.adapters.django_memory_snapshots import (
    upsert_snapshot as perform_upsert_snapshot,
)

_SnapshotCandidate = SnapshotCandidate
_OperationalPattern = OperationalPattern


# ---------------------------------------------------------------------------
# MIGRATION NOTE (T-014): DjangoServerMemoryStore will be physically moved to
# servers/adapters/memory_store.py. Import consumers have already been updated.
# DO NOT add new imports here — use servers.adapters.memory_store instead.
# ---------------------------------------------------------------------------
class DjangoServerMemoryStore:
    async def get_server_card(self, server_id: int) -> ServerMemoryCard:
        return await database_sync_to_async(self._get_server_card_sync, thread_sensitive=True)(server_id)

    async def search_runbooks(self, query: str, *, server_id: int | None = None, group_id: int | None = None) -> list[dict]:
        return await database_sync_to_async(self._search_runbooks_sync, thread_sensitive=True)(query, server_id=server_id, group_id=group_id)

    async def build_operational_recipes_prompt(
        self,
        query: str,
        *,
        server_ids: list[int] | None = None,
        group_ids: list[int] | None = None,
        limit: int = 5,
    ) -> str:
        return await database_sync_to_async(self._build_operational_recipes_prompt_sync, thread_sensitive=True)(
            query,
            server_ids=server_ids,
            group_ids=group_ids,
            limit=limit,
        )

    async def append_run_summary(self, run_id: int, summary: dict) -> str:
        return await database_sync_to_async(self._append_run_summary_sync, thread_sensitive=True)(run_id, summary)

    async def upsert_server_fact(self, server_id: int, fact: dict) -> str:
        return await database_sync_to_async(self._upsert_server_fact_sync, thread_sensitive=True)(server_id, fact)

    async def record_change(self, server_id: int, change: dict) -> str:
        return await database_sync_to_async(self._record_change_sync, thread_sensitive=True)(server_id, change)

    async def record_incident(self, server_id: int, incident: dict) -> str:
        return await database_sync_to_async(self._record_incident_sync, thread_sensitive=True)(server_id, incident)

    async def detect_conflicts(self, server_id: int, new_facts: list[dict]) -> list[dict]:
        return await database_sync_to_async(self._detect_conflicts_sync, thread_sensitive=True)(server_id, new_facts)

    async def repair_server_memory(self, server_id: int, *, stale_after_days: int = 30, create_notes: bool = True) -> dict:
        return await database_sync_to_async(self._repair_server_memory_sync, thread_sensitive=True)(
            server_id,
            stale_after_days=stale_after_days,
            create_notes=create_notes,
        )

    async def dream_server_memory(self, server_id: int, *, deactivate_noise: bool = True, job_kind: str = "hybrid") -> dict:
        return await database_sync_to_async(self._dream_server_memory_sync, thread_sensitive=True)(
            server_id,
            deactivate_noise=deactivate_noise,
            job_kind=job_kind,
        )

    async def ingest_event(self, server_id: int, **kwargs: Any) -> str:
        return await database_sync_to_async(self._ingest_event_sync, thread_sensitive=True)(server_id, **kwargs)

    async def get_memory_overview(self, server_id: int) -> dict[str, Any]:
        return await database_sync_to_async(self._get_memory_overview_sync, thread_sensitive=True)(server_id)

    async def run_dream_cycle(
        self,
        server_id: int,
        *,
        job_kind: str = "hybrid",
        respect_schedule: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        return await database_sync_to_async(self._run_dream_cycle_sync, thread_sensitive=True)(
            server_id,
            job_kind=job_kind,
            respect_schedule=respect_schedule,
            force=force,
        )

    async def sync_manual_knowledge_snapshot(self, knowledge_id: int) -> str:
        return await database_sync_to_async(self._sync_manual_knowledge_snapshot_sync, thread_sensitive=True)(knowledge_id)

    async def archive_manual_knowledge_snapshot(self, knowledge_id: int) -> int:
        return await database_sync_to_async(self._archive_manual_knowledge_snapshot_sync, thread_sensitive=True)(knowledge_id)

    async def archive_snapshot(self, server_id: int, snapshot_id: int, *, actor_user_id: int | None = None) -> dict[str, Any]:
        return await database_sync_to_async(self._archive_snapshot_sync, thread_sensitive=True)(
            server_id,
            snapshot_id,
            actor_user_id=actor_user_id,
        )

    async def hard_delete_snapshot(self, server_id: int, snapshot_id: int, *, actor_user_id: int | None = None) -> dict[str, Any]:
        return await database_sync_to_async(self._hard_delete_snapshot_sync, thread_sensitive=True)(
            server_id,
            snapshot_id,
            actor_user_id=actor_user_id,
        )

    async def purge_server_ai_memory(self, server_id: int, *, actor_user_id: int | None = None) -> dict[str, Any]:
        return await database_sync_to_async(self._purge_server_ai_memory_sync, thread_sensitive=True)(
            server_id,
            actor_user_id=actor_user_id,
        )

    async def promote_snapshot_to_manual_knowledge(
        self,
        server_id: int,
        snapshot_id: int,
        *,
        actor_user_id: int,
    ) -> dict[str, Any]:
        return await database_sync_to_async(self._promote_snapshot_to_manual_knowledge_sync, thread_sensitive=True)(
            server_id,
            snapshot_id,
            actor_user_id=actor_user_id,
        )

    async def promote_skill_draft_to_skill(
        self,
        server_id: int,
        snapshot_id: int,
        *,
        actor_user_id: int,
    ) -> dict[str, Any]:
        return await database_sync_to_async(self._promote_skill_draft_to_skill_sync, thread_sensitive=True)(
            server_id,
            snapshot_id,
            actor_user_id=actor_user_id,
        )

    def _get_or_create_policy_sync(self, *, user_id: int, agent=None):
        from servers.models import ServerMemoryPolicy

        policy, _created = ServerMemoryPolicy.objects.get_or_create(user_id=user_id)
        # Apply per-agent overrides when available (P1-6)
        if agent is not None:
            overrides = getattr(agent, "memory_policy_override", None) or {}
            for key, value in overrides.items():
                if hasattr(policy, key) and key not in ("id", "pk", "user", "user_id"):
                    setattr(policy, key, value)
        return policy

    def _get_server_card_sync(self, server_id: int) -> ServerMemoryCard:
        return perform_get_server_card(server_id)

    def _get_server_cards_batch_sync(self, server_ids: list[int]) -> list[ServerMemoryCard]:
        return perform_get_server_cards_batch(server_ids)

    def _search_runbooks_sync(self, query: str, *, server_id: int | None = None, group_id: int | None = None) -> list[dict]:
        return search_runbooks(query, server_id=server_id, group_id=group_id)

    def _build_operational_recipes_prompt_sync(
        self,
        query: str,
        *,
        server_ids: list[int] | None = None,
        group_ids: list[int] | None = None,
        limit: int = 5,
    ) -> str:
        return build_operational_recipes_prompt(query, server_ids=server_ids, group_ids=group_ids, limit=limit)

    def _append_run_summary_sync(self, run_id: int, summary: dict) -> str:
        return perform_append_run_summary(self, run_id, summary)

    def _upsert_server_fact_sync(
        self,
        server_id: int,
        fact: dict,
        *,
        source_ref: str = "",
        session_id: str = "",
    ) -> str:
        return perform_upsert_server_fact(self, server_id, fact, source_ref=source_ref, session_id=session_id)

    def _record_change_sync(
        self,
        server_id: int,
        change: dict,
        *,
        source_ref: str = "",
        session_id: str = "",
    ) -> str:
        return perform_record_change(self, server_id, change, source_ref=source_ref, session_id=session_id)

    def _record_incident_sync(
        self,
        server_id: int,
        incident: dict,
        *,
        source_ref: str = "",
        session_id: str = "",
    ) -> str:
        return perform_record_incident(self, server_id, incident, source_ref=source_ref, session_id=session_id)

    def _detect_conflicts_sync(self, server_id: int, new_facts: list[dict]) -> list[dict]:
        return perform_detect_conflicts(server_id, new_facts)

    def _repair_server_memory_sync(self, server_id: int, *, stale_after_days: int = 30, create_notes: bool = True) -> dict:
        return perform_repair_server_memory(self, server_id, stale_after_days=stale_after_days, create_notes=create_notes)

    def _ingest_event_sync(
        self,
        server_id: int,
        *,
        source_kind: str,
        actor_kind: str,
        event_type: str,
        raw_text: str = "",
        structured_payload: dict[str, Any] | None = None,
        source_ref: str = "",
        session_id: str = "",
        importance_hint: float = 0.5,
        actor_user_id: int | None = None,
        force_compact: bool = False,
    ) -> str:
        return perform_ingest_event(
            self,
            server_id,
            source_kind=source_kind,
            actor_kind=actor_kind,
            event_type=event_type,
            raw_text=raw_text,
            structured_payload=structured_payload,
            source_ref=source_ref,
            session_id=session_id,
            importance_hint=importance_hint,
            actor_user_id=actor_user_id,
            force_compact=force_compact,
        )

    @staticmethod
    def _maybe_compact_event_group_sync(event, *, threshold: int, force: bool) -> None:
        return maybe_compact_event_group(event, threshold=threshold, force=force)

    @staticmethod
    def _event_group_filters(event) -> dict[str, Any]:
        return event_group_filters(event)

    @staticmethod
    def _compact_open_groups_sync(server_id: int, *, force: bool = False) -> int:
        return perform_compact_open_groups(server_id, force=force)

    def _compact_group_sync(
        self,
        *,
        server_id: int,
        source_kind: str,
        source_ref: str = "",
        session_id: str = "",
        force: bool = False,
    ) -> int:
        return perform_compact_group(
            server_id=server_id,
            source_kind=source_kind,
            source_ref=source_ref,
            session_id=session_id,
            force=force,
        )

    @classmethod
    def _filter_memory_lines(cls, value: Any, *, limit: int = 6) -> list[str]:
        return filter_memory_lines(value, limit=limit)

    @classmethod
    def _sanitize_canonical_content(cls, memory_key: str, content: str, *, fallback: str) -> str:
        return sanitize_canonical_content(memory_key, content, fallback=fallback)

    def _dream_server_memory_sync(self, server_id: int, *, deactivate_noise: bool = True, job_kind: str = "hybrid") -> dict:
        return perform_dream_server_memory(self, server_id, deactivate_noise=deactivate_noise, job_kind=job_kind)

    def _build_snapshot_candidates(
        self,
        *,
        server,
        episodes: list[Any],
        snapshots: list[Any],
        recent_events: list[Any],
        latest_health,
        active_alerts: list[Any],
        revalidation_items: list[Any],
        allow_human_habits: bool,
        patterns: list[_OperationalPattern] | None = None,
    ) -> list[_SnapshotCandidate]:
        return build_snapshot_candidates(
            server=server,
            episodes=episodes,
            snapshots=snapshots,
            recent_events=recent_events,
            latest_health=latest_health,
            active_alerts=active_alerts,
            revalidation_items=revalidation_items,
            allow_human_habits=allow_human_habits,
            patterns=patterns,
            canonical_key_for_snapshot=self._canonical_key_for_snapshot,
            derive_patterns=self._derive_operational_patterns,
        )

    def _derive_operational_patterns(self, server_id: int) -> list[_OperationalPattern]:
        return perform_derive_operational_patterns(server_id)

    def _promote_pattern_candidates_sync(
        self,
        *,
        server_id: int,
        patterns: list[_OperationalPattern],
        snapshots: list[Any],
        enhancements: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, int]:
        return perform_promote_pattern_candidates(
            server_id=server_id,
            patterns=patterns,
            snapshots=snapshots,
            enhancements=enhancements,
        )

    def _archive_missing_candidate_snapshots_sync(self, server_id: int, *, active_keys: set[str]) -> int:
        return perform_archive_missing_candidate_snapshots(server_id, active_keys=active_keys)

    @classmethod
    def _preferred_memory_key_for_note(cls, *, title: str, category: str | None, content: str) -> str | None:
        return preferred_memory_key_for_note(title=title, category=category, content=content)

    def _canonical_key_for_snapshot(self, snapshot) -> str:
        return canonical_key_for_snapshot(snapshot)

    def _should_distill_with_llm(
        self,
        candidates: list[_SnapshotCandidate],
        existing_snapshots: list[Any],
    ) -> bool:
        return should_distill_with_llm(candidates, existing_snapshots)

    @staticmethod
    def _build_memory_warmup_prompt(server_id: int, *, last_n: int = 3) -> str:
        return build_memory_warmup_prompt(server_id, last_n=last_n)

    def _distill_with_llm_sync(
        self,
        *,
        server,
        candidates: list[_SnapshotCandidate],
        model_alias: str,
    ) -> dict[str, str]:
        return distill_with_llm(server=server, candidates=candidates, model_alias=model_alias)

    def _llm_enhance_patterns_sync(
        self,
        *,
        server,
        patterns: list[_OperationalPattern],
        model_alias: str,
    ) -> dict[str, dict[str, Any]]:
        return llm_enhance_patterns(server=server, patterns=patterns, model_alias=model_alias)

    def _upsert_snapshot_sync(
        self,
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
    ):
        return perform_upsert_snapshot(
            server_id=server_id,
            memory_key=memory_key,
            title=title,
            content=content,
            source_kind=source_kind,
            source_ref=source_ref,
            importance_score=importance_score,
            stability_score=stability_score,
            confidence=confidence,
            verified_at=verified_at,
            metadata=metadata,
            created_by_id=created_by_id,
            version_group_id=version_group_id,
            force_version=force_version,
        )

    def _ensure_revalidation_sync(
        self,
        server_id: int,
        *,
        memory_key: str,
        title: str,
        reason: str,
        payload: dict[str, Any] | None = None,
        source_snapshot=None,
    ):
        return perform_ensure_revalidation(
            server_id,
            memory_key=memory_key,
            title=title,
            reason=reason,
            payload=payload,
            source_snapshot=source_snapshot,
        )

    def _archive_old_events_sync(self, server_id: int, *, now=None) -> int:
        return perform_archive_old_events(self, server_id, now=now)

    def _archive_old_episodes_sync(self, server_id: int, *, now=None) -> int:
        return perform_archive_old_episodes(self, server_id, now=now)

    @staticmethod
    def _is_sleep_window_open(policy, *, now=None) -> bool:
        return is_sleep_window_open(policy, now=now)

    def _server_recently_busy_sync(self, server_id: int, *, minutes: int = 20) -> bool:
        return server_recently_busy(server_id, minutes=minutes)

    def _should_skip_scheduled_dream_sync(self, server_id: int, *, policy, job_kind: str) -> str:
        return should_skip_scheduled_dream(self, server_id, policy=policy, job_kind=job_kind)

    def _run_dream_cycle_sync(
        self,
        server_id: int,
        *,
        job_kind: str = "hybrid",
        respect_schedule: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        return perform_run_dream_cycle(
            self,
            server_id,
            job_kind=job_kind,
            respect_schedule=respect_schedule,
            force=force,
        )

    def _get_memory_overview_sync(self, server_id: int) -> dict[str, Any]:
        from servers.models import Server

        server = Server.objects.filter(pk=server_id).select_related("user").first()
        if server is None:
            return {}
        policy = self._get_or_create_policy_sync(user_id=server.user_id)
        return build_memory_overview_payload(server_id, policy)

    def _sync_manual_knowledge_snapshot_sync(self, knowledge_id: int) -> str:
        return perform_sync_manual_knowledge_snapshot(self, knowledge_id)

    def _archive_manual_knowledge_snapshot_sync(self, knowledge_id: int) -> int:
        return perform_archive_manual_knowledge_snapshot(knowledge_id)

    @staticmethod
    def _is_manual_bridge_memory_key(memory_key: str) -> bool:
        return is_manual_bridge_memory_key(memory_key)

    def _has_active_user_ai_snapshots_sync(self, server_id: int) -> bool:
        return has_active_user_ai_snapshots(server_id)

    def _hard_delete_snapshot_sync(
        self,
        server_id: int,
        snapshot_id: int,
        *,
        actor_user_id: int | None = None,
    ) -> dict[str, Any]:
        return perform_hard_delete_snapshot(server_id, snapshot_id, actor_user_id=actor_user_id)

    def _purge_server_ai_memory_sync(
        self,
        server_id: int,
        *,
        actor_user_id: int | None = None,
    ) -> dict[str, Any]:
        return perform_purge_server_ai_memory(self, server_id, actor_user_id=actor_user_id)

    def _archive_snapshot_sync(
        self,
        server_id: int,
        snapshot_id: int,
        *,
        actor_user_id: int | None = None,
        reason: str = "manual_archive",
    ) -> dict[str, Any]:
        return perform_archive_snapshot(
            self,
            server_id,
            snapshot_id,
            actor_user_id=actor_user_id,
            reason=reason,
        )

    def _promote_snapshot_to_manual_knowledge_sync(
        self,
        server_id: int,
        snapshot_id: int,
        *,
        actor_user_id: int,
    ) -> dict[str, Any]:
        return perform_promote_snapshot_to_manual_knowledge(
            self,
            server_id,
            snapshot_id,
            actor_user_id=actor_user_id,
        )

    def _promote_skill_draft_to_skill_sync(
        self,
        server_id: int,
        snapshot_id: int,
        *,
        actor_user_id: int,
    ) -> dict[str, Any]:
        return perform_promote_skill_draft_to_skill(
            self,
            server_id,
            snapshot_id,
            actor_user_id=actor_user_id,
        )
