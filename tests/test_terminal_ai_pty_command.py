from __future__ import annotations

import asyncio

import pytest

from servers.services.terminal_ai.active_command import (
    TerminalAiActiveCommandState,
    active_command_id,
    active_output_tail,
    append_active_output,
    initialize_active_command_state,
    register_active_command,
)
from servers.services.terminal_ai.pty_command import (
    monitor_install_progress,
    wait_for_pty_command_completion,
)


@pytest.mark.asyncio
async def test_wait_for_pty_command_completion_returns_tail_and_cleans_state():
    state = TerminalAiActiveCommandState()
    initialize_active_command_state(state)
    future = asyncio.get_running_loop().create_future()
    register_active_command(state, 5, future)
    append_active_output(state, "first\nsecond")
    future.set_result(0)

    result = await wait_for_pty_command_completion(
        state,
        cmd_id=5,
        command="echo ok",
        future=future,
        is_streaming=False,
        is_install=False,
        lock=asyncio.Lock(),
        send_ai_event=_noop_send,
        interrupt_streaming_after=_noop_interrupt_after,
        write_interrupt=lambda: None,
        detect_install_error=lambda _output: False,
        output_drain_delay=0,
    )

    assert result == (0, "first\nsecond")
    assert active_command_id(state) is None
    assert active_output_tail(state) == ""
    assert state.exit_futures == {}


@pytest.mark.asyncio
async def test_monitor_install_progress_sends_last_line_until_future_is_done():
    state = TerminalAiActiveCommandState()
    initialize_active_command_state(state)
    future = asyncio.get_running_loop().create_future()
    register_active_command(state, 7, future)
    append_active_output(state, "fetching\ninstalling package")
    events: list[dict] = []

    async def send_event(event: dict) -> None:
        events.append(event)
        future.set_result(0)

    await monitor_install_progress(
        state,
        cmd_id=7,
        command="apt install nginx",
        send_ai_event=send_event,
        write_interrupt=lambda: None,
        detect_install_error=lambda _output: False,
        interval=0,
        clock=lambda: 42.0,
    )

    assert events == [
        {
            "type": "ai_install_progress",
            "cmd": "apt install nginx",
            "elapsed": 0,
            "output_tail": "installing package",
        }
    ]


@pytest.mark.asyncio
async def test_monitor_install_progress_interrupts_when_error_is_detected():
    state = TerminalAiActiveCommandState()
    initialize_active_command_state(state)
    future = asyncio.get_running_loop().create_future()
    register_active_command(state, 8, future)
    append_active_output(state, "E: unable to locate package")
    interrupts: list[str] = []

    await monitor_install_progress(
        state,
        cmd_id=8,
        command="apt install missing",
        send_ai_event=_noop_send,
        write_interrupt=lambda: interrupts.append("ctrl-c"),
        detect_install_error=lambda output: "unable to locate" in output,
        interval=0,
    )

    assert interrupts == ["ctrl-c"]


async def _noop_send(_event: dict) -> None:
    return None


async def _noop_interrupt_after(_delay: float) -> None:
    return None
