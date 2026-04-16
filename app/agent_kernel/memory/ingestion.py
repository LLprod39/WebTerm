"""
app/agent_kernel/memory/ingestion.py

Target module for memory ingestion logic (T-014).
Will contain the following methods extracted from DjangoServerMemoryStore:
  - _ingest_event_sync
  - _maybe_compact_event_group_sync
  - _event_group_filters
  - _compact_open_groups_sync
  - _compact_group_sync
  - _episode_kind_for_source
  - _episode_title
  - _is_transport_event_type
  - _episode_summary_lines
  - _build_episode_summary
  - _extract_commands
  - _append_run_summary_sync
  - _upsert_server_fact_sync
  - _record_change_sync
  - _record_incident_sync
  - _detect_conflicts_sync

Migration plan:
1. Extract methods into an IngestionMixin class here
2. Make DjangoServerMemoryStore inherit from IngestionMixin
3. Remove methods from store.py class body
4. Ensure tests still pass after each step

Constants shared with ingestion (re-exported from store for backward compat):
"""
from app.agent_kernel.memory.store import (  # noqa: F401
    CANONICAL_MEMORY_KEYS,
    PATTERN_CANDIDATE_PREFIX,
    AUTOMATION_CANDIDATE_PREFIX,
    SKILL_DRAFT_PREFIX,
    SNAPSHOT_TITLES,
    SNAPSHOT_FALLBACKS,
)
