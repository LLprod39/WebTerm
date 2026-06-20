from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from servers.services import terminal_events
from servers.services.terminal_ai.command_outcome import unavailable_command_name

SendTerminalEvent = Callable[[dict[str, Any]], Awaitable[Any]]
SnapshotCommand = Callable[[str, int], Awaitable[Any]]
ExecuteDirectCommand = Callable[[str, int], Awaitable[tuple[int, str]]]
LogCommandHistory = Callable[..., Awaitable[Any]]
MarkPlanIndexDone = Callable[[int, int, str], Awaitable[Any]]
RecordUnavailableCommand = Callable[[str], None]


async def execute_terminal_parallel_batch(
    *,
    items: list[dict[str, Any]],
    plan_indices: list[int],
    dry_run: bool,
    has_ssh_connection: bool,
    user_id: int,
    server_id: int,
    send_event: SendTerminalEvent,
    snapshot_command: SnapshotCommand,
    execute_direct: ExecuteDirectCommand,
    log_command_history: LogCommandHistory,
    mark_plan_index_done: MarkPlanIndexDone,
    record_unavailable: RecordUnavailableCommand,
) -> None:
    """Run a batch of direct-mode terminal AI commands concurrently."""
    if not items:
        return

    item_ids = [int(item.get("id") or 0) for item in items]
    await send_event(terminal_events.ai_parallel_batch(status="start", ids=item_ids))

    for item in items:
        item["status"] = "running"
    for item_id in item_ids:
        await send_event(terminal_events.ai_command_status(item_id=item_id, status="running"))

    async def run_one(item: dict[str, Any]) -> tuple[int, int, str]:
        item_id = int(item.get("id") or 0)
        command = str(item.get("cmd") or "").strip()
        if not dry_run and has_ssh_connection:
            await snapshot_command(command, item_id)
        try:
            if dry_run:
                output = f"[DRY-RUN] Would execute: {command}"
                await send_event(
                    terminal_events.ai_direct_output(
                        item_id=item_id,
                        command=command,
                        output=output,
                        exit_code=0,
                        dry_run=True,
                    )
                )
                return item_id, 0, output
            exit_code, output = await execute_direct(command, item_id)
            return item_id, exit_code, output
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Parallel exec failed (id={}): {}", item_id, exc)
            return item_id, 1, f"WEUAI_EXECUTION_ERROR: {type(exc).__name__}: {exc}"

    results = await asyncio.gather(*(run_one(item) for item in items), return_exceptions=True)

    for item, plan_index, result in zip(items, plan_indices, results, strict=True):
        item_id = int(item.get("id") or 0)
        command = str(item.get("cmd") or "")
        if isinstance(result, BaseException):
            exit_code, output_snippet = 1, f"WEUAI_EXECUTION_ERROR: {result}"
        else:
            _, exit_code, output_snippet = result

        await log_command_history(
            user_id=user_id,
            server_id=server_id,
            command=command,
            output_snippet=output_snippet,
            exit_code=exit_code,
        )
        if unavailable_command := unavailable_command_name(command, exit_code):
            record_unavailable(unavailable_command)

        await mark_plan_index_done(plan_index, exit_code, output_snippet)
        await send_event(terminal_events.ai_command_status(item_id=item_id, status="done", exit_code=exit_code))

    await send_event(terminal_events.ai_parallel_batch(status="done", ids=item_ids))
