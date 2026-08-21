from __future__ import annotations

from typing import Any

from app.agent_kernel.memory.dream_candidates import build_snapshot_candidates
from app.agent_kernel.memory.types import OperationalPattern, SnapshotCandidate
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
from servers.adapters.django_memory_llm import build_memory_warmup_prompt, distill_with_llm, llm_enhance_patterns
from servers.adapters.django_memory_manual import (
    archive_manual_knowledge_snapshot as perform_archive_manual_knowledge_snapshot,
)
from servers.adapters.django_memory_manual import canonical_key_for_snapshot, is_manual_bridge_memory_key
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
from servers.adapters.django_memory_snapshot_actions import (
    archive_snapshot as perform_archive_snapshot,
)
from servers.adapters.django_memory_snapshot_actions import (
    hard_delete_snapshot as perform_hard_delete_snapshot,
)
from servers.adapters.django_memory_snapshot_actions import has_active_user_ai_snapshots
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


class DjangoMemoryStoreSnapshotMixin:
    def _dream_server_memory_sync(
        self, server_id: int, *, deactivate_noise: bool = True, job_kind: str = "hybrid"
    ) -> dict:
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
        generation_log=None,
    ) -> dict[str, int]:
        return perform_promote_pattern_candidates(
            server_id=server_id,
            patterns=patterns,
            snapshots=snapshots,
            enhancements=enhancements,
            generation_log=generation_log,
        )

    def _archive_missing_candidate_snapshots_sync(self, server_id: int, *, active_keys: set[str]) -> int:
        return perform_archive_missing_candidate_snapshots(server_id, active_keys=active_keys)

    def _canonical_key_for_snapshot(self, snapshot) -> str:
        return canonical_key_for_snapshot(snapshot)

    def _should_distill_with_llm(
        self,
        candidates: list[_SnapshotCandidate],
        existing_snapshots: list[Any],
    ) -> bool:
        from servers.adapters.django_memory_llm import should_distill_with_llm

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
        generation_log_out: list[Any] | None = None,
    ) -> dict[str, str]:
        return distill_with_llm(
            server=server,
            candidates=candidates,
            model_alias=model_alias,
            generation_log_out=generation_log_out,
        )

    def _llm_enhance_patterns_sync(
        self,
        *,
        server,
        patterns: list[_OperationalPattern],
        model_alias: str,
        generation_log_out: list[Any] | None = None,
    ) -> dict[str, dict[str, Any]]:
        return llm_enhance_patterns(
            server=server,
            patterns=patterns,
            model_alias=model_alias,
            generation_log_out=generation_log_out,
        )

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
        layer: str | None = None,
        enforce_trust_gate: bool = True,
        generation_log=None,
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
            layer=layer,
            enforce_trust_gate=enforce_trust_gate,
            generation_log=generation_log,
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
