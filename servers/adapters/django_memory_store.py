from __future__ import annotations

from typing import Any

from channels.db import database_sync_to_async

from app.agent_kernel.domain.specs import ServerMemoryCard
from app.agent_kernel.memory.line_filters import (
    filter_memory_lines,
    sanitize_canonical_content,
)
from app.agent_kernel.memory.ports import MemoryStore  # noqa: F401
from servers.adapters.django_memory_cards import (
    get_server_card as perform_get_server_card,
)
from servers.adapters.django_memory_cards import (
    get_server_cards_batch as perform_get_server_cards_batch,
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
from servers.adapters.django_memory_manual import (
    preferred_memory_key_for_note,
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
from servers.adapters.django_memory_store_mixins import DjangoMemoryStoreSnapshotMixin


# ---------------------------------------------------------------------------
# MIGRATION NOTE (T-014): DjangoServerMemoryStore will be physically moved to
# servers/adapters/memory_store.py. Import consumers have already been updated.
# DO NOT add new imports here — use servers.adapters.memory_store instead.
# ---------------------------------------------------------------------------
class DjangoServerMemoryStore(DjangoMemoryStoreSnapshotMixin):
    async def get_server_card(self, server_id: int) -> ServerMemoryCard:
        return await database_sync_to_async(self._get_server_card_sync, thread_sensitive=True)(server_id)

    async def search_runbooks(
        self, query: str, *, server_id: int | None = None, group_id: int | None = None
    ) -> list[dict]:
        return await database_sync_to_async(self._search_runbooks_sync, thread_sensitive=True)(
            query, server_id=server_id, group_id=group_id
        )

    async def build_operational_recipes_prompt(
        self,
        query: str,
        *,
        server_ids: list[int] | None = None,
        group_ids: list[int] | None = None,
        limit: int = 5,
        actor_user_id: int | None = None,
        agent_id: int | None = None,
    ) -> str:
        return await database_sync_to_async(self._build_operational_recipes_prompt_sync, thread_sensitive=True)(
            query,
            server_ids=server_ids,
            group_ids=group_ids,
            limit=limit,
            actor_user_id=actor_user_id,
            agent_id=agent_id,
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

    async def repair_server_memory(
        self, server_id: int, *, stale_after_days: int = 30, create_notes: bool = True
    ) -> dict:
        return await database_sync_to_async(self._repair_server_memory_sync, thread_sensitive=True)(
            server_id,
            stale_after_days=stale_after_days,
            create_notes=create_notes,
        )

    async def dream_server_memory(
        self, server_id: int, *, deactivate_noise: bool = True, job_kind: str = "hybrid"
    ) -> dict:
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
        return await database_sync_to_async(self._sync_manual_knowledge_snapshot_sync, thread_sensitive=True)(
            knowledge_id
        )

    async def archive_manual_knowledge_snapshot(self, knowledge_id: int) -> int:
        return await database_sync_to_async(self._archive_manual_knowledge_snapshot_sync, thread_sensitive=True)(
            knowledge_id
        )

    async def archive_snapshot(
        self, server_id: int, snapshot_id: int, *, actor_user_id: int | None = None
    ) -> dict[str, Any]:
        return await database_sync_to_async(self._archive_snapshot_sync, thread_sensitive=True)(
            server_id,
            snapshot_id,
            actor_user_id=actor_user_id,
        )

    async def hard_delete_snapshot(
        self, server_id: int, snapshot_id: int, *, actor_user_id: int | None = None
    ) -> dict[str, Any]:
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

    def _search_runbooks_sync(
        self, query: str, *, server_id: int | None = None, group_id: int | None = None
    ) -> list[dict]:
        return search_runbooks(query, server_id=server_id, group_id=group_id)

    def _build_operational_recipes_prompt_sync(
        self,
        query: str,
        *,
        server_ids: list[int] | None = None,
        group_ids: list[int] | None = None,
        limit: int = 5,
        actor_user_id: int | None = None,
        agent_id: int | None = None,
    ) -> str:
        return build_operational_recipes_prompt(
            query,
            server_ids=server_ids,
            group_ids=group_ids,
            limit=limit,
            actor_user_id=actor_user_id,
            agent_id=agent_id,
        )

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

    def _repair_server_memory_sync(
        self, server_id: int, *, stale_after_days: int = 30, create_notes: bool = True
    ) -> dict:
        return perform_repair_server_memory(
            self, server_id, stale_after_days=stale_after_days, create_notes=create_notes
        )

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
        session_id: str | None = "",
        importance_hint: float = 0.5,
        actor_user_id: int | None = None,
        force_compact: bool = False,
        event_metadata: dict[str, Any] | None = None,
        idempotency_key_override: str = "",
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
            event_metadata=event_metadata,
            idempotency_key_override=idempotency_key_override,
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

    @classmethod
    def _preferred_memory_key_for_note(cls, *, title: str, category: str | None, content: str) -> str | None:
        return preferred_memory_key_for_note(title=title, category=category, content=content)
