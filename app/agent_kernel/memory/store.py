"""Compatibility exports for the memory package.

Concrete Django-backed memory storage lives in
``servers.adapters.memory_store``. New app-layer code should import contracts
from ``app.agent_kernel.memory.ports`` and pure shared types from
``app.agent_kernel.memory.types``.
"""

from app.agent_kernel.memory.ports import MemoryStore
from app.agent_kernel.memory.types import (
    AUTOMATION_CANDIDATE_PREFIX,
    CANONICAL_MEMORY_KEYS,
    PATTERN_CANDIDATE_PREFIX,
    SKILL_DRAFT_PREFIX,
    SNAPSHOT_FALLBACKS,
    SNAPSHOT_TITLES,
    OperationalPattern,
    SnapshotCandidate,
)

_OperationalPattern = OperationalPattern
_SnapshotCandidate = SnapshotCandidate

__all__ = [
    "AUTOMATION_CANDIDATE_PREFIX",
    "CANONICAL_MEMORY_KEYS",
    "MemoryStore",
    "PATTERN_CANDIDATE_PREFIX",
    "SKILL_DRAFT_PREFIX",
    "SNAPSHOT_FALLBACKS",
    "SNAPSHOT_TITLES",
    "OperationalPattern",
    "SnapshotCandidate",
    "_OperationalPattern",
    "_SnapshotCandidate",
]
