"""
Command-history recording helpers for SSH terminal sessions.

The WebSocket consumer should coordinate terminal I/O; persistence, redaction,
and recent-activity shaping live here.
"""

from __future__ import annotations

from typing import Any

from app.agent_kernel.memory.redaction import redact_text
from servers.models import ServerCommandHistory
from servers.services.command_history import (
    get_recent_session_command_activity,
    save_command_history_entry,
)


def append_live_terminal_activity(
    entries: list[dict[str, Any]] | None,
    *,
    command: str,
    cwd: str,
    exit_code: int | None,
    source: str,
    max_entries: int = 12,
) -> list[dict[str, Any]]:
    if not command:
        return list(entries or [])
    result = list(entries or [])
    result.append(
        {
            "command": str(command or "")[:2000],
            "cwd": str(cwd or "")[:500],
            "exit_code": exit_code,
            "source": str(source or "live_session")[:40],
        }
    )
    return result[-max(1, max_entries) :]


def persist_manual_terminal_command_result(
    *,
    user_id: int,
    server_id: int,
    session_id: str,
    command: str,
    output: str,
    exit_code: int | None,
    cwd: str,
) -> None:
    save_command_history_entry(
        server_id=server_id,
        user_id=user_id,
        session_id=session_id,
        cwd=cwd,
        command=command,
        output=output or "",
        exit_code=exit_code,
    )


def persist_agent_command_history(
    *,
    user_id: int,
    server_id: int,
    command: str,
    output_snippet: str,
    exit_code: int,
) -> None:
    safe_output = redact_text(output_snippet or "").text
    save_command_history_entry(
        server_id=server_id,
        user_id=user_id,
        actor_kind=ServerCommandHistory.ACTOR_AGENT,
        source_kind=ServerCommandHistory.SOURCE_AGENT,
        command=command,
        output=safe_output,
        exit_code=exit_code,
    )


def load_recent_terminal_activity(
    *,
    server_id: int,
    session_id: str = "",
    limit: int = 8,
) -> list[dict[str, Any]]:
    return get_recent_session_command_activity(server_id=server_id, session_id=session_id, limit=limit)
