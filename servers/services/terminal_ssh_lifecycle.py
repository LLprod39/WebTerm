"""
Interactive SSH lifecycle helpers for terminal sessions.

The Channels consumer still owns WebSocket events and stream-reader tasks.
This module owns the AsyncSSH process lifecycle itself: open an interactive
PTY, resize it, and close process/connection handles defensively.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import asyncssh

from servers.services.terminal_connection_options import build_terminal_connect_kwargs
from servers.services.terminal_input import TerminalSize


@dataclass
class OpenTerminalSession:
    conn: Any
    proc: Any


async def open_terminal_ssh_session(
    *,
    server: Any,
    secret: str,
    term_type: str,
    term_size: TerminalSize,
    connect_factory=None,
) -> OpenTerminalSession:
    connect = connect_factory or asyncssh.connect
    connect_kwargs = await build_terminal_connect_kwargs(server, secret=secret or "")
    conn = await connect(**connect_kwargs)
    proc = await conn.create_process(
        term_type=term_type,
        term_size=(term_size.cols, term_size.rows, 0, 0),
        encoding="utf-8",
        errors="replace",
    )
    return OpenTerminalSession(conn=conn, proc=proc)


def resize_terminal_ssh_session(proc: Any, term_size: TerminalSize) -> None:
    if not proc:
        return
    if term_size.cols > 0 and term_size.rows > 0:
        proc.change_terminal_size(term_size.cols, term_size.rows)


async def close_ssh_handle(handle: Any, *, timeout: float = 5.0) -> None:
    if not handle:
        return
    try:
        handle.close()
        await asyncio.wait_for(handle.wait_closed(), timeout=timeout)
    except Exception:
        return


async def close_terminal_ssh_session(conn: Any, proc: Any, *, timeout: float = 5.0) -> None:
    await close_ssh_handle(proc, timeout=timeout)
    await close_ssh_handle(conn, timeout=timeout)
