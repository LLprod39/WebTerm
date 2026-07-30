"""
WebSocket consumers for interactive SSH terminal sessions.
"""

from __future__ import annotations

import asyncio
from typing import Any

import asyncssh
from channels.db import database_sync_to_async as database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from core_ui.activity import log_user_activity_async as log_user_activity_async
from servers.consumers.ssh_terminal_agent_runner import SSHTerminalAgentRunnerMixin
from servers.consumers.ssh_terminal_agent_support import SSHTerminalAgentSupportMixin
from servers.consumers.ssh_terminal_ai_controls import SSHTerminalAiControlsMixin
from servers.consumers.ssh_terminal_ai_execution import SSHTerminalAiExecutionMixin
from servers.consumers.ssh_terminal_ai_tools import SSHTerminalAiToolsMixin
from servers.consumers.ssh_terminal_io import SSHTerminalIoMixin
from servers.consumers.ssh_terminal_lifecycle import SSHTerminalLifecycleMixin
from servers.consumers.ssh_terminal_session_ops import SSHTerminalSessionOpsMixin
from servers.models import Server
from servers.services import terminal_input
from servers.services.terminal_ai.run_controller import TerminalAiRunController
from servers.services.terminal_ai.session import TerminalAiSession
from servers.services.terminal_manual_command_state import ManualCommandState

_TermSize = terminal_input.TerminalSize

__all__ = ["SSHTerminalConsumer", "database_sync_to_async", "log_user_activity_async"]


class SSHTerminalConsumer(
    SSHTerminalLifecycleMixin,
    SSHTerminalSessionOpsMixin,
    SSHTerminalAiControlsMixin,
    SSHTerminalAiToolsMixin,
    SSHTerminalAiExecutionMixin,
    SSHTerminalAgentRunnerMixin,
    SSHTerminalAgentSupportMixin,
    SSHTerminalIoMixin,
    AsyncJsonWebsocketConsumer,
):
    """Interactive SSH terminal WebSocket consumer."""

    _TerminalAiSessionCls = TerminalAiSession
    _TerminalAiRunControllerCls = TerminalAiRunController

    server: Server | None = None
    _user_id: int | None = None

    _ssh_conn: asyncssh.SSHClientConnection | None = None
    _ssh_proc: asyncssh.SSHClientProcess[str] | None = None
    _stdout_task: asyncio.Task[None] | None = None
    _stderr_task: asyncio.Task[None] | None = None
    _wait_task: asyncio.Task[None] | None = None
    _connection_heartbeat_task: asyncio.Task[None] | None = None
    _connect_lock: asyncio.Lock

    _ai_run: TerminalAiRunController
    _ai_lock: asyncio.Lock
    _ai_plan: list[dict[str, Any]]
    _ai_plan_index: int
    _ai_next_id: int
    _ai_forbidden_patterns: list[str]
    _ai_exit_futures: dict[int, asyncio.Future[int]]
    _ai_active_cmd_id: int | None
    _ai_active_output: str
    _ai_user_message: str
    _ai_chat_mode: str
    _ai_execution_mode: str
    _ai_step_extra_count: int
    _ai_settings: dict[str, Any]
    _ai_allowlist_patterns: list[str]
    _terminal_tail: str
    _ai_history: list[dict]
    _unavailable_cmds: set[str]  # commands that returned exit=127 this session
    _ai_error_retries: dict[int, int]  # cmd_id -> retry count (max 2)
    _ai_run_id: str
    _ai_marker_token: str
    _ai_stop_requested: bool
    _manual_state: ManualCommandState

    _marker_suppress: dict[str, bool]
    _marker_line_buf: dict[str, str]

    _nova_session_context: dict[str, Any]
    _nova_recent_activity: list[dict[str, Any]]
