"""SSH stream IO, process cleanup, and persistence helpers."""

from __future__ import annotations

import asyncio
from typing import Any

import asyncssh
from channels.db import database_sync_to_async
from loguru import logger

from core_ui.activity import log_user_activity_async
from servers.consumers.ssh_terminal_compat import consumer_module_attr
from servers.models import Server
from servers.services import terminal_input
from servers.services.terminal_ai.active_command import (
    resolve_exit_future,
)
from servers.services.terminal_command_recorder import (
    persist_agent_command_history,
)
from servers.services.terminal_connection_records import (
    mark_terminal_connection_closed,
    register_terminal_connection,
    touch_terminal_connection,
)
from servers.services.terminal_manual_command_state import (
    append_ai_output,
    append_manual_output,
    append_terminal_tail,
    finalize_manual_terminal_command,
)
from servers.services.terminal_ssh_lifecycle import (
    close_ssh_handle,
)
from servers.services.terminal_stream_state import filter_internal_markers

_TermSize = terminal_input.TerminalSize


class SSHTerminalIoMixin:
    async def _disconnect_ssh(self):
        log_activity_async = consumer_module_attr("log_user_activity_async", log_user_activity_async)

        was_connected = bool(self._ssh_conn or self._ssh_proc)

        await self._stop_connection_heartbeat()

        # Cancel streaming tasks first to avoid sending on closed socket
        await self._cancel_ai()
        current = asyncio.current_task()
        for t in (self._stdout_task, self._stderr_task, self._wait_task):
            if t and not t.done():
                if current is not None and t is current:
                    continue
                t.cancel()

        self._stdout_task = None
        self._stderr_task = None
        self._wait_task = None

        try:
            if self._ssh_proc:
                await close_ssh_handle(self._ssh_proc)
        finally:
            self._ssh_proc = None

        try:
            if self._ssh_conn:
                await close_ssh_handle(self._ssh_conn)
        finally:
            self._ssh_conn = None

        # Nova: tear down any cached extra-target connections so we
        # don't leak SSH sessions when the user closes the terminal.
        for conn in list(self._ai_state.extra_connections.values()):
            await close_ssh_handle(conn)
        self._ai_state.extra_connections.clear()

        if was_connected and self.scope.get("user") and getattr(self.scope["user"], "is_authenticated", False):
            await self._safe_send_json({"type": "status", "status": "disconnected"})

        if was_connected and self.server and self._user_id:
            await log_activity_async(
                user_id=self._user_id,
                category="servers",
                action="terminal_disconnect",
                status="info",
                description=f'Disconnected from server terminal "{self.server.name}"',
                entity_type="server",
                entity_id=self.server.id,
                entity_name=self.server.name,
            )

        if self._server_connection_id:
            await self._mark_server_connection_closed(self._server_connection_id)
            self._server_connection_id = None
        self._manual_state.reset()
        self._nova_session_context = {}
        self._nova_recent_activity = []

    async def _stream_reader(self, reader: asyncssh.SSHReader[str], stream: str):
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                filtered, markers = self._filter_internal_markers(stream, chunk)
                if markers:
                    for cmd_id, exit_code in markers:
                        self._set_ai_exit_code(cmd_id, exit_code)

                if filtered:
                    self._append_terminal_tail(filtered)
                    self._append_ai_output(filtered)
                    self._append_manual_output(filtered)
                    await self._safe_send_json({"type": "output", "stream": stream, "data": filtered})
                if markers:
                    for cmd_id, exit_code in markers:
                        await self._finalize_manual_terminal_command(cmd_id, exit_code)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("SSH stream reader failed")
            await self._safe_send_json({"type": "error", "message": f"stream {stream} failed: {e}"})

    def _filter_internal_markers(self, stream: str, data: str) -> tuple[str, list[tuple[int, int]]]:
        """
        Hide internal marker lines (used by AI to capture exit codes) from terminal output,
        but keep newline(s) to preserve terminal layout. Returns (filtered_text, markers).
        """
        if not hasattr(self, "_marker_suppress"):
            self._marker_suppress = {"stdout": False, "stderr": False}
        if not hasattr(self, "_marker_line_buf"):
            self._marker_line_buf = {"stdout": "", "stderr": ""}
        return filter_internal_markers(
            stream=stream,
            data=data,
            marker_prefix=self._marker_prefix(),
            marker_suppress=self._marker_suppress,
            marker_line_buf=self._marker_line_buf,
        )

    def _set_ai_exit_code(self, cmd_id: int, exit_code: int):
        resolve_exit_future(self._ai_state.active_command, cmd_id, exit_code)

    def _append_terminal_tail(self, text: str):
        append_terminal_tail(self, text)

    def _append_ai_output(self, text: str):
        append_ai_output(self._ai_state.active_command, text)

    def _append_manual_output(self, text: str):
        append_manual_output(self._manual_state, text)

    async def _finalize_manual_terminal_command(self, cmd_id: int, exit_code: int) -> None:
        sync_to_async = consumer_module_attr("database_sync_to_async", database_sync_to_async)

        result = await finalize_manual_terminal_command(
            self._manual_state,
            cmd_id,
            exit_code,
            session_context=self._nova_session_context,
            normalize_output=self._normalize_manual_command_output,
            persist_result=sync_to_async(
                self._persist_manual_terminal_command_result,
                thread_sensitive=True,
            ),
            append_recent_activity=self._append_nova_recent_activity,
        )
        if result.matched:
            self._nova_session_context = result.session_context
            if result.cwd_changed:
                await self._emit_terminal_session()

    _normalize_manual_command_output = staticmethod(terminal_input.normalize_manual_command_output)
    _strip_ansi_and_controls = staticmethod(terminal_input.strip_ansi_and_controls)

    async def _wait_for_process_exit(self):
        proc = self._ssh_proc
        if not proc:
            return
        try:
            await proc.wait_closed()
            await self._safe_send_json(
                {
                    "type": "exit",
                    "exit_status": proc.exit_status,
                    "exit_signal": proc.exit_signal,
                }
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("SSH wait task failed")
            await self._safe_send_json({"type": "error", "message": f"wait failed: {e}"})
        finally:
            await self._disconnect_ssh()

    _parse_term_size = staticmethod(terminal_input.parse_terminal_size)
    _build_exports = staticmethod(terminal_input.build_shell_exports)

    async def _get_session_master_password(self) -> str:
        """Get master password from session for auto-connect."""
        session = self.scope.get("session")
        if not session:
            return ""
        try:
            # Use database_sync_to_async for safe session access
            mp = await database_sync_to_async(lambda: session.get("_mp", ""))()
            return (mp or "").strip()
        except Exception:
            return ""

    async def _user_can_servers(self, user_id: int) -> bool:
        from servers.services.terminal_access import user_can_servers

        return await user_can_servers(user_id)

    async def _get_terminal_session_limit(self, user_id: int) -> dict[str, object] | None:
        from servers.services.terminal_access import get_terminal_session_limit

        return await get_terminal_session_limit(user_id)

    async def _get_server(self, user_id: int, server_id: int) -> Server:
        from servers.services.terminal_access import get_terminal_server

        return await get_terminal_server(user_id=user_id, server_id=server_id)

    @database_sync_to_async
    def _register_server_connection(self, user_id: int, server_id: int, connection_id: str) -> None:
        register_terminal_connection(user_id=user_id, server_id=server_id, connection_id=connection_id)

    @database_sync_to_async
    def _touch_server_connection(self, connection_id: str) -> None:
        touch_terminal_connection(connection_id)

    @database_sync_to_async
    def _mark_server_connection_closed(self, connection_id: str) -> None:
        mark_terminal_connection_closed(connection_id)

    async def _resolve_server_secret(self, server_id: int, master_password: str, plain_password: str) -> str:
        """
        Resolve password/passphrase for server authentication.

        - If server has encrypted_password and master_password provided -> decrypt.
        - Else fallback to plain_password provided by user (not stored).
        """
        from servers.services.terminal_access import resolve_server_secret

        return await resolve_server_secret(
            server_id=server_id,
            master_password=master_password,
            plain_password=plain_password,
        )

    async def _get_ai_rules_and_forbidden(
        self, user_id: int, server_id: int
    ) -> tuple[list[str], str, list[str], dict[str, Any]]:
        """
        Returns:
          - forbidden_patterns
          - rules_context_text
          - required_checks
          - merged_environment_vars (global/group/server network_config)

        Forwarder to :func:`servers.services.terminal_ai.load_terminal_rules`
        (F2-4) — the body was extracted out of the consumer to keep this
        file focused on WebSocket/SSH transport only.
        """
        from servers.services.terminal_ai import load_terminal_rules

        ctx = await load_terminal_rules(user_id=user_id, server_id=server_id)
        return ctx.as_tuple()

    async def _get_effective_environment_vars(self, user_id: int, server_id: int) -> dict[str, Any]:
        """Forwarder to :func:`servers.services.terminal_ai.load_effective_environment_vars` (F2-4)."""
        from servers.services.terminal_ai import load_effective_environment_vars

        return await load_effective_environment_vars(user_id=user_id, server_id=server_id)

    @database_sync_to_async
    def _log_ai_command_history(
        self,
        user_id: int,
        server_id: int,
        command: str,
        output_snippet: str,
        exit_code: int,
    ) -> None:
        persist_agent_command_history(
            user_id=user_id,
            server_id=server_id,
            command=command,
            output_snippet=output_snippet,
            exit_code=exit_code,
        )
