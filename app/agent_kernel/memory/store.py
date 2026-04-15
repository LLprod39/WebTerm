from __future__ import annotations

import ast
import json
import re
import shlex
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol

from asgiref.sync import async_to_sync, sync_to_async
from django.db import transaction
from django.utils import timezone

from app.agent_kernel.domain.specs import ServerMemoryCard
from app.agent_kernel.memory.compaction import compact_text, extract_signal_lines, unique_preserving_order
from app.agent_kernel.memory.redaction import payload_preview, redact_for_storage
from app.agent_kernel.memory.repair import (
    auto_resolve_stale_revalidations,
    compute_freshness_score,
    decay_confidence,
    detect_fact_conflicts,
    needs_revalidation,
)
from app.agent_kernel.memory.server_cards import build_server_memory_card

CANONICAL_MEMORY_KEYS = (
    "profile",
    "access",
    "risks",
    "runbook",
    "recent_changes",
    "human_habits",
)
PATTERN_CANDIDATE_PREFIX = "pattern_candidate:"
AUTOMATION_CANDIDATE_PREFIX = "automation_candidate:"
SKILL_DRAFT_PREFIX = "skill_draft:"
SNAPSHOT_TITLES = {
    "profile": "Canonical Profile",
    "access": "Canonical Access/Network",
    "risks": "Canonical Risks",
    "runbook": "Canonical Runbook",
    "recent_changes": "Canonical Recent Changes",
    "human_habits": "Canonical Human Habits",
}
SNAPSHOT_FALLBACKS = {
    "profile": "Базовый профиль сервера ещё собирается.",
    "access": "Сетевой и access-профиль пока не заполнен.",
    "risks": "Критичные активные риски не зафиксированы.",
    "runbook": "Runbook пополнится после новых успешных операций.",
    "recent_changes": "Значимых недавних изменений не зафиксировано.",
    "human_habits": "Повторяющиеся ручные привычки пока не выделены.",
}


class MemoryStore(Protocol):
    async def get_server_card(self, server_id: int) -> ServerMemoryCard: ...
    async def search_runbooks(self, query: str, *, server_id: int | None = None, group_id: int | None = None) -> list[dict]: ...
    async def build_operational_recipes_prompt(
        self,
        query: str,
        *,
        server_ids: list[int] | None = None,
        group_ids: list[int] | None = None,
        limit: int = 5,
    ) -> str: ...
    async def append_run_summary(self, run_id: int, summary: dict) -> str: ...
    async def upsert_server_fact(self, server_id: int, fact: dict) -> str: ...
    async def record_change(self, server_id: int, change: dict) -> str: ...
    async def record_incident(self, server_id: int, incident: dict) -> str: ...
    async def detect_conflicts(self, server_id: int, new_facts: list[dict]) -> list[dict]: ...
    async def repair_server_memory(self, server_id: int, *, stale_after_days: int = 30, create_notes: bool = True) -> dict: ...
    async def dream_server_memory(self, server_id: int, *, deactivate_noise: bool = True, job_kind: str = "hybrid") -> dict: ...
    async def archive_snapshot(self, server_id: int, snapshot_id: int, *, actor_user_id: int | None = None) -> dict[str, Any]: ...
    async def hard_delete_snapshot(self, server_id: int, snapshot_id: int, *, actor_user_id: int | None = None) -> dict[str, Any]: ...
    async def purge_server_ai_memory(self, server_id: int, *, actor_user_id: int | None = None) -> dict[str, Any]: ...
    async def promote_snapshot_to_manual_knowledge(
        self,
        server_id: int,
        snapshot_id: int,
        *,
        actor_user_id: int,
    ) -> dict[str, Any]: ...
    async def promote_skill_draft_to_skill(
        self,
        server_id: int,
        snapshot_id: int,
        *,
        actor_user_id: int,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class _SnapshotCandidate:
    memory_key: str
    title: str
    content: str
    importance_score: float
    stability_score: float
    confidence: float
    source_kind: str
    source_ref: str = ""
    verified_at: Any | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class _OperationalPattern:
    pattern_kind: str
    display_command: str
    normalized_command: str
    intent: str
    intent_label: str
    commands: tuple[str, ...]
    occurrences: int
    successful_runs: int
    measured_runs: int
    success_rate: float
    actor_kinds: tuple[str, ...]
    source_kinds: tuple[str, ...]
    verification_rate: float = 0.0
    has_verification_step: bool = False
    sample_outputs: tuple[str, ...] = ()
    common_cwds: tuple[str, ...] = ()
    distinct_sessions: int = 0
    last_seen: Any | None = None


class DjangoServerMemoryStore:
    async def get_server_card(self, server_id: int) -> ServerMemoryCard:
        return await sync_to_async(self._get_server_card_sync, thread_sensitive=True)(server_id)

    async def search_runbooks(self, query: str, *, server_id: int | None = None, group_id: int | None = None) -> list[dict]:
        return await sync_to_async(self._search_runbooks_sync, thread_sensitive=True)(query, server_id=server_id, group_id=group_id)

    async def build_operational_recipes_prompt(
        self,
        query: str,
        *,
        server_ids: list[int] | None = None,
        group_ids: list[int] | None = None,
        limit: int = 5,
    ) -> str:
        return await sync_to_async(self._build_operational_recipes_prompt_sync, thread_sensitive=True)(
            query,
            server_ids=server_ids,
            group_ids=group_ids,
            limit=limit,
        )

    async def append_run_summary(self, run_id: int, summary: dict) -> str:
        return await sync_to_async(self._append_run_summary_sync, thread_sensitive=True)(run_id, summary)

    async def upsert_server_fact(self, server_id: int, fact: dict) -> str:
        return await sync_to_async(self._upsert_server_fact_sync, thread_sensitive=True)(server_id, fact)

    async def record_change(self, server_id: int, change: dict) -> str:
        return await sync_to_async(self._record_change_sync, thread_sensitive=True)(server_id, change)

    async def record_incident(self, server_id: int, incident: dict) -> str:
        return await sync_to_async(self._record_incident_sync, thread_sensitive=True)(server_id, incident)

    async def detect_conflicts(self, server_id: int, new_facts: list[dict]) -> list[dict]:
        return await sync_to_async(self._detect_conflicts_sync, thread_sensitive=True)(server_id, new_facts)

    async def repair_server_memory(self, server_id: int, *, stale_after_days: int = 30, create_notes: bool = True) -> dict:
        return await sync_to_async(self._repair_server_memory_sync, thread_sensitive=True)(
            server_id,
            stale_after_days=stale_after_days,
            create_notes=create_notes,
        )

    async def dream_server_memory(self, server_id: int, *, deactivate_noise: bool = True, job_kind: str = "hybrid") -> dict:
        return await sync_to_async(self._dream_server_memory_sync, thread_sensitive=True)(
            server_id,
            deactivate_noise=deactivate_noise,
            job_kind=job_kind,
        )

    async def ingest_event(self, server_id: int, **kwargs: Any) -> str:
        return await sync_to_async(self._ingest_event_sync, thread_sensitive=True)(server_id, **kwargs)

    async def get_memory_overview(self, server_id: int) -> dict[str, Any]:
        return await sync_to_async(self._get_memory_overview_sync, thread_sensitive=True)(server_id)

    async def run_dream_cycle(
        self,
        server_id: int,
        *,
        job_kind: str = "hybrid",
        respect_schedule: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        return await sync_to_async(self._run_dream_cycle_sync, thread_sensitive=True)(
            server_id,
            job_kind=job_kind,
            respect_schedule=respect_schedule,
            force=force,
        )

    async def sync_manual_knowledge_snapshot(self, knowledge_id: int) -> str:
        return await sync_to_async(self._sync_manual_knowledge_snapshot_sync, thread_sensitive=True)(knowledge_id)

    async def archive_manual_knowledge_snapshot(self, knowledge_id: int) -> int:
        return await sync_to_async(self._archive_manual_knowledge_snapshot_sync, thread_sensitive=True)(knowledge_id)

    async def archive_snapshot(self, server_id: int, snapshot_id: int, *, actor_user_id: int | None = None) -> dict[str, Any]:
        return await sync_to_async(self._archive_snapshot_sync, thread_sensitive=True)(
            server_id,
            snapshot_id,
            actor_user_id=actor_user_id,
        )

    async def hard_delete_snapshot(self, server_id: int, snapshot_id: int, *, actor_user_id: int | None = None) -> dict[str, Any]:
        return await sync_to_async(self._hard_delete_snapshot_sync, thread_sensitive=True)(
            server_id,
            snapshot_id,
            actor_user_id=actor_user_id,
        )

    async def purge_server_ai_memory(self, server_id: int, *, actor_user_id: int | None = None) -> dict[str, Any]:
        return await sync_to_async(self._purge_server_ai_memory_sync, thread_sensitive=True)(
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
        return await sync_to_async(self._promote_snapshot_to_manual_knowledge_sync, thread_sensitive=True)(
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
        return await sync_to_async(self._promote_skill_draft_to_skill_sync, thread_sensitive=True)(
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
        from servers.models import (
            AgentRun,
            GlobalServerRules,
            Server,
            ServerAlert,
            ServerGroupKnowledge,
            ServerHealthCheck,
            ServerKnowledge,
            ServerMemoryEpisode,
            ServerMemoryRevalidation,
            ServerMemorySnapshot,
        )

        server = Server.objects.select_related("group", "user").get(pk=server_id)
        global_rules = GlobalServerRules.objects.filter(user=server.user).first()
        group_knowledge = []
        if server.group_id:
            group_knowledge = list(
                ServerGroupKnowledge.objects.filter(group=server.group, is_active=True).order_by("-updated_at")[:6]
            )
        snapshots = list(
            ServerMemorySnapshot.objects.filter(server=server, is_active=True, layer=ServerMemorySnapshot.LAYER_CANONICAL)
            .order_by("memory_key", "-version", "-updated_at")
        )
        episodes = list(
            ServerMemoryEpisode.objects.filter(server=server, is_active=True).order_by("-last_event_at", "-updated_at")[:8]
        )
        revalidations = list(
            ServerMemoryRevalidation.objects.filter(server=server, status=ServerMemoryRevalidation.STATUS_OPEN).order_by("-updated_at")[:6]
        )
        latest_health = ServerHealthCheck.objects.filter(server=server).order_by("-checked_at").first()
        active_alerts = list(ServerAlert.objects.filter(server=server, is_resolved=False).order_by("-created_at")[:5])
        recent_runs = list(AgentRun.objects.filter(server=server).select_related("agent").order_by("-started_at")[:4])
        legacy_knowledge = list(ServerKnowledge.objects.filter(server=server, is_active=True).order_by("-updated_at")[:8])
        return build_server_memory_card(
            server,
            global_rules=global_rules,
            group_knowledge=group_knowledge,
            snapshots=snapshots,
            episodes=episodes,
            revalidations=revalidations,
            latest_health=latest_health,
            active_alerts=active_alerts,
            recent_runs=recent_runs,
            legacy_knowledge=legacy_knowledge,
        )

    def _get_server_cards_batch_sync(self, server_ids: list[int]) -> list[ServerMemoryCard]:
        """Load multiple server cards with batched queries (P2-7).

        Instead of N separate _get_server_card_sync calls (each doing ~10
        queries), this prefetches all data in one pass, then partitions it
        by server_id for card building.
        """
        if not server_ids:
            return []
        from servers.models import (
            AgentRun,
            GlobalServerRules,
            Server,
            ServerAlert,
            ServerGroupKnowledge,
            ServerHealthCheck,
            ServerKnowledge,
            ServerMemoryEpisode,
            ServerMemoryRevalidation,
            ServerMemorySnapshot,
        )

        servers = {s.id: s for s in Server.objects.select_related("group", "user").filter(pk__in=server_ids)}
        if not servers:
            return []

        # Shared lookups
        user_ids = {s.user_id for s in servers.values() if s.user_id}
        group_ids = {s.group_id for s in servers.values() if s.group_id}

        # One query per model, filtered on all server_ids at once
        global_rules_by_user = {}
        for gr in GlobalServerRules.objects.filter(user_id__in=user_ids):
            global_rules_by_user[gr.user_id] = gr

        group_knowledge_by_group: dict[int, list] = {}
        if group_ids:
            for gk in ServerGroupKnowledge.objects.filter(group_id__in=group_ids, is_active=True).order_by("-updated_at"):
                group_knowledge_by_group.setdefault(gk.group_id, []).append(gk)

        snapshots_by_server: dict[int, list] = {}
        for s in ServerMemorySnapshot.objects.filter(
            server_id__in=server_ids, is_active=True, layer=ServerMemorySnapshot.LAYER_CANONICAL
        ).order_by("memory_key", "-version", "-updated_at"):
            snapshots_by_server.setdefault(s.server_id, []).append(s)

        episodes_by_server: dict[int, list] = {}
        for e in ServerMemoryEpisode.objects.filter(
            server_id__in=server_ids, is_active=True
        ).order_by("-last_event_at", "-updated_at")[:len(server_ids) * 8]:
            episodes_by_server.setdefault(e.server_id, []).append(e)

        revalidations_by_server: dict[int, list] = {}
        for r in ServerMemoryRevalidation.objects.filter(
            server_id__in=server_ids, status=ServerMemoryRevalidation.STATUS_OPEN
        ).order_by("-updated_at")[:len(server_ids) * 6]:
            revalidations_by_server.setdefault(r.server_id, []).append(r)

        latest_health_by_server: dict[int, ServerHealthCheck | None] = {}
        for hc in ServerHealthCheck.objects.filter(server_id__in=server_ids).order_by("server_id", "-checked_at"):
            if hc.server_id not in latest_health_by_server:
                latest_health_by_server[hc.server_id] = hc

        alerts_by_server: dict[int, list] = {}
        for a in ServerAlert.objects.filter(server_id__in=server_ids, is_resolved=False).order_by("-created_at"):
            alerts_by_server.setdefault(a.server_id, []).append(a)

        runs_by_server: dict[int, list] = {}
        for r in AgentRun.objects.filter(server_id__in=server_ids).select_related("agent").order_by("-started_at")[:len(server_ids) * 4]:
            runs_by_server.setdefault(r.server_id, []).append(r)

        knowledge_by_server: dict[int, list] = {}
        for k in ServerKnowledge.objects.filter(server_id__in=server_ids, is_active=True).order_by("-updated_at"):
            knowledge_by_server.setdefault(k.server_id, []).append(k)

        # Build cards
        cards = []
        for sid in server_ids:
            server = servers.get(sid)
            if not server:
                continue
            cards.append(
                build_server_memory_card(
                    server,
                    global_rules=global_rules_by_user.get(server.user_id),
                    group_knowledge=group_knowledge_by_group.get(server.group_id, [])[:6],
                    snapshots=snapshots_by_server.get(sid, []),
                    episodes=episodes_by_server.get(sid, [])[:8],
                    revalidations=revalidations_by_server.get(sid, [])[:6],
                    latest_health=latest_health_by_server.get(sid),
                    active_alerts=alerts_by_server.get(sid, [])[:5],
                    recent_runs=runs_by_server.get(sid, [])[:4],
                    legacy_knowledge=knowledge_by_server.get(sid, [])[:8],
                )
            )
        return cards

    def _search_runbooks_sync(self, query: str, *, server_id: int | None = None, group_id: int | None = None) -> list[dict]:
        from django.db.models import Q

        from servers.models import ServerGroupKnowledge, ServerKnowledge, ServerMemorySnapshot

        query = str(query or "").strip()
        if not query:
            return []
        query_lower = query.lower()
        items: list[dict] = []
        filters = Q(content__icontains=query) | Q(title__icontains=query)
        if server_id is not None:
            for item in (
                ServerMemorySnapshot.objects.filter(
                    filters,
                    server_id=server_id,
                    is_active=True,
                )
                .order_by("-updated_at")[:12]
            ):
                memory_key = str(item.memory_key or "")
                metadata = dict(item.metadata or {})
                include_manual_operational = (
                    memory_key.startswith(("manual_note:", "knowledge_note:"))
                    and (
                        str(metadata.get("category") or "").strip().lower() in {"solutions", "services"}
                        or str(item.title or "").lower().startswith("operational skill:")
                        or "workflow:" in str(item.content or "").lower()
                        or "связанный skill:" in str(item.content or "").lower()
                    )
                )
                if (
                    memory_key not in {"runbook", "human_habits"}
                    and not memory_key.startswith((PATTERN_CANDIDATE_PREFIX, AUTOMATION_CANDIDATE_PREFIX, SKILL_DRAFT_PREFIX))
                    and not include_manual_operational
                ):
                    continue
                score = self._runbook_match_score(
                    query_lower,
                    title=str(item.title or ""),
                    content=str(item.content or ""),
                    metadata=metadata,
                )
                items.append(
                    {
                        "scope": "server",
                        "title": item.title,
                        "content": compact_text(item.content, limit=240),
                        "category": metadata.get("category") or item.memory_key,
                        "memory_key": item.memory_key,
                        "metadata": metadata,
                        "confidence": float(item.confidence or 0.0),
                        "source_kind": item.source_kind,
                        "source_ref": item.source_ref,
                        "_score": score,
                        "_updated_at": getattr(item, "updated_at", None),
                    }
                )
            if not items:
                for item in ServerKnowledge.objects.filter(filters, server_id=server_id, is_active=True).order_by("-updated_at")[:6]:
                    score = self._runbook_match_score(
                        query_lower,
                        title=str(item.title or ""),
                        content=str(item.content or ""),
                        metadata={"category": item.category},
                    )
                    items.append(
                        {
                            "scope": "server",
                            "title": item.title,
                            "content": compact_text(item.content, limit=240),
                            "category": item.category,
                            "memory_key": f"knowledge:{item.id}",
                            "metadata": {"category": item.category},
                            "confidence": float(item.confidence or 0.0),
                            "source_kind": "manual_knowledge",
                            "source_ref": f"knowledge:{item.id}",
                            "_score": score,
                            "_updated_at": getattr(item, "updated_at", None),
                        }
                    )
        if group_id is not None:
            for item in ServerGroupKnowledge.objects.filter(filters, group_id=group_id, is_active=True).order_by("-updated_at")[:6]:
                score = self._runbook_match_score(
                    query_lower,
                    title=str(item.title or ""),
                    content=str(item.content or ""),
                    metadata={"category": item.category},
                )
                items.append(
                    {
                        "scope": "group",
                        "title": item.title,
                        "content": compact_text(item.content, limit=240),
                        "category": item.category,
                        "memory_key": f"group_knowledge:{item.id}",
                        "metadata": {"category": item.category},
                        "confidence": float(item.confidence or 0.0),
                        "source_kind": "group_knowledge",
                        "source_ref": f"group_knowledge:{item.id}",
                        "_score": score,
                        "_updated_at": getattr(item, "updated_at", None),
                    }
                )
        deduped: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        for item in sorted(
            items,
            key=lambda entry: (
                float(entry.get("_score") or 0.0),
                entry.get("_updated_at") or timezone.now(),
            ),
            reverse=True,
        ):
            key = (
                str(item.get("scope") or ""),
                str(item.get("title") or ""),
                str(item.get("content") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            item.pop("_score", None)
            item.pop("_updated_at", None)
            deduped.append(item)
        return deduped[:8]

    def _build_operational_recipes_prompt_sync(
        self,
        query: str,
        *,
        server_ids: list[int] | None = None,
        group_ids: list[int] | None = None,
        limit: int = 5,
    ) -> str:
        query_terms = self._extract_runbook_query_terms(query)
        if not query_terms:
            return "- Нет релевантных operational recipes."

        items: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()

        for server_id in list(server_ids or [])[:3]:
            for term in query_terms:
                for item in self._search_runbooks_sync(term, server_id=server_id):
                    key = (str(item.get("scope") or ""), str(item.get("title") or ""), str(item.get("content") or ""))
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append(item)

        for group_id in list(group_ids or [])[:3]:
            for term in query_terms:
                for item in self._search_runbooks_sync(term, group_id=group_id):
                    key = (str(item.get("scope") or ""), str(item.get("title") or ""), str(item.get("content") or ""))
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append(item)

        if not items:
            return "- Нет релевантных operational recipes."

        lines = []
        for item in items[: max(1, min(int(limit), 8))]:
            lines.append(self._format_operational_recipe_prompt_item(item))
        return "\n".join(lines)

    def _format_operational_recipe_prompt_item(self, item: dict[str, Any]) -> str:
        scope = str(item.get("scope") or "server")
        category = str(item.get("category") or "runbook")
        title = compact_text(str(item.get("title") or ""), limit=120)
        content = compact_text(str(item.get("content") or ""), limit=220)
        metadata = dict(item.get("metadata") or {})
        detail_parts: list[str] = [f"[{scope}/{category}] {title}: {content}"]
        for label, key, limit in (
            ("Use", "when_to_use", 140),
            ("Recipe", "playbook_summary", 160),
            ("Verify", "verification", 140),
            ("Rollback", "rollback_hint", 140),
            ("Attach", "runtime_attachment", 140),
        ):
            value = compact_text(str(metadata.get(key) or ""), limit=limit)
            if value:
                detail_parts.append(f"{label}={value}")
        risk_level = compact_text(str(metadata.get("risk_level") or ""), limit=40)
        if risk_level:
            detail_parts.append(f"Risk={risk_level}")
        confidence = item.get("confidence")
        if isinstance(confidence, (int, float)) and confidence > 0:
            detail_parts.append(f"Confidence={int(float(confidence) * 100)}%")
        return "- " + " | ".join(detail_parts[:7])

    @staticmethod
    def _extract_runbook_query_terms(query: str) -> list[str]:
        normalized = compact_text(str(query or "").replace("\n", " "), limit=240).strip()
        if not normalized:
            return []
        terms = unique_preserving_order([normalized], limit=1)
        token_candidates = re.findall(r"[A-Za-zА-Яа-яЁё0-9_./:-]{3,}", normalized.lower())
        stop_words = {
            "the", "and", "for", "with", "that", "from", "into", "this", "need", "after",
            "что", "для", "после", "перед", "если", "или", "при", "это", "как", "без",
            "server", "agent", "роль", "server_id", "group_id",
        }
        for token in token_candidates:
            if token in stop_words:
                continue
            terms.append(token)
            if len(terms) >= 8:
                break
        return unique_preserving_order(terms, limit=8)

    @staticmethod
    def _runbook_match_score(query_lower: str, *, title: str, content: str, metadata: dict[str, Any] | None = None) -> float:
        metadata = metadata or {}
        haystacks = [
            str(title or "").lower(),
            str(content or "").lower(),
            str(metadata.get("intent") or "").lower(),
            str(metadata.get("intent_label") or "").lower(),
            str(metadata.get("display_command") or "").lower(),
            " ".join(str(item).lower() for item in (metadata.get("commands") or []) if str(item).strip()),
        ]
        score = 0.0
        if haystacks[0] and query_lower in haystacks[0]:
            score += 3.0
        if haystacks[1] and query_lower in haystacks[1]:
            score += 2.0
        if any(query_lower in haystack for haystack in haystacks[2:]):
            score += 1.5
        if str(metadata.get("category") or "").strip().lower() in {"solutions", "services"}:
            score += 0.4
        return score

    def _append_run_summary_sync(self, run_id: int, summary: dict) -> str:
        from servers.models import AgentRun

        run = AgentRun.objects.select_related("server", "user", "agent").filter(pk=run_id).first()
        if not run or not run.server_id:
            return ""
        policy = self._get_or_create_policy_sync(user_id=run.user_id)
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
        event_id = self._ingest_event_sync(
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
                "tool_calls": summary.get("tool_calls") or [],
                "verification_summary": summary.get("verification_summary") or "",
            },
            importance_hint=0.92 if status in {"failed", "stopped"} else 0.8,
            actor_user_id=run.user_id,
            force_compact=True,
        )
        for fact in summary.get("facts") or []:
            self._upsert_server_fact_sync(run.server_id, fact, source_ref=source_ref, session_id=source_ref)
        for change in summary.get("changes") or []:
            self._record_change_sync(run.server_id, change, source_ref=source_ref, session_id=source_ref)
        for incident in summary.get("incidents") or []:
            self._record_incident_sync(run.server_id, incident, source_ref=source_ref, session_id=source_ref)
        from servers.tasks import run_dream_cycle_task
        run_dream_cycle_task.delay(run.server_id, job_kind="nearline")
        return event_id

    def _upsert_server_fact_sync(
        self,
        server_id: int,
        fact: dict,
        *,
        source_ref: str = "",
        session_id: str = "",
    ) -> str:
        title = (fact.get("title") or "Ops fact").strip()[:200]
        content = compact_text(fact.get("content") or "", limit=2400)
        memory_key = self._guess_memory_key(title=title, category=fact.get("category"), content=content)
        raw_category = str(fact.get("category") or "").strip()
        new_fact_variants = [{"title": title, "category": memory_key, "content": content}]
        if raw_category and raw_category.lower() != memory_key.lower():
            new_fact_variants.append({"title": title, "category": raw_category, "content": content})
        conflicts = self._detect_conflicts_sync(
            server_id,
            new_fact_variants,
        )
        if conflicts:
            # P2-5: use resolve_winning_fact to decide disposition
            from app.agent_kernel.memory.repair import resolve_winning_fact
            from servers.models import ServerMemorySnapshot

            conflict_info = conflicts[0]
            # Try to find metadata about the existing snapshot
            existing_snapshot = (
                ServerMemorySnapshot.objects
                .filter(server_id=server_id, title=conflict_info.get("title", ""), is_active=True)
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
                # Existing fact is still more trustworthy — skip ingestion
                logger.info("fact conflict: existing wins for '{}' on server {}", title, server_id)
                return ""
            if verdict == "revalidate":
                self._ensure_revalidation_sync(
                    server_id,
                    memory_key=memory_key,
                    title=title,
                    reason="Новый факт противоречит активной памяти сервера (требуется ручная проверка).",
                    payload=conflict_info,
                )
            # verdict == "incoming" → proceed with ingestion (fact wins)
        return self._ingest_event_sync(
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

    def _record_change_sync(
        self,
        server_id: int,
        change: dict,
        *,
        source_ref: str = "",
        session_id: str = "",
    ) -> str:
        title = change.get("title") or "Изменение состояния сервера"
        content = compact_text(change.get("content") or "", limit=1800)
        return self._ingest_event_sync(
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

    def _record_incident_sync(
        self,
        server_id: int,
        incident: dict,
        *,
        source_ref: str = "",
        session_id: str = "",
    ) -> str:
        title = incident.get("title") or "Инцидент"
        content = compact_text(incident.get("content") or "", limit=1800)
        event_id = self._ingest_event_sync(
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
        self._ensure_revalidation_sync(
            server_id,
            memory_key="risks",
            title=title[:200],
            reason="Новый инцидент требует перепроверки и учёта в risk profile.",
            payload={"content": content},
        )
        return event_id

    def _detect_conflicts_sync(self, server_id: int, new_facts: list[dict]) -> list[dict]:
        from servers.models import ServerMemorySnapshot

        existing = list(
            ServerMemorySnapshot.objects.filter(server_id=server_id, is_active=True).values("title", "memory_key", "content", "metadata")
        )
        normalized_existing = []
        for item in existing:
            memory_key = str(item.get("memory_key") or "")
            metadata = item.get("metadata") or {}
            category = str(metadata.get("category") or memory_key or "").strip()
            if memory_key.startswith(("manual_note:", "knowledge_note:")):
                category = category or self._guess_memory_key(
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

    def _repair_server_memory_sync(self, server_id: int, *, stale_after_days: int = 30, create_notes: bool = True) -> dict:
        from servers.models import ServerMemoryRevalidation, ServerMemorySnapshot

        now = timezone.now()
        updated = 0
        notes = 0
        for snapshot in ServerMemorySnapshot.objects.filter(server_id=server_id, is_active=True).order_by("memory_key", "-updated_at"):
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

        archived_records = self._archive_old_events_sync(server_id, now=now) + self._archive_old_episodes_sync(server_id, now=now)
        return {
            "server_id": server_id,
            "updated_records": updated,
            "created_notes": notes,
            "archived_records": archived_records,
        }

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
        from servers.models import Server, ServerMemoryEvent

        structured_payload = structured_payload or {}
        server = Server.objects.filter(pk=server_id).select_related("user").first()
        if server is None:
            return ""

        policy = self._get_or_create_policy_sync(user_id=server.user_id)
        if not bool(getattr(policy, "is_enabled", True)):
            return ""
        redacted_text, redacted_payload, redaction_report, redaction_hashes = redact_for_storage(
            raw_text=raw_text,
            payload=structured_payload,
        )
        redacted_text = compact_text(redacted_text, limit=8000 if policy.allow_sensitive_raw else 4000)

        event = ServerMemoryEvent.objects.create(
            server_id=server_id,
            actor_user_id=actor_user_id,
            source_kind=source_kind,
            actor_kind=actor_kind,
            source_ref=source_ref[:255],
            session_id=session_id[:120],
            event_type=event_type[:80],
            raw_text_redacted=redacted_text,
            structured_payload=redacted_payload,
            importance_hint=max(0.0, min(float(importance_hint or 0.5), 1.0)),
            redaction_report=redaction_report,
            redaction_hashes=redaction_hashes,
        )
        self._maybe_compact_event_group_sync(event, threshold=max(int(policy.nearline_event_threshold or 6), 2), force=force_compact)
        return str(event.pk)

    def _maybe_compact_event_group_sync(self, event, *, threshold: int, force: bool) -> None:
        from servers.models import ServerMemoryEvent

        filters = self._event_group_filters(event)
        count = ServerMemoryEvent.objects.filter(**filters, is_archived=False).count()
        if force or count >= threshold or event.event_type in {
            "session_closed",
            "rdp_session_closed",
            "run_completed",
            "run_failed",
            "run_stopped",
        }:
            self._compact_group_sync(
                server_id=event.server_id,
                source_kind=event.source_kind,
                source_ref=(event.source_ref or ""),
                session_id=(event.session_id or ""),
            )

    def _event_group_filters(self, event) -> dict[str, Any]:
        filters = {"server_id": event.server_id, "source_kind": event.source_kind}
        if event.session_id:
            filters["session_id"] = event.session_id
        elif event.source_ref:
            filters["source_ref"] = event.source_ref
        else:
            filters["created_at__gte"] = timezone.now() - timedelta(hours=6)
        return filters

    def _compact_open_groups_sync(self, server_id: int, *, force: bool = False) -> int:
        from servers.models import ServerMemoryEvent

        groups: set[tuple[str, str, str]] = set()
        for event in ServerMemoryEvent.objects.filter(server_id=server_id, is_archived=False).order_by("-created_at")[:80]:
            groups.add((event.source_kind, event.source_ref or "", event.session_id or ""))
        compacted = 0
        for source_kind, source_ref, session_id in groups:
            compacted += self._compact_group_sync(
                server_id=server_id,
                source_kind=source_kind,
                source_ref=source_ref,
                session_id=session_id,
                force=force,
            )
        return compacted

    def _compact_group_sync(
        self,
        *,
        server_id: int,
        source_kind: str,
        source_ref: str = "",
        session_id: str = "",
        force: bool = False,
    ) -> int:
        from servers.models import ServerMemoryEpisode, ServerMemoryEvent

        filters = {"server_id": server_id, "source_kind": source_kind, "is_archived": False}
        if session_id:
            filters["session_id"] = session_id
        elif source_ref:
            filters["source_ref"] = source_ref
        else:
            filters["created_at__gte"] = timezone.now() - timedelta(hours=6)

        with transaction.atomic():
            events = list(
                ServerMemoryEvent.objects.select_for_update()
                .filter(**filters)
                .order_by("created_at", "id")[:120]
            )
            if not events:
                return 0
            if len(events) < 2 and not force:
                return 0

            episode_kind = self._episode_kind_for_source(source_kind, events)
            summary_lines = self._episode_summary_lines(events)
            commands = self._extract_commands(events)[:12]
            if episode_kind in {"terminal_session", "rdp_session"} and not summary_lines and not commands:
                return 0
            title = self._episode_title(source_kind, episode_kind, events)
            summary = self._build_episode_summary(events, summary_lines=summary_lines)
            metadata = {
                "source_kind": source_kind,
                "event_types": list(dict.fromkeys(event.event_type for event in events))[:12],
                "commands": commands,
            }
            episode = (
                ServerMemoryEpisode.objects.select_for_update()
                .filter(
                    server_id=server_id,
                    source_kind=source_kind,
                    source_ref=source_ref,
                    session_id=session_id,
                    episode_kind=episode_kind,
                    is_active=True,
                )
                .order_by("-updated_at")
                .first()
            )
            if episode is None:
                ServerMemoryEpisode.objects.create(
                    server_id=server_id,
                    episode_kind=episode_kind,
                    source_kind=source_kind,
                    source_ref=source_ref,
                    session_id=session_id,
                    title=title,
                    summary=summary,
                    event_count=len(events),
                    importance_score=max(float(event.importance_hint or 0.5) for event in events),
                    confidence=min(0.95, 0.55 + min(len(events), 12) * 0.03),
                    metadata=metadata,
                    first_event_at=events[0].created_at,
                    last_event_at=events[-1].created_at,
                )
            else:
                episode.title = title
                episode.summary = summary
                episode.event_count = len(events)
                episode.importance_score = max(float(event.importance_hint or 0.5) for event in events)
                episode.confidence = min(0.95, 0.55 + min(len(events), 12) * 0.03)
                episode.metadata = metadata
                episode.first_event_at = events[0].created_at
                episode.last_event_at = events[-1].created_at
                episode.is_active = True
                episode.save(
                    update_fields=[
                        "title",
                        "summary",
                        "event_count",
                        "importance_score",
                        "confidence",
                        "metadata",
                        "first_event_at",
                        "last_event_at",
                        "is_active",
                        "updated_at",
                    ]
                )
        return 1

    def _episode_kind_for_source(self, source_kind: str, events: list[Any]) -> str:
        if source_kind == "terminal":
            return "terminal_session"
        if source_kind == "rdp":
            return "rdp_session"
        if source_kind in {"agent_run", "agent_event"}:
            text_blob = "\n".join((event.raw_text_redacted or "") for event in events).lower()
            if any(term in text_blob for term in ("deploy", "rollout", "rollback", "release")):
                return "deploy_operation"
            if any(event.event_type == "incident" for event in events):
                return "incident"
            return "agent_investigation"
        if source_kind in {"monitoring", "watcher"}:
            return "incident"
        if source_kind == "pipeline":
            return "pipeline_operation"
        return "misc"

    def _episode_title(self, source_kind: str, episode_kind: str, events: list[Any]) -> str:
        first = events[0]
        if episode_kind == "terminal_session":
            return f"Human terminal session ({first.created_at:%Y-%m-%d %H:%M})"
        if episode_kind == "rdp_session":
            return f"RDP session ({first.created_at:%Y-%m-%d %H:%M})"
        if episode_kind == "deploy_operation":
            return f"Deploy operation ({first.created_at:%Y-%m-%d %H:%M})"
        if episode_kind == "incident":
            return f"Incident window ({first.created_at:%Y-%m-%d %H:%M})"
        if episode_kind == "agent_investigation":
            return f"Agent investigation ({first.created_at:%Y-%m-%d %H:%M})"
        if source_kind == "pipeline":
            return f"Pipeline server activity ({first.created_at:%Y-%m-%d %H:%M})"
        return f"{source_kind} activity ({first.created_at:%Y-%m-%d %H:%M})"

    @staticmethod
    def _is_transport_event_type(event_type: str) -> bool:
        return event_type in {"session_opened", "session_closed", "rdp_session_opened", "rdp_session_closed"}

    @staticmethod
    def _looks_like_access_signal(line: str) -> bool:
        normalized = compact_text(str(line or ""), limit=220).lower()
        if not normalized:
            return False
        return (
            any(
                term in normalized
                for term in (
                    "vpn",
                    "bastion",
                    "jump host",
                    "gateway",
                    "host:",
                    "user=",
                    "published port",
                    "published ports",
                    "publish",
                    "доступ",
                    "listen ",
                    "порт",
                )
            )
            or bool(re.search(r"\bssh:\s*\d{1,3}(?:\.\d{1,3}){3}:\d+\b", normalized))
            or bool(re.search(r"\b\d+(?::\d+)?->\d+/(?:tcp|udp)\b", normalized))
            or bool(re.search(r"\b\d+\.\d+\.\d+\.\d+:\d+\b", normalized))
        )

    @classmethod
    def _is_command_like_line(cls, line: str) -> bool:
        normalized = compact_text(str(line or ""), limit=220).lower().strip()
        if not normalized:
            return False
        if normalized.startswith(("command used:", "команда:", "workflow:", "$ ", "`")):
            return True
        return any(
            normalized.startswith(prefix)
            for prefix in (
                "docker ",
                "systemctl ",
                "journalctl ",
                "ss ",
                "curl ",
                "mkdir ",
                "ps ",
                "top ",
                "uptime",
                "df ",
                "free ",
                "ip ",
                "cat ",
                "grep ",
                "find ",
                "tail ",
                "less ",
                "sudo ",
            )
        )

    @classmethod
    def _is_runbook_safe_line(cls, line: str) -> bool:
        normalized = compact_text(str(line or ""), limit=220)
        if not normalized:
            return False
        if cls._is_destructive_command(normalized):
            return False
        return not cls._looks_mutating_command(normalized)

    @classmethod
    def _is_session_noise_line(cls, line: str) -> bool:
        normalized = compact_text(str(line or ""), limit=220).lower()
        if not normalized:
            return True
        if normalized.startswith(("session_opened:", "session_closed:", "rdp_session_opened:", "rdp_session_closed:")):
            return True
        if normalized in {
            "ssh terminal session opened",
            "ssh terminal session closed",
            "rdp terminal session opened",
            "rdp terminal session closed",
        }:
            return True
        return bool(any(marker in normalized for marker in ("connection_id", "user_id")) and any(term in normalized for term in ("session_opened", "session_closed", "session opened", "session closed")))

    @classmethod
    def _filter_memory_lines(cls, value: Any, *, limit: int = 6) -> list[str]:
        normalized = cls._normalize_snapshot_lines(value, limit=max(limit * 2, 8))
        meaningful = [line for line in normalized if not cls._is_session_noise_line(line)]
        return unique_preserving_order(meaningful, limit=limit)

    @classmethod
    def _sanitize_canonical_content(cls, memory_key: str, content: str, *, fallback: str) -> str:
        lines = cls._normalize_snapshot_lines(content, limit=8)
        if memory_key == "access":
            lines = [line for line in lines if cls._looks_like_access_signal(line) and not cls._is_command_like_line(line)]
        elif memory_key == "human_habits":
            lines = [line for line in lines if line != "Повторяющиеся ручные привычки пока не выделены."]
        if not lines:
            return cls._render_snapshot_lines([], fallback=fallback)
        return cls._render_snapshot_lines(lines, fallback=fallback)

    @classmethod
    def _episode_summary_lines(cls, events: list[Any]) -> list[str]:
        lines: list[str] = []
        for event in events:
            event_type = str(getattr(event, "event_type", "") or "")
            if cls._is_transport_event_type(event_type):
                continue
            if event.raw_text_redacted:
                lines.extend(extract_signal_lines(event.raw_text_redacted, max_items=2))
            preview = payload_preview(event.structured_payload, limit=180)
            if preview:
                lines.append(f"{event_type}: {preview}")
        return cls._filter_memory_lines(lines, limit=10)

    def _build_episode_summary(self, events: list[Any], *, summary_lines: list[str] | None = None) -> str:
        normalized = summary_lines if summary_lines is not None else self._episode_summary_lines(events)
        if not normalized:
            normalized = ["Содержательная выжимка пока недоступна."]
        return "\n".join(f"- {line}" for line in normalized[:10])

    @staticmethod
    def _extract_commands(events: list[Any]) -> list[str]:
        commands: list[str] = []
        for event in events:
            command = str((event.structured_payload or {}).get("command") or "").strip()
            if command:
                commands.append(compact_text(command, limit=140))
        return unique_preserving_order(commands, limit=16)

    def _dream_server_memory_sync(self, server_id: int, *, deactivate_noise: bool = True, job_kind: str = "hybrid") -> dict:
        from servers.models import (
            Server,
            ServerAlert,
            ServerHealthCheck,
            ServerMemoryEpisode,
            ServerMemoryEvent,
            ServerMemoryRevalidation,
            ServerMemorySnapshot,
        )

        server = Server.objects.filter(pk=server_id).first()
        if server is None:
            return {"server_id": server_id, "updated_notes": 0, "created_versions": 0, "scanned_records": 0}

        self._compact_open_groups_sync(server_id, force=True)

        episodes = list(ServerMemoryEpisode.objects.filter(server_id=server_id, is_active=True).order_by("-last_event_at", "-updated_at")[:18])
        snapshots = list(
            ServerMemorySnapshot.objects.filter(server_id=server_id, is_active=True, layer=ServerMemorySnapshot.LAYER_CANONICAL)
            .order_by("memory_key", "-version", "-updated_at")
        )
        latest_health = ServerHealthCheck.objects.filter(server_id=server_id).order_by("-checked_at").first()
        active_alerts = list(ServerAlert.objects.filter(server_id=server_id, is_resolved=False).order_by("-created_at")[:8])
        revalidation_items = list(
            ServerMemoryRevalidation.objects.filter(server_id=server_id, status=ServerMemoryRevalidation.STATUS_OPEN).order_by("-updated_at")[:6]
        )
        recent_events = list(
            ServerMemoryEvent.objects.filter(server_id=server_id, is_archived=False)
            .order_by("-created_at")[:24]
        )
        policy = self._get_or_create_policy_sync(user_id=server.user_id)
        patterns = self._derive_operational_patterns(server.id)

        candidates = self._build_snapshot_candidates(
            server=server,
            episodes=episodes,
            snapshots=snapshots,
            recent_events=recent_events,
            latest_health=latest_health,
            active_alerts=active_alerts,
            revalidation_items=revalidation_items,
            allow_human_habits=policy.human_habits_capture_enabled,
            patterns=patterns,
        )

        llm_sections: dict[str, str] = {}
        if (
            job_kind in {"nightly", "hybrid"}
            and policy.dream_mode in {policy.DREAM_HYBRID, policy.DREAM_NIGHTLY_LLM}
            and self._should_distill_with_llm(candidates, snapshots)
        ):
            llm_sections = self._distill_with_llm_sync(server=server, candidates=candidates, model_alias=policy.nightly_model_alias)

        updated = 0
        created_versions = 0
        for candidate in candidates:
            raw_content = llm_sections.get(candidate.memory_key) or candidate.content
            safe_content = self._sanitize_canonical_content(
                candidate.memory_key,
                raw_content,
                fallback=SNAPSHOT_FALLBACKS.get(candidate.memory_key, candidate.content),
            )
            snapshot, created = self._upsert_snapshot_sync(
                server_id=server_id,
                memory_key=candidate.memory_key,
                title=candidate.title,
                content=safe_content,
                source_kind=candidate.source_kind,
                source_ref=candidate.source_ref,
                importance_score=candidate.importance_score,
                stability_score=candidate.stability_score,
                confidence=candidate.confidence,
                verified_at=candidate.verified_at,
                metadata=candidate.metadata or {},
            )
            updated += 1
            if created:
                created_versions += 1

        pattern_enhancements: dict[str, dict[str, Any]] = {}
        if job_kind in {"nightly", "hybrid"} and policy.dream_mode in {
            policy.DREAM_HYBRID,
            policy.DREAM_NIGHTLY_LLM,
        }:
            pattern_enhancements = self._llm_enhance_patterns_sync(
                server=server,
                patterns=patterns,
                model_alias=policy.nightly_model_alias,
            )

        candidate_result = self._promote_pattern_candidates_sync(
            server_id=server_id,
            patterns=patterns,
            snapshots=snapshots,
            enhancements=pattern_enhancements,
        )

        if deactivate_noise:
            self._archive_old_events_sync(server_id)
        return {
            "server_id": server_id,
            "updated_notes": updated,
            "created_versions": created_versions,
            "scanned_records": len(episodes),
            "pattern_candidates": candidate_result["pattern_candidates"],
            "automation_candidates": candidate_result["automation_candidates"],
            "skill_drafts": candidate_result["skill_drafts"],
        }

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
        snapshot_map = {item.memory_key: item for item in snapshots if item.memory_key not in {"manual_notes"}}
        profile_points: list[str] = []
        access_points: list[str] = []
        risk_points: list[str] = []
        runbook_points: list[str] = []
        change_points: list[str] = []
        manual_points: dict[str, list[str]] = {key: [] for key in CANONICAL_MEMORY_KEYS}

        if server.notes:
            profile_points.append(server.notes)
        if server.corporate_context:
            access_points.append(server.corporate_context)
        network_summary = server.get_network_context_summary()
        if network_summary and network_summary != "Стандартная сеть":
            access_points.append(network_summary)
        access_points.append(f"Host: {server.host}:{server.port} user={server.username}")
        profile_points.append(f"Server type: {server.server_type}")
        recent_signal_points = self._derive_recent_event_points(recent_events)
        access_points.extend(recent_signal_points["access"][:4])
        change_points.extend(recent_signal_points["recent_changes"][:4])

        if latest_health:
            profile_points.append(
                f"Health: status={latest_health.status}, cpu={latest_health.cpu_percent}, mem={latest_health.memory_percent}, disk={latest_health.disk_percent}"
            )

        for snapshot in snapshots:
            memory_key = str(getattr(snapshot, "memory_key", "") or "")
            if not memory_key.startswith(("manual_note:", "knowledge_note:")):
                continue
            target_key = self._canonical_key_for_snapshot(snapshot)
            lines = self._filter_memory_lines(getattr(snapshot, "content", "") or "", limit=6)
            if not lines:
                lines = [compact_text(str(getattr(snapshot, "content", "") or ""), limit=180)]
            manual_points[target_key].extend(lines[:4])

        profile_points.extend(manual_points["profile"][:4])
        access_points.extend(manual_points["access"][:4])
        risk_points.extend(manual_points["risks"][:4])
        runbook_points.extend(manual_points["runbook"][:4])
        change_points.extend(manual_points["recent_changes"][:4])

        for alert in active_alerts:
            risk_points.append(f"[{alert.severity}] {alert.title}: {compact_text(alert.message or '', limit=180)}")
        for item in revalidation_items:
            risk_points.append(f"Требует перепроверки: {item.title} — {compact_text(item.reason, limit=180)}")

        for item in episodes:
            lines = self._filter_memory_lines(str(item.summary or ""), limit=4)
            if not lines:
                continue
            if item.episode_kind in {"terminal_session", "rdp_session"}:
                access_points.extend([line for line in lines if self._looks_like_access_signal(line)][:2])
                runbook_points.extend([line for line in lines if self._is_runbook_safe_line(line)][:2])
            elif item.episode_kind == "deploy_operation":
                change_points.extend(lines[:3])
                runbook_points.extend([line for line in lines if self._is_runbook_safe_line(line)][:2])
            elif item.episode_kind == "incident":
                risk_points.extend(lines[:3])
            elif item.episode_kind == "agent_investigation":
                profile_points.extend(lines[:2])
                runbook_points.extend([line for line in lines if self._is_runbook_safe_line(line)][:2])
            elif item.episode_kind == "pipeline_operation":
                change_points.extend(lines[:3])

        patterns = patterns if patterns is not None else self._derive_operational_patterns(server.id)
        runbook_pattern_points = self._derive_runbook_patterns(patterns)
        if runbook_pattern_points:
            runbook_points.extend(runbook_pattern_points[:4])
        human_habits_points = self._derive_human_habits(server.id, patterns=patterns) if allow_human_habits else []

        return [
            _SnapshotCandidate(
                memory_key="profile",
                title=SNAPSHOT_TITLES["profile"],
                content=self._render_snapshot_lines(profile_points, fallback="Базовый профиль сервера ещё собирается."),
                importance_score=0.92,
                stability_score=0.86,
                confidence=0.84,
                source_kind="dream",
                verified_at=getattr(latest_health, "checked_at", None),
                metadata={"source_snapshot_id": getattr(snapshot_map.get("profile"), "id", None)},
            ),
            _SnapshotCandidate(
                memory_key="access",
                title=SNAPSHOT_TITLES["access"],
                content=self._render_snapshot_lines(access_points, fallback="Сетевой и access-профиль пока не заполнен."),
                importance_score=0.84,
                stability_score=0.8,
                confidence=0.8,
                source_kind="dream",
                metadata={"source_snapshot_id": getattr(snapshot_map.get("access"), "id", None)},
            ),
            _SnapshotCandidate(
                memory_key="risks",
                title=SNAPSHOT_TITLES["risks"],
                content=self._render_snapshot_lines(risk_points, fallback="Критичные активные риски не зафиксированы."),
                importance_score=0.95,
                stability_score=0.52,
                confidence=0.78 if risk_points else 0.7,
                source_kind="dream",
                verified_at=getattr(latest_health, "checked_at", None),
                metadata={"source_snapshot_id": getattr(snapshot_map.get("risks"), "id", None)},
            ),
            _SnapshotCandidate(
                memory_key="runbook",
                title=SNAPSHOT_TITLES["runbook"],
                content=self._render_snapshot_lines(runbook_points, fallback="Runbook пополнится после новых успешных операций."),
                importance_score=0.9,
                stability_score=0.74,
                confidence=0.79,
                source_kind="dream",
                metadata={"source_snapshot_id": getattr(snapshot_map.get("runbook"), "id", None)},
            ),
            _SnapshotCandidate(
                memory_key="recent_changes",
                title=SNAPSHOT_TITLES["recent_changes"],
                content=self._render_snapshot_lines(change_points, fallback="Значимых недавних изменений не зафиксировано."),
                importance_score=0.76,
                stability_score=0.38,
                confidence=0.74,
                source_kind="dream",
                metadata={"source_snapshot_id": getattr(snapshot_map.get("recent_changes"), "id", None)},
            ),
            _SnapshotCandidate(
                memory_key="human_habits",
                title=SNAPSHOT_TITLES["human_habits"],
                content=self._render_snapshot_lines(human_habits_points, fallback="Повторяющиеся ручные привычки пока не выделены."),
                importance_score=0.7,
                stability_score=0.62,
                confidence=0.7 if human_habits_points else 0.55,
                source_kind="dream",
                metadata={"source_snapshot_id": getattr(snapshot_map.get("human_habits"), "id", None)},
            ),
        ]

    def _derive_human_habits(self, server_id: int, *, patterns: list[_OperationalPattern] | None = None) -> list[str]:
        patterns = patterns if patterns is not None else self._derive_operational_patterns(server_id)
        habit_lines: list[str] = []
        for pattern in patterns:
            if "human" not in pattern.actor_kinds:
                continue
            minimum_occurrences = 3 if pattern.pattern_kind == "sequence" else 4
            if pattern.occurrences < minimum_occurrences:
                continue
            if pattern.distinct_sessions < 3:
                continue
            if pattern.measured_runs and pattern.success_rate < 0.8:
                continue
            if (
                self._pattern_has_mutating_step(pattern)
                or self._pattern_has_destructive_step(pattern)
                or self._pattern_has_setup_step(pattern)
            ):
                continue
            if pattern.pattern_kind == "sequence":
                habit_lines.append(
                    f"Повторяется ручной workflow [{pattern.intent}]: "
                    f"{' -> '.join(pattern.commands[:3])} "
                    f"({pattern.occurrences} запусков в {pattern.distinct_sessions} сессиях)"
                )
            else:
                habit_lines.append(
                    f"Повторяется ручной паттерн [{pattern.intent}]: {pattern.display_command} "
                    f"({pattern.occurrences} запусков в {pattern.distinct_sessions} сессиях)"
                )
        return habit_lines[:5]

    def _derive_runbook_patterns(self, patterns: list[_OperationalPattern]) -> list[str]:
        lines: list[str] = []
        for pattern in patterns:
            if pattern.occurrences < 2:
                continue
            if pattern.measured_runs and pattern.success_rate < 0.6:
                continue
            if self._pattern_has_destructive_step(pattern) and not (
                pattern.pattern_kind == "sequence" and (pattern.has_verification_step or pattern.verification_rate >= 0.5)
            ):
                continue
            if self._pattern_has_mutating_step(pattern) and not (
                pattern.pattern_kind == "sequence" and (pattern.has_verification_step or pattern.verification_rate >= 0.5)
            ):
                continue
            if pattern.pattern_kind == "sequence":
                lines.append(
                    f"Проверенный workflow [{pattern.intent}]: {' -> '.join(pattern.commands[:3])} "
                    f"({self._pattern_success_summary(pattern, noun='прогонов')})"
                )
            else:
                lines.append(
                    f"Проверенный паттерн [{pattern.intent}]: {pattern.display_command} "
                    f"({self._pattern_success_summary(pattern)})"
                )
        return lines[:6]

    def _derive_operational_patterns(self, server_id: int) -> list[_OperationalPattern]:
        from servers.models import ServerMemoryEvent

        now = timezone.now()
        recent = list(
            ServerMemoryEvent.objects.filter(
                server_id=server_id,
                event_type="command_executed",
                created_at__gte=now - timedelta(days=30),
            ).order_by("created_at", "id")[:220]
        )
        buckets: dict[str, dict[str, Any]] = {}
        session_events: dict[str, list[Any]] = {}
        for event in recent:
            payload = event.structured_payload or {}
            command = str(payload.get("command") or "").strip()
            if command:
                normalized = self._normalize_command_pattern(command)
                bucket = buckets.setdefault(
                    normalized,
                    {
                        "display_command": compact_text(command, limit=140),
                        "occurrences": 0,
                        "successful_runs": 0,
                        "measured_runs": 0,
                        "actor_kinds": set(),
                        "source_kinds": set(),
                        "verification_hits": 0,
                        "sample_outputs": [],
                        "common_cwds": [],
                        "session_keys": set(),
                        "last_seen": event.created_at,
                        "intent": self._classify_command_intent(command),
                    },
                )
                # Temporal decay: недавние события имеют больший вес
                age_days = (now - event.created_at).days if event.created_at else 15
                temporal_weight = max(0.1, 1.0 - age_days / 30.0)
                bucket["occurrences"] += 1
                bucket["weighted_occurrences"] = bucket.get("weighted_occurrences", 0.0) + temporal_weight
                bucket["actor_kinds"].add(str(event.actor_kind or "system"))
                bucket["source_kinds"].add(str(event.source_kind or "system"))
                if self._is_verification_command(command):
                    bucket["verification_hits"] += 1
                output_markers = self._event_output_markers(event)
                if output_markers:
                    bucket["sample_outputs"].extend(output_markers[:2])
                cwd = compact_text(str(payload.get("cwd") or "").strip(), limit=120)
                if cwd:
                    bucket["common_cwds"].append(cwd)
                if event.created_at and (bucket["last_seen"] is None or event.created_at > bucket["last_seen"]):
                    bucket["last_seen"] = event.created_at
                exit_code = payload.get("exit_code")
                if isinstance(exit_code, int):
                    bucket["measured_runs"] += 1
                    if exit_code == 0:
                        bucket["successful_runs"] += 1
                session_key = str(event.session_id or event.source_ref or "").strip()
                if session_key:
                    bucket["session_keys"].add(session_key)
                    session_events.setdefault(session_key, []).append(event)

        patterns: list[_OperationalPattern] = []
        for normalized, bucket in buckets.items():
            occurrences = int(bucket["occurrences"])
            weighted_occurrences = float(bucket.get("weighted_occurrences", occurrences))
            measured_runs = int(bucket["measured_runs"])
            successful_runs = int(bucket["successful_runs"])
            success_rate = (successful_runs / measured_runs) if measured_runs else 1.0
            # Используем взвешенное число вхождений для отсечки (temporal decay)
            if weighted_occurrences < 1.2 and occurrences < 2 and successful_runs < 2:
                continue
            patterns.append(
                _OperationalPattern(
                    pattern_kind="command",
                    display_command=str(bucket["display_command"]),
                    normalized_command=normalized,
                    intent=str(bucket["intent"]),
                    intent_label=self._describe_pattern_intent(
                        [str(bucket["display_command"])],
                        intent=str(bucket["intent"]),
                        sample_outputs=tuple(unique_preserving_order(bucket["sample_outputs"], limit=3)),
                    ),
                    commands=(str(bucket["display_command"]),),
                    occurrences=occurrences,
                    successful_runs=successful_runs,
                    measured_runs=measured_runs,
                    success_rate=success_rate,
                    actor_kinds=tuple(sorted(bucket["actor_kinds"])),
                    source_kinds=tuple(sorted(bucket["source_kinds"])),
                    verification_rate=float(bucket["verification_hits"] or 0) / max(occurrences, 1),
                    has_verification_step=bool(bucket["verification_hits"]),
                    sample_outputs=tuple(unique_preserving_order(bucket["sample_outputs"], limit=3)),
                    common_cwds=tuple(unique_preserving_order(bucket["common_cwds"], limit=3)),
                    distinct_sessions=max(1, len(bucket["session_keys"])) if bucket["session_keys"] else 0,
                    last_seen=bucket["last_seen"],
                )
            )
        patterns.extend(self._derive_sequence_patterns(session_events))
        patterns.sort(
            key=lambda item: (
                1 if item.pattern_kind == "sequence" else 0,
                item.occurrences,
                item.success_rate,
                item.verification_rate,
                1 if "human" in item.actor_kinds else 0,
                item.last_seen or timezone.now(),
            ),
            reverse=True,
        )
        return patterns[:12]

    def _derive_sequence_patterns(self, session_events: dict[str, list[Any]]) -> list[_OperationalPattern]:
        buckets: dict[str, dict[str, Any]] = {}
        for session_key, events in session_events.items():
            ordered = [item for item in sorted(events, key=lambda event: (event.created_at, event.id)) if item is not None]
            if len(ordered) < 2:
                continue
            max_window = min(3, len(ordered))
            for size in range(2, max_window + 1):
                for index in range(0, len(ordered) - size + 1):
                    window = ordered[index : index + size]
                    commands: list[str] = []
                    normalized_commands: list[str] = []
                    output_markers: list[str] = []
                    common_cwds: list[str] = []
                    actor_kinds: set[str] = set()
                    source_kinds: set[str] = set()
                    exit_codes: list[int] = []
                    verification_hits = 0
                    for event in window:
                        payload = event.structured_payload or {}
                        command = str(payload.get("command") or "").strip()
                        if not command:
                            commands = []
                            break
                        commands.append(compact_text(command, limit=120))
                        normalized_commands.append(self._normalize_command_pattern(command))
                        actor_kinds.add(str(event.actor_kind or "system"))
                        source_kinds.add(str(event.source_kind or "system"))
                        if self._is_verification_command(command):
                            verification_hits += 1
                        output_markers.extend(self._event_output_markers(event)[:1])
                        cwd = compact_text(str(payload.get("cwd") or "").strip(), limit=120)
                        if cwd:
                            common_cwds.append(cwd)
                        exit_code = payload.get("exit_code")
                        if isinstance(exit_code, int):
                            exit_codes.append(exit_code)
                    if len(commands) != size or len(set(normalized_commands)) < 2:
                        continue
                    signature = " => ".join(normalized_commands)
                    bucket = buckets.setdefault(
                        signature,
                        {
                            "commands": tuple(commands),
                            "intent": self._classify_sequence_intent(commands),
                            "occurrences": 0,
                            "successful_runs": 0,
                            "measured_runs": 0,
                            "verification_hits": 0,
                            "actor_kinds": set(),
                            "source_kinds": set(),
                            "sample_outputs": [],
                            "common_cwds": [],
                            "session_keys": set(),
                            "last_seen": window[-1].created_at,
                        },
                    )
                    bucket["occurrences"] += 1
                    bucket["actor_kinds"].update(actor_kinds)
                    bucket["source_kinds"].update(source_kinds)
                    bucket["session_keys"].add(session_key)
                    bucket["verification_hits"] += 1 if verification_hits else 0
                    if len(exit_codes) == size:
                        bucket["measured_runs"] += 1
                        if all(code == 0 for code in exit_codes):
                            bucket["successful_runs"] += 1
                    bucket["sample_outputs"].extend(output_markers[:2])
                    bucket["common_cwds"].extend(common_cwds[:2])
                    if window[-1].created_at and (
                        bucket["last_seen"] is None or window[-1].created_at > bucket["last_seen"]
                    ):
                        bucket["last_seen"] = window[-1].created_at

        patterns: list[_OperationalPattern] = []
        for signature, bucket in buckets.items():
            occurrences = int(bucket["occurrences"])
            if occurrences < 2:
                continue
            measured_runs = int(bucket["measured_runs"])
            successful_runs = int(bucket["successful_runs"])
            success_rate = (successful_runs / measured_runs) if measured_runs else 1.0
            verification_rate = float(bucket["verification_hits"] or 0) / max(occurrences, 1)
            patterns.append(
                _OperationalPattern(
                    pattern_kind="sequence",
                    display_command=" -> ".join(bucket["commands"]),
                    normalized_command=signature,
                    intent=str(bucket["intent"]),
                    intent_label=self._describe_pattern_intent(
                        list(bucket["commands"]),
                        intent=str(bucket["intent"]),
                        sample_outputs=tuple(unique_preserving_order(bucket["sample_outputs"], limit=4)),
                    ),
                    commands=tuple(bucket["commands"]),
                    occurrences=occurrences,
                    successful_runs=successful_runs,
                    measured_runs=measured_runs,
                    success_rate=success_rate,
                    actor_kinds=tuple(sorted(bucket["actor_kinds"])),
                    source_kinds=tuple(sorted(bucket["source_kinds"])),
                    verification_rate=verification_rate,
                    has_verification_step=verification_rate >= 0.5 or any(
                        self._is_verification_command(command) for command in bucket["commands"]
                    ),
                    sample_outputs=tuple(unique_preserving_order(bucket["sample_outputs"], limit=4)),
                    common_cwds=tuple(unique_preserving_order(bucket["common_cwds"], limit=3)),
                    distinct_sessions=max(1, len(bucket["session_keys"])) if bucket["session_keys"] else 0,
                    last_seen=bucket["last_seen"],
                )
            )
        return patterns

    @staticmethod
    def _event_output_markers(event: Any) -> list[str]:
        raw_text = str(getattr(event, "raw_text_redacted", "") or "")
        if not raw_text:
            return []
        lines = raw_text.splitlines()
        if lines and lines[0].lstrip().startswith("$"):
            raw_text = "\n".join(lines[1:])
        return [compact_text(item, limit=140) for item in extract_signal_lines(raw_text, max_items=2)]

    @staticmethod
    def _is_verification_command(command: str) -> bool:
        blob = str(command or "").lower()
        return any(
            term in blob
            for term in (
                "systemctl is-active",
                "systemctl status",
                "journalctl",
                "curl ",
                "wget ",
                "nginx -t",
                "haproxy -c",
                "docker ps",
                "docker stats",
                "kubectl rollout status",
                "kubectl get pods",
                "helm status",
                "ss -l",
                "uptime",
                "free -h",
            )
        )

    def _classify_sequence_intent(self, commands: list[str] | tuple[str, ...]) -> str:
        intents = [self._classify_command_intent(command) for command in commands if str(command or "").strip()]
        if not intents:
            return "ops"
        for preferred in ("docker", "service", "web", "kubernetes", "diagnostics", "inspection"):
            if preferred in intents:
                return preferred
        return intents[0]

    @staticmethod
    def _extract_pattern_subject(commands: list[str] | tuple[str, ...]) -> str:
        for command in commands:
            command_text = str(command or "").strip()
            if not command_text:
                continue
            if "nginx" in command_text.lower():
                return "nginx"
            match = re.search(
                r"(?:systemctl\s+(?:restart|reload|is-active|status)\s+)([A-Za-z0-9_.@-]+)",
                command_text,
                flags=re.IGNORECASE,
            )
            if match:
                return match.group(1).strip()
            match = re.search(r"(?:docker\s+compose\s+)([A-Za-z0-9_.@-]+)", command_text, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _describe_pattern_intent(
        self,
        commands: list[str] | tuple[str, ...],
        *,
        intent: str,
        sample_outputs: tuple[str, ...] = (),
    ) -> str:
        joined = " ".join(str(command or "").lower() for command in commands)
        outputs = " ".join(str(item or "").lower() for item in sample_outputs)
        subject = self._extract_pattern_subject(commands)
        if "nginx -t" in joined and "reload nginx" in joined:
            return "safe nginx reload after config check"
        if "systemctl restart" in joined and "systemctl is-active" in joined:
            return f"{subject or 'service'} restart with health verification"
        if "docker compose pull" in joined and "docker compose up" in joined:
            return "docker compose rollout"
        if "kubectl rollout" in joined and "kubectl get pods" in joined:
            return "kubernetes rollout verification"
        if "journalctl" in joined and "grep" in joined:
            return "log investigation workflow"
        if intent == "diagnostics" and ("load" in outputs or "active" in outputs):
            return "diagnostic verification workflow"
        return intent.replace("_", " ")

    def _promote_pattern_candidates_sync(
        self,
        *,
        server_id: int,
        patterns: list[_OperationalPattern],
        snapshots: list[Any],
        enhancements: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, int]:
        active_keys: set[str] = set()
        pattern_candidates = 0
        automation_candidates = 0
        skill_drafts = 0
        enhancements = enhancements or {}

        for pattern in patterns:
            if pattern.occurrences < 2:
                continue
            enhancement = enhancements.get(pattern.normalized_command) or {}
            pattern_key = f"{PATTERN_CANDIDATE_PREFIX}{self._pattern_key_suffix(pattern)}"
            active_keys.add(pattern_key)
            self._upsert_snapshot_sync(
                server_id=server_id,
                memory_key=pattern_key,
                title=f"Learned Pattern: {pattern.intent} :: {pattern.display_command[:72]}",
                content=self._render_snapshot_lines(self._pattern_candidate_lines(pattern, enhancement=enhancement), fallback=pattern.display_command),
                source_kind="dream",
                importance_score=0.68 if pattern.pattern_kind == "sequence" else 0.64,
                stability_score=min(0.9, 0.45 + min(pattern.occurrences, 6) * 0.06 + (0.05 if pattern.pattern_kind == "sequence" else 0.0)),
                confidence=min(0.97, max(0.58, pattern.success_rate + (0.04 if pattern.has_verification_step else 0.0))),
                metadata=self._pattern_metadata(pattern) | self._pattern_enhancement_metadata(enhancement),
            )
            pattern_candidates += 1

            if self._is_automation_candidate(pattern):
                automation_key = f"{AUTOMATION_CANDIDATE_PREFIX}{self._pattern_key_suffix(pattern)}"
                active_keys.add(automation_key)
                self._upsert_snapshot_sync(
                    server_id=server_id,
                    memory_key=automation_key,
                    title=f"Automation Candidate: {pattern.intent} :: {pattern.display_command[:68]}",
                    content=self._render_snapshot_lines(
                        self._automation_candidate_lines(pattern, enhancement=enhancement),
                        fallback=pattern.display_command,
                    ),
                    source_kind="dream",
                    importance_score=0.78 if pattern.pattern_kind == "sequence" else 0.72,
                    stability_score=min(0.92, 0.5 + min(pattern.occurrences, 6) * 0.05 + (0.06 if pattern.pattern_kind == "sequence" else 0.0)),
                    confidence=min(0.98, max(0.64, pattern.success_rate + (0.04 if pattern.has_verification_step else 0.0))),
                    metadata=self._pattern_metadata(pattern)
                    | {"candidate_kind": "automation"}
                    | self._pattern_enhancement_metadata(enhancement),
                )
                automation_candidates += 1
                if self._is_skill_draft_candidate(pattern):
                    skill_key = f"{SKILL_DRAFT_PREFIX}{self._pattern_key_suffix(pattern)}"
                    active_keys.add(skill_key)
                    self._upsert_snapshot_sync(
                        server_id=server_id,
                        memory_key=skill_key,
                        title=f"Skill Draft: {pattern.intent} :: {pattern.display_command[:68]}",
                        content=self._render_snapshot_lines(self._skill_draft_lines(pattern, enhancement=enhancement), fallback=pattern.display_command),
                        source_kind="dream",
                        importance_score=0.84 if pattern.pattern_kind == "sequence" else 0.76,
                        stability_score=min(0.94, 0.56 + min(pattern.occurrences, 7) * 0.04 + (0.08 if pattern.pattern_kind == "sequence" else 0.0)),
                        confidence=min(0.99, max(0.68, pattern.success_rate + (0.05 if pattern.has_verification_step else 0.0))),
                        metadata=self._pattern_metadata(pattern)
                        | {"candidate_kind": "skill_draft"}
                        | self._pattern_enhancement_metadata(enhancement),
                    )
                    skill_drafts += 1

        self._archive_missing_candidate_snapshots_sync(server_id, active_keys=active_keys)
        return {
            "pattern_candidates": pattern_candidates,
            "automation_candidates": automation_candidates,
            "skill_drafts": skill_drafts,
        }

    @staticmethod
    def _pattern_key_suffix(pattern: _OperationalPattern) -> str:
        return uuid.uuid5(uuid.NAMESPACE_DNS, pattern.normalized_command).hex[:16]

    @staticmethod
    def _pattern_metadata(pattern: _OperationalPattern) -> dict[str, Any]:
        return {
            "pattern_kind": pattern.pattern_kind,
            "normalized_command": pattern.normalized_command,
            "display_command": pattern.display_command,
            "commands": list(pattern.commands),
            "intent": pattern.intent,
            "intent_label": pattern.intent_label,
            "occurrences": pattern.occurrences,
            "successful_runs": pattern.successful_runs,
            "measured_runs": pattern.measured_runs,
            "success_rate": round(pattern.success_rate, 3),
            "verification_rate": round(pattern.verification_rate, 3),
            "has_verification_step": pattern.has_verification_step,
            "actor_kinds": list(pattern.actor_kinds),
            "source_kinds": list(pattern.source_kinds),
            "sample_outputs": list(pattern.sample_outputs),
            "common_cwds": list(pattern.common_cwds),
            "last_seen": pattern.last_seen.isoformat() if pattern.last_seen else None,
        }

    @staticmethod
    def _pattern_enhancement_metadata(enhancement: dict[str, Any] | None) -> dict[str, Any]:
        enhancement = enhancement or {}
        metadata: dict[str, Any] = {"llm_enhanced": bool(enhancement)}
        for key in (
            "when_to_use",
            "automation_hint",
            "skill_summary",
            "verification",
            "playbook_summary",
            "prerequisites",
            "rollback_hint",
            "risk_level",
            "runtime_attachment",
        ):
            value = compact_text(str(enhancement.get(key) or ""), limit=220)
            if value:
                metadata[key] = value
        success_signals = [
            compact_text(str(item), limit=140)
            for item in list(enhancement.get("success_signals") or [])[:4]
            if str(item or "").strip()
        ]
        if success_signals:
            metadata["success_signals"] = success_signals
        return metadata

    def _pattern_candidate_lines(self, pattern: _OperationalPattern, *, enhancement: dict[str, Any] | None = None) -> list[str]:
        enhancement = enhancement or {}
        lines = [
            f"Intent: {pattern.intent_label}",
            f"Повторяемость: {pattern.occurrences} запусков",
            f"Успех: {self._pattern_success_summary(pattern)}",
            f"Источники: {', '.join(pattern.source_kinds)}; акторы: {', '.join(pattern.actor_kinds)}",
        ]
        if pattern.pattern_kind == "sequence":
            lines.insert(0, f"Workflow: {' -> '.join(pattern.commands)}")
        else:
            lines.insert(0, f"Команда: {pattern.display_command}")
        if pattern.common_cwds:
            lines.append("Типовой cwd: " + ", ".join(pattern.common_cwds[:2]))
        if pattern.sample_outputs:
            lines.append("Сигналы успеха/вывода: " + " | ".join(pattern.sample_outputs[:2]))
        if enhancement.get("when_to_use"):
            lines.append("Когда использовать: " + compact_text(str(enhancement["when_to_use"]), limit=180))
        if enhancement.get("playbook_summary"):
            lines.append("Playbook: " + compact_text(str(enhancement["playbook_summary"]), limit=180))
        if enhancement.get("prerequisites"):
            lines.append("Prerequisites: " + compact_text(str(enhancement["prerequisites"]), limit=180))
        if enhancement.get("runtime_attachment"):
            lines.append("Runtime attach: " + compact_text(str(enhancement["runtime_attachment"]), limit=180))
        if enhancement.get("risk_level"):
            lines.append("Риск: " + compact_text(str(enhancement["risk_level"]), limit=80))
        lines.append("Паттерн годится как reusable operational шаблон после ручной проверки.")
        return lines

    @staticmethod
    def _pattern_success_summary(pattern: _OperationalPattern, *, noun: str = "запусков") -> str:
        if pattern.measured_runs:
            return f"{pattern.successful_runs}/{pattern.measured_runs} измеренных {noun} ({pattern.success_rate:.0%})"
        return f"exit code не сохранён; {pattern.occurrences} наблюдений"

    def _automation_candidate_lines(self, pattern: _OperationalPattern, *, enhancement: dict[str, Any] | None = None) -> list[str]:
        enhancement = enhancement or {}
        verification_step = self._automation_verification_hint(pattern)
        safety_mode = "read-only" if not self._looks_mutating_command(pattern.display_command) else "assisted"
        lines = [
            f"Intent: {pattern.intent_label}",
            f"Режим запуска: {safety_mode}",
        ]
        if pattern.pattern_kind == "sequence":
            for index, command in enumerate(pattern.commands, start=1):
                lines.append(f"Шаг {index}: выполнить `{command}` и сохранить stdout/stderr + exit code.")
            lines.append(f"Шаг {len(pattern.commands) + 1}: {verification_step}")
            lines.append(
                f"Шаг {len(pattern.commands) + 2}: записать краткую выжимку в recent_changes/runbook, если результат полезен."
            )
        else:
            lines.extend(
                [
                    f"Базовая команда: {pattern.display_command}",
                    "Шаг 1: выполнить команду и сохранить stdout/stderr + exit code.",
                    f"Шаг 2: {verification_step}",
                    "Шаг 3: записать краткую выжимку в recent_changes/runbook, если результат полезен.",
                ]
            )
        if enhancement.get("playbook_summary"):
            lines.append("Playbook summary: " + compact_text(str(enhancement["playbook_summary"]), limit=180))
        if enhancement.get("prerequisites"):
            lines.append("Prerequisites: " + compact_text(str(enhancement["prerequisites"]), limit=180))
        if pattern.sample_outputs:
            lines.append("Ожидаемые сигналы: " + " | ".join(pattern.sample_outputs[:2]))
        if enhancement.get("automation_hint"):
            lines.append("LLM Hint: " + compact_text(str(enhancement["automation_hint"]), limit=180))
        if enhancement.get("verification"):
            lines.append("Verification focus: " + compact_text(str(enhancement["verification"]), limit=180))
        if enhancement.get("rollback_hint"):
            lines.append("Rollback: " + compact_text(str(enhancement["rollback_hint"]), limit=180))
        if enhancement.get("risk_level"):
            lines.append("Risk: " + compact_text(str(enhancement["risk_level"]), limit=80))
        if enhancement.get("runtime_attachment"):
            lines.append("Runtime attach: " + compact_text(str(enhancement["runtime_attachment"]), limit=180))
        return lines

    def _skill_draft_lines(self, pattern: _OperationalPattern, *, enhancement: dict[str, Any] | None = None) -> list[str]:
        enhancement = enhancement or {}
        verification_step = self._automation_verification_hint(pattern)
        lines = [
            f"# Skill Draft: {pattern.intent_label}",
            f"- Trigger: задачи, где нужен {'workflow' if pattern.pattern_kind == 'sequence' else 'шаг'} "
            f"`{pattern.display_command}`.",
            f"- Reuse signal: {pattern.occurrences} повторений, успех {pattern.success_rate:.0%}.",
        ]
        if enhancement.get("skill_summary"):
            lines.append(f"- Summary: {compact_text(str(enhancement['skill_summary']), limit=180)}")
        if pattern.pattern_kind == "sequence":
            lines.append(f"- Workflow: {' -> '.join(pattern.commands)}")
        else:
            lines.append(f"- Primary command: {pattern.display_command}")
        lines.append(f"- Verification: {compact_text(str(enhancement.get('verification') or verification_step), limit=180)}")
        if enhancement.get("playbook_summary"):
            lines.append(f"- Playbook: {compact_text(str(enhancement['playbook_summary']), limit=180)}")
        if enhancement.get("prerequisites"):
            lines.append(f"- Preconditions: {compact_text(str(enhancement['prerequisites']), limit=180)}")
        if enhancement.get("rollback_hint"):
            lines.append(f"- Rollback: {compact_text(str(enhancement['rollback_hint']), limit=180)}")
        if enhancement.get("runtime_attachment"):
            lines.append(f"- Runtime attach: {compact_text(str(enhancement['runtime_attachment']), limit=180)}")
        hints: list[str] = []
        if pattern.common_cwds:
            hints.append(f"cwd {', '.join(pattern.common_cwds[:2])}")
        if pattern.sample_outputs:
            hints.append(f"signals {' | '.join(pattern.sample_outputs[:2])}")
        if enhancement.get("success_signals"):
            hints.append("llm signals " + " | ".join(str(item) for item in list(enhancement["success_signals"])[:2]))
        if hints:
            lines.append("- Hints: " + "; ".join(hints[:2]))
        else:
            lines.append("- Hints: вернуть короткую operational-выжимку и рекомендации по следующему действию.")
        return lines

    @staticmethod
    def _looks_mutating_command(command: str) -> bool:
        blob = str(command or "").lower()
        return any(
            term in blob
            for term in (
                "restart",
                "reload",
                "apply",
                "delete",
                "rm ",
                "useradd",
                "systemctl start",
                "systemctl stop",
                "apt ",
                "yum ",
                "dnf ",
                "kubectl apply",
                "docker compose up",
            )
        )

    @staticmethod
    def _is_destructive_command(command: str) -> bool:
        blob = str(command or "").lower()
        return any(
            term in blob
            for term in (
                "docker rm ",
                "docker rm -f",
                "docker system prune",
                "docker volume rm",
                "docker network rm",
                "kubectl delete",
                "helm uninstall",
                "rm -rf",
                "rm -f",
                "drop database",
                "systemctl stop",
                "systemctl disable",
            )
        )

    @staticmethod
    def _is_setup_command(command: str) -> bool:
        blob = str(command or "").lower().strip()
        return any(
            blob.startswith(prefix)
            for prefix in (
                "mkdir ",
                "install -d",
                "cp ",
                "mv ",
                "chmod ",
                "chown ",
                "tee ",
            )
        )

    @classmethod
    def _pattern_has_mutating_step(cls, pattern: _OperationalPattern) -> bool:
        commands = pattern.commands if pattern.pattern_kind == "sequence" else (pattern.display_command,)
        return any(cls._looks_mutating_command(command) for command in commands)

    @classmethod
    def _pattern_has_destructive_step(cls, pattern: _OperationalPattern) -> bool:
        commands = pattern.commands if pattern.pattern_kind == "sequence" else (pattern.display_command,)
        return any(cls._is_destructive_command(command) for command in commands)

    @classmethod
    def _pattern_has_setup_step(cls, pattern: _OperationalPattern) -> bool:
        commands = pattern.commands if pattern.pattern_kind == "sequence" else (pattern.display_command,)
        return any(cls._is_setup_command(command) for command in commands)

    @staticmethod
    def _automation_verification_hint(pattern: _OperationalPattern) -> str:
        if pattern.pattern_kind == "sequence" and pattern.has_verification_step:
            return "последний шаг workflow уже выступает как verification; нужно проверить его exit code и сигнал результата."
        if pattern.intent == "service":
            return "проверить `systemctl is-active <service>` и последние строки `journalctl`."
        if pattern.intent == "docker":
            return "проверить состояние контейнеров через `docker ps` и при необходимости `docker stats --no-stream`."
        if pattern.intent == "web":
            return "подтвердить конфиг и health-check веб-сервиса до/после действия."
        if pattern.intent == "kubernetes":
            return "проверить rollout/status нужного workload и последние pod events."
        if pattern.intent == "diagnostics":
            return "сравнить output с предыдущими эпизодами и выделить деградацию/аномалию."
        return "сохранить компактный отчёт и отметить, можно ли повторно автоматизировать этот шаг."

    @staticmethod
    def _is_automation_candidate(pattern: _OperationalPattern) -> bool:
        minimum_occurrences = 2 if pattern.pattern_kind == "sequence" else 3
        success_threshold = 0.75 if pattern.pattern_kind == "sequence" else 0.8
        if pattern.occurrences < minimum_occurrences:
            return False
        if pattern.measured_runs and pattern.success_rate < success_threshold:
            return False
        if DjangoServerMemoryStore._pattern_has_destructive_step(pattern):
            return pattern.pattern_kind == "sequence" and (
                pattern.has_verification_step or pattern.verification_rate >= 0.5
            )
        if DjangoServerMemoryStore._pattern_has_mutating_step(pattern) and not (
            pattern.pattern_kind == "sequence" and (pattern.has_verification_step or pattern.verification_rate >= 0.5)
        ):
            return False
        return pattern.intent in {"docker", "service", "web", "diagnostics", "kubernetes", "inspection", "ops"}

    @staticmethod
    def _is_skill_draft_candidate(pattern: _OperationalPattern) -> bool:
        minimum_occurrences = 2 if pattern.pattern_kind == "sequence" else 3
        success_threshold = 0.85 if pattern.pattern_kind == "sequence" else 0.9
        if pattern.occurrences < minimum_occurrences:
            return False
        if pattern.measured_runs and pattern.success_rate < success_threshold:
            return False
        if DjangoServerMemoryStore._pattern_has_destructive_step(pattern):
            return False
        if DjangoServerMemoryStore._pattern_has_mutating_step(pattern) and not (
            pattern.pattern_kind == "sequence" and (pattern.has_verification_step or pattern.verification_rate >= 0.5)
        ):
            return False
        if pattern.pattern_kind == "sequence" and not (pattern.has_verification_step or pattern.verification_rate >= 0.5):
            return False
        return len(pattern.actor_kinds) >= 1 and pattern.intent in {"docker", "service", "web", "diagnostics", "kubernetes", "inspection", "ops"}

    def _archive_missing_candidate_snapshots_sync(self, server_id: int, *, active_keys: set[str]) -> int:
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

    @staticmethod
    def _normalize_command_pattern(command: str) -> str:
        normalized = " ".join(str(command or "").strip().split())
        normalized = re.sub(r"^sudo\s+", "", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.lower()[:240]

    @staticmethod
    def _classify_command_intent(command: str) -> str:
        blob = str(command or "").lower()
        if any(term in blob for term in ("docker", "compose", "container")):
            return "docker"
        if any(term in blob for term in ("systemctl", "service ", "journalctl")):
            return "service"
        if any(term in blob for term in ("nginx", "apache", "haproxy")):
            return "web"
        if any(term in blob for term in ("ps ", "top", "htop", "uptime", "free ", "df ", "iostat", "vmstat")):
            return "diagnostics"
        if any(term in blob for term in ("kubectl", "helm", "k9s")):
            return "kubernetes"
        if any(term in blob for term in ("grep", "find", "cat ", "tail ", "less ", "awk ", "sed ")):
            return "inspection"
        return "ops"

    @classmethod
    def _preferred_memory_key_for_note(cls, *, title: str, category: str | None, content: str) -> str | None:
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

    def _canonical_key_for_snapshot(self, snapshot) -> str:
        metadata = getattr(snapshot, "metadata", None) or {}
        category = metadata.get("category")
        title = str(getattr(snapshot, "title", "") or "")
        content = str(getattr(snapshot, "content", "") or "")
        preferred = self._preferred_memory_key_for_note(
            title=title,
            category=str(category or ""),
            content=content,
        )
        if preferred:
            return preferred
        return self._guess_memory_key(
            title=title,
            category=str(category or ""),
            content=content,
        )

    def _should_distill_with_llm(
        self,
        candidates: list[_SnapshotCandidate],
        existing_snapshots: list[Any],
    ) -> bool:
        """
        GAP 2: delta-based LLM distillation trigger.

        Возвращает True только если суммарная разница между кандидатами
        и существующими снапшотами превышает порог 0.15.
        Это позволяет пропускать LLM-вызов когда данные существенно не менялись.
        """
        if not existing_snapshots:
            # Первый раз — всегда дистиллируем
            return True
        snapshot_map = {s.memory_key: s for s in existing_snapshots}
        total_delta = 0.0
        compared = 0
        for candidate in candidates:
            existing = snapshot_map.get(candidate.memory_key)
            if existing is None:
                total_delta += 1.0
                compared += 1
                continue
            delta = self._content_delta(
                str(getattr(existing, "content", "") or ""),
                candidate.content,
            )
            total_delta += delta
            compared += 1
        if compared == 0:
            return False
        avg_delta = total_delta / compared
        return avg_delta > 0.15

    def _build_memory_warmup_prompt(self, server_id: int, *, last_n: int = 3) -> str:
        """
        GAP 5: memory warmup prompt.

        Строит компактный блок из последних N AgentRun для вставки в prompt context.
        Помогает агенту учитывать историю предыдущих запусков без перегрузки
        полным memory card.
        """
        from servers.models import AgentRun

        recent_runs = list(
            AgentRun.objects.filter(server_id=server_id)
            .select_related("agent")
            .order_by("-started_at")[:max(1, min(int(last_n), 6))]
        )
        if not recent_runs:
            return ""
        lines = []
        for run in recent_runs:
            label = getattr(run.agent, "name", "Agent") if run.agent_id else "Agent"
            snippet_src = run.final_report or run.ai_analysis or ""
            snippet = compact_text(
                " ".join(line for line in snippet_src.splitlines() if line.strip()),
                limit=160,
            )
            ts = run.started_at.strftime("%Y-%m-%d %H:%M") if run.started_at else "?"
            lines.append(f"- [{run.status}] {label} @ {ts}: {snippet}")
        return "\n".join(lines)

    def _distill_with_llm_sync(
        self,
        *,
        server,
        candidates: list[_SnapshotCandidate],
        model_alias: str,
    ) -> dict[str, str]:
        from app.core.llm import LLMProvider

        sections = {candidate.memory_key: candidate.content for candidate in candidates}
        prompt = (
            "Ты перерабатываешь память DevOps-агента о сервере.\n"
            "Нельзя добавлять секреты, токены, пароли, приватные ключи или сырые логи.\n"
            "Приоритизируй повторяющиеся подтвержденные workflow, успешные команды людей и агентов, и короткие runbook-выжимки.\n"
            "Не делай поведенческих выводов по одному-двум эпизодам и не используй формулировки вроде "
            "'предпочитает', 'сразу', 'регулярно', 'игнорирует' без явного многосессионного доказательства.\n"
            "Не превращай destructive/mutating команды вроде `docker rm -f`, `delete`, `stop`, `disable` в рекомендуемый runbook, "
            "если нет явной verify/recreate последовательности.\n"
            "Никогда не утверждай, что контейнер автоматически пересоздаётся после `docker rm`, если в данных нет прямого evidence "
            "про orchestrator, compose-up или явный recreate.\n"
            "Для рисков не используй слова chronic/permanent/always без подтверждения во времени.\n"
            "Раздел human_habits заполняй только если read-only или verification workflow повторялся минимум в 3 отдельных сессиях; "
            "не относись к setup-командам вроде mkdir/cp/chmod и к разовым prepare-steps как к привычкам.\n"
            "Верни JSON-объект только с ключами profile, access, risks, runbook, recent_changes, human_habits.\n"
            "Значение каждого ключа — короткий Markdown bullet list, максимум 6 bullet lines.\n\n"
            f"Сервер: {server.name} ({server.host})\n"
            f"Исходные разделы:\n{json.dumps(sections, ensure_ascii=False)}"
        )
        provider = LLMProvider()
        try:
            chunks: list[str] = []

            async def _collect():
                async for chunk in provider.stream_chat(prompt, purpose="opssummary", specific_model=model_alias):
                    chunks.append(chunk)

            async_to_sync(_collect)()
            raw = "".join(chunks).strip()
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return {}
            parsed = json.loads(raw[start : end + 1])
            if not isinstance(parsed, dict):
                return {}
            cleaned: dict[str, str] = {}
            for key, value in parsed.items():
                if key in sections:
                    cleaned[key] = self._render_snapshot_lines(value, fallback=sections[key])
            return cleaned
        except Exception:
            return {}

    def _llm_enhance_patterns_sync(
        self,
        *,
        server,
        patterns: list[_OperationalPattern],
        model_alias: str,
    ) -> dict[str, dict[str, Any]]:
        from app.core.llm import LLMProvider

        candidates = [
            {
                "normalized_command": pattern.normalized_command,
                "pattern_kind": pattern.pattern_kind,
                "intent": pattern.intent,
                "intent_label": pattern.intent_label,
                "display_command": pattern.display_command,
                "commands": list(pattern.commands),
                "occurrences": pattern.occurrences,
                "success_rate": round(pattern.success_rate, 3),
                "verification_rate": round(pattern.verification_rate, 3),
                "has_verification_step": bool(pattern.has_verification_step),
                "common_cwds": list(pattern.common_cwds),
                "sample_outputs": list(pattern.sample_outputs),
            }
            for pattern in patterns
            if (pattern.pattern_kind == "sequence" and pattern.occurrences >= 2)
            or (pattern.pattern_kind == "command" and pattern.occurrences >= 3 and pattern.success_rate >= 0.8)
        ][:6]
        if not candidates:
            return {}

        prompt = (
            "Ты усиливаешь черновики operational playbooks для DevOps-памяти сервера.\n"
            "Не добавляй секреты, приватные ключи, токены, сырые логи и вымышленные шаги.\n"
            "Для каждого workflow верни только безопасные короткие поля when_to_use, automation_hint, "
            "skill_summary, verification, success_signals, playbook_summary, prerequisites, rollback_hint, "
            "risk_level, runtime_attachment.\n"
            "runtime_attachment должен быть коротким советом, как агенту лучше применить этот recipe в runtime.\n"
            "Ответь JSON-массивом объектов с ключами normalized_command, when_to_use, automation_hint, "
            "skill_summary, verification, success_signals, playbook_summary, prerequisites, rollback_hint, "
            "risk_level, runtime_attachment.\n\n"
            f"Сервер: {server.name} ({server.host})\n"
            f"Workflow candidates:\n{json.dumps(candidates, ensure_ascii=False)}"
        )
        provider = LLMProvider()
        try:
            chunks: list[str] = []

            async def _collect():
                async for chunk in provider.stream_chat(prompt, purpose="opssummary", specific_model=model_alias):
                    chunks.append(chunk)

            async_to_sync(_collect)()
            raw = "".join(chunks).strip()
            start = raw.find("[")
            end = raw.rfind("]")
            if start == -1 or end == -1 or end <= start:
                return {}
            parsed = json.loads(raw[start : end + 1])
            if not isinstance(parsed, list):
                return {}
            cleaned: dict[str, dict[str, Any]] = {}
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                normalized_command = str(item.get("normalized_command") or "").strip()
                if not normalized_command:
                    continue
                signals = item.get("success_signals")
                cleaned[normalized_command] = {
                    "when_to_use": compact_text(str(item.get("when_to_use") or ""), limit=180),
                    "automation_hint": compact_text(str(item.get("automation_hint") or ""), limit=180),
                    "skill_summary": compact_text(str(item.get("skill_summary") or ""), limit=180),
                    "verification": compact_text(str(item.get("verification") or ""), limit=180),
                    "playbook_summary": compact_text(str(item.get("playbook_summary") or ""), limit=180),
                    "prerequisites": compact_text(str(item.get("prerequisites") or ""), limit=180),
                    "rollback_hint": compact_text(str(item.get("rollback_hint") or ""), limit=180),
                    "risk_level": compact_text(str(item.get("risk_level") or ""), limit=80),
                    "runtime_attachment": compact_text(str(item.get("runtime_attachment") or ""), limit=180),
                    "success_signals": [
                        compact_text(str(signal), limit=140)
                        for signal in (signals if isinstance(signals, list) else [])
                        if str(signal or "").strip()
                    ][:3],
                }
            return cleaned
        except Exception:
            return {}

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
        from servers.models import ServerMemorySnapshot

        clean_content = compact_text(content, limit=3200)
        metadata = metadata or {}

        with transaction.atomic():
            existing = (
                ServerMemorySnapshot.objects.select_for_update()
                .filter(server_id=server_id, memory_key=memory_key, is_active=True)
                .order_by("-version", "-updated_at")
                .first()
            )
            if existing:
                delta = self._content_delta(existing.content, clean_content)
                confidence_shift = float(confidence or 0.0) - float(existing.confidence or 0.0)
                significant = force_version or delta >= 0.2 or abs(confidence_shift) >= 0.15
                if not significant:
                    dirty_fields: list[str] = []
                    if clean_content and clean_content != existing.content:
                        existing.content = clean_content
                        dirty_fields.append("content")
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
                    if dirty_fields:
                        dirty_fields.append("updated_at")
                        existing.save(update_fields=dirty_fields)
                    return existing, False

            version_group = version_group_id or getattr(existing, "version_group_id", "") or uuid.uuid4().hex
            version = (int(existing.version) + 1) if existing else 1
            next_metadata = dict(metadata)
            rewrite_reason = ""
            if existing:
                rewrite_reason = self._describe_snapshot_rewrite(
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
            snapshot = ServerMemorySnapshot.objects.create(
                server_id=server_id,
                created_by_id=created_by_id,
                memory_key=memory_key,
                layer=ServerMemorySnapshot.LAYER_CANONICAL,
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
            )
            if existing:
                existing_metadata = dict(existing.metadata or {})
                if rewrite_reason:
                    existing_metadata["superseded_reason"] = rewrite_reason
                existing.is_active = False
                existing.layer = ServerMemorySnapshot.LAYER_ARCHIVE
                existing.archived_at = timezone.now()
                existing.superseded_by = snapshot
                existing.metadata = existing_metadata
                existing.save(
                    update_fields=["is_active", "layer", "archived_at", "superseded_by", "metadata", "updated_at"]
                )
        return snapshot, True

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

    def _archive_old_events_sync(self, server_id: int, *, now=None) -> int:
        from servers.models import Server, ServerMemoryEvent

        now = now or timezone.now()
        server = Server.objects.filter(pk=server_id).select_related("user").first()
        if server is None:
            return 0
        policy = self._get_or_create_policy_sync(user_id=server.user_id)
        cutoff = now - timedelta(days=max(int(policy.raw_event_retention_days or 30), 1))
        return ServerMemoryEvent.objects.filter(server_id=server_id, is_archived=False, created_at__lt=cutoff).update(
            is_archived=True,
            archived_at=now,
        )

    def _archive_old_episodes_sync(self, server_id: int, *, now=None) -> int:
        from servers.models import Server, ServerMemoryEpisode

        now = now or timezone.now()
        server = Server.objects.filter(pk=server_id).select_related("user").first()
        if server is None:
            return 0
        policy = self._get_or_create_policy_sync(user_id=server.user_id)
        cutoff = now - timedelta(days=max(int(policy.episode_retention_days or 90), 1))
        return ServerMemoryEpisode.objects.filter(server_id=server_id, is_active=True, last_event_at__lt=cutoff).update(
            is_active=False,
            archived_at=now,
        )

    @staticmethod
    def _is_sleep_window_open(policy, *, now=None) -> bool:
        now = now or timezone.localtime()
        start = int(policy.sleep_start_hour or 0) % 24
        end = int(policy.sleep_end_hour or 0) % 24
        hour = now.hour
        if start == end:
            return True
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end

    def _server_recently_busy_sync(self, server_id: int, *, minutes: int = 20) -> bool:
        from servers.models import ServerMemoryEvent

        cutoff = timezone.now() - timedelta(minutes=max(int(minutes), 1))
        return ServerMemoryEvent.objects.filter(server_id=server_id, created_at__gte=cutoff, is_archived=False).exclude(
            source_kind="manual_knowledge"
        ).exists()

    def _should_skip_scheduled_dream_sync(self, server_id: int, *, policy, job_kind: str) -> str:
        if not bool(getattr(policy, "is_enabled", True)):
            return "disabled_by_policy"
        if job_kind == "nearline":
            return ""
        if not self._is_sleep_window_open(policy):
            return "outside_sleep_window"
        if job_kind in {"nightly", "hybrid"} and self._server_recently_busy_sync(server_id):
            return "server_recently_active"
        return ""

    def _run_dream_cycle_sync(
        self,
        server_id: int,
        *,
        job_kind: str = "hybrid",
        respect_schedule: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        from servers.models import Server

        server = Server.objects.filter(pk=server_id).select_related("user").first()
        if server is None:
            return {"server_id": server_id, "skipped": True, "reason": "server_not_found"}
        policy = self._get_or_create_policy_sync(user_id=server.user_id)
        if not force and not bool(getattr(policy, "is_enabled", True)):
            return {
                "server_id": server_id,
                "skipped": True,
                "reason": "disabled_by_policy",
                "compacted_groups": 0,
                "dream": {"updated_notes": 0, "created_versions": 0, "scanned_records": 0},
                "repair": {"updated_records": 0, "created_notes": 0, "archived_records": 0},
            }
        if respect_schedule:
            skip_reason = self._should_skip_scheduled_dream_sync(server_id, policy=policy, job_kind=job_kind)
            if skip_reason:
                return {
                    "server_id": server_id,
                    "skipped": True,
                    "reason": skip_reason,
                    "compacted_groups": 0,
                    "dream": {"updated_notes": 0, "created_versions": 0, "scanned_records": 0},
                    "repair": {"updated_records": 0, "created_notes": 0, "archived_records": 0},
                }
        compacted = self._compact_open_groups_sync(server_id, force=job_kind in {"nearline", "nightly", "hybrid"})
        dream = self._dream_server_memory_sync(server_id, deactivate_noise=job_kind in {"weekly", "hybrid", "nightly"}, job_kind=job_kind)
        repair = self._repair_server_memory_sync(server_id, stale_after_days=30, create_notes=job_kind in {"weekly", "hybrid", "nightly"})
        # Автоматически закрываем устаревшие revalidations после dream
        auto_resolved = auto_resolve_stale_revalidations(server_id, max_age_days=60)
        return {
            "server_id": server_id,
            "skipped": False,
            "reason": "",
            "compacted_groups": compacted,
            "dream": dream,
            "repair": repair,
            "auto_resolved_revalidations": auto_resolved,
        }

    def _get_memory_overview_sync(self, server_id: int) -> dict[str, Any]:
        from servers.models import Server, ServerMemoryEpisode, ServerMemoryRevalidation, ServerMemorySnapshot
        from servers.worker_state import serialize_background_worker_state

        server = Server.objects.filter(pk=server_id).select_related("user").first()
        if server is None:
            return {}
        policy = self._get_or_create_policy_sync(user_id=server.user_id)
        snapshots = list(
            ServerMemorySnapshot.objects.filter(server_id=server_id)
            .select_related("created_by", "superseded_by")
            .order_by("memory_key", "-version", "-updated_at")[:80]
        )
        active = [item for item in snapshots if item.is_active and item.layer == ServerMemorySnapshot.LAYER_CANONICAL]
        archived = [item for item in snapshots if not item.is_active or item.layer == ServerMemorySnapshot.LAYER_ARCHIVE]
        episodes = list(ServerMemoryEpisode.objects.filter(server_id=server_id).order_by("-last_event_at", "-updated_at")[:20])
        revalidations = list(ServerMemoryRevalidation.objects.filter(server_id=server_id).order_by("status", "-updated_at")[:20])
        canonical = [item for item in active if item.memory_key in CANONICAL_MEMORY_KEYS]
        manual = [item for item in active if item.memory_key.startswith(("manual_note:", "knowledge_note:"))]
        patterns = [item for item in active if item.memory_key.startswith(PATTERN_CANDIDATE_PREFIX)]
        automation_candidates = [item for item in active if item.memory_key.startswith(AUTOMATION_CANDIDATE_PREFIX)]
        skill_drafts = [item for item in active if item.memory_key.startswith(SKILL_DRAFT_PREFIX)]
        history_map: dict[str, list[Any]] = {}
        for item in snapshots:
            group_id = str(getattr(item, "version_group_id", "") or "")
            if not group_id:
                continue
            history_map.setdefault(group_id, []).append(item)
        for history_items in history_map.values():
            history_items.sort(key=lambda item: (item.version, item.updated_at or timezone.now()), reverse=True)
        return {
            "server_id": server_id,
            "policy": {
                "dream_mode": policy.dream_mode,
                "nightly_model_alias": policy.nightly_model_alias,
                "nearline_event_threshold": policy.nearline_event_threshold,
                "sleep_start_hour": policy.sleep_start_hour,
                "sleep_end_hour": policy.sleep_end_hour,
                "raw_event_retention_days": policy.raw_event_retention_days,
                "episode_retention_days": policy.episode_retention_days,
                "rdp_semantic_capture_enabled": policy.rdp_semantic_capture_enabled,
                "human_habits_capture_enabled": policy.human_habits_capture_enabled,
                "is_enabled": policy.is_enabled,
            },
            "daemon_state": serialize_background_worker_state("memory_dreams"),
            "worker_states": {
                "memory_dreams": serialize_background_worker_state("memory_dreams"),
                "agent_execution": serialize_background_worker_state("agent_execution"),
                "watchers": serialize_background_worker_state("watchers"),
            },
            "canonical": [self._serialize_snapshot(item, history_items=history_map.get(item.version_group_id, [])) for item in canonical],
            "manual": [self._serialize_snapshot(item, history_items=history_map.get(item.version_group_id, [])) for item in manual],
            "patterns": [self._serialize_snapshot(item, history_items=history_map.get(item.version_group_id, [])) for item in patterns],
            "automation_candidates": [
                self._serialize_snapshot(item, history_items=history_map.get(item.version_group_id, []))
                for item in automation_candidates
            ],
            "skill_drafts": [self._serialize_snapshot(item, history_items=history_map.get(item.version_group_id, [])) for item in skill_drafts],
            "revalidation": [self._serialize_revalidation(item) for item in revalidations],
            "episodes": [self._serialize_episode(item) for item in episodes if item.is_active],
            "archive": [
                *[
                    self._serialize_snapshot(item, history_items=history_map.get(item.version_group_id, [])) | {"kind": "snapshot"}
                    for item in archived[:20]
                ],
                *[self._serialize_episode(item) | {"kind": "episode"} for item in episodes if not item.is_active][:12],
            ],
            "stats": {
                "canonical": len(canonical),
                "manual": len(manual),
                "patterns": len(patterns),
                "automation_candidates": len(automation_candidates),
                "skill_drafts": len(skill_drafts),
                "revalidation_open": len([item for item in revalidations if item.status == "open"]),
                "episodes": len([item for item in episodes if item.is_active]),
                "archive": len(archived) + len([item for item in episodes if not item.is_active]),
            },
        }

    def _sync_manual_knowledge_snapshot_sync(self, knowledge_id: int) -> str:
        from servers.models import ServerKnowledge

        knowledge = ServerKnowledge.objects.select_related("server").filter(pk=knowledge_id).first()
        if knowledge is None:
            return ""
        prefix = "manual_note" if knowledge.source == "manual" else "knowledge_note"
        memory_key = f"{prefix}:{knowledge.id}"
        if not knowledge.is_active:
            self._archive_manual_knowledge_snapshot_sync(knowledge.id)
            self._ingest_event_sync(
                knowledge.server_id,
                source_kind="manual_knowledge",
                actor_kind="human",
                source_ref=f"knowledge:{knowledge.id}",
                session_id="",
                event_type="manual_note_disabled",
                raw_text=f"{knowledge.title}\n{knowledge.content}",
                structured_payload={"knowledge_id": knowledge.id, "category": knowledge.category, "memory_key": memory_key, "is_active": False},
                importance_hint=0.55,
                actor_user_id=knowledge.created_by_id,
            )
            return ""
        snapshot, _created = self._upsert_snapshot_sync(
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
            metadata={"category": knowledge.category, "knowledge_id": knowledge.id},
            version_group_id=f"{prefix.replace('_', '-')}-{knowledge.id}",
            force_version=True,
        )
        self._ingest_event_sync(
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

    def _archive_manual_knowledge_snapshot_sync(self, knowledge_id: int) -> int:
        from servers.models import ServerMemorySnapshot

        return ServerMemorySnapshot.objects.filter(memory_key__in=[f"manual_note:{knowledge_id}", f"knowledge_note:{knowledge_id}"], is_active=True).update(
            is_active=False,
            layer=ServerMemorySnapshot.LAYER_ARCHIVE,
            archived_at=timezone.now(),
        )

    @staticmethod
    def _is_manual_bridge_memory_key(memory_key: str) -> bool:
        return str(memory_key or "").startswith(("manual_note:", "knowledge_note:"))

    @staticmethod
    def _parse_trailing_int(value: Any, *, prefix: str | None = None) -> int | None:
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

    def _snapshot_linked_knowledge_id(self, snapshot) -> int | None:
        metadata = getattr(snapshot, "metadata", None) or {}
        for key in ("knowledge_id", "promoted_knowledge_id"):
            parsed = self._parse_trailing_int(metadata.get(key))
            if parsed:
                return parsed

        source_ref = str(getattr(snapshot, "source_ref", "") or "").strip()
        parsed = self._parse_trailing_int(source_ref, prefix="knowledge:")
        if parsed:
            return parsed

        memory_key = str(getattr(snapshot, "memory_key", "") or "")
        for prefix in ("manual_note:", "knowledge_note:"):
            parsed = self._parse_trailing_int(memory_key, prefix=prefix)
            if parsed:
                return parsed
        return None

    def _has_active_user_ai_snapshots_sync(self, server_id: int) -> bool:
        from servers.models import ServerMemorySnapshot

        return (
            ServerMemorySnapshot.objects.filter(server_id=server_id, is_active=True, archived_at__isnull=True)
            .exclude(memory_key__startswith="manual_note:")
            .exclude(memory_key__startswith="knowledge_note:")
            .exists()
        )

    def _hard_delete_snapshot_sync(
        self,
        server_id: int,
        snapshot_id: int,
        *,
        actor_user_id: int | None = None,
    ) -> dict[str, Any]:
        from servers.models import ServerKnowledge, ServerMemoryRevalidation, ServerMemorySnapshot

        snapshot = (
            ServerMemorySnapshot.objects.select_related("server")
            .filter(pk=snapshot_id, server_id=server_id)
            .first()
        )
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
        linked_knowledge_id = self._snapshot_linked_knowledge_id(snapshot)
        linked_bridge_keys: list[str] = []
        if linked_knowledge_id:
            linked_bridge_keys = [
                f"manual_note:{linked_knowledge_id}",
                f"knowledge_note:{linked_knowledge_id}",
            ]

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
                deleted_snapshots += ServerMemorySnapshot.objects.filter(
                    server_id=server_id,
                    memory_key__in=linked_bridge_keys,
                ).exclude(id__in=snapshot_ids).delete()[0]
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

    def _purge_server_ai_memory_sync(
        self,
        server_id: int,
        *,
        actor_user_id: int | None = None,
    ) -> dict[str, Any]:
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
            "overview": self._get_memory_overview_sync(server_id),
        }

    def _archive_snapshot_sync(
        self,
        server_id: int,
        snapshot_id: int,
        *,
        actor_user_id: int | None = None,
        reason: str = "manual_archive",
    ) -> dict[str, Any]:
        from servers.models import ServerMemorySnapshot

        snapshot = (
            ServerMemorySnapshot.objects.select_related("server")
            .filter(pk=snapshot_id, server_id=server_id)
            .first()
        )
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
            self._ingest_event_sync(
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
        return self._serialize_snapshot(snapshot)

    def _promote_snapshot_to_manual_knowledge_sync(
        self,
        server_id: int,
        snapshot_id: int,
        *,
        actor_user_id: int,
    ) -> dict[str, Any]:
        from servers.models import ServerKnowledge, ServerMemorySnapshot

        snapshot = (
            ServerMemorySnapshot.objects.select_related("server")
            .filter(pk=snapshot_id, server_id=server_id)
            .first()
        )
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
                category=self._knowledge_category_for_snapshot(snapshot),
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
            self._sync_manual_knowledge_snapshot_sync(knowledge.id)
            self._ingest_event_sync(
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

        archived_snapshot = self._archive_snapshot_sync(
            server_id,
            snapshot_id,
            actor_user_id=actor_user_id,
            reason="promoted_to_manual_note",
        )
        return {
            "knowledge_id": knowledge.id,
            "knowledge_title": knowledge.title,
            "snapshot": archived_snapshot,
            "overview": self._get_memory_overview_sync(server_id),
        }

    def _promote_skill_draft_to_skill_sync(
        self,
        server_id: int,
        snapshot_id: int,
        *,
        actor_user_id: int,
    ) -> dict[str, Any]:
        from django.contrib.auth.models import User

        from servers.models import ServerKnowledge, ServerMemorySnapshot
        from studio.models import StudioSkillAccess
        from studio.skill_authoring import scaffold_skill, slugify_skill_name, validate_skill_dir
        from studio.skill_registry import SkillNotFoundError, get_skill

        snapshot = (
            ServerMemorySnapshot.objects.select_related("server")
            .filter(pk=snapshot_id, server_id=server_id)
            .first()
        )
        if snapshot is None:
            raise ValueError("Memory snapshot not found")
        if not str(snapshot.memory_key or "").startswith(SKILL_DRAFT_PREFIX):
            raise ValueError("Selected snapshot is not a skill draft")

        user = User.objects.filter(pk=actor_user_id, is_active=True).first()
        if user is None:
            raise ValueError("User not found")

        metadata = dict(snapshot.metadata or {})
        existing_slug = str(metadata.get("promoted_skill_slug") or "").strip()
        skill = None
        if existing_slug:
            try:
                skill = get_skill(existing_slug)
            except SkillNotFoundError:
                skill = None

        validation_payload = None
        if skill is None:
            suffix = str(snapshot.memory_key or "").split(":", 1)[-1]
            intent = str(metadata.get("intent") or "ops").strip().lower() or "ops"
            skill_name = f"{snapshot.server.name} {intent.replace('_', ' ').title()} Ops"
            requested_slug = slugify_skill_name(f"{snapshot.server.name}-{intent}-{suffix[:8]}")
            description = (
                f"Автосгенерированный operational skill на основе повторяющегося паттерна "
                f"`{metadata.get('display_command') or snapshot.title}` для сервера {snapshot.server.name}."
            )
            recommended_tools = ["read_console", "ssh_execute", "report"]
            runtime_policy = {}
            if self._looks_mutating_command(str(metadata.get("display_command") or snapshot.content)):
                runtime_policy = {
                    "mutating_tool_patterns": ["ssh_execute"],
                    "required_preflight_tools": ["read_console"],
                    "auto_inject_pinned_arguments": True,
                }
            skill_dir = scaffold_skill(
                name=skill_name,
                description=description,
                slug=requested_slug,
                service=snapshot.server.name,
                category=intent,
                safety_level="high" if runtime_policy else "standard",
                ui_hint="server_ops",
                tags=["auto-generated", "server-memory", intent],
                guardrail_summary=[
                    "Resolve the target server before mutation.",
                    "Run verification after every change.",
                    "Do not expose secrets from command output.",
                ],
                recommended_tools=recommended_tools,
                runtime_policy=runtime_policy,
                with_scripts=False,
                with_references=False,
                with_assets=False,
                force=False,
            )
            skill_file = skill_dir / "SKILL.md"
            existing_content = skill_file.read_text(encoding="utf-8")
            workflow_commands = [str(item).strip() for item in (metadata.get("commands") or []) if str(item).strip()]
            workflow_section = ""
            if workflow_commands:
                workflow_section = "\n\n## Derived Workflow\n\n" + "\n".join(
                    f"{index}. `{command}`" for index, command in enumerate(workflow_commands[:6], start=1)
                )
            success_signals = [str(item).strip() for item in (metadata.get("sample_outputs") or []) if str(item).strip()]
            success_signal_section = ""
            if success_signals:
                success_signal_section = "\n\n## Success Signals\n\n" + "\n".join(
                    f"- {compact_text(item, limit=180)}" for item in success_signals[:4]
                )
            cwd_section = ""
            common_cwds = [str(item).strip() for item in (metadata.get("common_cwds") or []) if str(item).strip()]
            if common_cwds:
                cwd_section = "\n\n## Typical Working Directories\n\n" + "\n".join(
                    f"- `{compact_text(item, limit=160)}`" for item in common_cwds[:3]
                )
            skill_file.write_text(
                existing_content.rstrip()
                + "\n\n## Derived Draft\n\n"
                + snapshot.content.strip()
                + workflow_section
                + success_signal_section
                + cwd_section
                + "\n\n## Source Signal\n\n"
                + f"- Server: {snapshot.server.name} ({snapshot.server.host})\n"
                + f"- Memory key: {snapshot.memory_key}\n"
                + f"- Display command: {metadata.get('display_command') or 'n/a'}\n"
                + f"- Intent: {metadata.get('intent') or 'ops'}\n",
                encoding="utf-8",
            )
            validation = validate_skill_dir(skill_dir)
            validation_payload = validation.to_dict()
            if validation.errors:
                raise ValueError("Generated skill draft failed validation")
            try:
                skill = get_skill(skill_dir.name)
            except SkillNotFoundError as exc:
                raise ValueError("Generated skill could not be loaded") from exc
            access, _created = StudioSkillAccess.objects.get_or_create(
                slug=skill.slug,
                defaults={"owner": user},
            )
            if access.owner_id is None:
                access.owner = user
                access.save(update_fields=["owner"])
            metadata["promoted_skill_slug"] = skill.slug
            metadata["promoted_skill_path"] = skill.path
            metadata["promoted_to_skill_at"] = timezone.now().isoformat()
            snapshot.metadata = metadata
            snapshot.save(update_fields=["metadata", "updated_at"])
            self._ingest_event_sync(
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
        knowledge_content = self._build_skill_memory_note_content(snapshot, metadata, skill)
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
        self._sync_manual_knowledge_snapshot_sync(knowledge.id)

        archived_snapshot = self._archive_snapshot_sync(
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
            "validation": validation_payload or {"slug": skill.slug, "path": skill.path, "errors": [], "warnings": [], "is_valid": True},
            "overview": self._get_memory_overview_sync(server_id),
        }

    @staticmethod
    def _knowledge_category_for_snapshot(snapshot) -> str:
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

    def _serialize_snapshot(self, item, *, history_items: list[Any] | None = None) -> dict[str, Any]:
        metadata = item.metadata or {}
        return {
            "id": item.id,
            "memory_key": item.memory_key,
            "title": item.title,
            "content": item.content,
            "source_kind": item.source_kind,
            "source_ref": item.source_ref,
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
            "rewrite_reason": self._snapshot_rewrite_reason(item),
            "prior_snapshot_id": metadata.get("prior_snapshot_id"),
            "prior_version": metadata.get("prior_version"),
            "action_summary": self._snapshot_action_summary(item),
            "created_by_username": getattr(getattr(item, "created_by", None), "username", None),
            "history": [self._serialize_snapshot_history_item(history_item) for history_item in (history_items or [])[:6]],
        }

    @staticmethod
    def _serialize_episode(item) -> dict[str, Any]:
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

    @staticmethod
    def _serialize_revalidation(item) -> dict[str, Any]:
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
        }

    @staticmethod
    def _serialize_snapshot_history_item(item) -> dict[str, Any]:
        return {
            "id": item.id,
            "title": item.title,
            "version": item.version,
            "is_active": item.is_active,
            "source_kind": item.source_kind,
            "source_ref": item.source_ref,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            "archived_at": item.archived_at.isoformat() if item.archived_at else None,
            "rewrite_reason": DjangoServerMemoryStore._snapshot_rewrite_reason(item),
            "action_summary": DjangoServerMemoryStore._snapshot_action_summary(item),
            "created_by_username": getattr(getattr(item, "created_by", None), "username", None),
            "content_preview": compact_text(item.content, limit=220) if getattr(item, "content", "") else None,
        }

    @staticmethod
    def _snapshot_rewrite_reason(item) -> str | None:
        metadata = getattr(item, "metadata", None) or {}
        reason = str(metadata.get("rewrite_reason") or metadata.get("superseded_reason") or "").strip()
        return reason or None

    @staticmethod
    def _snapshot_action_summary(item) -> str | None:
        metadata = getattr(item, "metadata", None) or {}
        promoted_skill_slug = str(metadata.get("promoted_skill_slug") or "").strip()
        promoted_knowledge_id = metadata.get("promoted_knowledge_id")
        archived_reason = str(metadata.get("archived_reason") or "").strip()
        promoted_to_skill_at = str(metadata.get("promoted_to_skill_at") or "").strip()
        promoted_to_manual_at = str(metadata.get("promoted_to_manual_at") or "").strip()
        rewrite_reason = DjangoServerMemoryStore._snapshot_rewrite_reason(item)
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

    @staticmethod
    def _describe_snapshot_rewrite(
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

    @staticmethod
    def _build_skill_memory_note_content(snapshot, metadata: dict[str, Any], skill) -> str:
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

    @staticmethod
    def _try_parse_list_literal(raw: str) -> list[str] | None:
        text = str(raw or "").strip()
        if not text or not (text.startswith("[") and text.endswith("]")):
            return None
        for loader in (json.loads, ast.literal_eval):
            try:
                parsed = loader(text)
            except Exception:
                continue
            if isinstance(parsed, (list, tuple)):
                return [str(item) for item in parsed if str(item or "").strip()]
        return None

    @classmethod
    def _normalize_snapshot_lines(cls, value: Any, *, limit: int = 6) -> list[str]:
        pending = list(value) if isinstance(value, (list, tuple, set)) else [value]
        normalized: list[str] = []
        while pending:
            current = pending.pop(0)
            if isinstance(current, (list, tuple, set)):
                pending = list(current) + pending
                continue
            raw = str(current or "").strip()
            if not raw:
                continue
            parsed_lines = cls._try_parse_list_literal(raw)
            if parsed_lines is not None:
                pending = parsed_lines + pending
                continue
            for line in raw.splitlines():
                cleaned = compact_text(str(line).lstrip("- ").strip(), limit=220)
                if cleaned:
                    normalized.append(cleaned)
        return unique_preserving_order(normalized, limit=limit)

    @classmethod
    def _render_snapshot_lines(cls, lines: Any, *, fallback: str) -> str:
        normalized = cls._normalize_snapshot_lines(lines, limit=6)
        if not normalized:
            normalized = [fallback]
        return "\n".join(f"- {line}" for line in normalized[:6])

    @staticmethod
    def _tokenize_shell_command(command: str) -> list[str]:
        try:
            return shlex.split(str(command or ""))
        except Exception:
            return str(command or "").split()

    @classmethod
    def _docker_run_summary(cls, command: str) -> dict[str, Any]:
        tokens = cls._tokenize_shell_command(command)
        if len(tokens) < 2 or tokens[0] != "docker" or tokens[1] != "run":
            return {}
        name = ""
        image = ""
        published_ports: list[str] = []
        skip_next = False
        for index in range(2, len(tokens)):
            token = tokens[index]
            if skip_next:
                skip_next = False
                continue
            if token in {"--name", "-p", "--publish", "-v", "--volume", "-e", "--env", "--network", "--restart", "-w", "--workdir"}:
                if index + 1 < len(tokens):
                    value = tokens[index + 1]
                    if token == "--name":
                        name = value
                    if token in {"-p", "--publish"}:
                        published_ports.append(value)
                skip_next = True
                continue
            if token.startswith("--name="):
                name = token.split("=", 1)[1]
                continue
            if token.startswith("--publish="):
                published_ports.append(token.split("=", 1)[1])
                continue
            if token.startswith("-p") and token != "-p":
                published_ports.append(token[2:])
                continue
            if token.startswith("-"):
                continue
            image = token
            break
        return {
            "name": compact_text(name, limit=80),
            "image": compact_text(image, limit=80),
            "ports": [compact_text(item, limit=80) for item in published_ports if str(item or "").strip()],
        }

    @staticmethod
    def _extract_published_ports(blob: str) -> list[str]:
        matches = re.findall(r"(?:[\[\]0-9a-fA-F\.:]*:)?(\d+)->(\d+)\/([a-z]+)", str(blob or ""))
        return unique_preserving_order([f"{host}->{container}/{proto}" for host, container, proto in matches], limit=4)

    @classmethod
    def _derive_recent_event_points(cls, events: list[Any]) -> dict[str, list[str]]:
        access_points: list[str] = []
        change_points: list[str] = []
        for event in events:
            payload = getattr(event, "structured_payload", None) or {}
            command = str(payload.get("command") or "").strip()
            if not command:
                continue
            command_lower = command.lower()
            output_markers = cls._event_output_markers(event)
            published_ports = cls._extract_published_ports("\n".join(output_markers))

            if command_lower.startswith("docker run "):
                summary = cls._docker_run_summary(command)
                image = summary.get("image") or "unknown image"
                container_label = summary.get("name") or image
                ports = summary.get("ports") or published_ports
                port_text = ""
                if ports:
                    normalized_ports = [item.replace("/tcp", "") for item in ports]
                    port_text = "; опубликованы порты " + ", ".join(normalized_ports[:2])
                    access_points.append(
                        f"Docker publish: {container_label} доступен через {', '.join(normalized_ports[:2])}"
                    )
                change_points.append(f"Запущен контейнер {container_label} из {image}{port_text}")
                continue

            if "docker compose up" in command_lower:
                change_points.append(f"Выполнен rollout через `{compact_text(command, limit=120)}`")
                if published_ports:
                    access_points.append("После compose подтверждены опубликованные порты: " + ", ".join(published_ports[:2]))
                continue

            if command_lower.startswith("docker rm ") or command_lower.startswith("docker rm -f"):
                target = cls._tokenize_shell_command(command)[-1] if cls._tokenize_shell_command(command) else "container"
                change_points.append(f"Удалён контейнер {compact_text(target, limit=80)}")
                continue

            if "systemctl restart nginx" in command_lower:
                change_points.append("Выполнен restart nginx")
                continue

            if "systemctl reload nginx" in command_lower:
                change_points.append("Выполнен reload nginx")
                continue

            if command_lower.startswith("docker ps") and published_ports:
                access_points.append("docker ps подтверждает опубликованные порты: " + ", ".join(published_ports[:2]))

        return {
            "access": unique_preserving_order(access_points, limit=4),
            "recent_changes": unique_preserving_order(change_points, limit=6),
        }

    @staticmethod
    def _content_delta(old_content: str, new_content: str) -> float:
        old_lines = {line.strip().lower() for line in str(old_content or "").splitlines() if line.strip()}
        new_lines = {line.strip().lower() for line in str(new_content or "").splitlines() if line.strip()}
        if not old_lines and not new_lines:
            return 0.0
        if not old_lines or not new_lines:
            return 1.0
        return 1.0 - (len(old_lines & new_lines) / max(len(old_lines | new_lines), 1))

    @staticmethod
    def _guess_memory_key(*, title: str, category: str | None, content: str) -> str:
        blob = f"{title}\n{category or ''}\n{content}".lower()
        if any(term in blob for term in ("vpn", "bastion", "jump host", "gateway", "ssh ", "sudo")):
            return "access"
        if any(term in blob for term in ("risk", "issue", "critical", "warning", "degrad", "incident", "alert", "fail")):
            return "risks"
        if any(term in blob for term in ("runbook", "checklist", "command", "verify", "systemctl", "docker", "journalctl")):
            return "runbook"
        if any(term in blob for term in ("change", "updated", "deployed", "restart", "reload", "migrat")):
            return "recent_changes"
        if category in {"security", "network"}:
            return "access"
        if category in {"issues", "performance", "storage"}:
            return "risks"
        if category == "solutions":
            return "runbook"
        return "profile"
