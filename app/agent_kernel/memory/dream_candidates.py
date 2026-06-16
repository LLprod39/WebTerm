from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.agent_kernel.memory.compaction import compact_text
from app.agent_kernel.memory.line_filters import filter_memory_lines, is_runbook_safe_line, looks_like_access_signal
from app.agent_kernel.memory.pattern_utils import derive_human_habits, derive_runbook_patterns
from app.agent_kernel.memory.snapshot_utils import derive_recent_event_points, render_snapshot_lines
from app.agent_kernel.memory.types import CANONICAL_MEMORY_KEYS, SNAPSHOT_TITLES, OperationalPattern, SnapshotCandidate


def build_snapshot_candidates(
    *,
    server,
    episodes: list[Any],
    snapshots: list[Any],
    recent_events: list[Any],
    latest_health,
    active_alerts: list[Any],
    revalidation_items: list[Any],
    allow_human_habits: bool,
    patterns: list[OperationalPattern] | None = None,
    canonical_key_for_snapshot: Callable[[Any], str] | None = None,
    derive_patterns: Callable[[int], list[OperationalPattern]] | None = None,
) -> list[SnapshotCandidate]:
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
    recent_signal_points = derive_recent_event_points(recent_events)
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
        target_key = (
            canonical_key_for_snapshot(snapshot)
            if canonical_key_for_snapshot is not None
            else str(getattr(snapshot, "memory_key", "profile") or "profile")
        )
        if target_key not in manual_points:
            target_key = "profile"
        lines = filter_memory_lines(getattr(snapshot, "content", "") or "", limit=6)
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
        lines = filter_memory_lines(str(item.summary or ""), limit=4)
        if not lines:
            continue
        if item.episode_kind == "terminal_session":
            access_points.extend([line for line in lines if looks_like_access_signal(line)][:2])
            runbook_points.extend([line for line in lines if is_runbook_safe_line(line)][:2])
        elif item.episode_kind == "deploy_operation":
            change_points.extend(lines[:3])
            runbook_points.extend([line for line in lines if is_runbook_safe_line(line)][:2])
        elif item.episode_kind == "incident":
            risk_points.extend(lines[:3])
        elif item.episode_kind == "agent_investigation":
            profile_points.extend(lines[:2])
            runbook_points.extend([line for line in lines if is_runbook_safe_line(line)][:2])
        elif item.episode_kind == "pipeline_operation":
            change_points.extend(lines[:3])

    if patterns is None:
        patterns = derive_patterns(server.id) if derive_patterns is not None else []
    runbook_pattern_points = derive_runbook_patterns(patterns)
    if runbook_pattern_points:
        runbook_points.extend(runbook_pattern_points[:4])
    human_habits_points = derive_human_habits(patterns) if allow_human_habits else []

    return [
        SnapshotCandidate(
            memory_key="profile",
            title=SNAPSHOT_TITLES["profile"],
            content=render_snapshot_lines(profile_points, fallback="Базовый профиль сервера ещё собирается."),
            importance_score=0.92,
            stability_score=0.86,
            confidence=0.84,
            source_kind="dream",
            verified_at=getattr(latest_health, "checked_at", None),
            metadata={"source_snapshot_id": getattr(snapshot_map.get("profile"), "id", None)},
        ),
        SnapshotCandidate(
            memory_key="access",
            title=SNAPSHOT_TITLES["access"],
            content=render_snapshot_lines(access_points, fallback="Сетевой и access-профиль пока не заполнен."),
            importance_score=0.84,
            stability_score=0.8,
            confidence=0.8,
            source_kind="dream",
            metadata={"source_snapshot_id": getattr(snapshot_map.get("access"), "id", None)},
        ),
        SnapshotCandidate(
            memory_key="risks",
            title=SNAPSHOT_TITLES["risks"],
            content=render_snapshot_lines(risk_points, fallback="Критичные активные риски не зафиксированы."),
            importance_score=0.95,
            stability_score=0.52,
            confidence=0.78 if risk_points else 0.7,
            source_kind="dream",
            verified_at=getattr(latest_health, "checked_at", None),
            metadata={"source_snapshot_id": getattr(snapshot_map.get("risks"), "id", None)},
        ),
        SnapshotCandidate(
            memory_key="runbook",
            title=SNAPSHOT_TITLES["runbook"],
            content=render_snapshot_lines(runbook_points, fallback="Runbook пополнится после новых успешных операций."),
            importance_score=0.9,
            stability_score=0.74,
            confidence=0.79,
            source_kind="dream",
            metadata={"source_snapshot_id": getattr(snapshot_map.get("runbook"), "id", None)},
        ),
        SnapshotCandidate(
            memory_key="recent_changes",
            title=SNAPSHOT_TITLES["recent_changes"],
            content=render_snapshot_lines(change_points, fallback="Значимых недавних изменений не зафиксировано."),
            importance_score=0.76,
            stability_score=0.38,
            confidence=0.74,
            source_kind="dream",
            metadata={"source_snapshot_id": getattr(snapshot_map.get("recent_changes"), "id", None)},
        ),
        SnapshotCandidate(
            memory_key="human_habits",
            title=SNAPSHOT_TITLES["human_habits"],
            content=render_snapshot_lines(human_habits_points, fallback="Повторяющиеся ручные привычки пока не выделены."),
            importance_score=0.7,
            stability_score=0.62,
            confidence=0.7 if human_habits_points else 0.55,
            source_kind="dream",
            metadata={"source_snapshot_id": getattr(snapshot_map.get("human_habits"), "id", None)},
        ),
    ]
