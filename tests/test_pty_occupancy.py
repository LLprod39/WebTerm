from __future__ import annotations

import pytest

from servers.services.terminal_ai.pty_occupancy import (
    inspect_pty_occupancy,
    occupancy_prompt_note,
    wait_for_pty_idle,
)


def test_idle_when_buffer_empty():
    occupancy = inspect_pty_occupancy(input_buffer="  ")
    assert occupancy.idle is True
    assert occupancy.reason == ""


def test_typed_input_blocks_and_previews():
    occupancy = inspect_pty_occupancy(input_buffer="echo hello")
    assert occupancy.idle is False
    assert occupancy.reason == "typed_input"
    assert occupancy.preview == "echo hello"
    assert occupancy.is_typed_input is True
    note = occupancy_prompt_note(occupancy)
    assert "echo hello" in note
    assert "Не планируй печать" in note


def test_held_input_and_active_commands():
    held = inspect_pty_occupancy(input_forwarding_held=True)
    assert held.reason == "held_input"
    manual = inspect_pty_occupancy(manual_active_command_id=3)
    assert manual.reason == "manual_command"
    other_ai = inspect_pty_occupancy(ai_active_command_id=1, current_ai_command_id=2)
    assert other_ai.reason == "ai_command"
    same_ai = inspect_pty_occupancy(ai_active_command_id=2, current_ai_command_id=2)
    assert same_ai.idle is True


@pytest.mark.asyncio
async def test_wait_asks_once_then_idles():
    snapshots = [
        inspect_pty_occupancy(input_buffer="echo hello"),
        inspect_pty_occupancy(input_buffer="echo hello"),
        inspect_pty_occupancy(input_buffer=""),
    ]
    asked = []

    async def on_typed(occupancy):
        asked.append(occupancy.preview)
        return "wait"

    async def sleeper(_delay):
        return None

    clock_values = iter([0.0, 0.2, 0.4, 0.6])

    result = await wait_for_pty_idle(
        lambda: snapshots.pop(0),
        on_typed_input=on_typed,
        sleep=sleeper,
        clock=lambda: next(clock_values),
        poll_sec=0.2,
    )
    assert result == "idle"
    assert asked == ["echo hello"]


@pytest.mark.asyncio
async def test_wait_cancel_on_typed_input():
    async def on_typed(_occupancy):
        return "cancel"

    result = await wait_for_pty_idle(
        lambda: inspect_pty_occupancy(input_buffer="partial"),
        on_typed_input=on_typed,
        sleep=lambda _delay: _noop(),
        clock=lambda: 0.0,
    )
    assert result == "cancel"


async def _noop():
    return None


@pytest.mark.asyncio
async def test_busy_timeout_resets_when_reason_changes():
    states = [
        inspect_pty_occupancy(input_buffer="echo hi"),
        inspect_pty_occupancy(manual_active_command_id=9),
        inspect_pty_occupancy(manual_active_command_id=9),
    ]
    times = [0.0, 200.0, 200.1, 200.2]

    async def on_typed(_occupancy):
        return "wait"

    async def sleeper(_delay):
        return None

    result = await wait_for_pty_idle(
        lambda: states.pop(0) if states else inspect_pty_occupancy(manual_active_command_id=9),
        on_typed_input=on_typed,
        sleep=sleeper,
        clock=lambda: times.pop(0) if times else 400.0,
        typed_timeout_sec=300.0,
        busy_timeout_sec=120.0,
        poll_sec=0.2,
    )
    assert result == "timeout"
