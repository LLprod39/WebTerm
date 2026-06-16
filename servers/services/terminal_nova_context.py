"""Nova terminal-session context orchestration helpers.

The low-level prompt rendering and session-context parsing live under
``terminal_ai.session_context``. This module owns the consumer-facing glue:
probing the live SSH session, maintaining live recent activity, and loading
persisted activity for the Nova context bundle.
"""

from __future__ import annotations

import asyncio
from typing import Any

from channels.db import database_sync_to_async

from servers.services.terminal_ai.session_context import (
    build_initial_session_context,
    build_nova_context_bundle,
    build_session_probe_command,
)
from servers.services.terminal_command_recorder import (
    append_live_terminal_activity,
    load_recent_terminal_activity,
)

_RECENT_ACTIVITY_LIMIT = 8


async def probe_nova_session_context(
    ssh_conn: Any,
    *,
    merged_env: dict[str, Any],
    fallback_host: str,
    timeout: float = 3.0,
) -> dict[str, Any]:
    if not ssh_conn:
        return build_initial_session_context("", merged_env=merged_env, fallback_host=fallback_host)

    output = ""
    try:
        result = await asyncio.wait_for(
            ssh_conn.run(build_session_probe_command(), check=False),
            timeout=timeout,
        )
        output = f"{result.stdout or ''}\n{result.stderr or ''}"
    except Exception:
        output = ""
    return build_initial_session_context(output, merged_env=merged_env, fallback_host=fallback_host)


def append_nova_recent_activity(
    entries: list[dict[str, Any]] | None,
    *,
    command: str,
    cwd: str,
    exit_code: int | None,
    source: str,
) -> list[dict[str, Any]]:
    return append_live_terminal_activity(
        list(entries or []),
        command=command,
        cwd=cwd,
        exit_code=exit_code,
        source=source,
    )


async def collect_nova_context_bundle(
    *,
    server_id: int | None,
    session_id: str,
    session_context: dict[str, Any] | None,
    live_activity: list[dict[str, Any]] | None,
    ai_settings: dict[str, Any] | None,
):
    include_session_context = bool((ai_settings or {}).get("nova_session_context_enabled", True))
    include_recent_activity = bool((ai_settings or {}).get("nova_recent_activity_enabled", True))
    persisted_activity: list[dict[str, Any]] = []
    if include_recent_activity and server_id:
        try:
            persisted_activity = await database_sync_to_async(
                load_recent_terminal_activity,
                thread_sensitive=True,
            )(
                server_id=server_id,
                session_id=session_id or "",
                limit=_RECENT_ACTIVITY_LIMIT,
            )
        except Exception:
            persisted_activity = []

    return build_nova_context_bundle(
        snapshot=session_context or {},
        live_activity=list(live_activity or []),
        persisted_activity=persisted_activity,
        include_session_context=include_session_context,
        include_recent_activity=include_recent_activity,
    )


def terminal_session_payload(session_context: dict[str, Any] | None) -> dict[str, str]:
    cwd = str((session_context or {}).get("cwd") or "").strip()
    return {"type": "terminal_session", "cwd": cwd}
