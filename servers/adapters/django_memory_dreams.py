from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone

from app.agent_kernel.memory.trust import TRUST_LLM_DISTILLED, VERIFICATION_NEEDS_REVALIDATION
from app.agent_kernel.memory.types import SNAPSHOT_FALLBACKS
from servers.adapters.django_memory_repair import auto_resolve_stale_revalidations


def dream_server_memory(store: Any, server_id: int, *, deactivate_noise: bool = True, job_kind: str = "hybrid") -> dict:
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

    store._compact_open_groups_sync(server_id, force=True)

    episodes = list(
        ServerMemoryEpisode.objects.filter(server_id=server_id, is_active=True).order_by(
            "-last_event_at", "-updated_at"
        )[:18]
    )
    snapshots = list(
        ServerMemorySnapshot.objects.filter(
            server_id=server_id, is_active=True, layer=ServerMemorySnapshot.LAYER_CANONICAL
        ).order_by("memory_key", "-version", "-updated_at")
    )
    latest_health = ServerHealthCheck.objects.filter(server_id=server_id).order_by("-checked_at").first()
    active_alerts = list(ServerAlert.objects.filter(server_id=server_id, is_resolved=False).order_by("-created_at")[:8])
    revalidation_items = list(
        ServerMemoryRevalidation.objects.filter(
            server_id=server_id, status=ServerMemoryRevalidation.STATUS_OPEN
        ).order_by("-updated_at")[:6]
    )
    recent_events = list(
        ServerMemoryEvent.objects.filter(server_id=server_id, is_archived=False).order_by("-created_at")[:24]
    )
    policy = store._get_or_create_policy_sync(user_id=server.user_id)
    patterns = store._derive_operational_patterns(server.id)

    candidates = store._build_snapshot_candidates(
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
    distillation_logs: list[Any] = []
    if (
        job_kind in {"nightly", "hybrid"}
        and policy.dream_mode in {policy.DREAM_HYBRID, policy.DREAM_NIGHTLY_LLM}
        and store._should_distill_with_llm(candidates, snapshots)
    ):
        llm_sections = store._distill_with_llm_sync(
            server=server,
            candidates=candidates,
            model_alias=policy.nightly_model_alias,
            generation_log_out=distillation_logs,
        )

    updated = 0
    created_versions = 0
    llm_review_candidates = 0
    distillation_log = distillation_logs[-1] if distillation_logs else None
    review_required_keys = {"risks", "runbook", "human_habits"}
    for candidate in candidates:
        llm_content = llm_sections.get(candidate.memory_key)
        if llm_content and candidate.memory_key in review_required_keys:
            candidate_content = store._sanitize_canonical_content(
                candidate.memory_key,
                llm_content,
                fallback=SNAPSHOT_FALLBACKS.get(candidate.memory_key, candidate.content),
            )
            review_snapshot, review_created = store._upsert_snapshot_sync(
                server_id=server_id,
                memory_key=f"llm_candidate:{candidate.memory_key}",
                title=f"LLM Review Candidate: {candidate.title}",
                content=candidate_content,
                source_kind="dream",
                source_ref=f"generation:{distillation_log.pk}" if distillation_log else "",
                importance_score=candidate.importance_score,
                stability_score=candidate.stability_score,
                confidence=min(float(candidate.confidence or 0.0), 0.7),
                metadata={
                    **(candidate.metadata or {}),
                    "candidate_requires_review": True,
                    "trust_level": TRUST_LLM_DISTILLED,
                    "verification_status": VERIFICATION_NEEDS_REVALIDATION,
                    "original_memory_key": candidate.memory_key,
                    "generation_log_id": distillation_log.pk if distillation_log else None,
                },
                layer=ServerMemorySnapshot.LAYER_CANDIDATE,
                generation_log=distillation_log,
            )
            store._ensure_revalidation_sync(
                server_id,
                memory_key=review_snapshot.memory_key,
                title=review_snapshot.title,
                reason="LLM-derived operational memory requires authorized human approval.",
                payload={
                    "snapshot_id": review_snapshot.pk,
                    "original_memory_key": candidate.memory_key,
                    "generation_log_id": distillation_log.pk if distillation_log else None,
                },
                source_snapshot=review_snapshot,
            )
            llm_review_candidates += 1
            if review_created:
                created_versions += 1

        raw_content = (
            llm_content if llm_content and candidate.memory_key not in review_required_keys else candidate.content
        )
        canonical_metadata = dict(candidate.metadata or {})
        if llm_content and candidate.memory_key not in review_required_keys:
            canonical_metadata.update(
                {
                    "derivation_kind": TRUST_LLM_DISTILLED,
                    "generation_log_id": distillation_log.pk if distillation_log else None,
                    "derived_from_trust_level": canonical_metadata.get("trust_level"),
                }
            )
        safe_content = store._sanitize_canonical_content(
            candidate.memory_key,
            raw_content,
            fallback=SNAPSHOT_FALLBACKS.get(candidate.memory_key, candidate.content),
        )
        _snapshot, created = store._upsert_snapshot_sync(
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
            metadata=canonical_metadata,
            generation_log=(
                distillation_log if llm_content and candidate.memory_key not in review_required_keys else None
            ),
        )
        updated += 1
        if created:
            created_versions += 1

    pattern_enhancements: dict[str, dict[str, Any]] = {}
    pattern_generation_logs: list[Any] = []
    if job_kind in {"nightly", "hybrid"} and policy.dream_mode in {policy.DREAM_HYBRID, policy.DREAM_NIGHTLY_LLM}:
        pattern_enhancements = store._llm_enhance_patterns_sync(
            server=server,
            patterns=patterns,
            model_alias=policy.nightly_model_alias,
            generation_log_out=pattern_generation_logs,
        )

    candidate_result = store._promote_pattern_candidates_sync(
        server_id=server_id,
        patterns=patterns,
        snapshots=snapshots,
        enhancements=pattern_enhancements,
        generation_log=pattern_generation_logs[-1] if pattern_generation_logs else None,
    )

    if deactivate_noise:
        store._archive_old_events_sync(server_id)
    return {
        "server_id": server_id,
        "updated_notes": updated,
        "created_versions": created_versions,
        "scanned_records": len(episodes),
        "pattern_candidates": candidate_result["pattern_candidates"],
        "automation_candidates": candidate_result["automation_candidates"],
        "skill_drafts": candidate_result["skill_drafts"],
        "llm_review_candidates": llm_review_candidates,
    }


def archive_old_events(store: Any, server_id: int, *, now=None) -> int:
    from servers.models import Server, ServerMemoryEvent

    now = now or timezone.now()
    server = Server.objects.filter(pk=server_id).select_related("user").first()
    if server is None:
        return 0
    policy = store._get_or_create_policy_sync(user_id=server.user_id)
    cutoff = now - timedelta(days=max(int(policy.raw_event_retention_days or 30), 1))
    return ServerMemoryEvent.objects.filter(server_id=server_id, is_archived=False, created_at__lt=cutoff).update(
        is_archived=True,
        archived_at=now,
    )


def archive_old_episodes(store: Any, server_id: int, *, now=None) -> int:
    from servers.models import Server, ServerMemoryEpisode

    now = now or timezone.now()
    server = Server.objects.filter(pk=server_id).select_related("user").first()
    if server is None:
        return 0
    policy = store._get_or_create_policy_sync(user_id=server.user_id)
    cutoff = now - timedelta(days=max(int(policy.episode_retention_days or 90), 1))
    return ServerMemoryEpisode.objects.filter(server_id=server_id, is_active=True, last_event_at__lt=cutoff).update(
        is_active=False,
        archived_at=now,
    )


def is_sleep_window_open(policy: Any, *, now=None) -> bool:
    now = now or timezone.localtime()
    start = int(policy.sleep_start_hour or 0) % 24
    end = int(policy.sleep_end_hour or 0) % 24
    hour = now.hour
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def server_recently_busy(server_id: int, *, minutes: int = 20) -> bool:
    from servers.models import ServerMemoryEvent

    cutoff = timezone.now() - timedelta(minutes=max(int(minutes), 1))
    return (
        ServerMemoryEvent.objects.filter(server_id=server_id, created_at__gte=cutoff, is_archived=False)
        .exclude(source_kind="manual_knowledge")
        .exists()
    )


def should_skip_scheduled_dream(store: Any, server_id: int, *, policy: Any, job_kind: str) -> str:
    if not bool(getattr(policy, "is_enabled", True)):
        return "disabled_by_policy"
    if job_kind == "nearline":
        return ""
    if not is_sleep_window_open(policy):
        return "outside_sleep_window"
    if job_kind in {"nightly", "hybrid"} and store._server_recently_busy_sync(server_id):
        return "server_recently_active"
    return ""


def run_dream_cycle(
    store: Any,
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
    policy = store._get_or_create_policy_sync(user_id=server.user_id)
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
        skip_reason = store._should_skip_scheduled_dream_sync(server_id, policy=policy, job_kind=job_kind)
        if skip_reason:
            return {
                "server_id": server_id,
                "skipped": True,
                "reason": skip_reason,
                "compacted_groups": 0,
                "dream": {"updated_notes": 0, "created_versions": 0, "scanned_records": 0},
                "repair": {"updated_records": 0, "created_notes": 0, "archived_records": 0},
            }
    compacted = store._compact_open_groups_sync(server_id, force=job_kind in {"nearline", "nightly", "hybrid"})
    dream = store._dream_server_memory_sync(
        server_id, deactivate_noise=job_kind in {"weekly", "hybrid", "nightly"}, job_kind=job_kind
    )
    repair = store._repair_server_memory_sync(
        server_id, stale_after_days=30, create_notes=job_kind in {"weekly", "hybrid", "nightly"}
    )
    return {
        "server_id": server_id,
        "skipped": False,
        "reason": "",
        "compacted_groups": compacted,
        "dream": dream,
        "repair": repair,
        "auto_resolved_revalidations": auto_resolve_stale_revalidations(server_id, max_age_days=60),
    }
