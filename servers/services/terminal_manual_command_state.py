from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from servers.services.terminal_ai.active_command import (
    TerminalAiActiveCommandState,
    append_active_output,
)
from servers.services.terminal_ai.session_context import apply_successful_command_context
from servers.services.terminal_stream_state import append_clean_output
from servers.services.terminal_transport_state import TerminalTransportState


@dataclass
class ManualCommandState:
    """Mutable state owned by interactive, non-AI terminal commands."""

    input_buffer: str = ""
    input_forwarding_held: bool = False
    capture_suppression: int = 0
    next_command_id: int = 1_000_000
    pending_commands: list[dict[str, Any]] = field(default_factory=list)
    active_command_id: int | None = None
    active_output: str = ""

    def reset(self) -> None:
        self.input_buffer = ""
        self.input_forwarding_held = False
        self.capture_suppression = 0
        self.next_command_id = 1_000_000
        self.pending_commands.clear()
        self.active_command_id = None
        self.active_output = ""


@dataclass(frozen=True)
class ManualCommandFinalizeResult:
    session_context: dict[str, Any]
    cwd_changed: bool = False
    matched: bool = False


PersistResult = Callable[..., Awaitable[Any]]
AppendRecentActivity = Callable[..., None]


def append_terminal_tail(state: TerminalTransportState, text: str) -> None:
    state.terminal_tail = append_clean_output(state.terminal_tail, text, limit=8000)


def append_ai_output(state: TerminalAiActiveCommandState, text: str) -> None:
    append_active_output(state, text)


def append_manual_output(state: ManualCommandState, text: str) -> None:
    if not text:
        return
    if state.active_command_id is None:
        return
    state.active_output = append_clean_output(state.active_output, text, limit=12000)


async def finalize_manual_terminal_command(
    state: ManualCommandState,
    cmd_id: int,
    exit_code: int,
    *,
    session_context: dict[str, Any] | None,
    normalize_output: Callable[[str, str], str],
    persist_result: PersistResult,
    append_recent_activity: AppendRecentActivity,
) -> ManualCommandFinalizeResult:
    """Persist a completed manual command without reaching through a consumer."""
    current_context = dict(session_context or {})
    pending = list(state.pending_commands)
    if not pending:
        return ManualCommandFinalizeResult(session_context=current_context)

    item = next((entry for entry in pending if int(entry.get("id") or 0) == int(cmd_id)), None)
    if item is None:
        return ManualCommandFinalizeResult(session_context=current_context)

    raw_output = state.active_output if int(state.active_command_id or 0) == int(cmd_id) else ""
    clean_output = normalize_output(str(item.get("command") or ""), raw_output)
    await persist_result(
        user_id=int(item.get("user_id") or 0),
        server_id=int(item.get("server_id") or 0),
        session_id=str(item.get("session_id") or ""),
        command=str(item.get("command") or ""),
        output=clean_output,
        exit_code=int(exit_code),
        cwd=str(item.get("cwd") or ""),
    )
    append_recent_activity(
        command=str(item.get("command") or ""),
        cwd=str(item.get("cwd") or ""),
        exit_code=int(exit_code),
        source="live_session",
    )
    context_before = current_context or dict(item.get("context_before") or {})
    old_cwd = str(context_before.get("cwd") or item.get("cwd") or "")
    updated_context = apply_successful_command_context(
        context_before,
        command=str(item.get("command") or ""),
        exit_code=int(exit_code),
    )
    new_cwd = str(updated_context.get("cwd") or "")

    state.pending_commands = [entry for entry in pending if int(entry.get("id") or 0) != int(cmd_id)]
    if int(state.active_command_id or 0) == int(cmd_id):
        state.active_command_id = None
        state.active_output = ""
    if state.active_command_id is None and state.pending_commands:
        state.active_command_id = int(state.pending_commands[0].get("id") or 0) or None
        state.active_output = ""

    return ManualCommandFinalizeResult(
        session_context=updated_context,
        cwd_changed=bool(new_cwd and new_cwd != old_cwd),
        matched=True,
    )
