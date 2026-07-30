"""Explicit SSH/WebSocket transport state for the terminal consumer."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import asyncssh


@dataclass
class TerminalTransportState:
    """Mutable state tied to one interactive terminal connection."""

    ssh_conn: asyncssh.SSHClientConnection | None = None
    ssh_proc: asyncssh.SSHClientProcess[str] | None = None
    stdout_task: asyncio.Task[None] | None = None
    stderr_task: asyncio.Task[None] | None = None
    wait_task: asyncio.Task[None] | None = None
    heartbeat_task: asyncio.Task[None] | None = None
    connect_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    server_connection_id: str | None = None
    terminal_tail: str = ""
    marker_suppress: dict[str, bool] = field(
        default_factory=lambda: {"stdout": False, "stderr": False}
    )
    marker_line_buffer: dict[str, str] = field(
        default_factory=lambda: {"stdout": "", "stderr": ""}
    )
    intercept_editors: bool = True
    nova_session_context: dict[str, Any] = field(default_factory=dict)
    nova_recent_activity: list[dict[str, Any]] = field(default_factory=list)

    def reset_for_connect(self) -> None:
        self.ssh_conn = None
        self.ssh_proc = None
        self.stdout_task = None
        self.stderr_task = None
        self.wait_task = None
        self.heartbeat_task = None
        self.connect_lock = asyncio.Lock()
        self.server_connection_id = None
        self.terminal_tail = ""
        self.marker_suppress = {"stdout": False, "stderr": False}
        self.marker_line_buffer = {"stdout": "", "stderr": ""}
        self.intercept_editors = True
        self.nova_session_context.clear()
        self.nova_recent_activity.clear()

    def reset_after_disconnect(self) -> None:
        self.ssh_conn = None
        self.ssh_proc = None
        self.stdout_task = None
        self.stderr_task = None
        self.wait_task = None
        self.heartbeat_task = None
        self.server_connection_id = None
        self.terminal_tail = ""
        self.marker_suppress = {"stdout": False, "stderr": False}
        self.marker_line_buffer = {"stdout": "", "stderr": ""}
        self.nova_session_context.clear()
        self.nova_recent_activity.clear()
