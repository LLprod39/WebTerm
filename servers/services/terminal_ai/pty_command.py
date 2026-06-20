"""Runtime helpers for Terminal AI commands executed through the interactive PTY."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from servers.services import terminal_events
from servers.services.terminal_ai.active_command import (
    active_output_tail,
    clear_active_command,
    exit_future,
    pop_exit_future,
)

STREAMING_INTERRUPT_DELAY_SEC = 8.0
STREAMING_TIMEOUT_SEC = 30
COMMAND_TIMEOUT_SEC = 600
OUTPUT_DRAIN_DELAY_SEC = 0.4

SendEvent = Callable[[dict[str, Any]], Awaitable[None]]
DetectInstallError = Callable[[str], bool]
WriteInterrupt = Callable[[], None]
InterruptStreamingAfter = Callable[[float], Awaitable[None]]


async def wait_for_pty_command_completion(
    owner: Any,
    *,
    cmd_id: int,
    command: str,
    future: asyncio.Future[int],
    is_streaming: bool,
    is_install: bool,
    lock: Any,
    send_ai_event: SendEvent,
    interrupt_streaming_after: InterruptStreamingAfter,
    write_interrupt: WriteInterrupt,
    detect_install_error: DetectInstallError,
    install_monitor_interval: float = 30.0,
    output_drain_delay: float = OUTPUT_DRAIN_DELAY_SEC,
) -> tuple[int, str]:
    """Wait for the PTY marker future and return ``(exit_code, output_tail)``."""
    interrupt_task: asyncio.Task[None] | None = None
    if is_streaming:
        interrupt_task = asyncio.create_task(interrupt_streaming_after(STREAMING_INTERRUPT_DELAY_SEC))

    monitor_task: asyncio.Task[None] | None = None
    if is_install and not is_streaming:
        monitor_task = asyncio.create_task(
            monitor_install_progress(
                owner,
                cmd_id=cmd_id,
                command=command,
                send_ai_event=send_ai_event,
                write_interrupt=write_interrupt,
                detect_install_error=detect_install_error,
                interval=install_monitor_interval,
            )
        )

    exit_code = -1
    timeout = STREAMING_TIMEOUT_SEC if is_streaming else COMMAND_TIMEOUT_SEC
    try:
        exit_code = int(await asyncio.wait_for(future, timeout=timeout))
    except asyncio.TimeoutError:
        if not is_streaming:
            raise TimeoutError("Timeout waiting for command completion marker") from None
        _write_interrupt_safely(write_interrupt)
        exit_code = 130
    finally:
        await _cancel_task(interrupt_task)
        await _cancel_task(monitor_task)
        async with lock:
            pop_exit_future(owner, cmd_id)

    await asyncio.sleep(output_drain_delay)
    output_snippet = active_output_tail(owner)
    async with lock:
        clear_active_command(owner, cmd_id)
    return exit_code, output_snippet


async def monitor_install_progress(
    owner: Any,
    *,
    cmd_id: int,
    command: str,
    send_ai_event: SendEvent,
    write_interrupt: WriteInterrupt,
    detect_install_error: DetectInstallError,
    interval: float = 30.0,
    clock: Callable[[], float] | None = None,
) -> None:
    """Send install progress updates until the command completes or fails clearly."""
    now = clock or asyncio.get_event_loop().time
    start = now()
    try:
        while True:
            await asyncio.sleep(interval)
            future = exit_future(owner, cmd_id)
            if not future or future.done():
                return

            output_so_far = active_output_tail(owner, limit=3000)
            elapsed = int(now() - start)
            last_line = (output_so_far.strip().split("\n")[-1] or "").strip()

            try:
                await send_ai_event(
                    terminal_events.ai_install_progress(
                        command=command,
                        elapsed=elapsed,
                        output_tail=last_line,
                    )
                )
            except Exception:
                return

            if detect_install_error(output_so_far):
                logger.warning("Install error detected in output, sending Ctrl+C: %s", command)
                _write_interrupt_safely(write_interrupt)
                return
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Install monitoring failed")


async def _cancel_task(task: asyncio.Task[None] | None) -> None:
    if task and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def _write_interrupt_safely(write_interrupt: WriteInterrupt) -> None:
    with contextlib.suppress(Exception):
        write_interrupt()
