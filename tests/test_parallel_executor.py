"""Tests for 4.2 parallel execution grouping (servers/services/parallel_executor.py).

Covers:
1. ``collect_parallel_batch`` — grouping consecutive direct commands.
2. Edge cases: step mode, blocked, confirm, mixed exec modes, limits.
"""

from servers.services.parallel_executor import (
    MAX_PARALLEL_BATCH,
    collect_parallel_batch,
)


def _item(
    *,
    exec_mode: str = "direct",
    status: str = "pending",
    blocked: bool = False,
    requires_confirm: bool = False,
) -> dict:
    return {
        "id": 0,
        "cmd": "echo test",
        "exec_mode": exec_mode,
        "status": status,
        "blocked": blocked,
        "requires_confirm": requires_confirm,
    }


class TestCollectParallelBatch:
    """Grouping logic for parallel execution."""

    def test_two_direct_commands_batched(self):
        plan = [_item(), _item()]
        result = collect_parallel_batch(plan, 0, step_mode=False)
        assert result == [0, 1]

    def test_three_direct_commands_batched(self):
        plan = [_item(), _item(), _item()]
        result = collect_parallel_batch(plan, 0, step_mode=False)
        assert result == [0, 1, 2]

    def test_single_direct_not_batched(self):
        """Single item should fall through to sequential path."""
        plan = [_item()]
        result = collect_parallel_batch(plan, 0, step_mode=False)
        assert result == []

    def test_step_mode_never_batches(self):
        plan = [_item(), _item(), _item()]
        result = collect_parallel_batch(plan, 0, step_mode=True)
        assert result == []

    def test_pty_command_breaks_batch(self):
        plan = [_item(), _item(exec_mode="pty"), _item()]
        result = collect_parallel_batch(plan, 0, step_mode=False)
        assert result == []  # only 1 direct before PTY, not enough

    def test_direct_then_pty_then_direct(self):
        plan = [_item(), _item(), _item(exec_mode="pty"), _item(), _item()]
        result = collect_parallel_batch(plan, 0, step_mode=False)
        assert result == [0, 1]  # batch stops at PTY

    def test_blocked_command_breaks_batch(self):
        plan = [_item(), _item(blocked=True), _item()]
        result = collect_parallel_batch(plan, 0, step_mode=False)
        assert result == []  # only 1 before block

    def test_confirm_breaks_batch(self):
        plan = [_item(), _item(requires_confirm=True), _item()]
        result = collect_parallel_batch(plan, 0, step_mode=False)
        assert result == []

    def test_done_items_skipped_in_batch(self):
        """Already-done items are skipped but don't break the batch."""
        plan = [_item(), _item(status="done"), _item(), _item()]
        result = collect_parallel_batch(plan, 0, step_mode=False)
        assert result == [0, 2, 3]  # skips index 1 (done)

    def test_start_index_offset(self):
        plan = [_item(exec_mode="pty"), _item(), _item(), _item()]
        result = collect_parallel_batch(plan, 1, step_mode=False)
        assert result == [1, 2, 3]

    def test_max_batch_size_enforced(self):
        plan = [_item() for _ in range(MAX_PARALLEL_BATCH + 3)]
        result = collect_parallel_batch(plan, 0, step_mode=False)
        assert len(result) == MAX_PARALLEL_BATCH

    def test_empty_plan(self):
        result = collect_parallel_batch([], 0, step_mode=False)
        assert result == []

    def test_out_of_bounds_index(self):
        plan = [_item()]
        result = collect_parallel_batch(plan, 5, step_mode=False)
        assert result == []

    def test_first_item_pty_returns_empty(self):
        """If the first item at start_index is PTY, return empty."""
        plan = [_item(exec_mode="pty"), _item()]
        result = collect_parallel_batch(plan, 0, step_mode=False)
        assert result == []
