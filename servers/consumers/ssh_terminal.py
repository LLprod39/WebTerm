"""
WebSocket consumers for interactive SSH terminal sessions.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import uuid
from typing import Any

import asyncssh
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from loguru import logger

from core_ui.activity import log_user_activity_async
from core_ui.audit import audit_context
from servers.memory_heuristics import is_trivial_memory_command
from servers.models import Server
from servers.secret_utils import has_saved_server_secret
from servers.services import terminal_events, terminal_input, terminal_nova_context
from servers.services.editor_intercept import detect_editor_command
from servers.services.terminal_ai import preferences as ai_preferences
from servers.services.terminal_ai.memory import sanitize_memory_line
from servers.services.terminal_ai.planning import extract_json_object
from servers.services.terminal_ai.policy import compute_confirm_reason, match_patterns
from servers.services.terminal_ai.reporter import build_fallback_report, compute_report_status
from servers.services.terminal_command_recorder import (
    persist_agent_command_history,
    persist_manual_terminal_command_result,
)
from servers.services.terminal_connection_records import (
    mark_terminal_connection_closed,
    register_terminal_connection,
    touch_terminal_connection,
)
from servers.services.terminal_ssh_lifecycle import (
    close_ssh_handle,
    open_terminal_ssh_session,
    resize_terminal_ssh_session,
)
from servers.services.terminal_manual_command_state import (
    append_ai_output,
    append_manual_output,
    append_terminal_tail,
    finalize_manual_terminal_command,
)
from servers.services.terminal_stream_state import (
    filter_internal_markers,
    set_exit_future_result,
)

_TermSize = terminal_input.TerminalSize

_WEUAI_MARKER_PREFIX = "__WEUAI_EXIT_"

# Limit concurrent terminal-AI LLM calls to avoid provider rate limits (429)
_TERMINAL_AI_LLM_SEMAPHORE = asyncio.Semaphore(4)


class SSHTerminalConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket protocol (JSON):
      - server -> client:
          {type: "ready", server_id, server_name, auth_method, has_encrypted_secret}
          {type: "status", status: "connecting"|"connected"|"disconnected"}
          {type: "output", stream: "stdout"|"stderr", data: "<chunk>"}
          {type: "error", message: "<text>"}
          {type: "exit", exit_status: int|null, exit_signal: any|null}
          {type: "ai_status", status: "thinking"|"running"|"waiting_confirm"|"idle", ...}
          {type: "ai_response", assistant_text: str, commands: [{id, cmd, why, requires_confirm, reason, risk_categories?, risk_reasons?}]}
          {type: "ai_command_status", id: int, status: "running"|"done"|"skipped", exit_code?, reason?}
          {type: "ai_direct_output", id: int, cmd: str, output: str, exit_code: int, dry_run: bool}
          {type: "ai_report", report: str, status: "ok"|"warning"|"error"}
          {type: "ai_error", message: "<text>"}
          {type: "ai_recovery", original_cmd, new_cmd, new_id, why}
          {type: "ai_question", q_id, question, cmd, exit_code}
          {type: "ai_install_progress", cmd, elapsed, output_tail}
      - client -> server:
          {type: "connect", master_password?, password?, cols?, rows?, term_type?}
          {type: "input", data: "<keystrokes>"}
          {type: "resize", cols, rows}
          {type: "disconnect"}
          {type: "ai_request", message: "<text>", chat_mode?: "ask"|"agent", execution_mode?: "auto"|"step"|"fast", ai_settings?: {...}}
          {type: "ai_confirm", id: <int>}
          {type: "ai_cancel", id: <int>}
          {type: "ai_reply", q_id: str, text: str}
          {type: "ai_generate_report", force?: bool}
          {type: "ai_clear_memory"}
          {type: "ai_explain_output", id: int, cmd: str, output: str, exit_code?: int, question?: str}
    """

    server: Server | None = None
    _user_id: int | None = None

    _ssh_conn: asyncssh.SSHClientConnection | None = None
    _ssh_proc: asyncssh.SSHClientProcess[str] | None = None
    _stdout_task: asyncio.Task[None] | None = None
    _stderr_task: asyncio.Task[None] | None = None
    _wait_task: asyncio.Task[None] | None = None
    _connection_heartbeat_task: asyncio.Task[None] | None = None
    _connect_lock: asyncio.Lock

    _ai_lock: asyncio.Lock
    _ai_task: asyncio.Task[None] | None = None
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
    _ai_reply_futures: dict[str, asyncio.Future]  # q_id → future waiting for user reply
    _ai_error_retries: dict[int, int]  # cmd_id → retry count (max 2)
    _ai_run_id: str
    _ai_marker_token: str
    _ai_stop_requested: bool
    _manual_next_cmd_id: int
    _manual_pending_commands: list[dict[str, Any]]
    _manual_active_cmd_id: int | None
    _manual_active_output: str

    _marker_suppress: dict[str, bool]
    _marker_line_buf: dict[str, str]

    _nova_session_context: dict[str, Any]
    _nova_recent_activity: list[dict[str, Any]]

    @staticmethod
    def _resolve_ws_token_user(token: str):
        """Validate a short-lived WS token and return the User or None."""
        from django.contrib.auth.models import User as _User
        from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

        signer = TimestampSigner(salt="ws-token")
        try:
            user_id = int(signer.unsign(token, max_age=300))
            return _User.objects.filter(id=user_id, is_active=True).first()
        except (BadSignature, SignatureExpired, ValueError, TypeError):
            return None

    _default_ai_settings = staticmethod(ai_preferences.default_ai_settings)
    _parse_bool = staticmethod(ai_preferences.parse_bool)
    _normalize_pattern_list = staticmethod(ai_preferences.normalize_pattern_list)
    _normalize_int_list = staticmethod(ai_preferences.normalize_int_list)
    _normalize_ai_settings = staticmethod(ai_preferences.normalize_ai_settings)
    _clone_ai_settings = staticmethod(ai_preferences.clone_ai_settings)
    _is_auto_report_enabled = staticmethod(ai_preferences.is_auto_report_enabled)
    _normalize_ai_chat_mode = staticmethod(ai_preferences.normalize_ai_chat_mode)

    async def connect(self):
        self._connect_lock = asyncio.Lock()

        user = self.scope.get("user")

        # Fallback: authenticate via ?ws_token query parameter.
        # Required when the Vite dev-proxy doesn't forward the Cookie header
        # on WebSocket upgrades (common http-proxy limitation).
        if not user or not getattr(user, "is_authenticated", False):
            from urllib.parse import parse_qs, unquote

            qs = self.scope.get("query_string", b"").decode()
            qs_params = parse_qs(qs)
            ws_token = unquote(qs_params.get("ws_token", [""])[0])
            if ws_token:
                user = await database_sync_to_async(self._resolve_ws_token_user)(ws_token)
                logger.debug("WS connect: token auth resolved user={}", user)

        logger.debug("WS connect: user={} authenticated={}", user, getattr(user, "is_authenticated", "N/A"))
        if not user or not getattr(user, "is_authenticated", False):
            logger.warning("WS connect REJECT 4401: not authenticated (user={})", user)
            await self._reject_with_error(
                code=4401,
                message="Сессия истекла или пользователь не авторизован.",
                error_code="auth_required",
            )
            return

        self._user_id = int(user.id)
        self._ai_lock = asyncio.Lock()
        self._ai_task = None
        # F2-1: per-request queue / run-id / cursor / step-counter state
        # lives in a single TerminalAiSession object. The historical
        # ``self._ai_*`` attributes are kept as @property forwarders to
        # avoid churning the hundreds of call-sites in this file.
        from servers.services.terminal_ai import TerminalAiSession

        self._ai_session = TerminalAiSession()
        self._ai_forbidden_patterns = []
        self._ai_exit_futures = {}
        self._ai_active_cmd_id = None
        self._ai_active_output = ""
        self._ai_settings = self._default_ai_settings()
        self._ai_allowlist_patterns = []
        self._terminal_tail = ""
        self._ai_history = []
        self._unavailable_cmds: set[str] = set()
        self._ai_reply_futures: dict[str, asyncio.Future] = {}
        self._ai_error_retries: dict[int, int] = {}
        self._ai_run_id = ""
        self._ai_marker_token = ""
        # Nova: cached SSH connections to authorised extra targets for
        # the agent loop. Keys: target name (e.g. ``srv-42``) → live
        # asyncssh.SSHClientConnection. Closed in ``_disconnect_ssh``.
        self._agent_extra_conns: dict[str, Any] = {}
        self._marker_suppress = {"stdout": False, "stderr": False}
        self._marker_line_buf = {"stdout": "", "stderr": ""}
        self._manual_input_buffer = ""
        self._input_capture_suppress = 0
        self._manual_next_cmd_id = 1_000_000
        self._manual_pending_commands: list[dict[str, Any]] = []
        self._manual_active_cmd_id = None
        self._manual_active_output = ""
        self._ai_audit_context: dict[str, Any] = {}
        self._server_connection_id: str | None = None
        self._connection_heartbeat_task = None
        # Fire-and-forget tasks spawned outside _ai_process_queue (F1-7),
        # tracked so disconnect/cancel can drain them without leaks.
        self._ai_background_tasks: set[asyncio.Task[Any]] = set()
        self._nova_session_context = {}
        self._nova_recent_activity = []

        can_servers = await self._user_can_servers(user.id)
        logger.debug("WS connect: user={} can_servers={}", user, can_servers)
        if not can_servers:
            logger.warning("WS connect REJECT 4403: no servers permission (user={})", user)
            await self._reject_with_error(
                code=4403,
                message="Нет доступа к разделу серверов.",
                error_code="servers_forbidden",
            )
            return

        server_id = self.scope.get("url_route", {}).get("kwargs", {}).get("server_id")
        if not server_id:
            logger.warning("WS connect REJECT 4400: no server_id in URL")
            await self._reject_with_error(
                code=4400,
                message="Некорректный идентификатор сервера.",
                error_code="server_id_missing",
            )
            return

        try:
            self.server = await self._get_server(user.id, int(server_id))
        except Server.DoesNotExist:
            logger.warning("WS connect REJECT 4404: server {} not found for user={}", server_id, user)
            await self._reject_with_error(
                code=4404,
                message="Сервер не найден или доступ к нему уже отозван.",
                error_code="server_not_found",
            )
            return
        except Exception as exc:
            logger.exception(
                "WS connect REJECT: unexpected error fetching server {} for user={}: {}", server_id, user, exc
            )
            await self._reject_with_error(
                code=4500,
                message="Не удалось подготовить подключение к серверу.",
                error_code="server_connect_prepare_failed",
            )
            return

        has_encrypted_secret = await database_sync_to_async(has_saved_server_secret, thread_sensitive=True)(self.server)

        # F2-9: restore persisted chat history so the conversation survives
        # WS reconnects / page reloads. Respects per-user memory_ttl_requests
        # when applying the rolling window later, but we always load a
        # reasonable max-recent here.
        #
        # A3: gate the restore on the current ``memory_enabled`` setting so
        # a user who turned memory off still sees an empty context on the
        # next connect, even if the DB hasn't been wiped yet (e.g. they
        # flipped the setting through another client).
        memory_enabled_now = bool(
            (self._ai_settings or {}).get("memory_enabled", True)
        )
        if memory_enabled_now:
            try:
                from servers.services.terminal_ai import load_recent as _load_history

                restored = await _load_history(
                    user_id=self._user_id,
                    server_id=self.server.id,
                    limit=40,
                )
                if restored:
                    self._ai_history = list(restored)
            except Exception as hist_exc:  # pragma: no cover — non-fatal
                logger.warning("terminal-ai chat history restore failed: %s", hist_exc)

        await self.accept()
        await self._safe_send_json(
            {
                "type": "ready",
                "server_id": self.server.id,
                "server_name": self.server.name,
                "auth_method": self.server.auth_method,
                "has_encrypted_secret": has_encrypted_secret,
                # F2-9: signal the client that prior messages are available.
                "restored_history_count": len(self._ai_history or []),
            }
        )

    async def disconnect(self, code):
        await self._cancel_ai()
        await self._drain_ai_background_tasks()
        await self._disconnect_ssh()

    async def _drain_ai_background_tasks(self) -> None:
        """Cancel and drain any fire-and-forget AI background tasks (F1-7)."""
        tasks = list(getattr(self, "_ai_background_tasks", ()) or ())
        for t in tasks:
            if not t.done():
                t.cancel()
        for t in tasks:
            # Best-effort drain — never raise out of disconnect().
            with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError, Exception):
                await asyncio.wait_for(t, timeout=2.0)
        if hasattr(self, "_ai_background_tasks"):
            self._ai_background_tasks.clear()

    async def receive_json(self, content: Any, **kwargs):
        msg_type = (content or {}).get("type")
        if msg_type == "connect":
            await self._handle_connect(content or {})
            return
        if msg_type == "input":
            await self._handle_input((content or {}).get("data", ""))
            return
        if msg_type == "resize":
            await self._handle_resize(content or {})
            return
        if msg_type == "disconnect":
            await self._disconnect_ssh()
            return
        if msg_type == "ai_request":
            await self._handle_ai_request(content or {})
            return
        if msg_type == "ai_generate_report":
            await self._handle_ai_generate_report(content or {})
            return
        if msg_type == "ai_confirm":
            await self._handle_ai_confirm(content or {})
            return
        if msg_type == "ai_cancel":
            await self._handle_ai_cancel(content or {})
            return
        if msg_type == "ai_stop":
            await self._handle_ai_stop()
            return
        if msg_type == "ai_reply":
            # User replied to an ai_question card
            q_id = str((content or {}).get("q_id") or "")
            text = str((content or {}).get("text") or "").strip()
            fut = self._ai_reply_futures.get(q_id)
            if fut and not fut.done():
                fut.set_result(text)
            return
        if msg_type == "ai_clear_memory":
            await self._handle_ai_clear_memory()
            return
        if msg_type == "ai_explain_output":
            await self._handle_ai_explain_output(content or {})
            return
        if msg_type == "set_editor_intercept":
            self._intercept_editors = bool((content or {}).get("enabled", True))
            return
        if msg_type == "ping":
            if self._server_connection_id:
                await self._touch_server_connection(self._server_connection_id)
            await self._safe_send_json({"type": "pong"})
            return

        await self._safe_send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})

    @staticmethod
    def _new_run_id() -> str:
        return f"run_{uuid.uuid4().hex[:12]}"

    @staticmethod
    def _new_marker_token() -> str:
        return uuid.uuid4().hex[:10]

    def _marker_prefix(self) -> str:
        token = str(getattr(self, "_ai_marker_token", "") or "").strip()
        if token:
            return f"{_WEUAI_MARKER_PREFIX}{token}_"
        return _WEUAI_MARKER_PREFIX

    def _with_ai_run_id(self, payload: dict[str, Any]) -> dict[str, Any]:
        msg_type = str((payload or {}).get("type") or "")
        if msg_type.startswith("ai_") and self._ai_run_id:
            out = dict(payload)
            out.setdefault("run_id", self._ai_run_id)
            return out
        return payload

    async def _safe_send_json(self, payload: dict[str, Any]) -> None:
        """
        Send JSON to the WebSocket without raising. Logs and swallows errors so that
        closed connections or send failures do not break background tasks or leave
        the user with no feedback.
        """
        try:
            await self.send_json(payload)
        except Exception as e:
            logger.debug(
                "Terminal WebSocket send failed (connection may be closed): %s",
                e,
                server_id=getattr(self.server, "id", None),
            )

    async def _emit_terminal_session(self) -> None:
        await self._safe_send_json(
            terminal_nova_context.terminal_session_payload(getattr(self, "_nova_session_context", None))
        )

    @staticmethod
    def _terminal_session_heartbeat_interval() -> int:
        try:
            interval = int(getattr(settings, "SSH_TERMINAL_SESSION_HEARTBEAT_SECONDS", 30) or 30)
        except Exception:
            interval = 30
        return max(interval, 0)

    def _start_connection_heartbeat(self) -> None:
        if not self._server_connection_id:
            return
        interval = self._terminal_session_heartbeat_interval()
        if interval <= 0:
            return
        if self._connection_heartbeat_task and not self._connection_heartbeat_task.done():
            self._connection_heartbeat_task.cancel()
        self._connection_heartbeat_task = asyncio.create_task(self._run_connection_heartbeat(interval))

    async def _stop_connection_heartbeat(self) -> None:
        task = self._connection_heartbeat_task
        self._connection_heartbeat_task = None
        if not task or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _run_connection_heartbeat(self, interval: int) -> None:
        try:
            while self._server_connection_id:
                await asyncio.sleep(interval)
                if not self._server_connection_id or not (self._ssh_conn or self._ssh_proc):
                    return
                await self._touch_server_connection(self._server_connection_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Terminal connection heartbeat failed")

    async def _send_ai_event(self, payload: dict[str, Any]) -> None:
        # B3: redact secrets from AI-generated text before reaching the client.
        from servers.services.egress_redaction import redact_ai_event

        redact_ai_event(payload)
        await self._safe_send_json(self._with_ai_run_id(payload))

    async def _handle_connect(self, content: dict[str, Any]):
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
                await log_user_activity_async(
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
                await log_user_activity_async(
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
        if not data:
            return
        if not self._ssh_proc:
            return
        try:
            completed_commands = await self._capture_terminal_input(data)
            if not completed_commands:
                self._ssh_proc.stdin.write(data)
                return

            # Intercept editor commands (nano, vim, vi, etc.) → GUI editor
            if len(completed_commands) == 1 and getattr(self, "_intercept_editors", True):
                editor_info = detect_editor_command(completed_commands[0])
                if editor_info:
                    # Characters were already forwarded to pty keystroke-by-
                    # keystroke, so we must CANCEL the typed command — NOT
                    # execute it.  Ctrl+U clears the line, Ctrl+C aborts.
                    self._ssh_proc.stdin.write("\x15\x03")

                    await self._safe_send_json(
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
                and self._should_use_manual_command_marker(completed_commands[0])
            )
            if not can_capture_result:
                self._ssh_proc.stdin.write(data)
                for command in completed_commands:
                    current_cwd = str((getattr(self, "_nova_session_context", None) or {}).get("cwd") or "")
                    await self._log_manual_terminal_command(command)
                    await database_sync_to_async(self._persist_manual_terminal_command_result, thread_sensitive=True)(
                        user_id=self._user_id or 0,
                        server_id=self.server.id if self.server else 0,
                        session_id=self._server_connection_id or "",
                        command=command,
                        output="",
                        exit_code=None,
                        cwd=current_cwd,
                    )
                    self._append_nova_recent_activity(
                        command=command,
                        cwd=current_cwd,
                        exit_code=None,
                        source="live_session",
                    )
                return

            command_index = 0
            for chunk in re.split(r"(\r\n|\r|\n)", data):
                if not chunk:
                    continue
                self._ssh_proc.stdin.write(chunk)
                if chunk in ("\r\n", "\r", "\n") and command_index < len(completed_commands):
                    await self._enqueue_manual_terminal_command_capture(completed_commands[command_index])
                    command_index += 1
        except Exception as e:
            await self._safe_send_json({"type": "error", "message": f"stdin write failed: {e}"})

    _should_use_manual_command_marker = staticmethod(terminal_input.should_use_manual_command_marker)
    _strip_terminal_input_sequences = staticmethod(terminal_input.strip_terminal_input_sequences)

    @contextlib.contextmanager
    def _suppress_terminal_input_capture(self):
        self._input_capture_suppress = int(getattr(self, "_input_capture_suppress", 0) or 0) + 1
        try:
            yield
        finally:
            self._input_capture_suppress = max(0, int(getattr(self, "_input_capture_suppress", 1) or 1) - 1)

    async def _capture_terminal_input(self, data: str) -> list[str]:
        if int(getattr(self, "_input_capture_suppress", 0) or 0) > 0:
            return []

        captured = terminal_input.capture_completed_terminal_commands(
            data,
            buffer=str(getattr(self, "_manual_input_buffer", "") or ""),
        )
        self._manual_input_buffer = captured.buffer
        return captured.commands

    async def _log_manual_terminal_command(self, command: str) -> None:
        if not command or not self.server or not self._user_id:
            return

        await log_user_activity_async(
            user_id=self._user_id,
            category="terminal",
            action="terminal_command",
            status="success",
            description=command[:4000],
            entity_type="server",
            entity_id=self.server.id,
            entity_name=self.server.name,
            metadata={
                "source": "interactive_shell",
                "command_length": len(command),
            },
        )

    async def _enqueue_manual_terminal_command_capture(self, command: str) -> None:
        if not command or not self.server or not self._user_id or not self._ssh_proc:
            return

        await self._log_manual_terminal_command(command)

        cmd_id = int(getattr(self, "_manual_next_cmd_id", 1_000_000) or 1_000_000)
        self._manual_next_cmd_id = cmd_id + 1
        self._manual_pending_commands.append(
            {
                "id": cmd_id,
                "command": command,
                "session_id": self._server_connection_id or "",
                "user_id": self._user_id,
                "server_id": self.server.id,
                "cwd": str((getattr(self, "_nova_session_context", None) or {}).get("cwd") or ""),
                "context_before": dict(getattr(self, "_nova_session_context", None) or {}),
            }
        )
        if self._manual_active_cmd_id is None:
            self._manual_active_cmd_id = cmd_id
            self._manual_active_output = ""

        marker_prefix = self._marker_prefix()
        marker_var = f"{marker_prefix}{cmd_id}"
        marker_cmd = f'{marker_var}=$?; echo "{marker_prefix}{cmd_id}:${{{marker_var}}}__"'
        self._ssh_proc.stdin.write(marker_cmd + "\n")

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
            cmd_id = self._ai_active_cmd_id
            fut = (self._ai_exit_futures or {}).get(cmd_id) if cmd_id is not None else None

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

    async def _handle_ai_stop(self):
        active_cmd_id = await self._interrupt_active_command()

        pending_to_skip: list[int] = []
        async with self._ai_lock:
            self._ai_stop_requested = True
            for item in self._ai_plan[self._ai_plan_index :]:
                iid = int(item.get("id") or 0)
                status = str(item.get("status") or "pending")
                if iid and iid != active_cmd_id and status not in ("done", "skipped", "cancelled"):
                    pending_to_skip.append(iid)

        if active_cmd_id is not None:
            await self._send_ai_event(
                {
                    "type": "ai_command_status",
                    "id": active_cmd_id,
                    "status": "cancelled",
                    "reason": "stopped",
                }
            )
        for cmd_id in pending_to_skip:
            await self._send_ai_event(
                {
                    "type": "ai_command_status",
                    "id": cmd_id,
                    "status": "skipped",
                    "reason": "stopped",
                }
            )

        await self._cancel_ai()
        await self._send_ai_event({"type": "ai_status", "status": "idle"})

    async def _cancel_ai(self):
        # Can be called from disconnect/cleanup paths
        if not hasattr(self, "_ai_lock"):
            return
        async with self._ai_lock:
            await self._cancel_ai_locked()

    async def _cancel_ai_locked(self):
        current = asyncio.current_task()
        if self._ai_task and not self._ai_task.done() and (current is None or self._ai_task is not current):
            self._ai_task.cancel()
        self._ai_task = None

        for fut in (self._ai_exit_futures or {}).values():
            if not fut.done():
                fut.cancel()
        self._ai_exit_futures = {}

        for fut in (getattr(self, "_ai_reply_futures", None) or {}).values():
            if not fut.done():
                fut.cancel()
        if hasattr(self, "_ai_reply_futures"):
            self._ai_reply_futures = {}

        self._ai_plan = []
        self._ai_plan_index = 0
        self._ai_forbidden_patterns = []
        self._ai_active_cmd_id = None
        self._ai_active_output = ""
        self._ai_stop_requested = False
        self._ai_step_extra_count = 0

    @staticmethod
    def _normalize_execution_mode(mode: str) -> str:
        from servers.services.terminal_ai import normalize_execution_mode

        return normalize_execution_mode(mode)

    def _resolve_auto_execution_mode(self, plan_obj: dict[str, Any], commands_raw: Any, user_message: str) -> str:
        """
        Resolve concrete execution mode for an auto request.
        Priority:
          1) planner-provided execution_mode
          2) safety fallback from planned commands / user intent
        """
        from servers.services.terminal_ai import resolve_auto_execution_mode

        return resolve_auto_execution_mode(
            plan_obj=plan_obj,
            commands_raw=commands_raw,
            user_message=user_message,
        )

    async def _handle_ai_request(self, content: Any):
        payload = content if isinstance(content, dict) else {}
        msg = str(payload.get("message") or "").strip()
        requested_chat_mode = self._normalize_ai_chat_mode(payload.get("chat_mode") or payload.get("assistant_mode"))
        ai_settings = self._normalize_ai_settings(payload.get("ai_settings"))
        requested_mode = self._normalize_execution_mode(payload.get("execution_mode") or payload.get("mode") or "")
        if not msg:
            return

        async with self._ai_lock:
            await self._cancel_ai_locked()
            # A3: detect memory_enabled transition True → False so we can
            # wipe both in-memory and persisted chat history in one shot.
            # Capture the *previous* value before overwriting ``_ai_settings``.
            prev_memory_enabled = bool(
                (self._ai_settings or {}).get("memory_enabled", True)
            )
            new_memory_enabled = bool(ai_settings.get("memory_enabled", True))
            memory_disabled_now = prev_memory_enabled and not new_memory_enabled

            self._ai_settings = self._clone_ai_settings(ai_settings)
            self._ai_allowlist_patterns = list(self._ai_settings.get("allowlist_patterns") or [])
            self._ai_run_id = self._new_run_id()
            self._ai_marker_token = self._new_marker_token()
            self._ai_plan = []
            self._ai_plan_index = 0
            self._ai_next_id = 1
            self._ai_user_message = msg
            self._ai_chat_mode = requested_chat_mode
            self._ai_execution_mode = "step" if requested_mode == "auto" else requested_mode
            self._ai_step_extra_count = 0
            self._ai_last_done_items = []
            self._ai_last_report = ""
            if not bool(self._ai_settings.get("memory_enabled", True)):
                self._ai_history = []

        # A3: persist the wipe to the DB when the user just flipped
        # memory_enabled from True → False. Doing this *outside* the lock
        # because ``clear_history`` is an async DB call.
        if memory_disabled_now:
            try:
                user_id = int(getattr(self, "_user_id", 0) or 0)
                server_id = int(getattr(self.server, "id", 0) or 0) if getattr(self, "server", None) else 0
                if user_id and server_id:
                    from servers.services.terminal_ai import clear_history as _clear_history

                    await _clear_history(user_id=user_id, server_id=server_id)
            except Exception as exc:  # pragma: no cover — non-fatal
                logger.debug("A3 chat-history wipe skipped: %s", exc)

        logger.debug(
            "Terminal AI request: server_id=%s run_id=%s",
            getattr(self.server, "id", None),
            self._ai_run_id,
        )
        if not self._ssh_proc:
            await self._send_ai_event({"type": "ai_error", "message": "SSH не подключён. Сначала нажмите Connect."})
            return
        if not self.server or not self._user_id:
            await self._send_ai_event({"type": "ai_error", "message": "Server not loaded"})
            return

        # 2.11: per-server read-only guard. Check flag synchronously via
        # database_sync_to_async before starting any LLM/exec work.
        if getattr(self.server, "ai_read_only", False):
            await self._send_ai_event(
                {
                    "type": "ai_error",
                    "message": (
                        "Сервер переведён в режим read-only для AI. "
                        "AI-агент может только читать состояние; изменяющие команды заблокированы."
                    ),
                }
            )
            await self._send_ai_event({"type": "ai_status", "status": "idle"})
            return

        self._ai_audit_context = {
            "user_id": self._user_id,
            "channel": "ws",
            "path": f"/ws/servers/{self.server.id}/terminal/",
            "entity_type": "server",
            "entity_id": str(self.server.id),
            "entity_name": self.server.name,
        }

        # Save user message to history
        self._add_to_history("user", msg)
        await log_user_activity_async(
            user_id=self._user_id,
            category="assistant",
            action="terminal_ai_request",
            status="success",
            description=msg[:400],
            entity_type="server",
            entity_id=self.server.id if self.server else "",
            entity_name=self.server.name if self.server else "",
            metadata={
                "message_length": len(msg),
                "chat_mode": requested_chat_mode,
                "execution_mode": requested_mode,
                "memory_enabled": bool(self._ai_settings.get("memory_enabled", True)),
                "auto_report": str(self._ai_settings.get("auto_report") or "auto"),
            },
        )
        await self._send_ai_event(
            {
                "type": "ai_status",
                "status": "thinking",
                "chat_mode": requested_chat_mode,
                "execution_mode": requested_mode,
            }
        )

        with audit_context(**self._ai_audit_context):
            # Nova: branch into the ReAct agent loop when requested. It
            # is a full alternative to the plan-then-execute pipeline —
            # no `_ai_plan`, no `_ai_process_queue`, no per-step planner.
            if requested_mode == "agent":
                async with self._ai_lock:
                    self._ai_task = asyncio.create_task(
                        self._run_ai_agent_background(
                            user_message=msg,
                            chat_mode=requested_chat_mode,
                        )
                    )
                return

            try:
                forbidden_patterns, rules_context, required_checks, _ = await self._get_ai_rules_and_forbidden(
                    self._user_id,
                    self.server.id,
                )
                merged_forbidden = list(forbidden_patterns or [])
                for pattern in list(self._ai_settings.get("blocklist_patterns") or []):
                    if str(pattern or "").strip() and str(pattern).strip().lower() not in {
                        p.lower() for p in merged_forbidden
                    }:
                        merged_forbidden.append(str(pattern).strip())
                plan_obj = await self._ai_plan_commands(
                    user_message=msg,
                    rules_context=rules_context,
                    terminal_tail=(self._terminal_tail or "")[-2000:],
                    history=list(self._ai_history) if bool(self._ai_settings.get("memory_enabled", True)) else [],
                    unavailable_cmds=set(getattr(self, "_unavailable_cmds", set())),
                    chat_mode=requested_chat_mode,
                    execution_mode=requested_mode,
                    # A5: forward dry-run state so the planner prompt can
                    # adapt (no hard behaviour change — the short-circuit
                    # in _ai_process_queue is authoritative).
                    dry_run=bool(self._ai_settings.get("dry_run", False)),
                )
            except Exception as e:
                err_msg = str(e).strip() or "Unknown error"
                if any(
                    hint in err_msg.lower() for hint in ("timeout", "429", "rate", "resource exhausted", "overloaded")
                ):
                    err_msg = "Временная ошибка API (лимит или перегрузка). Попробуйте позже."
                await self._send_ai_event({"type": "ai_error", "message": err_msg})
                await self._send_ai_event({"type": "ai_status", "status": "idle"})
                return

        mode = str(plan_obj.get("mode") or "execute").lower().strip()
        assistant_text = str(plan_obj.get("assistant_text") or "").strip()
        commands_raw = plan_obj.get("commands") or []
        selected_mode = requested_mode
        if requested_mode == "auto":
            selected_mode = self._resolve_auto_execution_mode(plan_obj, commands_raw, msg)
        if selected_mode not in ("step", "fast"):
            selected_mode = "step"

        async with self._ai_lock:
            self._ai_execution_mode = selected_mode

        # --- answer / ask mode: just reply, no commands needed ---
        if mode in ("answer", "ask"):
            self._add_to_history("assistant", assistant_text or "(ответ)")
            await self._send_ai_event(
                {
                    "type": "ai_response",
                    "mode": mode,
                    "assistant_text": assistant_text,
                    "commands": [],
                    "chat_mode": requested_chat_mode,
                    "execution_mode": selected_mode,
                    "requested_execution_mode": requested_mode,
                }
            )
            await self._send_ai_event({"type": "ai_status", "status": "idle"})
            return

        # --- execute mode ---
        commands: list[dict[str, str]] = []
        if isinstance(commands_raw, list):
            for it in commands_raw:
                if not isinstance(it, dict):
                    continue
                cmd = str(it.get("cmd") or "").strip()
                if not cmd:
                    continue
                why = str(it.get("why") or "").strip()
                commands.append({"cmd": cmd, "why": why})
        max_initial_commands = 3 if selected_mode == "step" else 10
        commands = commands[:max_initial_commands]

        plan_items: list[dict[str, Any]] = []
        seen_cmds: set[str] = set()
        next_id = 1
        # Always run preflight checks first (if configured).
        for check_cmd in required_checks or []:
            check = str(check_cmd or "").strip()
            if not check:
                continue
            key = check.lower()
            if key in seen_cmds:
                continue
            seen_cmds.add(key)
            item_id = next_id
            next_id += 1
            plan_items.append(
                self._build_plan_item(
                    item_id=item_id,
                    cmd=check,
                    why="Обязательная preflight-проверка перед выполнением задачи",
                    forbidden_patterns=merged_forbidden,
                    allowlist_patterns=list(self._ai_allowlist_patterns or []),
                    confirm_dangerous_commands=bool(self._ai_settings.get("confirm_dangerous_commands", True)),
                )
            )

        for c in commands:
            cmd = c["cmd"]
            key = cmd.lower()
            if key in seen_cmds:
                continue
            seen_cmds.add(key)
            why = c.get("why") or ""
            item_id = next_id
            next_id += 1
            plan_items.append(
                self._build_plan_item(
                    item_id=item_id,
                    cmd=cmd,
                    why=why,
                    forbidden_patterns=merged_forbidden,
                    allowlist_patterns=list(self._ai_allowlist_patterns or []),
                    confirm_dangerous_commands=bool(self._ai_settings.get("confirm_dangerous_commands", True)),
                    # F2-8: forward LLM-provided exec_mode hint when present.
                    exec_mode=c.get("exec_mode"),
                )
            )

        # Hard limit to keep runs predictable in terminal.
        plan_items = plan_items[:12]

        if requested_chat_mode == "ask" and plan_items:
            ask_prefix = "Режим Ask активен: команды ниже предложены для ручного запуска и не выполнятся без вашего подтверждения."
            assistant_text = f"{ask_prefix}\n\n{assistant_text}" if assistant_text else ask_prefix

        async with self._ai_lock:
            self._ai_plan = plan_items
            self._ai_plan_index = 0
            self._ai_next_id = next_id
            self._ai_forbidden_patterns = merged_forbidden or []

        await self._send_ai_event(
            {
                "type": "ai_response",
                "mode": "execute",
                "assistant_text": assistant_text,
                "commands": plan_items,
                "chat_mode": requested_chat_mode,
                "execution_mode": selected_mode,
                "requested_execution_mode": requested_mode,
            }
        )

        if not plan_items:
            self._add_to_history("assistant", assistant_text or "Команды не нужны")
            await self._send_ai_event({"type": "ai_status", "status": "idle"})
            return

        await self._send_ai_event({"type": "ai_status", "status": "running"})
        with audit_context(**self._ai_audit_context):
            async with self._ai_lock:
                self._ai_task = asyncio.create_task(self._ai_process_queue())

    async def _handle_ai_confirm(self, content: dict[str, Any]):
        try:
            cmd_id = int(content.get("id"))
        except Exception:
            await self._send_ai_event({"type": "ai_error", "message": "Некорректный id для подтверждения"})
            return

        should_start = False
        async with self._ai_lock:
            if not self._ai_plan or self._ai_plan_index >= len(self._ai_plan):
                return
            item = self._ai_plan[self._ai_plan_index]
            if int(item.get("id") or 0) != cmd_id:
                await self._send_ai_event(
                    {"type": "ai_error", "message": "Подтверждать можно только текущую ожидающую команду"}
                )
                return
            if not item.get("requires_confirm"):
                return
            item["requires_confirm"] = False
            item["confirmed"] = True
            item["status"] = "pending"
            if not self._ai_task or self._ai_task.done():
                should_start = True

        await self._send_ai_event({"type": "ai_command_status", "id": cmd_id, "status": "confirmed"})
        if should_start:
            await self._send_ai_event({"type": "ai_status", "status": "running"})
            with audit_context(**getattr(self, "_ai_audit_context", {})):
                async with self._ai_lock:
                    self._ai_task = asyncio.create_task(self._ai_process_queue())

    async def _handle_ai_cancel(self, content: dict[str, Any]):
        try:
            cmd_id = int(content.get("id"))
        except Exception:
            await self._send_ai_event({"type": "ai_error", "message": "Некорректный id для отмены"})
            return

        should_start = False
        async with self._ai_lock:
            if not self._ai_plan or self._ai_plan_index >= len(self._ai_plan):
                return
            item = self._ai_plan[self._ai_plan_index]
            if int(item.get("id") or 0) != cmd_id:
                await self._send_ai_event(
                    {"type": "ai_error", "message": "Отменять можно только текущую ожидающую команду"}
                )
                return
            item["status"] = "skipped"
            self._ai_plan_index += 1
            if not self._ai_task or self._ai_task.done():
                should_start = True

        await self._send_ai_event({"type": "ai_command_status", "id": cmd_id, "status": "skipped"})
        if should_start:
            await self._send_ai_event({"type": "ai_status", "status": "running"})
            with audit_context(**getattr(self, "_ai_audit_context", {})):
                async with self._ai_lock:
                    self._ai_task = asyncio.create_task(self._ai_process_queue())

    async def _handle_ai_clear_memory(self):
        async with self._ai_lock:
            self._ai_history = []
            self._ai_last_done_items = []
            self._ai_last_report = ""
        # F2-9: also wipe the persistent DB copy so a page reload does not
        # restore the history the user just cleared.
        try:
            user_id = int(getattr(self, "_user_id", 0) or 0)
            server_id = int(getattr(self.server, "id", 0) or 0) if getattr(self, "server", None) else 0
            if user_id and server_id:
                from servers.services.terminal_ai import clear_history as _clear_history

                await _clear_history(user_id=user_id, server_id=server_id)
        except Exception as exc:  # pragma: no cover — non-fatal
            logger.debug("terminal-ai chat history clear skipped: %s", exc)
        await self._send_ai_event(
            terminal_events.ai_response(
                assistant_text="🧹 Память текущего чата очищена.",
                execution_mode=str(getattr(self, "_ai_execution_mode", "step")),
            )
        )

    async def _handle_ai_explain_output(self, content: dict[str, Any]):
        """A6: turn a (command, output, exit_code) triple into a short
        human-readable explanation via the cheap ``terminal_chat`` bucket.

        Frontend sends::

            { type: "ai_explain_output", id: <cmd_id>, cmd, output, exit_code, question? }

        We reply with a single ``ai_explanation`` event keyed by the same
        ``id`` so the UI can render it inline next to the command card.
        """
        payload = content if isinstance(content, dict) else {}
        cmd = str(payload.get("cmd") or payload.get("command") or "").strip()
        output = str(payload.get("output") or "")
        cmd_id = payload.get("id")
        question = str(payload.get("question") or "").strip()
        try:
            exit_code: int | None = int(payload.get("exit_code"))
        except (TypeError, ValueError):
            exit_code = None

        if not cmd and not output:
            await self._send_ai_event(
                terminal_events.ai_error("Нужна команда и её вывод для объяснения.")
            )
            return

        from servers.services.terminal_ai import explain_command_output

        await self._send_ai_event(terminal_events.ai_status("explaining", id=cmd_id))

        try:
            text = await explain_command_output(
                command=cmd,
                output=output,
                exit_code=exit_code,
                user_question=question,
                semaphore=_TERMINAL_AI_LLM_SEMAPHORE,
            )
            await self._send_ai_event(
                terminal_events.ai_explanation(item_id=cmd_id, command=cmd, explanation=text)
            )
        except Exception as exc:
            logger.warning("AI output explanation failed: %s", exc)
            await self._send_ai_event(
                terminal_events.ai_error("Не удалось объяснить вывод команды.")
            )
        finally:
            await self._send_ai_event(terminal_events.ai_status("idle"))

    async def _handle_ai_generate_report(self, content: dict[str, Any]):
        force_regenerate = self._parse_bool((content or {}).get("force"), False)
        async with self._ai_lock:
            if self._ai_task and not self._ai_task.done():
                await self._send_ai_event(
                    terminal_events.ai_error("Дождитесь завершения текущего запуска ассистента.")
                )
                return
            done_items = list(self._ai_last_done_items or [])
            user_message = str(self._ai_user_message or "")
            cached_report = "" if force_regenerate else str(self._ai_last_report or "")

        if not done_items:
            await self._send_ai_event(
                terminal_events.ai_error("Нет завершённых команд для формирования отчёта.")
            )
            return

        try:
            await self._send_ai_event(terminal_events.ai_status("generating_report"))
            report = cached_report or await self._generate_ai_report_text(user_message, done_items)
            status = self._compute_report_status(done_items)
            await self._send_ai_event(terminal_events.ai_report(report=report, status=status))
            async with self._ai_lock:
                self._ai_last_report = report
            if bool(self._ai_settings.get("memory_enabled", True)):
                self._add_to_history("assistant", f"[Ручной отчёт]\n{report[:400]}")
        except Exception as exc:
            await self._send_ai_event(terminal_events.ai_error(str(exc) or "Не удалось сформировать отчёт"))
        finally:
            await self._send_ai_event(terminal_events.ai_status("idle"))

    def _add_to_history(self, role: str, text: str) -> None:
        """Append a message to the conversation history (in-memory + DB, F2-9).

        The in-memory deque is the fast path used by every prompt builder;
        we additionally fire-and-forget a DB write so the conversation
        survives WebSocket reconnects and page reloads.
        """
        if not bool(getattr(self, "_ai_settings", {}).get("memory_enabled", True)):
            return
        entry = {"role": role, "text": (text or "")[:800]}
        if not hasattr(self, "_ai_history"):
            self._ai_history = []
        self._ai_history.append(entry)
        ttl_requests = int(getattr(self, "_ai_settings", {}).get("memory_ttl_requests", 6) or 6)
        max_entries = max(4, min(ttl_requests, 20) * 6)
        if len(self._ai_history) > max_entries:
            self._ai_history = self._ai_history[-max_entries:]

        # F2-9: persist to DB in a tracked background task so UX is not
        # slowed down by the extra INSERT + pruning queries.
        try:
            user_id = int(getattr(self, "_user_id", 0) or 0)
            server_id = int(getattr(self.server, "id", 0) or 0) if getattr(self, "server", None) else 0
            if user_id and server_id and entry["text"]:
                from servers.services.terminal_ai import append_message as _append_history

                task = asyncio.create_task(
                    _append_history(
                        user_id=user_id,
                        server_id=server_id,
                        role=role,
                        text=entry["text"],
                        max_entries=max_entries * 2,
                    )
                )
                self._ai_background_tasks.add(task)
                task.add_done_callback(self._ai_background_tasks.discard)
        except RuntimeError:
            # No running event loop (e.g. synchronous test harness) — skip.
            pass
        except Exception as exc:  # pragma: no cover — non-fatal
            logger.debug("terminal-ai chat history persist skipped: %s", exc)

    def _build_plan_item(
        self,
        item_id: int,
        cmd: str,
        why: str,
        forbidden_patterns: list[str] | None = None,
        allowlist_patterns: list[str] | None = None,
        confirm_dangerous_commands: bool = True,
        exec_mode: str | None = None,
    ) -> dict[str, Any]:
        from servers.services.terminal_ai import build_plan_item

        return build_plan_item(
            item_id=item_id,
            command=cmd,
            why=why,
            chat_mode=getattr(self, "_ai_chat_mode", "agent"),
            forbidden_patterns=forbidden_patterns,
            allowlist_patterns=allowlist_patterns,
            confirm_dangerous_commands=confirm_dangerous_commands,
            exec_mode=exec_mode,
        )

    def _legacy_direct_exec_enabled(self) -> bool:
        """Whether legacy Terminal AI may use the non-PTY direct executor."""
        return self._normalize_execution_mode(getattr(self, "_ai_execution_mode", "step")) != "fast"

    @staticmethod
    def _normalize_command_text(cmd: str) -> str:
        from servers.services.terminal_ai import normalize_command_text

        return normalize_command_text(cmd)

    async def _ai_process_queue(self):
        """
        Execute queued AI commands sequentially.
        Pauses when a command requires confirmation.
        """
        send_idle = True
        execution_mode = self._normalize_execution_mode(getattr(self, "_ai_execution_mode", "step"))
        step_mode = execution_mode == "step"
        direct_exec_enabled = self._legacy_direct_exec_enabled()
        try:
            while True:
                if not self._ssh_proc:
                    break
                if not self.server or not self._user_id:
                    break

                # 4.2: parallel batch detection ──────────────────────────
                batch_indices: list[int] = []
                plan_snapshot: list[dict[str, Any]] = []
                async with self._ai_lock:
                    if not self._ai_plan or self._ai_plan_index >= len(self._ai_plan):
                        break
                    if direct_exec_enabled and not step_mode and self._ssh_conn:
                        from servers.services.parallel_executor import collect_parallel_batch

                        batch_indices = collect_parallel_batch(
                            self._ai_plan, self._ai_plan_index, step_mode=step_mode,
                        )
                        if batch_indices:
                            plan_snapshot = [self._ai_plan[i] for i in batch_indices]

                if batch_indices:
                    await self._execute_parallel_batch(plan_snapshot, batch_indices)
                    async with self._ai_lock:
                        new_idx = max(batch_indices) + 1
                        if new_idx > self._ai_plan_index:
                            self._ai_plan_index = new_idx
                    continue
                # ── end parallel batch ─────────────────────────────────────

                async with self._ai_lock:
                    item = self._ai_plan[self._ai_plan_index]
                    item_id = int(item.get("id") or 0)
                    cmd = str(item.get("cmd") or "").strip()
                    reason = str(item.get("reason") or "").strip()
                    requires_confirm = bool(item.get("requires_confirm"))
                    status = str(item.get("status") or "pending")

                    if status in ("done", "skipped", "cancelled"):
                        self._ai_plan_index += 1
                        continue

                    if bool(item.get("blocked")):
                        item["status"] = "skipped"
                        self._ai_plan_index += 1
                        await self._send_ai_event(
                            terminal_events.ai_command_status(
                                item_id=item_id,
                                status="skipped",
                                reason=reason or "forbidden",
                            )
                        )
                        continue

                    if requires_confirm:
                        item["status"] = "pending_confirm"
                        # Pause until user confirms/cancels current command
                        await self._send_ai_event(
                            terminal_events.ai_status(
                                "waiting_confirm",
                                id=item_id,
                                reason=reason or "dangerous",
                            )
                        )
                        send_idle = False
                        return

                    item["status"] = "running"

                await self._send_ai_event(
                    terminal_events.ai_command_status(item_id=item_id, status="running")
                )

                # F2-8 v2: route safe stateless commands through a non-PTY
                # channel so the interactive shell is not polluted by
                # diagnostic reads (df -h, ps aux, systemctl status…).
                item_exec_mode = str(item.get("exec_mode") or "pty").strip().lower()
                if not direct_exec_enabled and item_exec_mode == "direct":
                    item_exec_mode = "pty"
                # A5: dry-run short-circuit. We do NOT touch the remote
                # host at all — neither via PTY nor via exec_direct. The
                # fake output makes downstream history/report/memory work
                # exactly as on a real run so the user can preview the
                # plan end-to-end.
                dry_run_active = bool((self._ai_settings or {}).get("dry_run", False))

                # 2.4: capture pre-execution snapshot for file-modifying cmds.
                if not dry_run_active and self._ssh_conn:
                    await self._maybe_snapshot_file(cmd, item_id)

                try:
                    if dry_run_active:
                        output_snippet = f"[DRY-RUN] Would execute: {cmd}"
                        exit_code = 0
                        # Emit a direct_output-style event so the UI
                        # renders the preview inline without marker tokens.
                        await self._send_ai_event(
                            terminal_events.ai_direct_output(
                                item_id=item_id,
                                command=cmd,
                                output=output_snippet,
                                exit_code=0,
                                dry_run=True,
                            )
                        )
                    elif item_exec_mode == "direct":
                        exit_code, output_snippet = await self._ai_execute_command_direct(cmd, item_id)
                    else:
                        exit_code, output_snippet = await self._ai_execute_command(cmd, item_id)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning("AI command execution failed (id=%s): %s", item_id, e)
                    # Do not crash the whole queue on one bad command; let recovery logic decide.
                    exit_code = 1
                    output_snippet = f"WEUAI_EXECUTION_ERROR: {type(e).__name__}: {e}"
                await self._log_ai_command_history(
                    user_id=self._user_id,
                    server_id=self.server.id,
                    command=cmd,
                    output_snippet=output_snippet,
                    exit_code=exit_code,
                )

                # Track unavailable commands (exit=127 = "command not found")
                if exit_code == 127:
                    base_cmd = cmd.strip().split()[0].split("/")[-1] if cmd.strip() else ""
                    if base_cmd:
                        self._unavailable_cmds.add(base_cmd)

                # ── Adaptive error recovery ─────────────────────────────────
                # For non-trivial failures (not success, not interrupted, not skipped):
                # call the LLM to decide: retry / skip / ask user / abort.
                #
                # F1-9: in step-mode we skip this dedicated recovery call and let
                # the unified post-step controller (_ai_step_decide_next) handle
                # both success and error cases in a single LLM round-trip
                # (-30–50% LLM cost in step-mode on errors). In fast-mode the
                # block below is the only place where errors are handled.
                recovery_action = None
                skip_recovery = step_mode  # unified controller handles errors
                if exit_code not in (0, 130, None) and not item.get("_no_recovery") and not skip_recovery:
                    retries = self._ai_error_retries.get(item_id, 0)
                    if retries < 2:
                        await self._send_ai_event(
                            terminal_events.ai_status(
                                "analyzing_error",
                                cmd=cmd,
                                exit_code=exit_code,
                            )
                        )
                        try:
                            async with self._ai_lock:
                                remaining_cmds = [
                                    it.get("cmd", "")
                                    for it in self._ai_plan[self._ai_plan_index + 1 :]
                                    if it.get("status") not in ("done", "skipped")
                                ]
                            decision = await self._ai_handle_error(cmd, exit_code, output_snippet, remaining_cmds)
                            recovery_action = decision.get("action", "skip")

                            if recovery_action == "retry":
                                new_cmd = str(decision.get("cmd") or "").strip()
                                why = str(decision.get("why") or "Retry after error")
                                if new_cmd and new_cmd != cmd:
                                    next_id = self._ai_next_id
                                    self._ai_next_id += 1
                                    self._ai_error_retries[next_id] = retries + 1
                                    async with self._ai_lock:
                                        forbidden_patterns = list(self._ai_forbidden_patterns or [])
                                        allowlist_patterns = list(self._ai_allowlist_patterns or [])
                                        confirm_dangerous = bool(
                                            self._ai_settings.get("confirm_dangerous_commands", True)
                                        )
                                    new_item = self._build_plan_item(
                                        item_id=next_id,
                                        cmd=new_cmd,
                                        why=why,
                                        forbidden_patterns=forbidden_patterns,
                                        allowlist_patterns=allowlist_patterns,
                                        confirm_dangerous_commands=confirm_dangerous,
                                    )
                                    new_item["_no_recovery"] = False
                                    async with self._ai_lock:
                                        # Insert right after current position
                                        self._ai_plan.insert(self._ai_plan_index + 1, new_item)
                                    await self._send_ai_event(
                                        {
                                            "type": "ai_recovery",
                                            "original_cmd": cmd,
                                            "new_cmd": new_cmd,
                                            "new_id": next_id,
                                            "why": why,
                                            "requires_confirm": bool(new_item.get("requires_confirm")),
                                            "reason": str(new_item.get("reason") or ""),
                                            "streaming": bool(new_item.get("streaming")),
                                        }
                                    )

                            elif recovery_action == "ask":
                                question = str(decision.get("question") or "Как лучше продолжить?")
                                q_id = f"q_{item_id}_{self._ai_next_id}"
                                self._ai_next_id += 1
                                loop = asyncio.get_event_loop()
                                reply_fut: asyncio.Future = loop.create_future()
                                self._ai_reply_futures[q_id] = reply_fut
                                await self._send_ai_event(
                                    {
                                        "type": "ai_question",
                                        "q_id": q_id,
                                        "question": question,
                                        "cmd": cmd,
                                        "exit_code": exit_code,
                                    }
                                )
                                try:
                                    user_reply = await asyncio.wait_for(reply_fut, timeout=300)
                                    self._add_to_history("user", f"[Ответ агенту]: {user_reply}")
                                    # Re-evaluate with user's answer
                                    decision2 = await self._ai_handle_error(
                                        cmd, exit_code, output_snippet, remaining_cmds, user_reply=user_reply
                                    )
                                    if decision2.get("action") == "retry":
                                        new_cmd2 = str(decision2.get("cmd") or "").strip()
                                        why2 = str(decision2.get("why") or "")
                                        if new_cmd2 and new_cmd2 != cmd:
                                            next_id2 = self._ai_next_id
                                            self._ai_next_id += 1
                                            self._ai_error_retries[next_id2] = retries + 1
                                            async with self._ai_lock:
                                                forbidden_patterns = list(self._ai_forbidden_patterns or [])
                                                allowlist_patterns = list(self._ai_allowlist_patterns or [])
                                                confirm_dangerous = bool(
                                                    self._ai_settings.get("confirm_dangerous_commands", True)
                                                )
                                            new_item2 = self._build_plan_item(
                                                item_id=next_id2,
                                                cmd=new_cmd2,
                                                why=why2,
                                                forbidden_patterns=forbidden_patterns,
                                                allowlist_patterns=allowlist_patterns,
                                                confirm_dangerous_commands=confirm_dangerous,
                                            )
                                            new_item2["_no_recovery"] = False
                                            async with self._ai_lock:
                                                self._ai_plan.insert(self._ai_plan_index + 1, new_item2)
                                            await self._send_ai_event(
                                                {
                                                    "type": "ai_recovery",
                                                    "original_cmd": cmd,
                                                    "new_cmd": new_cmd2,
                                                    "new_id": next_id2,
                                                    "why": why2,
                                                    "requires_confirm": bool(new_item2.get("requires_confirm")),
                                                    "reason": str(new_item2.get("reason") or ""),
                                                    "streaming": bool(new_item2.get("streaming")),
                                                }
                                            )
                                            recovery_action = "retry"
                                    elif decision2.get("action") == "abort":
                                        recovery_action = "abort"
                                        await self._send_ai_event(
                                            {
                                                "type": "ai_error",
                                                "message": str(decision2.get("why") or "Выполнение прервано"),
                                            }
                                        )
                                except asyncio.TimeoutError:
                                    # User didn't reply in time → skip
                                    logger.info("ai_question timeout, skipping command")
                                    recovery_action = "skip"
                                finally:
                                    self._ai_reply_futures.pop(q_id, None)

                            elif recovery_action == "abort":
                                await self._send_ai_event(
                                    {
                                        "type": "ai_error",
                                        "message": str(
                                            decision.get("why") or "Выполнение прервано из-за критической ошибки"
                                        ),
                                    }
                                )

                        except asyncio.CancelledError:
                            raise
                        except Exception as e:
                            logger.warning("Error recovery LLM failed: %s", e)
                            recovery_action = "skip"

                if recovery_action == "abort":
                    break
                # ── End adaptive error recovery ─────────────────────────────

                async with self._ai_lock:
                    if (
                        self._ai_plan_index < len(self._ai_plan)
                        and int(self._ai_plan[self._ai_plan_index].get("id") or 0) == item_id
                    ):
                        self._ai_plan[self._ai_plan_index]["status"] = "done"
                        self._ai_plan[self._ai_plan_index]["exit_code"] = exit_code
                        self._ai_plan[self._ai_plan_index]["output_snippet"] = output_snippet or ""
                        self._ai_plan_index += 1

                is_stream = bool(item.get("streaming", False))
                await self._send_ai_event(
                    {
                        "type": "ai_command_status",
                        "id": item_id,
                        "status": "done",
                        "exit_code": exit_code,
                        "streaming": is_stream,
                    }
                )

                # Step-by-step mode: re-evaluate after each command, not only on errors.
                if step_mode:
                    try:
                        async with self._ai_lock:
                            remaining_cmds = [
                                str(it.get("cmd") or "").strip()
                                for it in self._ai_plan[self._ai_plan_index :]
                                if it.get("status") not in ("done", "skipped")
                            ]
                        decision = await self._ai_step_decide_next(
                            user_goal=(self._ai_user_message or ""),
                            last_cmd=cmd,
                            exit_code=int(exit_code if exit_code is not None else -1),
                            output=output_snippet or "",
                            remaining_cmds=remaining_cmds,
                        )

                        action = str(decision.get("action") or "continue").lower().strip()
                        # Ask user if required, then re-evaluate with reply.
                        if action == "ask":
                            question = str(decision.get("question") or "Как продолжить дальше?").strip()
                            q_id = f"q_step_{item_id}_{self._ai_next_id}"
                            self._ai_next_id += 1
                            loop = asyncio.get_event_loop()
                            reply_fut: asyncio.Future = loop.create_future()
                            self._ai_reply_futures[q_id] = reply_fut
                            await self._send_ai_event(
                                {
                                    "type": "ai_question",
                                    "q_id": q_id,
                                    "question": question,
                                    "cmd": cmd,
                                    "exit_code": exit_code,
                                }
                            )
                            try:
                                user_reply = await asyncio.wait_for(reply_fut, timeout=300)
                                self._add_to_history("user", f"[Ответ на шаг]: {user_reply}")
                                decision = await self._ai_step_decide_next(
                                    user_goal=(self._ai_user_message or ""),
                                    last_cmd=cmd,
                                    exit_code=int(exit_code if exit_code is not None else -1),
                                    output=output_snippet or "",
                                    remaining_cmds=remaining_cmds,
                                    user_reply=user_reply,
                                )
                                action = str(decision.get("action") or "continue").lower().strip()
                            except asyncio.TimeoutError:
                                action = "continue"
                            finally:
                                self._ai_reply_futures.pop(q_id, None)

                        # F1-9: unified step controller also handles retry/skip on error.
                        if action == "retry":
                            # Replace failed cmd with fixed one; insert next in queue.
                            retries = self._ai_error_retries.get(item_id, 0)
                            new_cmd = str(decision.get("cmd") or "").strip()
                            if new_cmd and new_cmd != cmd and retries < 2:
                                async with self._ai_lock:
                                    forbidden_patterns = list(self._ai_forbidden_patterns or [])
                                    allowlist_patterns = list(self._ai_allowlist_patterns or [])
                                    retry_id = int(self._ai_next_id)
                                    self._ai_next_id += 1
                                    self._ai_error_retries[retry_id] = retries + 1
                                    retry_item = self._build_plan_item(
                                        item_id=retry_id,
                                        cmd=new_cmd,
                                        why=str(decision.get("why") or "Retry after error (step-mode)"),
                                        forbidden_patterns=forbidden_patterns,
                                        allowlist_patterns=allowlist_patterns,
                                        confirm_dangerous_commands=bool(
                                            self._ai_settings.get("confirm_dangerous_commands", True)
                                        ),
                                    )
                                    retry_item["_no_recovery"] = False
                                    self._ai_plan.insert(self._ai_plan_index, retry_item)
                                await self._send_ai_event(
                                    {
                                        "type": "ai_recovery",
                                        "original_cmd": cmd,
                                        "new_cmd": new_cmd,
                                        "new_id": retry_id,
                                        "why": str(decision.get("why") or ""),
                                        "requires_confirm": bool(retry_item.get("requires_confirm")),
                                        "reason": str(retry_item.get("reason") or ""),
                                        "streaming": bool(retry_item.get("streaming")),
                                    }
                                )
                        elif action == "skip":
                            # Non-critical failure on the (already completed) item; just proceed.
                            # Nothing to do — the remaining plan continues as-is.
                            pass
                        elif action == "next":
                            next_cmd = str(decision.get("next_cmd") or "").strip()
                            if next_cmd:
                                extra_limit = 20
                                if self._ai_step_extra_count >= extra_limit:
                                    await self._send_ai_event(
                                        {
                                            "type": "ai_response",
                                            "mode": "answer",
                                            "assistant_text": (
                                                "Достигнут защитный лимит дополнительных адаптивных шагов "
                                                f"({extra_limit}) в режиме step-by-step. "
                                                "Продолжаю выполнение уже запланированных команд. "
                                                "Для длинных линейных задач переключите режим на Fast или Auto."
                                            ),
                                            "commands": [],
                                            "execution_mode": "step",
                                        }
                                    )
                                else:
                                    async with self._ai_lock:
                                        forbidden_patterns = list(self._ai_forbidden_patterns or [])
                                        allowlist_patterns = list(self._ai_allowlist_patterns or [])
                                        next_id = int(self._ai_next_id)
                                        self._ai_next_id += 1
                                        self._ai_step_extra_count += 1
                                        new_item = self._build_plan_item(
                                            item_id=next_id,
                                            cmd=next_cmd,
                                            why=str(decision.get("why") or "Следующий адаптивный шаг"),
                                            forbidden_patterns=forbidden_patterns,
                                            allowlist_patterns=allowlist_patterns,
                                            confirm_dangerous_commands=bool(
                                                self._ai_settings.get("confirm_dangerous_commands", True)
                                            ),
                                        )
                                        self._ai_plan.insert(self._ai_plan_index, new_item)
                                    await self._send_ai_event(
                                        {
                                            "type": "ai_response",
                                            "mode": "execute",
                                            "assistant_text": str(
                                                decision.get("assistant_text")
                                                or "Добавляю следующий шаг по результатам проверки."
                                            ),
                                            "commands": [new_item],
                                            "execution_mode": "step",
                                        }
                                    )

                        elif action == "done":
                            done_text = str(
                                decision.get("assistant_text") or "Цель достигнута. Останавливаю дальнейшие шаги."
                            ).strip()
                            self._add_to_history("assistant", done_text)
                            await self._send_ai_event(
                                {
                                    "type": "ai_response",
                                    "mode": "answer",
                                    "assistant_text": done_text,
                                    "commands": [],
                                    "execution_mode": "step",
                                }
                            )
                            pending_ids: list[int] = []
                            async with self._ai_lock:
                                for it in self._ai_plan[self._ai_plan_index :]:
                                    iid = int(it.get("id") or 0)
                                    st = str(it.get("status") or "")
                                    if iid and st not in ("done", "skipped", "cancelled"):
                                        it["status"] = "skipped"
                                        pending_ids.append(iid)
                                self._ai_plan_index = len(self._ai_plan)
                            for pid in pending_ids:
                                await self._send_ai_event(
                                    {
                                        "type": "ai_command_status",
                                        "id": pid,
                                        "status": "skipped",
                                        "reason": "goal_achieved",
                                    }
                                )
                            break

                        elif action == "abort":
                            await self._send_ai_event(
                                {
                                    "type": "ai_error",
                                    "message": str(
                                        decision.get("assistant_text")
                                        or "Выполнение остановлено из-за критического состояния."
                                    ),
                                }
                            )
                            break
                        # continue => keep executing current queue
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        logger.warning("Step-by-step post-step analysis failed: %s", e)

            # После выполнения всех команд — сформировать отчёт по выводу (анализ логов, проблем и т.д.)
            if send_idle:
                user_msg = getattr(self, "_ai_user_message", "") or ""
                async with self._ai_lock:
                    plan_snapshot = list(self._ai_plan) if self._ai_plan else []
                done_items = [
                    {
                        "cmd": str(it.get("cmd") or "").strip(),
                        "exit_code": it.get("exit_code"),
                        "output": (str(it.get("output_snippet") or "").strip())[:4000],
                    }
                    for it in plan_snapshot
                    if str(it.get("status") or "") == "done"
                ]
                done_with_output = [x for x in done_items if (x.get("output") or "").strip()]
                async with self._ai_lock:
                    self._ai_last_done_items = list(done_items)
                if user_msg and done_items:
                    report = ""
                    if self._is_auto_report_enabled(self._ai_settings, getattr(self, "_ai_execution_mode", "step")):
                        await self._send_ai_event({"type": "ai_status", "status": "generating_report"})
                        report = await self._generate_ai_report_text(user_msg, done_items)
                        # A5: clearly mark the report so the user can't
                        # confuse a dry-run preview with a real operation.
                        if bool((self._ai_settings or {}).get("dry_run", False)) and report:
                            report = (
                                "🔸 **DRY-RUN RESULT** — никаких изменений на сервере не сделано.\n\n"
                                + report
                            )
                        await self._send_ai_event(
                            {
                                "type": "ai_report",
                                "report": report,
                                "status": self._compute_report_status(done_items),
                            }
                        )
                    async with self._ai_lock:
                        self._ai_last_report = report
                    if bool(self._ai_settings.get("memory_enabled", True)):
                        exec_summary_parts = []
                        for it in done_items:
                            c = it.get("exit_code")
                            mark = "✓" if c == 0 else ("⏹" if c == 130 else f"✗(exit={c})")
                            exec_summary_parts.append(f"  {mark} {it['cmd']}")
                        exec_summary = "Выполнено:\n" + "\n".join(exec_summary_parts)
                        self._add_to_history("assistant", exec_summary)
                        if report:
                            self._add_to_history("assistant", f"[Отчёт]\n{report[:400]}")

                    # Save concise server memory snapshot only for durable
                    # operational signals. The extraction is done in a
                    # fire-and-forget background task (F1-7) so that the UI
                    # sees ``idle`` immediately after the report; the memory
                    # write is ~4-5s of LLM latency that must not block UX.
                    memory_candidates = self._select_memory_candidate_commands(done_with_output)
                    # A2: additional guard — skip the LLM extraction call
                    # on trivially-diagnostic runs (single command, or all
                    # commands in the noise list with zero-exit). Saves
                    # ~30% of extraction calls in typical usage without
                    # losing any durable signal.
                    from servers.services.terminal_ai import should_extract_memory as _should_extract

                    if (
                        memory_candidates
                        and _should_extract(done_items)
                        and self.server
                        and self._user_id
                        and bool(self._ai_settings.get("memory_enabled", True))
                    ):
                        self._spawn_memory_extraction_task(
                            user_message=user_msg,
                            commands_with_output=memory_candidates,
                            report=report,
                            user_id=int(self._user_id),
                            server_id=int(self.server.id),
                            audit_ctx=dict(self._ai_audit_context or {}),
                        )

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("AI processing failed")
            err_msg = str(e).strip() or "Unknown error"
            if any(
                hint in err_msg.lower() for hint in ("timeout", "429", "rate", "resource exhausted", "overloaded")
            ):
                err_msg = "Временная ошибка API (лимит или перегрузка). Попробуйте позже."
            await self._send_ai_event({"type": "ai_error", "message": err_msg})
        finally:
            if send_idle:
                await self._send_ai_event({"type": "ai_status", "status": "idle"})

    async def _ai_execute_command(self, cmd: str, cmd_id: int) -> tuple[int, str]:
        """
        Type and execute a command in the interactive PTY and wait for an internal marker.
        For streaming/interactive commands: auto-interrupts with Ctrl+C after 8 s.
        Returns (exit_code, output_snippet).
        """
        if not self._ssh_proc:
            raise RuntimeError("SSH process not connected")

        clean_cmd = self._normalize_command_text(cmd)
        if not clean_cmd:
            return -1, ""

        is_streaming = self._is_streaming_command(clean_cmd)
        is_install = self._is_install_command(clean_cmd)

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[int] = loop.create_future()
        async with self._ai_lock:
            self._ai_exit_futures[cmd_id] = fut
            self._ai_active_cmd_id = cmd_id
            self._ai_active_output = ""

        with self._suppress_terminal_input_capture():
            await self._ai_type_text(clean_cmd)
            self._ssh_proc.stdin.write("\n")

            # Marker line to capture exit status (filtered from UI output)
            marker_prefix = self._marker_prefix()
            marker_var = f"{marker_prefix}{cmd_id}"
            marker_cmd = f'{marker_var}=$?; echo "{marker_prefix}{cmd_id}:${{{marker_var}}}__"'
            self._ssh_proc.stdin.write(marker_cmd + "\n")

        # For streaming commands: schedule Ctrl+C after 8 s to allow output capture
        interrupt_task: asyncio.Task | None = None
        if is_streaming:
            interrupt_task = asyncio.create_task(self._interrupt_streaming_after(8.0))

        # For install commands: start periodic monitoring
        monitor_task: asyncio.Task | None = None
        if is_install and not is_streaming:
            monitor_task = asyncio.create_task(self._monitor_install(cmd_id, clean_cmd))

        exit_code = -1
        timeout = 30 if is_streaming else 600  # installs may take up to 10 min
        try:
            exit_code = int(await asyncio.wait_for(fut, timeout=timeout))
        except asyncio.TimeoutError:
            if is_streaming:
                # Force Ctrl+C as last resort
                try:
                    if self._ssh_proc:
                        self._ssh_proc.stdin.write("\x03")
                except Exception:
                    pass
                exit_code = 130
            else:
                raise TimeoutError("Timeout waiting for command completion marker")
        finally:
            # Always cancel the interrupt/monitor tasks if still pending
            if interrupt_task and not interrupt_task.done():
                interrupt_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await interrupt_task
            if monitor_task and not monitor_task.done():
                monitor_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await monitor_task
            async with self._ai_lock:
                self._ai_exit_futures.pop(cmd_id, None)

        # Short delay so buffered output arrives in _ai_active_output
        await asyncio.sleep(0.4)
        output_snippet = (self._ai_active_output or "")[-6000:]
        async with self._ai_lock:
            self._ai_active_cmd_id = None
        return exit_code, output_snippet

    # F2-8 v2: non-PTY execution path for safe stateless reads.
    #
    # How it differs from :meth:`_ai_execute_command`:
    #   * uses a fresh channel via ``SSHClientConnection.run(...)`` — nothing
    #     is typed into the interactive PTY, so the user's shell state (cwd,
    #     history, env) is untouched and there are no marker tokens mixed
    #     into the terminal output;
    #   * has its own shorter default timeout (30s) because ``direct`` is
    #     only picked for non-streaming read-only commands;
    #   * emits an ``ai_direct_output`` WS event so the UI can render the
    #     captured stdout inline in the AI panel rather than the terminal.
    DIRECT_EXEC_TIMEOUT_SEC = 30
    DIRECT_EXEC_MAX_OUTPUT = 6000

    async def _ai_execute_command_direct(self, cmd: str, cmd_id: int) -> tuple[int, str]:
        """Execute ``cmd`` via a non-PTY asyncssh channel.

        Returns ``(exit_code, captured_output)``; the caller treats this
        tuple the same way as :meth:`_ai_execute_command` so recovery,
        logging and memory-ingestion flows all keep working.
        """
        if not self._ssh_conn:
            raise RuntimeError("SSH connection not established")

        clean_cmd = self._normalize_command_text(cmd)
        if not clean_cmd:
            return -1, ""

        try:
            result = await asyncio.wait_for(
                self._ssh_conn.run(clean_cmd, check=False),
                timeout=self.DIRECT_EXEC_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            output_snippet = "WEUAI_EXECUTION_ERROR: direct exec timed out"
            exit_code = 124  # POSIX convention for `timeout`
        else:
            stdout = str(result.stdout or "")
            stderr = str(result.stderr or "")
            combined = stdout + (("\n" + stderr) if stderr else "")
            output_snippet = combined[-self.DIRECT_EXEC_MAX_OUTPUT :]
            # asyncssh returns None when the remote side reported no exit
            # status (rare, but happens on certain device shells). Treat as
            # failure so the recovery path kicks in.
            exit_code = (
                int(result.exit_status) if result.exit_status is not None else 1
            )

        # Surface the captured output to the UI — this is the ONLY place
        # the user sees direct-path output (the PTY was not touched).
        await self._send_ai_event(
            {
                "type": "ai_direct_output",
                "id": cmd_id,
                "cmd": clean_cmd,
                "output": output_snippet,
                "exit_code": exit_code,
            }
        )
        return exit_code, output_snippet

    # ── 2.4: pre-execution file snapshots ──────────────────────────────────

    SNAPSHOT_READ_TIMEOUT_SEC = 10

    async def _maybe_snapshot_file(self, cmd: str, cmd_id: int) -> None:
        """If *cmd* will modify a file, read it via SSH and save a snapshot.

        Best-effort: any failure is logged but never blocks execution.
        """
        from servers.services.terminal_snapshotting import capture_pre_execution_snapshot

        if not self._ssh_conn or not self.server:
            return
        await capture_pre_execution_snapshot(
            command=cmd,
            cmd_id=cmd_id,
            ssh_conn=self._ssh_conn,
            server_id=int(self.server.id),
            user_id=self._user_id,
            timeout_seconds=self.SNAPSHOT_READ_TIMEOUT_SEC,
        )

    # ── 4.2: parallel batch execution ──────────────────────────────────────

    async def _execute_parallel_batch(
        self,
        items: list[dict[str, Any]],
        plan_indices: list[int],
    ) -> None:
        """Run a batch of ``exec_mode=direct`` commands concurrently.

        Each command gets its own non-PTY SSH channel via
        :meth:`_ai_execute_command_direct`.  Snapshots, history logging
        and status events are handled per-command.  No error recovery is
        attempted within the batch — failed items are simply marked done
        with their exit code so downstream reporting can handle them.
        """
        if not items:
            return

        item_ids = [int(it.get("id") or 0) for it in items]
        await self._send_ai_event(
            {
                "type": "ai_parallel_batch",
                "status": "start",
                "ids": item_ids,
                "count": len(items),
            }
        )

        # Mark all as running.
        for it in items:
            it["status"] = "running"
        for iid in item_ids:
            await self._send_ai_event(
                {"type": "ai_command_status", "id": iid, "status": "running"}
            )

        dry_run_active = bool((self._ai_settings or {}).get("dry_run", False))

        async def _run_one(item: dict[str, Any]) -> tuple[int, int, str]:
            """Execute a single direct command. Returns (item_id, exit_code, output)."""
            iid = int(item.get("id") or 0)
            cmd = str(item.get("cmd") or "").strip()
            # 2.4: snapshot before execution
            if not dry_run_active and self._ssh_conn:
                await self._maybe_snapshot_file(cmd, iid)
            try:
                if dry_run_active:
                    out = f"[DRY-RUN] Would execute: {cmd}"
                    await self._send_ai_event(
                        {
                            "type": "ai_direct_output",
                            "id": iid,
                            "cmd": cmd,
                            "output": out,
                            "exit_code": 0,
                            "dry_run": True,
                        }
                    )
                    return iid, 0, out
                ec, out = await self._ai_execute_command_direct(cmd, iid)
                return iid, ec, out
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("Parallel exec failed (id=%s): %s", iid, e)
                return iid, 1, f"WEUAI_EXECUTION_ERROR: {type(e).__name__}: {e}"

        results = await asyncio.gather(*[_run_one(it) for it in items], return_exceptions=True)

        # Process results.
        for item, plan_idx, result in zip(items, plan_indices, results, strict=True):
            iid = int(item.get("id") or 0)
            if isinstance(result, BaseException):
                exit_code, output_snippet = 1, f"WEUAI_EXECUTION_ERROR: {result}"
            else:
                _, exit_code, output_snippet = result

            await self._log_ai_command_history(
                user_id=self._user_id,
                server_id=self.server.id,
                command=str(item.get("cmd") or ""),
                output_snippet=output_snippet,
                exit_code=exit_code,
            )
            if exit_code == 127:
                base_cmd = str(item.get("cmd") or "").strip().split()[0].split("/")[-1]
                if base_cmd:
                    self._unavailable_cmds.add(base_cmd)

            async with self._ai_lock:
                if plan_idx < len(self._ai_plan):
                    self._ai_plan[plan_idx]["status"] = "done"
                    self._ai_plan[plan_idx]["exit_code"] = exit_code
                    self._ai_plan[plan_idx]["output_snippet"] = output_snippet or ""

            await self._send_ai_event(
                {
                    "type": "ai_command_status",
                    "id": iid,
                    "status": "done",
                    "exit_code": exit_code,
                }
            )

        await self._send_ai_event(
            {
                "type": "ai_parallel_batch",
                "status": "done",
                "ids": item_ids,
                "count": len(items),
            }
        )

    async def _interrupt_streaming_after(self, delay: float) -> None:
        """Send Ctrl+C after `delay` seconds to interrupt a streaming command."""
        await asyncio.sleep(delay)
        if self._ssh_proc:
            with contextlib.suppress(Exception):
                self._ssh_proc.stdin.write("\x03")

    @staticmethod
    def _is_streaming_command(cmd: str) -> bool:
        return terminal_input.is_streaming_command(cmd)

    @staticmethod
    def _is_install_command(cmd: str) -> bool:
        return terminal_input.is_install_command(cmd)

    @staticmethod
    def _is_trivial_memory_command(cmd: str) -> bool:
        return is_trivial_memory_command(cmd)

    def _select_memory_candidate_commands(self, commands_with_output: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # F2-3: forwarder — canonical impl in servers.services.terminal_ai.memory
        from servers.services.terminal_ai import select_memory_candidate_commands

        return select_memory_candidate_commands(commands_with_output)

    @staticmethod
    def _detect_install_error(output: str) -> bool:
        return terminal_input.detect_install_error(output)

    async def _monitor_install(self, cmd_id: int, cmd: str, interval: float = 30.0) -> None:
        """
        Periodically send install progress updates to the frontend.
        If a clear error is detected, sends Ctrl+C to interrupt the install.
        """
        start = asyncio.get_event_loop().time()
        try:
            while True:
                await asyncio.sleep(interval)
                # Check if command already finished
                fut = (self._ai_exit_futures or {}).get(cmd_id)
                if not fut or fut.done():
                    return

                output_so_far = (self._ai_active_output or "")[-3000:]
                elapsed = int(asyncio.get_event_loop().time() - start)

                # Send progress notification to frontend
                last_line = (output_so_far.strip().split("\n")[-1] or "").strip()
                try:
                    await self._send_ai_event(
                        {
                            "type": "ai_install_progress",
                            "cmd": cmd,
                            "elapsed": elapsed,
                            "output_tail": last_line[:200],
                        }
                    )
                except Exception:
                    return

                # Abort if a clear error is detected in output
                if self._detect_install_error(output_so_far):
                    logger.warning("Install error detected in output, sending Ctrl+C: %s", cmd)
                    try:
                        if self._ssh_proc:
                            self._ssh_proc.stdin.write("\x03")
                    except Exception:
                        pass
                    return
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Install monitoring failed")

    async def _ai_handle_error(
        self,
        cmd: str,
        exit_code: int,
        output: str,
        remaining_cmds: list[str],
        user_reply: str | None = None,
    ) -> dict[str, Any]:
        """
        Ask LLM to decide what to do after a command failed.
        Returns {"action": "retry"|"skip"|"ask"|"abort", "cmd"?, "why"?, "question"?}

        Untrusted output/user_reply is sanitised by
        :func:`servers.services.terminal_ai.prompts.build_recovery_prompt`
        before embedding into the prompt (F1-1 / F1-2).
        The response is validated against
        :class:`servers.services.terminal_ai.schemas.TerminalPlanResponse`
        (F1-6).
        """
        from servers.services.terminal_ai import decide_recovery

        return await decide_recovery(
            cmd=cmd,
            exit_code=exit_code,
            output=output or "",
            remaining_cmds=remaining_cmds or [],
            user_reply=user_reply,
            semaphore=_TERMINAL_AI_LLM_SEMAPHORE,
        )

    async def _ai_step_decide_next(
        self,
        user_goal: str,
        last_cmd: str,
        exit_code: int,
        output: str,
        remaining_cmds: list[str],
        user_reply: str | None = None,
    ) -> dict[str, Any]:
        """
        Step-by-step controller:
        after each command decides whether to continue current plan, add a new command,
        ask user, finish, or abort.

        Untrusted goal/output/user_reply are sanitised by
        :func:`servers.services.terminal_ai.prompts.build_step_decision_prompt`
        before embedding into the prompt (F1-1 / F1-2).
        """
        from servers.services.terminal_ai import decide_step_next

        return await decide_step_next(
            user_goal=user_goal,
            last_cmd=last_cmd,
            exit_code=exit_code,
            output=output or "",
            remaining_cmds=remaining_cmds or [],
            user_reply=user_reply,
            semaphore=_TERMINAL_AI_LLM_SEMAPHORE,
        )

    async def _ai_type_text(self, text: str):
        if not self._ssh_proc or not text:
            return
        step = 1 if len(text) <= 80 else 4
        delay = 0.01 if step == 1 else 0.006
        for i in range(0, len(text), step):
            self._ssh_proc.stdin.write(text[i : i + step])
            await asyncio.sleep(delay)

    # ── Nova agent entry point ─────────────────────────────────────────────

    async def _run_ai_agent_background(
        self,
        *,
        user_message: str,
        chat_mode: str,
    ) -> None:
        try:
            with audit_context(**getattr(self, "_ai_audit_context", {})):
                await self._ai_run_agent(
                    user_message=user_message,
                    chat_mode=chat_mode,
                )
        except asyncio.CancelledError:
            raise
        finally:
            async with self._ai_lock:
                if self._ai_task is asyncio.current_task():
                    self._ai_task = None
            await self._send_ai_event({"type": "ai_status", "status": "idle"})

    async def _ai_run_agent(
        self,
        *,
        user_message: str,
        chat_mode: str,
    ) -> None:
        """Drive the Terminal Agent ReAct loop for one user turn.

        Builds an :class:`AgentContext` from the current SSH session,
        streams loop events to the client as ``agent_*`` WebSocket
        messages, and persists the final assistant reply to chat
        history on completion.
        """
        from servers.services.terminal_ai.agent import (
            AgentContext,
            default_tool_set,
            run_agent_loop,
        )
        from servers.services.terminal_ai.agent.tools import ServerTarget, UserPromptRequest

        if not self._ssh_conn or not self.server:
            await self._send_ai_event(
                {"type": "ai_error", "message": "SSH connection required for agent mode"}
            )
            return

        # Primary target = this session's server.
        primary = ServerTarget(
            name="primary",
            server_id=int(self.server.id),
            display_name=str(self.server.name or ""),
            host=str(getattr(self.server, "host", "") or ""),
            ssh_conn=self._ssh_conn,
            read_only=bool(getattr(self.server, "ai_read_only", False)),
            is_primary=True,
        )

        extras = await self._ai_build_agent_extras()

        try:
            _, rules_context, _, _ = await self._get_ai_rules_and_forbidden(
                self._user_id,
                self.server.id,
            )
        except Exception:
            rules_context = ""

        memory_context = ""
        memory_enabled = bool(
            (self._ai_settings or {}).get("memory_enabled", True)
        )
        if memory_enabled:
            server_ids = [int(self.server.id)] + [
                int(t.server_id) for t in extras.values() if t.server_id
            ]
            memory_context = await self._ai_build_agent_memory_context(server_ids)

        nova_context = await self._collect_nova_context_bundle()

        # ask_user pump: reuse the existing `ai_question` / `ai_reply`
        # bridge. The client already knows how to respond (same flow as
        # step-mode clarification questions); the agent loop just needs
        # to await the future for q_id.
        async def _prompt_user(request: UserPromptRequest) -> str | None:
            q_id = f"q_agent_{self._new_run_id()}"
            loop = asyncio.get_event_loop()
            reply_fut: asyncio.Future = loop.create_future()
            self._ai_reply_futures[q_id] = reply_fut
            await self._send_ai_event(
                {
                    "type": "ai_question",
                    "q_id": q_id,
                    "question": request.question,
                    "source": "agent",
                    "options": [
                        {
                            "label": option.label,
                            "value": option.value,
                            "description": option.description,
                        }
                        for option in request.options
                    ],
                    "allow_multiple": bool(request.allow_multiple),
                    "free_text_allowed": bool(request.free_text_allowed),
                    "placeholder": request.placeholder,
                }
            )
            try:
                return await asyncio.wait_for(
                    reply_fut,
                    timeout=max(5.0, float(request.timeout_seconds)),
                )
            except asyncio.TimeoutError:
                return None
            except asyncio.CancelledError:
                raise
            finally:
                self._ai_reply_futures.pop(q_id, None)

        def _stop_requested() -> bool:
            return bool(getattr(self, "_ai_stop_requested", False)) or not self._ssh_proc

        # Event emitter — redacts secrets + tags run_id, same pipeline
        # the legacy ai_* events use.
        async def _emit(ev: dict[str, Any]) -> None:
            await self._send_ai_event(ev)

        # Lazy SSH-open for extras. The agent calls this on first use
        # of each extra target (via ``ctx.ensure_connection``) so we
        # never open sockets the loop doesn't actually touch.
        # ``extras_meta`` maps target name → server metadata for lookup.
        extras_meta = dict(extras)

        async def _open_target(target_name: str) -> Any | None:
            cached = self._agent_extra_conns.get(target_name)
            if cached is not None:
                return cached
            target = extras_meta.get(target_name)
            if target is None:
                return None
            conn = await self._open_agent_target_conn(target.server_id)
            if conn is not None:
                self._agent_extra_conns[target_name] = conn
            return conn

        ctx = AgentContext(
            user_message=user_message,
            primary=primary,
            extras=extras,
            user_id=self._user_id,
            emit=_emit,
            prompt_user=_prompt_user,
            open_target=_open_target,
            stop_requested=_stop_requested,
            rules_context=rules_context,
            memory_context=memory_context,
            session_context=nova_context.session_context,
            recent_activity_context=nova_context.recent_activity_context,
            ui_context_payload=nova_context.ui_payload,
            dry_run=bool((self._ai_settings or {}).get("dry_run", False)),
        )

        try:
            result = await run_agent_loop(ctx, default_tool_set())
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — never crash the consumer
            logger.warning("agent loop failed: %s", exc)
            await self._send_ai_event(
                {"type": "ai_error", "message": f"Agent loop failed: {exc}"}
            )
            return

        # Persist the final assistant reply to chat history so future
        # turns see it.
        final_text = (result.final_text or "").strip()

        # Fallback — when the loop halted before the model could emit
        # ``done`` (budget / timeout / stop), the user otherwise ends
        # up staring at a wall of tool calls with no summary. Surface
        # a short human-readable notice explaining what happened and
        # how many steps were completed so they know the agent *did*
        # work, just didn't finish cleanly.
        if not final_text and result.stopped:
            reason_label = {
                "max_iterations": "достигнут лимит шагов",
                "total_timeout": "истёк общий тайм-аут",
                "llm_timeout": "LLM не ответил вовремя",
                "llm_error": "ошибка LLM",
                "user_stop": "остановлено вами",
                "fatal_tool_error": "критическая ошибка инструмента",
                "cancelled": "выполнение отменено",
            }.get(result.stop_reason or "", result.stop_reason or "остановлен")
            final_text = (
                f"Не удалось завершить задачу: {reason_label}. "
                f"Выполнено шагов: {result.iterations}, "
                f"вызовов инструментов: {result.tool_calls}. "
                "Посмотрите историю инструментов выше или переформулируйте запрос."
            )

        if final_text:
            self._add_to_history("assistant", final_text)
            # Mirror into the legacy ai_response stream so clients that
            # only subscribed to the plan-based flow still see the answer.
            await self._send_ai_event(
                {"type": "ai_response", "assistant_text": final_text}
            )

    async def _ai_build_agent_extras(self) -> dict[str, Any]:
        """Return the opt-in extra targets the user authorised for this session.

        Reads ``ai_settings.extra_target_server_ids`` (list of server
        ids the user has access to). Each target opens its own SSH
        connection. Failed connections are skipped with a warning.
        """
        from servers.services.terminal_agent_context import build_agent_extra_targets

        return await build_agent_extra_targets(
            ai_settings=self._ai_settings,
            user_id=self._user_id,
            primary_server_id=int(self.server.id) if self.server else None,
        )

    async def _ai_build_agent_memory_context(self, server_ids: list[int]) -> str:
        """Render a layered-memory prompt block for the agent.

        Loads :class:`ServerMemoryCard` for every authorised target in
        one batched query and renders them via
        :func:`render_server_cards_prompt`. Everything here is
        best-effort — an empty string is returned on any error so the
        agent simply starts without prior knowledge instead of crashing.
        """
        from servers.services.terminal_agent_context import build_agent_memory_context

        return await build_agent_memory_context(server_ids)

    async def _open_agent_target_conn(self, server_id: int) -> Any | None:
        """Open an asyncssh connection to an authorised extra target.

        Reuses the session's master password (loaded from the Django
        session store at terminal-open time) to unlock the target's
        encrypted secret. Returns ``None`` on any failure — the agent
        receives a tool error and can ``ask_user`` for credentials.
        """
        try:
            server = await self._load_server_for_agent(server_id)
            if server is None:
                logger.warning(
                    "agent open_target: server %s not accessible", server_id
                )
                return None

            master_password = await self._get_session_master_password()
            if not master_password:
                master_password = (os.environ.get("MASTER_PASSWORD") or "").strip()

            secret = await self._resolve_server_secret(
                server_id=server.id,
                master_password=master_password or "",
                plain_password="",
            )
            from servers.services.terminal_connection_options import build_terminal_connect_kwargs

            connect_kwargs = await build_terminal_connect_kwargs(server, secret=secret or "")
            return await asyncssh.connect(**connect_kwargs)
        except Exception as exc:  # noqa: BLE001 — never crash the agent
            logger.warning("agent open_target(server_id=%s) failed: %s", server_id, exc)
            return None

    async def _load_server_for_agent(self, server_id: int) -> Any | None:
        """Fetch a server model the user is authorised to access."""
        from servers.services.terminal_agent_context import load_user_accessible_server

        if not self._user_id:
            return None
        return await load_user_accessible_server(
            user_id=int(self._user_id),
            server_id=server_id,
        )

    async def _list_user_accessible_servers(
        self, *, user_id: int, server_ids: list[int]
    ) -> list[dict]:
        """Return server metadata for ids the user can access.

        Checks ownership, direct shares, and group membership — same
        ACL the terminal-open flow uses.
        """
        from servers.services.terminal_agent_context import list_user_accessible_servers

        return await list_user_accessible_servers(
            user_id=user_id,
            server_ids=server_ids,
        )

    async def _ai_plan_commands(
        self,
        user_message: str,
        rules_context: str,
        terminal_tail: str,
        history: list[dict] | None = None,
        unavailable_cmds: set[str] | None = None,
        chat_mode: str = "agent",
        execution_mode: str = "step",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Ask internal LLM to decide mode and return JSON:
          mode=answer → just reply, no commands
          mode=ask    → ask a clarifying question
          mode=execute → run commands on the server

        Untrusted inputs (terminal_tail, rules_context, history, user_message)
        are sanitised by
        :func:`servers.services.terminal_ai.prompts.build_planner_prompt`
        before embedding into the prompt (F1-1 / F1-2).
        The response is validated against
        :class:`servers.services.terminal_ai.schemas.TerminalPlanResponse`
        (F1-6).
        """
        from servers.services.terminal_ai import plan_terminal_commands

        logger.debug(
            "Terminal AI plan_commands: server_id=%s run_id=%s",
            getattr(self.server, "id", None),
            getattr(self, "_ai_run_id", ""),
        )

        return await plan_terminal_commands(
            user_message=user_message,
            rules_context=rules_context,
            terminal_tail=terminal_tail,
            history=history,
            unavailable_cmds=unavailable_cmds,
            chat_mode=chat_mode,
            execution_mode=execution_mode,
            dry_run=dry_run,
            semaphore=_TERMINAL_AI_LLM_SEMAPHORE,
        )

    _compute_report_status = staticmethod(compute_report_status)
    _build_fallback_report = staticmethod(build_fallback_report)

    async def _generate_ai_report_text(self, user_message: str, done_items: list[dict[str, Any]]) -> str:
        from servers.services.terminal_ai import generate_ai_report_text

        return await generate_ai_report_text(
            user_message,
            done_items,
            semaphore=_TERMINAL_AI_LLM_SEMAPHORE,
        )

    async def _ai_make_report(self, user_message: str, commands_with_output: list[dict[str, Any]]) -> str:
        """
        По выводу выполненных команд и запросу пользователя формирует краткий отчёт:
        какие проблемы обнаружены или что проблем нет.

        Untrusted output/user_message is sanitised by
        :func:`servers.services.terminal_ai.prompts.build_report_prompt`
        before embedding into the prompt (F1-1 / F1-2).
        """
        from servers.services.terminal_ai import make_ai_report

        return await make_ai_report(
            user_message,
            commands_with_output,
            semaphore=_TERMINAL_AI_LLM_SEMAPHORE,
        )

    _sanitize_memory_line = staticmethod(sanitize_memory_line)

    def _spawn_memory_extraction_task(
        self,
        *,
        user_message: str,
        commands_with_output: list[dict[str, Any]],
        report: str,
        user_id: int,
        server_id: int,
        audit_ctx: dict[str, Any],
    ) -> None:
        """Fire-and-forget: extract + persist server memory (F1-7).

        The extraction+save pair is ~4-5s of LLM latency + DB writes. Running
        them inline in ``_ai_process_queue`` blocks the UI ``idle`` event.
        Instead we spawn a detached task and track it so disconnect/cancel
        can wait on or cancel in-flight background work.
        """
        loop = asyncio.get_event_loop()
        task = loop.create_task(
            self._run_memory_extraction_background(
                user_message=user_message,
                commands_with_output=list(commands_with_output or []),
                report=report or "",
                user_id=user_id,
                server_id=server_id,
                audit_ctx=dict(audit_ctx or {}),
            ),
            name=f"terminal-ai-memory-{getattr(self, '_ai_run_id', '')}",
        )
        self._ai_background_tasks.add(task)
        task.add_done_callback(self._ai_background_tasks.discard)

    async def _run_memory_extraction_background(
        self,
        *,
        user_message: str,
        commands_with_output: list[dict[str, Any]],
        report: str,
        user_id: int,
        server_id: int,
        audit_ctx: dict[str, Any],
    ) -> None:
        """Body of the fire-and-forget memory-extraction task (F1-7)."""
        try:
            with audit_context(**audit_ctx):
                from servers.services.terminal_ai import run_memory_extraction

                await run_memory_extraction(
                    user_message=user_message,
                    commands_with_output=commands_with_output,
                    report=report,
                    user_id=user_id,
                    server_id=server_id,
                    semaphore=_TERMINAL_AI_LLM_SEMAPHORE,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Background memory extraction failed: %s", exc)

    async def _ai_extract_server_memory(
        self,
        user_message: str,
        commands_with_output: list[dict[str, Any]],
        report: str = "",
    ) -> dict[str, Any]:
        """
        Build concise, durable server context from current run:
        key facts, important paths/services, and active issues.

        Untrusted output/report/user_message is sanitised by
        :func:`servers.services.terminal_ai.prompts.build_memory_extraction_prompt`
        before embedding into the prompt (F1-1 / F1-2). The response is
        validated against
        :class:`servers.services.terminal_ai.schemas.MemoryExtraction` (F1-6).
        """
        from servers.services.terminal_ai import extract_server_memory

        return await extract_server_memory(
            user_message=user_message,
            commands_with_output=commands_with_output,
            report=report,
            semaphore=_TERMINAL_AI_LLM_SEMAPHORE,
        )

    async def _save_ai_server_profile(
        self,
        user_id: int,
        server_id: int,
        summary: str,
        facts: list[str],
        issues: list[str],
    ) -> dict[str, Any]:
        """Forwarder to :func:`servers.services.terminal_ai.save_server_profile` (F2-3)."""
        from servers.services.terminal_ai import save_server_profile

        return await save_server_profile(
            user_id=user_id,
            server_id=server_id,
            summary=summary,
            facts=facts,
            issues=issues,
        )

    _extract_json_object = staticmethod(extract_json_object)

    def _compute_confirm_reason(
        self,
        cmd: str,
        forbidden_patterns: list[str],
        allowlist_patterns: list[str] | None = None,
        *,
        confirm_dangerous_commands: bool = True,
    ) -> str:
        return compute_confirm_reason(
            cmd,
            forbidden_patterns=forbidden_patterns,
            allowlist_patterns=allowlist_patterns,
            confirm_dangerous_commands=confirm_dangerous_commands,
        )

    _matches_patterns = staticmethod(match_patterns)

    async def _disconnect_ssh(self):
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
        for conn in list(getattr(self, "_agent_extra_conns", {}).values()):
            await close_ssh_handle(conn)
        self._agent_extra_conns = {}

        if was_connected and self.scope.get("user") and getattr(self.scope["user"], "is_authenticated", False):
            await self._safe_send_json({"type": "status", "status": "disconnected"})

        if was_connected and self.server and self._user_id:
            await log_user_activity_async(
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
        self._manual_pending_commands = []
        self._manual_active_cmd_id = None
        self._manual_active_output = ""
        self._manual_input_buffer = ""
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
        set_exit_future_result(self._ai_exit_futures, cmd_id, exit_code)

    def _append_terminal_tail(self, text: str):
        append_terminal_tail(self, text)

    def _append_ai_output(self, text: str):
        append_ai_output(self, text)

    def _append_manual_output(self, text: str):
        append_manual_output(self, text)

    async def _finalize_manual_terminal_command(self, cmd_id: int, exit_code: int) -> None:
        await finalize_manual_terminal_command(self, cmd_id, exit_code, persist_result=database_sync_to_async(self._persist_manual_terminal_command_result, thread_sensitive=True))

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
