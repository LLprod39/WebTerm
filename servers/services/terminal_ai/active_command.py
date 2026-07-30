"""State helpers for the currently running Terminal AI PTY command."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from servers.services.terminal_stream_state import append_clean_output, set_exit_future_result

ACTIVE_OUTPUT_LIMIT = 6000


@dataclass
class TerminalAiActiveCommandState:
    """Mutable PTY marker/output state for the currently running AI command."""

    exit_futures: dict[int, Any] = field(default_factory=dict)
    command_id: int | None = None
    output: str = ""

    def reset(self) -> None:
        self.exit_futures.clear()
        self.command_id = None
        self.output = ""


def initialize_active_command_state(state: TerminalAiActiveCommandState) -> None:
    state.reset()


def register_active_command(state: TerminalAiActiveCommandState, cmd_id: int, future: Any) -> None:
    state.exit_futures[int(cmd_id)] = future
    state.command_id = int(cmd_id)
    state.output = ""


def active_command_id(state: TerminalAiActiveCommandState) -> int | None:
    return int(state.command_id) if state.command_id is not None else None


def exit_future(state: TerminalAiActiveCommandState, cmd_id: int | None) -> Any | None:
    if cmd_id is None:
        return None
    return state.exit_futures.get(int(cmd_id))


def resolve_exit_future(state: TerminalAiActiveCommandState, cmd_id: int, exit_code: int) -> None:
    set_exit_future_result(state.exit_futures, cmd_id, exit_code)


def pop_exit_future(state: TerminalAiActiveCommandState, cmd_id: int) -> None:
    state.exit_futures.pop(int(cmd_id), None)


def cancel_exit_futures(state: TerminalAiActiveCommandState) -> None:
    for future in state.exit_futures.values():
        if not future.done():
            future.cancel()
    state.exit_futures.clear()


def clear_active_command(state: TerminalAiActiveCommandState, cmd_id: int | None = None) -> None:
    active_id = active_command_id(state)
    if cmd_id is None or active_id == int(cmd_id):
        state.command_id = None
        state.output = ""


def append_active_output(state: TerminalAiActiveCommandState, text: str, *, limit: int = ACTIVE_OUTPUT_LIMIT) -> None:
    if not text or active_command_id(state) is None:
        return
    state.output = append_clean_output(
        state.output,
        text,
        limit=limit,
    )


def active_output_tail(state: TerminalAiActiveCommandState, *, limit: int = ACTIVE_OUTPUT_LIMIT) -> str:
    return state.output[-limit:]
