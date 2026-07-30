from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from servers.services import terminal_input
from servers.services.editor_intercept import detect_editor_command
from servers.services.terminal_manual_command_state import ManualCommandState

ActivityLogger = Callable[..., Awaitable[Any]]
PersistManualCommandResult = Callable[..., Awaitable[Any]]


def _current_cwd(session_context: dict[str, Any] | None) -> str:
    return str((session_context or {}).get("cwd") or "")


async def capture_terminal_input(state: ManualCommandState, data: str) -> list[str]:
    if state.capture_suppression > 0:
        return []

    captured = terminal_input.capture_completed_terminal_commands(
        data,
        buffer=state.input_buffer,
    )
    state.input_buffer = captured.buffer
    return captured.commands


async def log_manual_terminal_command(
    command: str,
    *,
    server: Any,
    user_id: int | None,
    log_activity: ActivityLogger,
) -> None:
    if not command or not server or not user_id:
        return

    await log_activity(
        user_id=user_id,
        category="terminal",
        action="terminal_command",
        status="success",
        description=command[:4000],
        entity_type="server",
        entity_id=server.id,
        entity_name=server.name,
        metadata={
            "source": "interactive_shell",
            "command_length": len(command),
        },
    )


async def enqueue_manual_terminal_command_capture(
    state: ManualCommandState,
    command: str,
    *,
    server: Any,
    user_id: int | None,
    ssh_proc: Any,
    server_connection_id: str | None,
    session_context: dict[str, Any] | None,
    marker_prefix: str,
    log_activity: ActivityLogger,
) -> None:
    if not command or not server or not user_id or not ssh_proc:
        return

    await log_manual_terminal_command(
        command,
        server=server,
        user_id=user_id,
        log_activity=log_activity,
    )

    cmd_id = state.next_command_id
    state.next_command_id = cmd_id + 1
    state.pending_commands.append(
        {
            "id": cmd_id,
            "command": command,
            "session_id": server_connection_id or "",
            "user_id": user_id,
            "server_id": server.id,
            "cwd": _current_cwd(session_context),
            "context_before": dict(session_context or {}),
        }
    )
    if state.active_command_id is None:
        state.active_command_id = cmd_id
        state.active_output = ""

    marker_var = f"{marker_prefix}{cmd_id}"
    marker_cmd = f'{marker_var}=$?; echo "{marker_prefix}{cmd_id}:${{{marker_var}}}__"'
    ssh_proc.stdin.write(marker_cmd + "\n")


async def persist_uncaptured_manual_command(
    command: str,
    *,
    server: Any,
    user_id: int | None,
    server_connection_id: str | None,
    session_context: dict[str, Any] | None,
    append_recent_activity: Callable[..., None],
    log_activity: ActivityLogger,
    persist_result: PersistManualCommandResult,
) -> None:
    current_cwd = _current_cwd(session_context)
    await log_manual_terminal_command(
        command,
        server=server,
        user_id=user_id,
        log_activity=log_activity,
    )
    await persist_result(
        user_id=user_id or 0,
        server_id=server.id if server else 0,
        session_id=server_connection_id or "",
        command=command,
        output="",
        exit_code=None,
        cwd=current_cwd,
    )
    append_recent_activity(
        command=command,
        cwd=current_cwd,
        exit_code=None,
        source="live_session",
    )


async def handle_terminal_input(
    state: ManualCommandState,
    data: str,
    *,
    server: Any,
    user_id: int | None,
    ssh_proc: Any,
    server_connection_id: str | None,
    session_context: dict[str, Any] | None,
    marker_prefix: str,
    intercept_editors: bool,
    send_json: Callable[[dict[str, Any]], Awaitable[Any]],
    append_recent_activity: Callable[..., None],
    log_activity: ActivityLogger,
    persist_result: PersistManualCommandResult,
) -> None:
    if not data:
        return
    if not ssh_proc:
        return

    try:
        completed_commands = await capture_terminal_input(state, data)
        if not completed_commands:
            ssh_proc.stdin.write(data)
            return

        if len(completed_commands) == 1 and intercept_editors:
            editor_info = detect_editor_command(completed_commands[0])
            if editor_info:
                ssh_proc.stdin.write("\x15\x03")
                await send_json(
                    {
                        "type": "editor_intercept",
                        "path": editor_info["path"],
                        "editor": editor_info["editor"],
                        "sudo": editor_info["sudo"],
                    }
                )
                return

        newline_count = len(re.findall(r"\r\n|\r|\n", data))
        can_capture_result = (
            len(completed_commands) == 1
            and newline_count == 1
            and terminal_input.should_use_manual_command_marker(completed_commands[0])
        )
        if not can_capture_result:
            ssh_proc.stdin.write(data)
            for command in completed_commands:
                await persist_uncaptured_manual_command(
                    command,
                    server=server,
                    user_id=user_id,
                    server_connection_id=server_connection_id,
                    session_context=session_context,
                    append_recent_activity=append_recent_activity,
                    log_activity=log_activity,
                    persist_result=persist_result,
                )
            return

        command_index = 0
        for chunk in re.split(r"(\r\n|\r|\n)", data):
            if not chunk:
                continue
            ssh_proc.stdin.write(chunk)
            if chunk in ("\r\n", "\r", "\n") and command_index < len(completed_commands):
                await enqueue_manual_terminal_command_capture(
                    state,
                    completed_commands[command_index],
                    server=server,
                    user_id=user_id,
                    ssh_proc=ssh_proc,
                    server_connection_id=server_connection_id,
                    session_context=session_context,
                    marker_prefix=marker_prefix,
                    log_activity=log_activity,
                )
                command_index += 1
    except Exception as exc:  # noqa: BLE001
        await send_json({"type": "error", "message": f"stdin write failed: {exc}"})
