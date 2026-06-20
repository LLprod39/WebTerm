from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from servers.services import terminal_input
from servers.services.editor_intercept import detect_editor_command

ActivityLogger = Callable[..., Awaitable[Any]]
PersistManualCommandResult = Callable[..., Awaitable[Any]]


def _current_cwd(owner: Any) -> str:
    return str((getattr(owner, "_nova_session_context", None) or {}).get("cwd") or "")


async def capture_terminal_input(owner: Any, data: str) -> list[str]:
    if int(getattr(owner, "_input_capture_suppress", 0) or 0) > 0:
        return []

    captured = terminal_input.capture_completed_terminal_commands(
        data,
        buffer=str(getattr(owner, "_manual_input_buffer", "") or ""),
    )
    owner._manual_input_buffer = captured.buffer
    return captured.commands


async def log_manual_terminal_command(owner: Any, command: str, *, log_activity: ActivityLogger) -> None:
    if not command or not getattr(owner, "server", None) or not getattr(owner, "_user_id", None):
        return

    await log_activity(
        user_id=owner._user_id,
        category="terminal",
        action="terminal_command",
        status="success",
        description=command[:4000],
        entity_type="server",
        entity_id=owner.server.id,
        entity_name=owner.server.name,
        metadata={
            "source": "interactive_shell",
            "command_length": len(command),
        },
    )


async def enqueue_manual_terminal_command_capture(
    owner: Any,
    command: str,
    *,
    log_activity: ActivityLogger,
) -> None:
    if (
        not command
        or not getattr(owner, "server", None)
        or not getattr(owner, "_user_id", None)
        or not getattr(owner, "_ssh_proc", None)
    ):
        return

    await log_manual_terminal_command(owner, command, log_activity=log_activity)

    cmd_id = int(getattr(owner, "_manual_next_cmd_id", 1_000_000) or 1_000_000)
    owner._manual_next_cmd_id = cmd_id + 1
    owner._manual_pending_commands.append(
        {
            "id": cmd_id,
            "command": command,
            "session_id": getattr(owner, "_server_connection_id", None) or "",
            "user_id": owner._user_id,
            "server_id": owner.server.id,
            "cwd": _current_cwd(owner),
            "context_before": dict(getattr(owner, "_nova_session_context", None) or {}),
        }
    )
    if owner._manual_active_cmd_id is None:
        owner._manual_active_cmd_id = cmd_id
        owner._manual_active_output = ""

    marker_prefix = owner._marker_prefix()
    marker_var = f"{marker_prefix}{cmd_id}"
    marker_cmd = f'{marker_var}=$?; echo "{marker_prefix}{cmd_id}:${{{marker_var}}}__"'
    owner._ssh_proc.stdin.write(marker_cmd + "\n")


async def persist_uncaptured_manual_command(
    owner: Any,
    command: str,
    *,
    log_activity: ActivityLogger,
    persist_result: PersistManualCommandResult,
) -> None:
    current_cwd = _current_cwd(owner)
    await log_manual_terminal_command(owner, command, log_activity=log_activity)
    await persist_result(
        user_id=getattr(owner, "_user_id", None) or 0,
        server_id=owner.server.id if getattr(owner, "server", None) else 0,
        session_id=getattr(owner, "_server_connection_id", None) or "",
        command=command,
        output="",
        exit_code=None,
        cwd=current_cwd,
    )
    owner._append_nova_recent_activity(
        command=command,
        cwd=current_cwd,
        exit_code=None,
        source="live_session",
    )


async def handle_terminal_input(
    owner: Any,
    data: str,
    *,
    log_activity: ActivityLogger,
    persist_result: PersistManualCommandResult,
) -> None:
    if not data:
        return
    if not getattr(owner, "_ssh_proc", None):
        return

    try:
        completed_commands = await capture_terminal_input(owner, data)
        if not completed_commands:
            owner._ssh_proc.stdin.write(data)
            return

        if len(completed_commands) == 1 and getattr(owner, "_intercept_editors", True):
            editor_info = detect_editor_command(completed_commands[0])
            if editor_info:
                owner._ssh_proc.stdin.write("\x15\x03")
                await owner._safe_send_json(
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
            owner._ssh_proc.stdin.write(data)
            for command in completed_commands:
                await persist_uncaptured_manual_command(
                    owner,
                    command,
                    log_activity=log_activity,
                    persist_result=persist_result,
                )
            return

        command_index = 0
        for chunk in re.split(r"(\r\n|\r|\n)", data):
            if not chunk:
                continue
            owner._ssh_proc.stdin.write(chunk)
            if chunk in ("\r\n", "\r", "\n") and command_index < len(completed_commands):
                await enqueue_manual_terminal_command_capture(
                    owner,
                    completed_commands[command_index],
                    log_activity=log_activity,
                )
                command_index += 1
    except Exception as exc:  # noqa: BLE001
        await owner._safe_send_json({"type": "error", "message": f"stdin write failed: {exc}"})
