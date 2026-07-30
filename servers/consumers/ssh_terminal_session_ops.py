"""Interactive terminal input, resize, and session context behavior."""

from __future__ import annotations

import asyncio
import contextlib
import errno
import os
import uuid
from typing import Any

import asyncssh
from channels.db import database_sync_to_async
from loguru import logger

from core_ui.activity import log_user_activity_async
from servers.consumers.ssh_terminal_compat import consumer_module_attr
from servers.services import terminal_input, terminal_nova_context
from servers.services.terminal_ai.active_command import (
    active_command_id,
    exit_future,
)
from servers.services.terminal_command_recorder import (
    persist_manual_terminal_command_result,
)
from servers.services.terminal_manual_input import handle_terminal_input
from servers.services.terminal_ssh_lifecycle import (
    open_terminal_ssh_session,
    resize_terminal_ssh_session,
)

_TermSize = terminal_input.TerminalSize


class SSHTerminalSessionOpsMixin:
    @staticmethod
    def _format_ssh_connect_error(exc: Exception) -> str:
        """Map SSH/network connect failures to a short user-facing message."""
        errnos: set[int] = set()
        stack: list[BaseException] = [exc]
        seen: set[int] = set()
        while stack:
            current = stack.pop()
            obj_id = id(current)
            if obj_id in seen:
                continue
            seen.add(obj_id)

            errno_val = getattr(current, "errno", None)
            if isinstance(errno_val, int):
                errnos.add(errno_val)

            # asyncio may wrap OSError as "Connect call failed (...)" without errno
            # on the outer exception in some paths; also walk causes/context.
            for attr in ("__cause__", "__context__"):
                nested = getattr(current, attr, None)
                if isinstance(nested, BaseException):
                    stack.append(nested)
            if isinstance(current, BaseExceptionGroup):
                stack.extend(current.exceptions)

        if isinstance(exc, ConnectionResetError) or errno.ECONNRESET in errnos:
            return (
                "SSH сервер принял TCP-соединение и сразу закрыл его "
                "(Connection reset by peer). Проверьте sshd, порт, firewall, "
                "bastion/VPN и allowlist по IP."
            )
        if errno.ECONNREFUSED in errnos:
            return "SSH порт недоступен (Connection refused). Проверьте, что sshd запущен и слушает нужный порт."
        if errno.EHOSTUNREACH in errnos or errno.ENETUNREACH in errnos:
            return (
                "Нет маршрута до SSH-хоста (host/network unreachable). "
                "Проверьте IP, VPN/bastion, маршрутизацию и firewall."
            )
        if errno.ETIMEDOUT in errnos or isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
            return "Таймаут подключения к SSH серверу. Проверьте маршрут, firewall, bastion/VPN и доступность порта."
        if isinstance(exc, asyncssh.misc.HostKeyNotVerifiable):
            return f"SSH host key не доверен: {exc}"
        if isinstance(exc, asyncssh.misc.PermissionDenied):
            return f"SSH аутентификация отклонена: {exc}"
        if isinstance(exc, asyncssh.Error):
            return f"SSH ошибка: {exc}"

        text = str(exc) or exc.__class__.__name__
        # Fallback for wrapped OSError messages without errno on the outer type.
        lowered = text.lower()
        if "connection refused" in lowered:
            return "SSH порт недоступен (Connection refused). Проверьте, что sshd запущен и слушает нужный порт."
        if "unreachable" in lowered or "no route" in lowered:
            return (
                "Нет маршрута до SSH-хоста (host/network unreachable). "
                "Проверьте IP, VPN/bastion, маршрутизацию и firewall."
            )
        if "timed out" in lowered or "timeout" in lowered:
            return "Таймаут подключения к SSH серверу. Проверьте маршрут, firewall, bastion/VPN и доступность порта."
        if "connection reset" in lowered:
            return (
                "SSH сервер принял TCP-соединение и сразу закрыл его "
                "(Connection reset by peer). Проверьте sshd, порт, firewall, "
                "bastion/VPN и allowlist по IP."
            )
        return text

    async def _handle_connect(self, content: dict[str, Any]):
        log_activity_async = consumer_module_attr("log_user_activity_async", log_user_activity_async)

        if not self.server:
            await self._safe_send_json({"type": "error", "message": "Server not loaded"})
            return

        async with self._connect_lock:
            if self._ssh_conn and self._ssh_proc:
                # Already connected
                return

            await self._safe_send_json({"type": "status", "status": "connecting"})

            master_password = (content.get("master_password") or "").strip()
            # Auto-connect: if master_password not provided, try to get from session
            if not master_password:
                master_password = await self._get_session_master_password()
            if not master_password:
                master_password = (os.environ.get("MASTER_PASSWORD") or "").strip()
            plain_password = (content.get("password") or "").strip()
            term_type = (content.get("term_type") or "xterm-256color").strip() or "xterm-256color"
            term_size = self._parse_term_size(content)

            try:
                secret = await self._resolve_server_secret(
                    server_id=self.server.id,
                    master_password=master_password,
                    plain_password=plain_password,
                )
            except Exception as e:
                await self._safe_send_json({"type": "error", "message": f"Ошибка секретов SSH: {e}"})
                await self._safe_send_json({"type": "status", "status": "disconnected"})
                return

            try:
                limit_error = await self._get_terminal_session_limit(self._user_id)
                if limit_error:
                    await self._safe_send_json(
                        {"type": "error", "message": f"SSH connect blocked: {limit_error['error']}"}
                    )
                    await self._safe_send_json({"type": "status", "status": "disconnected"})
                    return

                network_config = self.server.network_config or {}

                opened = await open_terminal_ssh_session(
                    server=self.server,
                    secret=secret or "",
                    term_type=term_type,
                    term_size=term_size,
                )
                self._ssh_conn = opened.conn
                self._ssh_proc = opened.proc

                # Apply merged environment variables (global/group/server) into shell session.
                merged_env: dict[str, Any] = {}
                if self._user_id and self.server:
                    try:
                        merged_env = await self._get_effective_environment_vars(self._user_id, self.server.id)
                    except Exception:
                        merged_env = {}
                if not merged_env and isinstance(network_config, dict):
                    merged_env = dict(network_config.get("environment") or {})
                exports = self._build_exports(merged_env)
                if exports:
                    self._ssh_proc.stdin.write(exports + "\n")

                await self._safe_send_json({"type": "status", "status": "connected"})
                await log_activity_async(
                    user_id=self._user_id,
                    category="servers",
                    action="terminal_connect",
                    status="success",
                    description=f'Connected to server terminal "{self.server.name}"',
                    entity_type="server",
                    entity_id=self.server.id,
                    entity_name=self.server.name,
                    metadata={
                        "host": self.server.host,
                        "port": self.server.port,
                        "auth_method": self.server.auth_method,
                    },
                )
                self._server_connection_id = f"term-{uuid.uuid4().hex}"
                await self._register_server_connection(
                    user_id=self._user_id,
                    server_id=self.server.id,
                    connection_id=self._server_connection_id,
                )
                self._start_connection_heartbeat()

                self._stdout_task = asyncio.create_task(self._stream_reader(self._ssh_proc.stdout, "stdout"))
                self._stderr_task = asyncio.create_task(self._stream_reader(self._ssh_proc.stderr, "stderr"))
                self._wait_task = asyncio.create_task(self._wait_for_process_exit())

                self._nova_session_context = await self._probe_nova_session_context(merged_env)
                self._nova_recent_activity = []
                await self._emit_terminal_session()

            except Exception as e:
                logger.exception("SSH terminal connect failed")
                error_message = self._format_ssh_connect_error(e)
                await log_activity_async(
                    user_id=self._user_id,
                    category="servers",
                    action="terminal_connect",
                    status="error",
                    description=f"SSH terminal connect failed: {error_message}",
                    entity_type="server",
                    entity_id=self.server.id if self.server else "",
                    entity_name=self.server.name if self.server else "",
                )
                await self._safe_send_json({"type": "error", "message": f"SSH connect failed: {error_message}"})
                await self._safe_send_json({"type": "status", "status": "disconnected"})
                await self._disconnect_ssh()

    async def _handle_input(self, data: str):
        log_activity_async = consumer_module_attr("log_user_activity_async", log_user_activity_async)
        sync_to_async = consumer_module_attr("database_sync_to_async", database_sync_to_async)

        await handle_terminal_input(
            self._manual_state,
            data,
            server=self.server,
            user_id=self._user_id,
            ssh_proc=self._ssh_proc,
            server_connection_id=self._server_connection_id,
            session_context=self._nova_session_context,
            marker_prefix=self._marker_prefix(),
            intercept_editors=self._intercept_editors,
            send_json=self._safe_send_json,
            append_recent_activity=self._append_nova_recent_activity,
            log_activity=log_activity_async,
            persist_result=sync_to_async(
                self._persist_manual_terminal_command_result,
                thread_sensitive=True,
            ),
        )

    _should_use_manual_command_marker = staticmethod(terminal_input.should_use_manual_command_marker)
    _strip_terminal_input_sequences = staticmethod(terminal_input.strip_terminal_input_sequences)

    @contextlib.contextmanager
    def _suppress_terminal_input_capture(self):
        self._manual_state.capture_suppression += 1
        try:
            yield
        finally:
            self._manual_state.capture_suppression = max(
                0,
                self._manual_state.capture_suppression - 1,
            )

    @staticmethod
    def _persist_manual_terminal_command_result(
        *,
        user_id: int,
        server_id: int,
        session_id: str,
        command: str,
        output: str,
        exit_code: int | None,
        cwd: str,
    ) -> None:
        persist_manual_terminal_command_result(
            user_id=user_id,
            server_id=server_id,
            session_id=session_id,
            command=command,
            output=output,
            exit_code=exit_code,
            cwd=cwd,
        )

    async def _probe_nova_session_context(self, merged_env: dict[str, Any]) -> dict[str, Any]:
        fallback_host = str(getattr(self.server, "host", "") or "") if self.server else ""
        return await terminal_nova_context.probe_nova_session_context(
            self._ssh_conn,
            merged_env=merged_env,
            fallback_host=fallback_host,
        )

    def _append_nova_recent_activity(
        self,
        *,
        command: str,
        cwd: str,
        exit_code: int | None,
        source: str,
    ) -> None:
        self._nova_recent_activity = terminal_nova_context.append_nova_recent_activity(
            getattr(self, "_nova_recent_activity", None),
            command=command,
            cwd=cwd,
            exit_code=exit_code,
            source=source,
        )

    async def _collect_nova_context_bundle(self):
        return await terminal_nova_context.collect_nova_context_bundle(
            server_id=self.server.id if self.server else None,
            session_id=self._server_connection_id or "",
            session_context=getattr(self, "_nova_session_context", None),
            live_activity=getattr(self, "_nova_recent_activity", None),
            ai_settings=self._ai_settings,
        )

    async def _handle_resize(self, content: dict[str, Any]):
        if not self._ssh_proc:
            return
        try:
            term_size = self._parse_term_size(content)
            resize_terminal_ssh_session(self._ssh_proc, term_size)
        except Exception as e:
            await self._safe_send_json({"type": "error", "message": f"resize failed: {e}"})

    async def _interrupt_active_command(self) -> int | None:
        """
        Try to interrupt active command with Ctrl+C and unblock waiter with exit=130.
        Returns active cmd_id if interrupted.
        """
        async with self._ai_lock:
            cmd_id = active_command_id(self)
            fut = exit_future(self, cmd_id)

        if cmd_id is None:
            return None

        try:
            if self._ssh_proc:
                self._ssh_proc.stdin.write("\x03")
        except Exception:
            pass

        async with self._ai_lock:
            if fut and not fut.done():
                with contextlib.suppress(Exception):
                    fut.set_result(130)
        return cmd_id
