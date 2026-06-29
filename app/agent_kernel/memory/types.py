from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


@dataclass(frozen=True)
class SnapshotCandidate:
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
class OperationalPattern:
    pattern_kind: str
    display_command: str
    normalized_command: str
    intent: str
    intent_label: str
    commands: tuple[str, ...]
    occurrences: int
    successful_runs: int
    measured_runs: int
    success_rate: float | None
    actor_kinds: tuple[str, ...]
    source_kinds: tuple[str, ...]
    verification_rate: float = 0.0
    has_verification_step: bool = False
    sample_outputs: tuple[str, ...] = ()
    common_cwds: tuple[str, ...] = ()
    distinct_sessions: int = 0
    last_seen: Any | None = None
