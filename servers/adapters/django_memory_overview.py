from __future__ import annotations

from typing import Any

from django.utils import timezone

from app.agent_kernel.memory.types import (
    AUTOMATION_CANDIDATE_PREFIX,
    CANONICAL_MEMORY_KEYS,
    PATTERN_CANDIDATE_PREFIX,
    SKILL_DRAFT_PREFIX,
)
from servers.adapters.django_memory_serializers import serialize_episode, serialize_revalidation, serialize_snapshot


def build_memory_overview_payload(server_id: int, policy: Any) -> dict[str, Any]:
    from servers.models import ServerMemoryEpisode, ServerMemoryRevalidation, ServerMemorySnapshot
    from servers.worker_state import serialize_background_worker_state

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
        "canonical": [serialize_snapshot(item, history_items=history_map.get(item.version_group_id, [])) for item in canonical],
        "manual": [serialize_snapshot(item, history_items=history_map.get(item.version_group_id, [])) for item in manual],
        "patterns": [serialize_snapshot(item, history_items=history_map.get(item.version_group_id, [])) for item in patterns],
        "automation_candidates": [
            serialize_snapshot(item, history_items=history_map.get(item.version_group_id, []))
            for item in automation_candidates
        ],
        "skill_drafts": [serialize_snapshot(item, history_items=history_map.get(item.version_group_id, [])) for item in skill_drafts],
        "revalidation": [serialize_revalidation(item) for item in revalidations],
        "episodes": [serialize_episode(item) for item in episodes if item.is_active],
        "archive": [
            *[
                serialize_snapshot(item, history_items=history_map.get(item.version_group_id, [])) | {"kind": "snapshot"}
                for item in archived[:20]
            ],
            *[serialize_episode(item) | {"kind": "episode"} for item in episodes if not item.is_active][:12],
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
