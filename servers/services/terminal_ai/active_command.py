"""State helpers for the currently running Terminal AI PTY command."""

from __future__ import annotations

from typing import Any

from servers.services.terminal_stream_state import append_clean_output, set_exit_future_result

ACTIVE_OUTPUT_LIMIT = 6000


def initialize_active_command_state(owner: Any) -> None:
    owner._ai_exit_futures = {}
    owner._ai_active_cmd_id = None
    owner._ai_active_output = ""


def register_active_command(owner: Any, cmd_id: int, future: Any) -> None:
    owner._ai_exit_futures[int(cmd_id)] = future
    owner._ai_active_cmd_id = int(cmd_id)
    owner._ai_active_output = ""


def active_command_id(owner: Any) -> int | None:
    cmd_id = getattr(owner, "_ai_active_cmd_id", None)
    return int(cmd_id) if cmd_id is not None else None


def exit_future(owner: Any, cmd_id: int | None) -> Any | None:
    if cmd_id is None:
        return None
    return (getattr(owner, "_ai_exit_futures", {}) or {}).get(int(cmd_id))


def resolve_exit_future(owner: Any, cmd_id: int, exit_code: int) -> None:
    set_exit_future_result(getattr(owner, "_ai_exit_futures", None), cmd_id, exit_code)


def pop_exit_future(owner: Any, cmd_id: int) -> None:
    (getattr(owner, "_ai_exit_futures", {}) or {}).pop(int(cmd_id), None)


def cancel_exit_futures(owner: Any) -> None:
    for future in (getattr(owner, "_ai_exit_futures", {}) or {}).values():
        if not future.done():
            future.cancel()
    owner._ai_exit_futures = {}


def clear_active_command(owner: Any, cmd_id: int | None = None) -> None:
    active_id = active_command_id(owner)
    if cmd_id is None or active_id == int(cmd_id):
        owner._ai_active_cmd_id = None
        owner._ai_active_output = ""


def append_active_output(owner: Any, text: str, *, limit: int = ACTIVE_OUTPUT_LIMIT) -> None:
    if not text or active_command_id(owner) is None:
        return
    owner._ai_active_output = append_clean_output(
        getattr(owner, "_ai_active_output", ""),
        text,
        limit=limit,
    )


def active_output_tail(owner: Any, *, limit: int = ACTIVE_OUTPUT_LIMIT) -> str:
    return str(getattr(owner, "_ai_active_output", "") or "")[-limit:]
