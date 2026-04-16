"""
app/agent_kernel/memory/dreams.py

Target module for the memory dream/compaction cycle (T-014).
Will contain the following methods extracted from DjangoServerMemoryStore:
  - _dream_server_memory_sync        (line ~1267 in store.py)
  - _build_snapshot_candidates       (line ~1377)
  - _derive_human_habits             (line ~1526)
  - _derive_runbook_patterns         (line ~1558)
  - _derive_operational_patterns     (line ~1585)
  - _derive_sequence_patterns        (line ~1697)
  - _promote_pattern_candidates_sync (line ~1896)
  - _run_dream_cycle_sync            (line ~2771)
  - _dream_server_memory_sync        (entry point)
  - _should_skip_scheduled_dream_sync
  - _is_sleep_window_open
  - _server_recently_busy_sync

Migration plan:
1. Extract into DreamsMixin class here
2. DjangoServerMemoryStore inherits DreamsMixin
3. Remove methods from store.py
4. Run: pytest tests/test_ops_agent_kernel.py after each step
"""
