from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from servers.services import terminal_events

DEFAULT_DIRECT_EXEC_TIMEOUT_SEC = 30
DEFAULT_DIRECT_EXEC_MAX_OUTPUT = 6000

SendTerminalEvent = Callable[[dict[str, Any]], Awaitable[Any]]
NormalizeCommand = Callable[[str], str]


async def execute_direct_terminal_command(
    *,
    ssh_conn: Any,
    command: str,
    item_id: int,
    send_event: SendTerminalEvent,
    normalize_command: NormalizeCommand,
    timeout_seconds: float = DEFAULT_DIRECT_EXEC_TIMEOUT_SEC,
    max_output_chars: int = DEFAULT_DIRECT_EXEC_MAX_OUTPUT,
) -> tuple[int, str]:
    """Execute a command via a non-PTY SSH channel and emit its UI event."""
    if not ssh_conn:
        raise RuntimeError("SSH connection not established")

    clean_cmd = normalize_command(command)
    if not clean_cmd:
        return -1, ""

    try:
        result = await asyncio.wait_for(
            ssh_conn.run(clean_cmd, check=False),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        output_snippet = "WEUAI_EXECUTION_ERROR: direct exec timed out"
        exit_code = 124
    else:
        stdout = str(result.stdout or "")
        stderr = str(result.stderr or "")
        combined = stdout + (("\n" + stderr) if stderr else "")
        output_snippet = combined[-max(1, int(max_output_chars)) :]
        exit_code = int(result.exit_status) if result.exit_status is not None else 1

    await send_event(
        terminal_events.ai_direct_output(
            item_id=item_id,
            command=clean_cmd,
            output=output_snippet,
            exit_code=exit_code,
        )
    )
    return exit_code, output_snippet
