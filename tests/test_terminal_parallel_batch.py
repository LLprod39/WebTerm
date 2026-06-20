from __future__ import annotations

import pytest

from servers.services.terminal_parallel_batch import execute_terminal_parallel_batch


class ParallelBatchHarness:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.snapshots: list[tuple[str, int]] = []
        self.direct_calls: list[tuple[str, int]] = []
        self.history: list[dict] = []
        self.marked: list[tuple[int, int, str]] = []
        self.unavailable: list[str] = []
        self.direct_results: dict[int, tuple[int, str]] = {}

    async def send_event(self, event: dict) -> None:
        self.events.append(event)

    async def snapshot_command(self, command: str, item_id: int) -> None:
        self.snapshots.append((command, item_id))

    async def execute_direct(self, command: str, item_id: int) -> tuple[int, str]:
        self.direct_calls.append((command, item_id))
        if item_id not in self.direct_results:
            return 0, f"out-{item_id}"
        return self.direct_results[item_id]

    async def log_command_history(self, **kwargs) -> None:
        self.history.append(kwargs)

    async def mark_plan_index_done(self, plan_index: int, exit_code: int, output_snippet: str) -> None:
        self.marked.append((plan_index, exit_code, output_snippet))

    def record_unavailable(self, command: str) -> None:
        self.unavailable.append(command)


@pytest.mark.asyncio
async def test_execute_terminal_parallel_batch_runs_and_marks_each_item():
    harness = ParallelBatchHarness()
    items = [
        {"id": 1, "cmd": "df -h", "status": "pending"},
        {"id": 2, "cmd": "free -m", "status": "pending"},
    ]

    await execute_terminal_parallel_batch(
        items=items,
        plan_indices=[0, 1],
        dry_run=False,
        has_ssh_connection=True,
        user_id=10,
        server_id=20,
        send_event=harness.send_event,
        snapshot_command=harness.snapshot_command,
        execute_direct=harness.execute_direct,
        log_command_history=harness.log_command_history,
        mark_plan_index_done=harness.mark_plan_index_done,
        record_unavailable=harness.record_unavailable,
    )

    assert [item["status"] for item in items] == ["running", "running"]
    assert harness.snapshots == [("df -h", 1), ("free -m", 2)]
    assert harness.direct_calls == [("df -h", 1), ("free -m", 2)]
    assert harness.marked == [(0, 0, "out-1"), (1, 0, "out-2")]
    assert harness.history[0]["user_id"] == 10
    assert harness.history[1]["server_id"] == 20
    assert harness.events[0] == {"type": "ai_parallel_batch", "status": "start", "ids": [1, 2], "count": 2}
    assert harness.events[-1] == {"type": "ai_parallel_batch", "status": "done", "ids": [1, 2], "count": 2}


@pytest.mark.asyncio
async def test_execute_terminal_parallel_batch_dry_run_skips_remote_execution():
    harness = ParallelBatchHarness()
    items = [{"id": 1, "cmd": "df -h", "status": "pending"}]

    await execute_terminal_parallel_batch(
        items=items,
        plan_indices=[3],
        dry_run=True,
        has_ssh_connection=True,
        user_id=10,
        server_id=20,
        send_event=harness.send_event,
        snapshot_command=harness.snapshot_command,
        execute_direct=harness.execute_direct,
        log_command_history=harness.log_command_history,
        mark_plan_index_done=harness.mark_plan_index_done,
        record_unavailable=harness.record_unavailable,
    )

    assert harness.snapshots == []
    assert harness.direct_calls == []
    assert harness.marked == [(3, 0, "[DRY-RUN] Would execute: df -h")]
    assert any(event["type"] == "ai_direct_output" and event["dry_run"] for event in harness.events)


@pytest.mark.asyncio
async def test_execute_terminal_parallel_batch_records_unavailable_command():
    harness = ParallelBatchHarness()
    harness.direct_results[1] = (127, "sh: nosuch: command not found")

    await execute_terminal_parallel_batch(
        items=[{"id": 1, "cmd": "nosuch --flag"}],
        plan_indices=[0],
        dry_run=False,
        has_ssh_connection=False,
        user_id=10,
        server_id=20,
        send_event=harness.send_event,
        snapshot_command=harness.snapshot_command,
        execute_direct=harness.execute_direct,
        log_command_history=harness.log_command_history,
        mark_plan_index_done=harness.mark_plan_index_done,
        record_unavailable=harness.record_unavailable,
    )

    assert harness.snapshots == []
    assert harness.marked == [(0, 127, "sh: nosuch: command not found")]
    assert harness.unavailable == ["nosuch"]
