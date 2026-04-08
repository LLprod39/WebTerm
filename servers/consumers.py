"""
WebSocket consumers for interactive SSH terminal sessions.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shlex
import uuid
from dataclasses import dataclass
from errno import ECONNRESET
from typing import Any, Optional

import asyncssh
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from loguru import logger

from app.runtime_limits import get_terminal_session_limit_error
from app.tools.safety import is_dangerous_command
from core_ui.activity import log_user_activity_async
from core_ui.audit import audit_context
from core_ui.context_processors import user_can_feature
from servers.memory_heuristics import (
    is_trivial_memory_command,
    normalize_memory_command_text,
    should_capture_command_history_memory,
    should_persist_ai_memory,
)
from servers.models import Server, ServerConnection, ServerShare
from servers.secret_utils import get_server_auth_secret, has_saved_server_secret
from servers.ssh_host_keys import build_server_connect_kwargs, ensure_server_known_hosts


@dataclass(frozen=True)
class _TermSize:
    cols: int
    rows: int


_WEUAI_MARKER_PREFIX = "__WEUAI_EXIT_"

# Regex to detect commands that produce infinite/continuous output or need user input
_STREAMING_CMD_RE = re.compile(
    r"(?:"
    r"\btail\s+.*-[a-zA-Z]*[fF]\b"                              # tail -f / -F / -fq
    r"|\btail\s+--follow\b"
    r"|\bjournalctl\s+.*(?:-[a-zA-Z]*[fF]\b|--follow\b)"        # journalctl -f/-fu/--follow
    r"|\bdocker\s+logs?\s+.*(?:-[a-zA-Z]*[fF]\b|--follow\b)"   # docker logs -f/--follow
    r"|\bkubectl\s+logs?\s+.*-[a-zA-Z]*[fF]\b"                  # kubectl logs -f
    r"|\bpodman\s+logs?\s+.*(?:-[a-zA-Z]*[fF]\b|--follow\b)"
    r"|\bwatch\s+"                                               # watch anything
    r"|\btcpdump\b"
    r"|\bstrace\b"
    r"|\bping\s+(?!.*-c\s*\d)"                                   # ping without -c count
    r")",
    re.IGNORECASE,
)
_INTERACTIVE_CMDS = {"top", "htop", "iotop", "iftop", "nethogs", "vim", "vi", "nano", "less", "more", "man", "pstree", "glances"}

# Regex to detect long-running install/build commands that should be monitored
_INSTALL_CMD_RE = re.compile(
    r"(?:"
    r"\bapt(?:-get)?\s+(?:install|upgrade|dist-upgrade)\b"
    r"|\byum\s+(?:install|update)\b"
    r"|\bdnf\s+(?:install|upgrade)\b"
    r"|\bpip[23]?\s+install\b"
    r"|\bnpm\s+(?:install|ci|i\b)"
    r"|\byarn\s+(?:install|add)\b"
    r"|\bdocker\s+(?:pull|build)\b"
    r"|\bcomposer\s+(?:install|update)\b"
    r"|\bcargo\s+(?:install|build)\b"
    r"|\bgo\s+(?:get|install|build)\b"
    r"|\bmake\s+(?:install|all|build)\b"
    r")",
    re.IGNORECASE,
)

# Patterns that clearly indicate a failed install
_INSTALL_ERROR_RE = re.compile(
    r"(?:"
    r"E: Unable to locate package"
    r"|No such package|could not find package"
    r"|npm ERR!"
    r"|ERROR: Could not install"
    r"|error: could not"
    r"|Failed to fetch"
    r"|dpkg: error"
    r")",
    re.IGNORECASE,
)

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
          {type: "ai_response", assistant_text: str, commands: [{id, cmd, why, requires_confirm, reason}]}
          {type: "ai_command_status", id: int, status: "running"|"done"|"skipped", exit_code?, reason?}
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
    """

    server: Optional[Server] = None
    _user_id: Optional[int] = None

    _ssh_conn: Optional[asyncssh.SSHClientConnection] = None
    _ssh_proc: Optional[asyncssh.SSHClientProcess[str]] = None
    _stdout_task: Optional[asyncio.Task[None]] = None
    _stderr_task: Optional[asyncio.Task[None]] = None
    _wait_task: Optional[asyncio.Task[None]] = None
    _connection_heartbeat_task: Optional[asyncio.Task[None]] = None
    _connect_lock: asyncio.Lock

    _ai_lock: asyncio.Lock
    _ai_task: Optional[asyncio.Task[None]] = None
    _ai_plan: list[dict[str, Any]]
    _ai_plan_index: int
    _ai_next_id: int
    _ai_forbidden_patterns: list[str]
    _ai_exit_futures: dict[int, asyncio.Future[int]]
    _ai_active_cmd_id: Optional[int]
    _ai_active_output: str
    _ai_user_message: str
    _ai_chat_mode: str
    _ai_execution_mode: str
    _ai_step_extra_count: int
    _ai_settings: dict[str, Any]
    _ai_allowlist_patterns: list[str]
    _ai_last_done_items: list[dict[str, Any]]
    _ai_last_report: str

    _terminal_tail: str
    _ai_history: list[dict]
    _unavailable_cmds: set[str]    # commands that returned exit=127 this session
    _ai_reply_futures: dict[str, "asyncio.Future[str]"]  # q_id → future waiting for user reply
    _ai_error_retries: dict[int, int]   # cmd_id → retry count (max 2)
    _ai_run_id: str
    _ai_marker_token: str
    _ai_stop_requested: bool

    _marker_suppress: dict[str, bool]
    _marker_line_buf: dict[str, str]

    @staticmethod
    def _resolve_ws_token_user(token: str):
        """Validate a short-lived WS token and return the User or None."""
        from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
        from django.contrib.auth.models import User as _User
        signer = TimestampSigner(salt="ws-token")
        try:
            user_id = int(signer.unsign(token, max_age=300))
            return _User.objects.filter(id=user_id, is_active=True).first()
        except (BadSignature, SignatureExpired, ValueError, TypeError):
            return None

    async def _reject_with_error(self, *, code: int, message: str, error_code: str) -> None:
        try:
            await self.accept()
            await self._safe_send_json(
                {
                    "type": "error",
                    "message": message,
                    "fatal": True,
                    "error_code": error_code,
                }
            )
        except Exception:
            pass
        await self.close(code=code)

    @staticmethod
    def _format_ssh_connect_error(exc: Exception) -> str:
        if isinstance(exc, ConnectionResetError) or getattr(exc, "errno", None) == ECONNRESET:
            return (
                "SSH сервер принял TCP-соединение и сразу закрыл его "
                "(Connection reset by peer). Проверьте sshd, порт, firewall, bastion/VPN и allowlist по IP."
            )
        if isinstance(exc, TimeoutError):
            return "Таймаут подключения к SSH серверу. Проверьте маршрут, firewall, bastion/VPN и доступность порта."
        if isinstance(exc, asyncssh.misc.HostKeyNotVerifiable):
            return f"SSH host key не доверен: {exc}"
        return str(exc) or exc.__class__.__name__

    @staticmethod
    def _default_ai_settings() -> dict[str, Any]:
        return {
            "memory_enabled": True,
            "memory_ttl_requests": 6,
            "auto_report": "auto",
            "confirm_dangerous_commands": True,
            "allowlist_patterns": [],
            "blocklist_patterns": [],
        }

    @staticmethod
    def _parse_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _normalize_pattern_list(raw_value: Any) -> list[str]:
        if isinstance(raw_value, str):
            values = raw_value.replace("\r", "\n").split("\n")
        elif isinstance(raw_value, list):
            values = [str(item or "") for item in raw_value]
        else:
            values = []

        seen: set[str] = set()
        normalized: list[str] = []
        for item in values:
            line = str(item or "").strip()
            if not line:
                continue
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(line)
        return normalized[:50]

    def _normalize_ai_settings(self, raw_value: Any) -> dict[str, Any]:
        incoming = raw_value if isinstance(raw_value, dict) else {}
        defaults = self._default_ai_settings()
        auto_report = str(incoming.get("auto_report") or defaults["auto_report"]).strip().lower()
        if auto_report not in {"auto", "on", "off"}:
            auto_report = str(defaults["auto_report"])

        try:
            ttl = int(incoming.get("memory_ttl_requests") or defaults["memory_ttl_requests"])
        except (TypeError, ValueError):
            ttl = int(defaults["memory_ttl_requests"])
        ttl = max(1, min(ttl, 20))

        return {
            "memory_enabled": self._parse_bool(incoming.get("memory_enabled"), bool(defaults["memory_enabled"])),
            "memory_ttl_requests": ttl,
            "auto_report": auto_report,
            "confirm_dangerous_commands": self._parse_bool(
                incoming.get("confirm_dangerous_commands"),
                bool(defaults["confirm_dangerous_commands"]),
            ),
            "allowlist_patterns": self._normalize_pattern_list(incoming.get("allowlist_patterns")),
            "blocklist_patterns": self._normalize_pattern_list(incoming.get("blocklist_patterns")),
        }

    @staticmethod
    def _clone_ai_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
        base = settings or {}
        return {
            "memory_enabled": bool(base.get("memory_enabled", True)),
            "memory_ttl_requests": int(base.get("memory_ttl_requests", 6) or 6),
            "auto_report": str(base.get("auto_report") or "auto"),
            "confirm_dangerous_commands": bool(base.get("confirm_dangerous_commands", True)),
            "allowlist_patterns": list(base.get("allowlist_patterns") or []),
            "blocklist_patterns": list(base.get("blocklist_patterns") or []),
        }

    @staticmethod
    def _is_auto_report_enabled(settings: dict[str, Any], execution_mode: str) -> bool:
        mode = str(settings.get("auto_report") or "auto").strip().lower()
        if mode == "on":
            return True
        if mode == "off":
            return False
        return str(execution_mode or "").strip().lower() == "step"

    @staticmethod
    def _normalize_ai_chat_mode(value: Any) -> str:
        mode = str(value or "").strip().lower()
        return mode if mode in {"ask", "agent"} else "agent"

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
        self._ai_plan = []
        self._ai_plan_index = 0
        self._ai_next_id = 1
        self._ai_forbidden_patterns = []
        self._ai_exit_futures = {}
        self._ai_active_cmd_id = None
        self._ai_active_output = ""
        self._ai_user_message = ""
        self._ai_chat_mode = "agent"
        self._ai_execution_mode = "step"
        self._ai_step_extra_count = 0
        self._ai_settings = self._default_ai_settings()
        self._ai_allowlist_patterns = []
        self._ai_last_done_items = []
        self._ai_last_report = ""
        self._terminal_tail = ""
        self._ai_history = []
        self._unavailable_cmds: set[str] = set()
        self._ai_reply_futures: dict[str, asyncio.Future] = {}
        self._ai_error_retries: dict[int, int] = {}
        self._ai_run_id = ""
        self._ai_marker_token = ""
        self._ai_stop_requested = False
        self._marker_suppress = {"stdout": False, "stderr": False}
        self._marker_line_buf = {"stdout": "", "stderr": ""}
        self._manual_input_buffer = ""
        self._input_capture_suppress = 0
        self._ai_audit_context: dict[str, Any] = {}
        self._server_connection_id: str | None = None
        self._connection_heartbeat_task = None

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
            logger.exception("WS connect REJECT: unexpected error fetching server {} for user={}: {}", server_id, user, exc)
            await self._reject_with_error(
                code=4500,
                message="Не удалось подготовить подключение к серверу.",
                error_code="server_connect_prepare_failed",
            )
            return

        has_encrypted_secret = await database_sync_to_async(has_saved_server_secret, thread_sensitive=True)(self.server)
        await self.accept()
        await self._safe_send_json(
            {
                "type": "ready",
                "server_id": self.server.id,
                "server_name": self.server.name,
                "auth_method": self.server.auth_method,
                "has_encrypted_secret": has_encrypted_secret,
            }
        )

    async def disconnect(self, code):
        await self._cancel_ai()
        await self._disconnect_ssh()

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
        token = (self._ai_marker_token or "").strip()
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
                    await self._safe_send_json({"type": "error", "message": f"SSH connect blocked: {limit_error['error']}"})
                    await self._safe_send_json({"type": "status", "status": "disconnected"})
                    return

                known_hosts = await ensure_server_known_hosts(self.server)
                connect_kwargs = build_server_connect_kwargs(
                    self.server,
                    secret=secret or "",
                    known_hosts=known_hosts,
                    connect_timeout=max(1, int(getattr(settings, "SSH_CONNECT_TIMEOUT_SECONDS", 10) or 10)),
                    login_timeout=max(1, int(getattr(settings, "SSH_LOGIN_TIMEOUT_SECONDS", 20) or 20)),
                    keepalive_interval=max(1, int(getattr(settings, "SSH_KEEPALIVE_INTERVAL_SECONDS", 20) or 20)),
                    keepalive_count_max=max(1, int(getattr(settings, "SSH_KEEPALIVE_COUNT_MAX", 3) or 3)),
                )
                network_config = self.server.network_config or {}

                self._ssh_conn = await asyncssh.connect(**connect_kwargs)
                self._ssh_proc = await self._ssh_conn.create_process(
                    term_type=term_type,
                    # AsyncSSH TermSize = (cols, rows, pixwidth, pixheight)
                    term_size=(term_size.cols, term_size.rows, 0, 0),
                    encoding="utf-8",
                    errors="replace",
                )

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
                    category='servers',
                    action='terminal_connect',
                    status='success',
                    description=f'Connected to server terminal "{self.server.name}"',
                    entity_type='server',
                    entity_id=self.server.id,
                    entity_name=self.server.name,
                    metadata={
                        'host': self.server.host,
                        'port': self.server.port,
                        'auth_method': self.server.auth_method,
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

            except Exception as e:
                logger.exception("SSH terminal connect failed")
                error_message = self._format_ssh_connect_error(e)
                await log_user_activity_async(
                    user_id=self._user_id,
                    category='servers',
                    action='terminal_connect',
                    status='error',
                    description=f'SSH terminal connect failed: {error_message}',
                    entity_type='server',
                    entity_id=self.server.id if self.server else '',
                    entity_name=self.server.name if self.server else '',
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
            await self._capture_terminal_input(data)
            self._ssh_proc.stdin.write(data)
        except Exception as e:
            await self._safe_send_json({"type": "error", "message": f"stdin write failed: {e}"})

    @staticmethod
    def _strip_terminal_input_sequences(data: str) -> str:
        cleaned = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", data or "")
        cleaned = re.sub(r"\x1b.", "", cleaned)
        return cleaned

    @contextlib.contextmanager
    def _suppress_terminal_input_capture(self):
        self._input_capture_suppress = int(getattr(self, "_input_capture_suppress", 0) or 0) + 1
        try:
            yield
        finally:
            self._input_capture_suppress = max(0, int(getattr(self, "_input_capture_suppress", 1) or 1) - 1)

    async def _capture_terminal_input(self, data: str) -> None:
        if int(getattr(self, "_input_capture_suppress", 0) or 0) > 0:
            return

        cleaned = self._strip_terminal_input_sequences(data)
        if not cleaned:
            return

        for char in cleaned:
            if char in ("\r", "\n"):
                command = str(getattr(self, "_manual_input_buffer", "") or "").strip()
                self._manual_input_buffer = ""
                if command:
                    await self._log_manual_terminal_command(command)
                continue
            if char in ("\x7f", "\b"):
                self._manual_input_buffer = str(getattr(self, "_manual_input_buffer", "") or "")[:-1]
                continue
            if char == "\x15":
                self._manual_input_buffer = ""
                continue
            if ord(char) < 32 and char != "\t":
                continue
            self._manual_input_buffer = (str(getattr(self, "_manual_input_buffer", "") or "") + char)[-8000:]

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
        await database_sync_to_async(self._persist_manual_terminal_command, thread_sensitive=True)(
            user_id=self._user_id,
            server_id=self.server.id,
            session_id=self._server_connection_id or "",
            command=command,
        )

    @staticmethod
    def _persist_manual_terminal_command(*, user_id: int, server_id: int, session_id: str, command: str) -> None:
        from servers.models import ServerCommandHistory

        ServerCommandHistory.objects.create(
            server_id=server_id,
            user_id=user_id,
            actor_kind=ServerCommandHistory.ACTOR_HUMAN,
            source_kind=ServerCommandHistory.SOURCE_TERMINAL,
            session_id=session_id,
            command=command,
            output="",
            exit_code=None,
        )

    async def _handle_resize(self, content: dict[str, Any]):
        if not self._ssh_proc:
            return
        try:
            term_size = self._parse_term_size(content)
            if term_size.cols > 0 and term_size.rows > 0:
                self._ssh_proc.change_terminal_size(term_size.cols, term_size.rows)
        except Exception as e:
            await self._safe_send_json({"type": "error", "message": f"resize failed: {e}"})

    async def _interrupt_active_command(self) -> Optional[int]:
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
                try:
                    fut.set_result(130)
                except Exception:
                    pass
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
        if self._ai_task and not self._ai_task.done():
            if current is None or self._ai_task is not current:
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
        raw = str(mode or "").strip().lower()
        if raw in ("auto", "smart", "adaptive_auto", "recommended"):
            return "auto"
        if raw in ("step", "step_by_step", "step-by-step", "sequential", "adaptive"):
            return "step"
        if raw in ("fast", "plan", "batch"):
            return "fast"
        return "step"

    def _resolve_auto_execution_mode(self, plan_obj: dict[str, Any], commands_raw: Any, user_message: str) -> str:
        """
        Resolve concrete execution mode for an auto request.
        Priority:
          1) planner-provided execution_mode
          2) safety fallback from planned commands / user intent
        """
        planner_mode = self._normalize_execution_mode(str((plan_obj or {}).get("execution_mode") or ""))
        if planner_mode in ("step", "fast"):
            return planner_mode

        commands_count = len(commands_raw) if isinstance(commands_raw, list) else 0
        if commands_count <= 2:
            # Very short, deterministic tasks are usually faster in linear mode.
            return "fast"

        text = str(user_message or "").lower()
        danger_hints = (
            "delete",
            "drop",
            "rm ",
            "truncate",
            "restart",
            "stop",
            "reboot",
            "firewall",
            "iptables",
            "migration",
            "migrate",
            "upgrade",
            "install",
            "prod",
            "production",
        )
        if any(h in text for h in danger_hints):
            return "step"

        return "step"

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
            category='assistant',
            action='terminal_ai_request',
            status='success',
            description=msg[:400],
            entity_type='server',
            entity_id=self.server.id if self.server else '',
            entity_name=self.server.name if self.server else '',
            metadata={
                'message_length': len(msg),
                'chat_mode': requested_chat_mode,
                'execution_mode': requested_mode,
                'memory_enabled': bool(self._ai_settings.get("memory_enabled", True)),
                'auto_report': str(self._ai_settings.get("auto_report") or "auto"),
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
            try:
                forbidden_patterns, rules_context, required_checks, _ = await self._get_ai_rules_and_forbidden(
                    self._user_id,
                    self.server.id,
                )
                merged_forbidden = list(forbidden_patterns or [])
                for pattern in list(self._ai_settings.get("blocklist_patterns") or []):
                    if str(pattern or "").strip() and str(pattern).strip().lower() not in {p.lower() for p in merged_forbidden}:
                        merged_forbidden.append(str(pattern).strip())
                plan_obj = await self._ai_plan_commands(
                    user_message=msg,
                    rules_context=rules_context,
                    terminal_tail=(self._terminal_tail or "")[-2000:],
                    history=list(self._ai_history) if bool(self._ai_settings.get("memory_enabled", True)) else [],
                    unavailable_cmds=set(getattr(self, "_unavailable_cmds", set())),
                    chat_mode=requested_chat_mode,
                    execution_mode=requested_mode,
                )
            except Exception as e:
                err_msg = str(e).strip() or "Unknown error"
                if any(hint in err_msg.lower() for hint in ("timeout", "429", "rate", "resource exhausted", "overloaded")):
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
            await self._send_ai_event({
                "type": "ai_response",
                "mode": mode,
                "assistant_text": assistant_text,
                "commands": [],
                "chat_mode": requested_chat_mode,
                "execution_mode": selected_mode,
                "requested_execution_mode": requested_mode,
            })
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

        await self._send_ai_event({
            "type": "ai_response",
            "mode": "execute",
            "assistant_text": assistant_text,
            "commands": plan_items,
            "chat_mode": requested_chat_mode,
            "execution_mode": selected_mode,
            "requested_execution_mode": requested_mode,
        })

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
                await self._send_ai_event({"type": "ai_error", "message": "Подтверждать можно только текущую ожидающую команду"})
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
                await self._send_ai_event({"type": "ai_error", "message": "Отменять можно только текущую ожидающую команду"})
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
        await self._send_ai_event(
            {
                "type": "ai_response",
                "mode": "answer",
                "assistant_text": "🧹 Память текущего чата очищена.",
                "commands": [],
                "execution_mode": str(getattr(self, "_ai_execution_mode", "step")),
            }
        )

    async def _handle_ai_generate_report(self, content: dict[str, Any]):
        force_regenerate = self._parse_bool((content or {}).get("force"), False)
        async with self._ai_lock:
            if self._ai_task and not self._ai_task.done():
                await self._send_ai_event({"type": "ai_error", "message": "Дождитесь завершения текущего запуска ассистента."})
                return
            done_items = list(self._ai_last_done_items or [])
            user_message = str(self._ai_user_message or "")
            cached_report = "" if force_regenerate else str(self._ai_last_report or "")

        if not done_items:
            await self._send_ai_event({"type": "ai_error", "message": "Нет завершённых команд для формирования отчёта."})
            return

        try:
            await self._send_ai_event({"type": "ai_status", "status": "generating_report"})
            report = cached_report or await self._generate_ai_report_text(user_message, done_items)
            status = self._compute_report_status(done_items)
            await self._send_ai_event({"type": "ai_report", "report": report, "status": status})
            async with self._ai_lock:
                self._ai_last_report = report
            if bool(self._ai_settings.get("memory_enabled", True)):
                self._add_to_history("assistant", f"[Ручной отчёт]\n{report[:400]}")
        except Exception as exc:
            await self._send_ai_event({"type": "ai_error", "message": str(exc) or "Не удалось сформировать отчёт"})
        finally:
            await self._send_ai_event({"type": "ai_status", "status": "idle"})

    def _add_to_history(self, role: str, text: str) -> None:
        """Append a message to the conversation history (max 20 entries)."""
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

    def _build_plan_item(
        self,
        item_id: int,
        cmd: str,
        why: str,
        forbidden_patterns: list[str] | None = None,
        allowlist_patterns: list[str] | None = None,
        confirm_dangerous_commands: bool = True,
    ) -> dict[str, Any]:
        clean_cmd = str(cmd or "").strip()
        reason = self._compute_confirm_reason(
            clean_cmd,
            forbidden_patterns or [],
            allowlist_patterns or [],
            confirm_dangerous_commands=confirm_dangerous_commands,
        )
        blocked = reason in {"forbidden", "outside_allowlist"}
        requires_confirm = bool(reason == "dangerous")
        if getattr(self, "_ai_chat_mode", "agent") == "ask" and clean_cmd and not blocked:
            requires_confirm = True
            if not reason:
                reason = "ask_mode"
        return {
            "id": int(item_id),
            "cmd": clean_cmd,
            "why": str(why or "").strip(),
            # forbidden => hard block, dangerous/ask_mode => explicit confirm
            "requires_confirm": requires_confirm,
            "blocked": blocked,
            "reason": reason,
            "status": "blocked" if blocked else "pending",
            "streaming": self._is_streaming_command(clean_cmd),
        }

    @staticmethod
    def _normalize_command_text(cmd: str) -> str:
        clean_cmd = normalize_memory_command_text(cmd)
        if not clean_cmd:
            return ""
        return clean_cmd

    async def _ai_process_queue(self):
        """
        Execute queued AI commands sequentially.
        Pauses when a command requires confirmation.
        """
        send_idle = True
        step_mode = self._normalize_execution_mode(getattr(self, "_ai_execution_mode", "step")) == "step"
        try:
            while True:
                if not self._ssh_proc:
                    break
                if not self.server or not self._user_id:
                    break

                async with self._ai_lock:
                    if not self._ai_plan or self._ai_plan_index >= len(self._ai_plan):
                        break
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
                            {
                                "type": "ai_command_status",
                                "id": item_id,
                                "status": "skipped",
                                "reason": reason or "forbidden",
                            }
                        )
                        continue

                    if requires_confirm:
                        item["status"] = "pending_confirm"
                        # Pause until user confirms/cancels current command
                        await self._send_ai_event(
                            {
                                "type": "ai_status",
                                "status": "waiting_confirm",
                                "id": item_id,
                                "reason": reason or "dangerous",
                            }
                        )
                        send_idle = False
                        return

                    item["status"] = "running"

                await self._send_ai_event({"type": "ai_command_status", "id": item_id, "status": "running"})

                try:
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
                # call the LLM to decide: retry / skip / ask user / abort
                recovery_action = None
                if exit_code not in (0, 130, None) and not item.get("_no_recovery"):
                    retries = self._ai_error_retries.get(item_id, 0)
                    if retries < 2:
                        await self._send_ai_event({
                            "type": "ai_status",
                            "status": "analyzing_error",
                            "cmd": cmd,
                            "exit_code": exit_code,
                        })
                        try:
                            async with self._ai_lock:
                                remaining_cmds = [
                                    it.get("cmd", "") for it in self._ai_plan[self._ai_plan_index + 1:]
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
                                        confirm_dangerous = bool(self._ai_settings.get("confirm_dangerous_commands", True))
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
                                    await self._send_ai_event({
                                        "type": "ai_recovery",
                                        "original_cmd": cmd,
                                        "new_cmd": new_cmd,
                                        "new_id": next_id,
                                        "why": why,
                                        "requires_confirm": bool(new_item.get("requires_confirm")),
                                        "reason": str(new_item.get("reason") or ""),
                                        "streaming": bool(new_item.get("streaming")),
                                    })

                            elif recovery_action == "ask":
                                question = str(decision.get("question") or "Как лучше продолжить?")
                                q_id = f"q_{item_id}_{self._ai_next_id}"
                                self._ai_next_id += 1
                                loop = asyncio.get_event_loop()
                                reply_fut: asyncio.Future = loop.create_future()
                                self._ai_reply_futures[q_id] = reply_fut
                                await self._send_ai_event({
                                    "type": "ai_question",
                                    "q_id": q_id,
                                    "question": question,
                                    "cmd": cmd,
                                    "exit_code": exit_code,
                                })
                                try:
                                    user_reply = await asyncio.wait_for(reply_fut, timeout=300)
                                    self._add_to_history("user", f"[Ответ агенту]: {user_reply}")
                                    # Re-evaluate with user's answer
                                    decision2 = await self._ai_handle_error(
                                        cmd, exit_code, output_snippet, remaining_cmds,
                                        user_reply=user_reply
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
                                                confirm_dangerous = bool(self._ai_settings.get("confirm_dangerous_commands", True))
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
                                            await self._send_ai_event({
                                                "type": "ai_recovery",
                                                "original_cmd": cmd,
                                                "new_cmd": new_cmd2,
                                                "new_id": next_id2,
                                                "why": why2,
                                                "requires_confirm": bool(new_item2.get("requires_confirm")),
                                                "reason": str(new_item2.get("reason") or ""),
                                                "streaming": bool(new_item2.get("streaming")),
                                            })
                                            recovery_action = "retry"
                                    elif decision2.get("action") == "abort":
                                        recovery_action = "abort"
                                        await self._send_ai_event({
                                            "type": "ai_error",
                                            "message": str(decision2.get("why") or "Выполнение прервано"),
                                        })
                                except asyncio.TimeoutError:
                                    # User didn't reply in time → skip
                                    logger.info("ai_question timeout, skipping command")
                                    recovery_action = "skip"
                                finally:
                                    self._ai_reply_futures.pop(q_id, None)

                            elif recovery_action == "abort":
                                await self._send_ai_event({
                                    "type": "ai_error",
                                    "message": str(decision.get("why") or "Выполнение прервано из-за критической ошибки"),
                                })

                        except asyncio.CancelledError:
                            raise
                        except Exception as e:
                            logger.warning("Error recovery LLM failed: %s", e)
                            recovery_action = "skip"

                if recovery_action == "abort":
                    break
                # ── End adaptive error recovery ─────────────────────────────

                async with self._ai_lock:
                    if self._ai_plan_index < len(self._ai_plan) and int(self._ai_plan[self._ai_plan_index].get("id") or 0) == item_id:
                        self._ai_plan[self._ai_plan_index]["status"] = "done"
                        self._ai_plan[self._ai_plan_index]["exit_code"] = exit_code
                        self._ai_plan[self._ai_plan_index]["output_snippet"] = output_snippet or ""
                        self._ai_plan_index += 1

                is_stream = bool(item.get("streaming", False))
                await self._send_ai_event({"type": "ai_command_status", "id": item_id, "status": "done", "exit_code": exit_code, "streaming": is_stream})

                # Step-by-step mode: re-evaluate after each command, not only on errors.
                if step_mode:
                    try:
                        async with self._ai_lock:
                            remaining_cmds = [
                                str(it.get("cmd") or "").strip()
                                for it in self._ai_plan[self._ai_plan_index :]
                                if str(it.get("status") or "") not in ("done", "skipped", "cancelled")
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

                        if action == "next":
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
                                            confirm_dangerous_commands=bool(self._ai_settings.get("confirm_dangerous_commands", True)),
                                        )
                                        self._ai_plan.insert(self._ai_plan_index, new_item)
                                    await self._send_ai_event(
                                        {
                                            "type": "ai_response",
                                            "mode": "execute",
                                            "assistant_text": str(decision.get("assistant_text") or "Добавляю следующий шаг по результатам проверки."),
                                            "commands": [new_item],
                                            "execution_mode": "step",
                                        }
                                    )

                        elif action == "done":
                            done_text = str(decision.get("assistant_text") or "Цель достигнута. Останавливаю дальнейшие шаги.").strip()
                            self._add_to_history("assistant", done_text[:800])
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
                                    "message": str(decision.get("assistant_text") or "Выполнение остановлено из-за критического состояния."),
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

                    # Save concise server memory snapshot only for durable operational signals.
                    memory_candidates = self._select_memory_candidate_commands(done_with_output)
                    if memory_candidates and self.server and self._user_id and bool(self._ai_settings.get("memory_enabled", True)):
                        try:
                            memory_obj = await self._ai_extract_server_memory(
                                user_message=user_msg,
                                commands_with_output=memory_candidates,
                                report=report,
                            )
                            mem_summary = str(memory_obj.get("summary") or "").strip()
                            mem_facts = memory_obj.get("facts") or []
                            mem_issues = memory_obj.get("issues") or []
                            if mem_summary or mem_facts or mem_issues:
                                await self._save_ai_server_profile(
                                    user_id=self._user_id,
                                    server_id=self.server.id,
                                    summary=mem_summary,
                                    facts=mem_facts,
                                    issues=mem_issues,
                                )
                        except Exception as e:
                            logger.warning("Server memory snapshot save failed: %s", e)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("AI processing failed")
            err_msg = str(e).strip() or "Unknown error"
            if any(hint in err_msg.lower() for hint in ("timeout", "429", "rate", "resource exhausted", "overloaded")):
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
            marker_cmd = (
                f"{marker_var}=$?; echo \"{marker_prefix}{cmd_id}:${{{marker_var}}}__\""
            )
            self._ssh_proc.stdin.write(marker_cmd + "\n")

        # For streaming commands: schedule Ctrl+C after 8 s to allow output capture
        interrupt_task: Optional[asyncio.Task] = None
        if is_streaming:
            interrupt_task = asyncio.create_task(self._interrupt_streaming_after(8.0))

        # For install commands: start periodic monitoring
        monitor_task: Optional[asyncio.Task] = None
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
                try:
                    await interrupt_task
                except asyncio.CancelledError:
                    pass
            if monitor_task and not monitor_task.done():
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass
            async with self._ai_lock:
                self._ai_exit_futures.pop(cmd_id, None)

        # Short delay so buffered output arrives in _ai_active_output
        await asyncio.sleep(0.4)
        output_snippet = (self._ai_active_output or "")[-6000:]
        async with self._ai_lock:
            self._ai_active_cmd_id = None
        return exit_code, output_snippet

    async def _interrupt_streaming_after(self, delay: float) -> None:
        """Send Ctrl+C after `delay` seconds to interrupt a streaming command."""
        await asyncio.sleep(delay)
        if self._ssh_proc:
            try:
                self._ssh_proc.stdin.write("\x03")
            except Exception:
                pass

    @staticmethod
    def _is_streaming_command(cmd: str) -> bool:
        """Return True if cmd would produce continuous output or need user input."""
        c = (cmd or "").strip()
        if not c:
            return False
        if _STREAMING_CMD_RE.search(c):
            return True
        # Check bare interactive command names
        cmd_name = c.split()[0].split("/")[-1].lower()
        return cmd_name in _INTERACTIVE_CMDS

    @staticmethod
    def _is_install_command(cmd: str) -> bool:
        """Return True if cmd is a package/dependency install (potentially long-running)."""
        return bool(_INSTALL_CMD_RE.search(cmd or ""))

    @staticmethod
    def _is_trivial_memory_command(cmd: str) -> bool:
        return is_trivial_memory_command(cmd)

    def _select_memory_candidate_commands(self, commands_with_output: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for row in commands_with_output or []:
            command = self._normalize_command_text(str(row.get("cmd") or ""))
            if not command:
                continue
            output = str(row.get("output") or "").strip()
            exit_code = row.get("exit_code")
            if not should_capture_command_history_memory(
                command=command,
                output=output,
                exit_code=exit_code,
                actor_kind="agent",
                source_kind="agent",
            ):
                continue
            candidates.append({**row, "cmd": command, "output": output})
        return candidates

    @staticmethod
    def _detect_install_error(output: str) -> bool:
        """Return True if output clearly shows an install failure."""
        return bool(_INSTALL_ERROR_RE.search(output or ""))

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
                    await self._send_ai_event({
                        "type": "ai_install_progress",
                        "cmd": cmd,
                        "elapsed": elapsed,
                        "output_tail": last_line[:200],
                    })
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
        """
        from app.core.llm import LLMProvider

        remaining_text = (
            "\n".join(f"  {i + 1}. {c}" for i, c in enumerate(remaining_cmds[:5]))
            or "(нет следующих команд)"
        )
        user_block = f"\n\nОтвет пользователя: «{user_reply}»" if user_reply else ""

        prompt = f"""Ты DevOps-агент. Команда завершилась с ошибкой. Реши, что делать дальше.

КОМАНДА: {cmd}
КОД ВЫХОДА: {exit_code}
ВЫВОД:
{(output or '(нет вывода)')[:2000]}

СЛЕДУЮЩИЕ КОМАНДЫ В ПЛАНЕ:
{remaining_text}{user_block}

ПРАВИЛА ПРИНЯТИЯ РЕШЕНИЯ:
- exit=127 → команда не найдена → action=retry с альтернативой (ss вместо netstat, ip addr вместо ifconfig, etc.)
- Ошибка прав доступа ("Permission denied", "sudo required", exit=1/126) → action=ask (спросить пользователя нужен ли sudo)
- Явная опечатка или неправильные флаги → action=retry с исправленной командой
- Критическая ошибка, делающая следующие команды бессмысленными → action=abort
- Незначительная ошибка, остальные команды независимы → action=skip
- Неоднозначная ситуация — нужна информация от пользователя → action=ask

ФОРМАТ ОТВЕТА (только JSON, без markdown):
{{
  "action": "retry" | "skip" | "ask" | "abort",
  "cmd": "новая_команда (только для action=retry)",
  "why": "краткое объяснение решения (1-2 предложения)",
  "question": "вопрос пользователю (только для action=ask)"
}}

Верни только JSON."""

        llm = LLMProvider()
        out = ""
        async with _TERMINAL_AI_LLM_SEMAPHORE:
            async for chunk in llm.stream_chat(prompt, model="auto", purpose="chat"):
                out += chunk
                if len(out) > 3000:
                    break

        try:
            result = self._extract_json_object(out)
            action = str(result.get("action") or "skip").lower().strip()
            if action not in ("retry", "skip", "ask", "abort"):
                action = "skip"
            result["action"] = action
            return result
        except Exception as e:
            logger.warning("_ai_handle_error JSON parse failed: %s, output: %.200s", e, out)
            return {"action": "skip", "why": "Не удалось разобрать ответ LLM — пропускаю команду"}

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
        """
        from app.core.llm import LLMProvider

        remaining_text = (
            "\n".join(f"  {i + 1}. {c}" for i, c in enumerate(remaining_cmds[:6]))
            or "(нет оставшихся команд)"
        )
        user_reply_block = f"\n\nОтвет пользователя: «{user_reply}»" if user_reply else ""
        prompt = f"""Ты DevOps-агент в режиме step-by-step.
После КАЖДОГО шага ты анализируешь вывод и выбираешь следующее действие.

ЦЕЛЬ ПОЛЬЗОВАТЕЛЯ:
{user_goal}

ПОСЛЕДНЯЯ КОМАНДА:
{last_cmd}
EXIT_CODE: {exit_code}
ВЫВОД:
{(output or '(нет вывода)')[:2500]}

ОСТАВШИЙСЯ ПЛАН:
{remaining_text}{user_reply_block}

Выбери одно действие:
- continue: оставить текущий план без изменений
- next: добавить СЛЕДУЮЩУЮ команду перед оставшимся планом
- done: цель уже достигнута, можно завершать
- ask: нужен короткий вопрос к пользователю
- abort: критическая ситуация, выполнение надо прервать

Правила:
- Если цель уже достигнута по выводу, выбирай done.
- Если есть явный лучший следующий шаг, выбирай next.
- Если данных мало или нужно решение пользователя, выбирай ask.
- Не предлагай опасные/разрушительные команды без явной необходимости.

ФОРМАТ (только JSON):
{{
  "action": "continue" | "next" | "done" | "ask" | "abort",
  "assistant_text": "краткий комментарий пользователю (опционально)",
  "next_cmd": "команда (только для action=next)",
  "why": "зачем этот шаг (для action=next)",
  "question": "вопрос пользователю (только для action=ask)"
}}
"""
        llm = LLMProvider()
        out = ""
        async with _TERMINAL_AI_LLM_SEMAPHORE:
            async for chunk in llm.stream_chat(prompt, model="auto", purpose="chat"):
                out += chunk
                if len(out) > 5000:
                    break
        try:
            result = self._extract_json_object(out)
        except Exception as e:
            logger.warning("_ai_step_decide_next JSON parse failed: %s, output: %.200s", e, out)
            return {"action": "continue"}

        action = str(result.get("action") or "continue").lower().strip()
        if action not in {"continue", "next", "done", "ask", "abort"}:
            action = "continue"
        result["action"] = action
        return result

    async def _ai_type_text(self, text: str):
        if not self._ssh_proc or not text:
            return
        step = 1 if len(text) <= 80 else 4
        delay = 0.01 if step == 1 else 0.006
        for i in range(0, len(text), step):
            self._ssh_proc.stdin.write(text[i : i + step])
            await asyncio.sleep(delay)

    async def _ai_plan_commands(
        self,
        user_message: str,
        rules_context: str,
        terminal_tail: str,
        history: list[dict] | None = None,
        unavailable_cmds: set[str] | None = None,
        chat_mode: str = "agent",
        execution_mode: str = "step",
    ) -> dict[str, Any]:
        """
        Ask internal LLM to decide mode and return JSON:
          mode=answer → just reply, no commands
          mode=ask    → ask a clarifying question
          mode=execute → run commands on the server
        """
        from app.core.llm import LLMProvider

        logger.debug(
            "Terminal AI plan_commands: server_id=%s run_id=%s",
            getattr(self.server, "id", None),
            getattr(self, "_ai_run_id", ""),
        )
        # Build history context (exclude last entry = current user message)
        history_lines: list[str] = []
        for h in (history or [])[:-1]:
            role = str(h.get("role") or "user")
            text = str(h.get("text") or "")[:600]
            prefix = "Пользователь" if role == "user" else "Ассистент"
            history_lines.append(f"[{prefix}]: {text}")
        history_text = "\n".join(history_lines) if history_lines else "(начало диалога)"

        # Build unavailable tools warning
        unavail = sorted(unavailable_cmds or set())
        unavail_block = ""
        if unavail:
            tools_list = ", ".join(f"`{t}`" for t in unavail)
            unavail_block = f"""
═══ НЕДОСТУПНЫЕ ИНСТРУМЕНТЫ (НЕ ИСПОЛЬЗОВАТЬ) ═══
На этом сервере НЕ установлены (exit=127 при попытке): {tools_list}
→ Используй ТОЛЬКО доступные альтернативы:
   • вместо `netstat` → `ss`
   • вместо `ufw` → `iptables` (если есть права) или просто сообщи что не установлен
   • вместо `ifconfig` → `ip addr`
   • вместо `service` → `systemctl`
"""

        mode_selector_block = ""
        if execution_mode == "auto":
            mode_selector_block = """
- execution_mode=auto: выбери execution_mode самостоятельно:
  • step — если задача рискованная/неоднозначная/требует проверки после каждого шага
  • fast — если задача линейная и предсказуемая
"""
        else:
            mode_selector_block = f"""
- execution_mode фиксирован пользователем: используй {execution_mode} (не меняй).
"""

        chat_mode_block = ""
        if chat_mode == "ask":
            chat_mode_block = """
РЕЖИМ ЧАТА: ASK
- Пользователь не хочет автозапуск команд.
- Если для задачи нужны команды на сервере, всё равно используй mode=execute, но сформируй это как предложения/шаги для пользователя.
- assistant_text должен коротко объяснить, что команды ниже предложены для ручного запуска.
"""
        else:
            chat_mode_block = """
РЕЖИМ ЧАТА: AGENT
- Если задача требует действий на сервере, предпочитай mode=execute.
- Команды будут выполняться автоматически, кроме опасных действий, которые потребуют подтверждения.
"""

        prompt = f"""Ты умный DevOps/SSH ассистент в составе платформы управления серверами.
Ты ведёшь диалог с пользователем и имеешь доступ к SSH-терминалу сервера.

{chat_mode_block}

РЕЖИМ ВЫПОЛНЕНИЯ: {execution_mode}
- auto: агент сам выбирает step/fast для этого запуска.
- step: выдай короткий стартовый план (обычно 1-3 команды), дальше план будет адаптироваться после каждого шага.
- fast: можно выдать полный линейный план сразу (до 6 команд).
{mode_selector_block}

═══ ТВОЯ ЗАДАЧА ═══
Самостоятельно решить, что делать с запросом пользователя, выбрав один из режимов:
  • mode=answer  — ответить, объяснить, проконсультировать (БЕЗ команд)
  • mode=execute — выполнить команды на сервере
  • mode=ask     — задать уточняющий вопрос пользователю

═══ ПРАВИЛА ВЫБОРА РЕЖИМА ═══
→ Общие вопросы, "что такое X", "как работает Y", теория → mode=answer
→ Приветствия, благодарности, короткие реплики → mode=answer (кратко)
→ Нужно что-то проверить/сделать/настроить на сервере → mode=execute
→ Пользователь хочет одновременно объяснения и действий → mode=execute (объяснение в assistant_text)
→ Запрос слишком неоднозначен, нужна конкретика → mode=ask
{unavail_block}
═══ КРИТИЧЕСКИЕ ПРАВИЛА ДЛЯ КОМАНД (только mode=execute) ═══
1. НИКОГДА не используй команды с бесконечным выводом — они зависнут:
   ✗ tail -f   → ✓ tail -n 100
   ✗ journalctl -f   → ✓ journalctl -n 100 --no-pager
   ✗ docker logs -f  → ✓ docker logs --tail=100
   ✗ watch cmd       → ✓ разовая команда
   ✗ top/htop        → ✓ ps aux --sort=-%cpu | head -20
   ✗ ping host       → ✓ ping -c 4 host
2. Используй --no-pager для journalctl, systemctl show, git log и т.д.
3. Максимум 6 команд. Начинай с диагностики, потом действия.
4. Разрушительные команды (rm -rf, drop, truncate) — только если явно попросили + нужно подтверждение.
5. Для редактирования файлов: используй sed -i, awk, tee или heredoc (cat > file << 'EOF').

═══ ФОРМАТ ОТВЕТА (ТОЛЬКО JSON, без markdown вокруг) ═══
{{
  "execution_mode": "step" | "fast",
  "mode": "answer" | "execute" | "ask",
  "assistant_text": "текст пользователю (Markdown, всегда заполнен)",
  "commands": [{{"cmd": "команда", "why": "зачем эта команда"}}]
}}
Поле execution_mode всегда обязательно.
Поле commands — только для mode=execute. Для остальных режимов — [].

═══ КОНТЕКСТ СЕРВЕРА/ПОЛИТИКИ ═══
{rules_context or "(нет)"}

═══ ИСТОРИЯ ДИАЛОГА ═══
{history_text}

═══ ПОСЛЕДНИЙ ВЫВОД ТЕРМИНАЛА ═══
{terminal_tail or "(пусто)"}

═══ ТЕКУЩИЙ ЗАПРОС ПОЛЬЗОВАТЕЛЯ ═══
{user_message}

Верни только JSON."""

        llm = LLMProvider()
        out = ""
        async with _TERMINAL_AI_LLM_SEMAPHORE:
            async for chunk in llm.stream_chat(prompt, model="auto", purpose="chat"):
                out += chunk
                if len(out) > 20000:
                    break

        if (out or "").strip().lower().startswith("error:"):
            raise ValueError(out.strip())

        return self._extract_json_object(out)

    @staticmethod
    def _compute_report_status(done_items: list[dict[str, Any]]) -> str:
        codes = [item.get("exit_code") for item in done_items]
        non_captured = [c for c in codes if c != 130]
        if non_captured and all(c == 0 for c in non_captured if c is not None):
            return "ok"
        if any(c not in (None, 0, 130) for c in codes):
            ok_count = sum(1 for c in codes if c in (0, 130))
            return "error" if ok_count < len(codes) / 2 else "warning"
        return "warning"

    @staticmethod
    def _build_fallback_report(done_items: list[dict[str, Any]]) -> str:
        codes = [item.get("exit_code") for item in done_items]
        all_ok = all(code == 0 for code in codes if code is not None)
        if all_ok:
            return (
                "Команды выполнены успешно (код выхода 0). Вывод смотрите в консоли слева. "
                "Краткий анализ по выводу сформировать не удалось — попробуйте запрос ещё раз или проверьте логи вручную."
            )
        return (
            "Команды выполнены. Коды выхода: "
            + ", ".join(str(code) for code in codes)
            + ". Вывод в консоли слева. Для анализа проверьте вывод вручную."
        )

    async def _generate_ai_report_text(self, user_message: str, done_items: list[dict[str, Any]]) -> str:
        done_with_output = [item for item in done_items if (item.get("output") or "").strip()]
        report = ""
        if done_with_output:
            try:
                report = (await self._ai_make_report(user_message, done_with_output)).strip()
            except Exception as exc:
                logger.warning("AI report generation failed: %s", exc)
        if not report:
            report = self._build_fallback_report(done_items)
        return report

    async def _ai_make_report(self, user_message: str, commands_with_output: list[dict[str, Any]]) -> str:
        """
        По выводу выполненных команд и запросу пользователя формирует краткий отчёт:
        какие проблемы обнаружены или что проблем нет.
        """
        from app.core.llm import LLMProvider

        # Build a summary header (makes it easy for the LLM to reference commands by exact text)
        summary_lines = []
        for i, row in enumerate(commands_with_output[:10], 1):
            cmd_text = str(row.get("cmd") or "").strip() or f"cmd_{i}"
            code = row.get("exit_code")
            mark = "OK" if code == 0 else ("CAPTURED" if code == 130 else f"FAIL(exit={code})")
            summary_lines.append(f"  {i}. [{mark}] {cmd_text}")
        summary = "\n".join(summary_lines)

        # Detailed blocks — use COMMAND:/EXIT_CODE:/OUTPUT: labels, no brackets that confuse the LLM
        parts = []
        for i, row in enumerate(commands_with_output[:10], 1):
            cmd_text = str(row.get("cmd") or "").strip() or f"cmd_{i}"
            code = row.get("exit_code")
            out = (str(row.get("output") or "")).strip() or "(no output)"
            parts.append(
                f"COMMAND: {cmd_text}\n"
                f"EXIT_CODE: {code}\n"
                f"OUTPUT:\n{out[:1200]}"
            )
        context = "\n\n---\n\n".join(parts)

        prompt = f"""Ты старший DevOps-инженер. Напиши отчёт по результатам выполнения команд.

Список выполненных команд:
{summary}

ПРАВИЛА ДЛИНЫ:
- Если вывод содержит список объектов (контейнеры, образы, процессы, файлы, порты, пользователи) — покажи ПОЛНЫЙ список в таблице. Не обрезай.
- Если вывод короткий или числовой — будь кратким (до 15 строк).
- Цель: отчёт должен содержать всю полезную информацию из вывода, но без воды.

СТРУКТУРА (только актуальные секции):
**Статус**: ✅ OK / ⚠️ Предупреждение / ❌ Ошибка + одна фраза-итог.

**Контейнеры / Образы / Процессы / Порты** (нужный заголовок):
Таблица со ВСЕМИ найденными объектами. Колонки подбери по содержимому.
Для docker ps: Имя | Образ | Статус | Порты
Для docker images: Репозиторий | Тег | Размер | Создан
Для процессов: PID | Команда | CPU% | MEM%
Для портов: Протокол | Адрес | Порт | Сервис (если известен)

**Проблемы** (если есть):
Список ≤3 пунктов. Формат: `точная-команда` — что случилось — последствие.
Команда exit=127 = "не установлена" (не критическая ошибка). Не пиши "ошибка сервера".
Если основные команды выполнились — Статус ✅ OK, отсутствие утилит упомяни только в Проблемах.

**Действия** (только если есть реальные проблемы): ≤2 конкретных команды.

ПРИМЕР формата Проблем:
- `ufw status verbose` — утилита не установлена (exit 127) — рекомендуется `apt install ufw`
- `iptables -L -v -n` — требуются права root (exit 4) — выполни с sudo

Начинай сразу с **Статус**. Без заголовка "Отчёт:" и преамбулы.
Ссылайся на команды по ТОЧНОМУ тексту из списка выше (в обратных кавычках).

ЗАПРОС ПОЛЬЗОВАТЕЛЯ: {user_message[:300]}

ВЫВОД КОМАНД:
{context[:8000]}

Отчёт:"""

        llm = LLMProvider()
        out = ""
        async with _TERMINAL_AI_LLM_SEMAPHORE:
            async for chunk in llm.stream_chat(prompt, model="auto", purpose="chat"):
                out += chunk
                if len(out) > 12000:
                    break
        return (out or "").strip()

    @staticmethod
    def _sanitize_memory_line(text: str) -> str:
        line = str(text or "").replace("\n", " ").replace("\r", " ").strip()
        if not line:
            return ""
        # Never persist obvious secrets in long-term server memory.
        if re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", line, flags=re.IGNORECASE):
            return ""
        line = re.sub(
            r"(?i)\b([a-z0-9_.-]*(?:password|passwd|token|secret|api[_-]?key|authorization)[a-z0-9_.-]*)\b\s*[:=]\s*([^\s,;]+)",
            r"\1=[REDACTED]",
            line,
        )
        line = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{10,}\b", "Bearer [REDACTED]", line)
        line = re.sub(r"\s+", " ", line).strip(" -")
        if len(line) > 260:
            line = line[:257].rstrip() + "..."
        return line

    async def _ai_extract_server_memory(
        self,
        user_message: str,
        commands_with_output: list[dict[str, Any]],
        report: str = "",
    ) -> dict[str, Any]:
        """
        Build concise, durable server context from current run:
        key facts, important paths/services, and active issues.
        """
        from app.core.llm import LLMProvider

        blocks: list[str] = []
        for idx, row in enumerate((commands_with_output or [])[:8], 1):
            cmd = str(row.get("cmd") or "").strip()
            code = row.get("exit_code")
            out = str(row.get("output") or "").strip()
            blocks.append(
                f"{idx}. CMD: {cmd}\nEXIT: {code}\nOUT:\n{out[:1200]}"
            )
        commands_block = "\n\n---\n\n".join(blocks) if blocks else "(нет данных)"
        report_block = (report or "").strip()[:1800] or "(нет отчёта)"

        prompt = f"""Ты формируешь долгосрочную память о сервере после выполненной задачи.
Нужны только факты, которые помогут будущим задачам на этом сервере.

ЗАПРОС ПОЛЬЗОВАТЕЛЯ:
{(user_message or '')[:300]}

КРАТКИЙ ОТЧЁТ:
{report_block}

ВЫПОЛНЕННЫЕ КОМАНДЫ И ВЫВОД:
{commands_block}

Верни только JSON:
{{
  "summary": "1-2 коротких предложения, что важно запомнить",
  "facts": [
    "стабильный факт с конкретикой (версия, путь, сервис, порт, стек)"
  ],
  "issues": [
    "актуальная проблема/риск с привязкой к факту"
  ]
}}

Правила:
- facts: максимум 8 пунктов, только подтверждённые по выводу.
- issues: максимум 4 пункта.
- Не добавляй секреты: пароли, токены, ключи.
- Если данных мало, верни пустые списки, но summary оставь.
"""

        llm = LLMProvider()
        out = ""
        async with _TERMINAL_AI_LLM_SEMAPHORE:
            async for chunk in llm.stream_chat(prompt, model="auto", purpose="chat"):
                out += chunk
                if len(out) > 7000:
                    break

        try:
            obj = self._extract_json_object(out)
        except Exception as e:
            logger.warning("_ai_extract_server_memory JSON parse failed: %s, output: %.200s", e, out)
            return {"summary": "", "facts": [], "issues": []}

        summary = self._sanitize_memory_line(str(obj.get("summary") or ""))

        def _clean_list(raw: Any, limit: int) -> list[str]:
            if not isinstance(raw, list):
                return []
            seen: set[str] = set()
            cleaned: list[str] = []
            for it in raw:
                line = self._sanitize_memory_line(str(it or ""))
                if not line:
                    continue
                key = line.lower()
                if key in seen:
                    continue
                seen.add(key)
                cleaned.append(line)
                if len(cleaned) >= limit:
                    break
            return cleaned

        facts = _clean_list(obj.get("facts"), 8)
        issues = _clean_list(obj.get("issues"), 4)
        return {
            "summary": summary,
            "facts": facts,
            "issues": issues,
        }

    @database_sync_to_async
    def _save_ai_server_profile(
        self,
        user_id: int,
        server_id: int,
        summary: str,
        facts: list[str],
        issues: list[str],
    ) -> dict[str, Any]:
        from django.contrib.auth.models import User
        from servers.knowledge_service import ServerKnowledgeService
        from servers.models import Server

        user = User.objects.filter(id=user_id).first()
        server = Server.objects.filter(id=server_id).first()
        if not server:
            return {"saved": 0, "titles": []}

        cleaned_summary = self._sanitize_memory_line(summary)
        cleaned_facts = [self._sanitize_memory_line(x) for x in (facts or [])]
        cleaned_facts = [x for x in cleaned_facts if x]
        cleaned_issues = [self._sanitize_memory_line(x) for x in (issues or [])]
        cleaned_issues = [x for x in cleaned_issues if x]

        # Do not persist ephemeral chat summaries without durable facts/issues.
        if not should_persist_ai_memory(facts=cleaned_facts, issues=cleaned_issues):
            return {"saved": 0, "titles": []}

        saved = 0
        titles: list[str] = []
        now_str = timezone.now().strftime("%Y-%m-%d %H:%M")

        if cleaned_summary or cleaned_facts:
            profile_parts = [f"Обновлено: {now_str}"]
            if cleaned_summary:
                profile_parts.append(f"Кратко: {cleaned_summary}")
            if cleaned_facts:
                profile_parts.append("Факты:")
                profile_parts.extend([f"- {x}" for x in cleaned_facts[:10]])
            profile_content = "\n".join(profile_parts)[:3500]
            ServerKnowledgeService.save_ai_knowledge(
                server=server,
                title="Профиль сервера (авто)",
                content=profile_content,
                category="config",
                user=user,
                confidence=0.88,
            )
            saved += 1
            titles.append("Профиль сервера (авто)")

        if cleaned_issues:
            issues_parts = [f"Обновлено: {now_str}", "Риски/замечания:"]
            issues_parts.extend([f"- {x}" for x in cleaned_issues[:8]])
            issues_content = "\n".join(issues_parts)[:2500]
            ServerKnowledgeService.save_ai_knowledge(
                server=server,
                title="Текущие риски (авто)",
                content=issues_content,
                category="issues",
                user=user,
                confidence=0.8,
            )
            saved += 1
            titles.append("Текущие риски (авто)")

        return {"saved": saved, "titles": titles}

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any]:
        t = (text or "").strip()
        # Strip common code fences if any
        if "```" in t:
            t = re.sub(r"```(?:json)?", "", t, flags=re.IGNORECASE).replace("```", "").strip()
        start = t.find("{")
        if start < 0:
            raise ValueError(f"AI не вернул JSON: {t[:400]}")
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(t[start:])
        if not isinstance(obj, dict):
            raise ValueError("AI JSON должен быть объектом")
        return obj

    def _compute_confirm_reason(
        self,
        cmd: str,
        forbidden_patterns: list[str],
        allowlist_patterns: list[str] | None = None,
        *,
        confirm_dangerous_commands: bool = True,
    ) -> str:
        text = (cmd or "").strip()
        if not text:
            return ""
        if self._matches_patterns(text, forbidden_patterns or []):
            return "forbidden"
        if allowlist_patterns and not self._matches_patterns(text, allowlist_patterns or []):
            return "outside_allowlist"
        if confirm_dangerous_commands and is_dangerous_command(text):
            return "dangerous"
        return ""

    @staticmethod
    def _matches_patterns(cmd: str, patterns: list[str]) -> bool:
        cmd_l = (cmd or "").lower()
        for p in patterns or []:
            pat = (str(p or "")).strip()
            if not pat:
                continue
            pl = pat.lower()
            if pl.startswith("re:"):
                expr = pat[3:].strip()
                if not expr:
                    continue
                try:
                    if re.search(expr, cmd, flags=re.IGNORECASE):
                        return True
                except re.error:
                    continue
                continue

            pat_tokens = re.findall(r"[a-z0-9_./:-]+", pl)
            cmd_tokens = re.findall(r"[a-z0-9_./:-]+", cmd_l)
            if pat_tokens and cmd_tokens:
                plen = len(pat_tokens)
                for i in range(0, len(cmd_tokens) - plen + 1):
                    if cmd_tokens[i : i + plen] == pat_tokens:
                        return True

            if pl in cmd_l:
                return True
        return False

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
                try:
                    self._ssh_proc.close()
                    await asyncio.wait_for(self._ssh_proc.wait_closed(), timeout=5)
                except Exception:
                    pass
        finally:
            self._ssh_proc = None

        try:
            if self._ssh_conn:
                try:
                    self._ssh_conn.close()
                    await asyncio.wait_for(self._ssh_conn.wait_closed(), timeout=5)
                except Exception:
                    pass
        finally:
            self._ssh_conn = None

        if was_connected and self.scope.get("user") and getattr(self.scope["user"], "is_authenticated", False):
            await self._safe_send_json({"type": "status", "status": "disconnected"})

        if was_connected and self.server and self._user_id:
            await log_user_activity_async(
                user_id=self._user_id,
                category='servers',
                action='terminal_disconnect',
                status='info',
                description=f'Disconnected from server terminal "{self.server.name}"',
                entity_type='server',
                entity_id=self.server.id,
                entity_name=self.server.name,
            )

        if self._server_connection_id:
            await self._mark_server_connection_closed(self._server_connection_id)
            self._server_connection_id = None

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
                    await self._safe_send_json({"type": "output", "stream": stream, "data": filtered})
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
        if not data:
            return "", []

        markers: list[tuple[int, int]] = []
        out: list[str] = []
        i = 0

        # Ensure state exists (older instances)
        if not hasattr(self, "_marker_suppress"):
            self._marker_suppress = {"stdout": False, "stderr": False}
        if not hasattr(self, "_marker_line_buf"):
            self._marker_line_buf = {"stdout": "", "stderr": ""}

        suppress = bool(self._marker_suppress.get(stream, False))
        buf = self._marker_line_buf.get(stream, "")
        marker_prefix = self._marker_prefix()
        marker_re = re.compile(rf"^{re.escape(marker_prefix)}(\d+):(-?\d+)__\s*$")

        while i < len(data):
            if suppress:
                nl = data.find("\n", i)
                if nl == -1:
                    buf += data[i:]
                    i = len(data)
                    break
                buf += data[i:nl]
                # Try parse marker output line: __WEUAI_EXIT_<token>_<id>:<code>__
                m = marker_re.match(buf.strip())
                if m:
                    try:
                        markers.append((int(m.group(1)), int(m.group(2))))
                    except Exception:
                        pass
                buf = ""
                suppress = False
                # Preserve the newline which ended the suppressed line
                out.append("\n")
                i = nl + 1
                continue

            idx = data.find(marker_prefix, i)
            if idx == -1:
                out.append(data[i:])
                i = len(data)
                break

            out.append(data[i:idx])
            suppress = True
            buf = ""
            i = idx

        self._marker_suppress[stream] = suppress
        self._marker_line_buf[stream] = buf
        return "".join(out), markers

    def _set_ai_exit_code(self, cmd_id: int, exit_code: int):
        try:
            fut = (self._ai_exit_futures or {}).get(int(cmd_id))
            if fut and not fut.done():
                fut.set_result(int(exit_code))
        except Exception:
            return

    def _append_terminal_tail(self, text: str):
        if not text:
            return
        clean = self._strip_ansi_and_controls(text)
        if not clean:
            return
        self._terminal_tail = (self._terminal_tail or "") + clean
        # keep last ~8k chars
        if len(self._terminal_tail) > 8000:
            self._terminal_tail = self._terminal_tail[-8000:]

    def _append_ai_output(self, text: str):
        if not text:
            return
        if getattr(self, "_ai_active_cmd_id", None) is None:
            return
        clean = self._strip_ansi_and_controls(text)
        if not clean:
            return
        self._ai_active_output = (self._ai_active_output or "") + clean
        if len(self._ai_active_output) > 6000:
            self._ai_active_output = self._ai_active_output[-6000:]

    @staticmethod
    def _strip_ansi_and_controls(text: str) -> str:
        if not text:
            return ""
        # ANSI escape sequences
        out = re.sub(r"\x1B[@-_][0-?]*[ -/]*[@-~]", "", text)
        # C0 controls except line breaks and tab
        out = re.sub(r"[\x00-\x08\x0B-\x1F\x7F]", "", out)
        return out

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

    @staticmethod
    def _parse_term_size(content: dict[str, Any]) -> _TermSize:
        try:
            cols = int(content.get("cols") or 80)
        except Exception:
            cols = 80
        try:
            rows = int(content.get("rows") or 24)
        except Exception:
            rows = 24
        cols = max(10, min(cols, 400))
        rows = max(5, min(rows, 200))
        return _TermSize(cols=cols, rows=rows)

    @staticmethod
    def _build_exports(env_vars: dict[str, Any]) -> str:
        exports: list[str] = []
        for k, v in (env_vars or {}).items():
            key = str(k or "").strip()
            if not key:
                continue
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
                continue
            # Avoid newlines which would break the shell
            value = str(v if v is not None else "").replace("\n", " ").replace("\r", " ").strip()
            exports.append(f"export {key}={shlex.quote(value)}")
        return "; ".join(exports)

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

    @database_sync_to_async
    def _user_can_servers(self, user_id: int) -> bool:
        from django.contrib.auth.models import User

        user = User.objects.filter(id=user_id).first()
        return bool(user and user_can_feature(user, "servers"))

    @database_sync_to_async
    def _get_terminal_session_limit(self, user_id: int) -> dict[str, object] | None:
        from django.contrib.auth.models import User

        user = User.objects.filter(id=user_id).first()
        return get_terminal_session_limit_error(user)

    @database_sync_to_async
    def _get_server(self, user_id: int, server_id: int) -> Server:
        now = timezone.now()
        return (
            Server.objects.select_related("group", "user")
            .filter(id=server_id, is_active=True)
            .filter(
                Q(user_id=user_id)
                | (
                    Q(shares__user_id=user_id, shares__is_revoked=False)
                    & (Q(shares__expires_at__isnull=True) | Q(shares__expires_at__gt=now))
                )
            )
            .distinct()
            .get()
        )

    @database_sync_to_async
    def _register_server_connection(self, user_id: int, server_id: int, connection_id: str) -> None:
        from app.agent_kernel.memory.store import DjangoServerMemoryStore

        now = timezone.now()
        ServerConnection.objects.update_or_create(
            connection_id=connection_id,
            defaults={
                "server_id": server_id,
                "user_id": user_id,
                "status": "connected",
                "last_seen_at": now,
                "disconnected_at": None,
            },
        )
        DjangoServerMemoryStore()._ingest_event_sync(
            server_id,
            source_kind="terminal",
            actor_kind="human",
            source_ref=connection_id,
            session_id=connection_id,
            event_type="session_opened",
            raw_text="SSH terminal session opened",
            structured_payload={"connection_id": connection_id, "user_id": user_id},
            importance_hint=0.55,
            actor_user_id=user_id,
            force_compact=True,
        )

    @database_sync_to_async
    def _touch_server_connection(self, connection_id: str) -> None:
        ServerConnection.objects.filter(
            connection_id=connection_id,
            status="connected",
            disconnected_at__isnull=True,
        ).update(last_seen_at=timezone.now())

    @database_sync_to_async
    def _mark_server_connection_closed(self, connection_id: str) -> None:
        from app.agent_kernel.memory.store import DjangoServerMemoryStore

        now = timezone.now()
        connection = ServerConnection.objects.filter(connection_id=connection_id).first()
        if connection is None:
            return
        ServerConnection.objects.filter(connection_id=connection_id).update(
            status="disconnected",
            last_seen_at=now,
            disconnected_at=now,
        )
        DjangoServerMemoryStore()._ingest_event_sync(
            connection.server_id,
            source_kind="terminal",
            actor_kind="human",
            source_ref=connection_id,
            session_id=connection_id,
            event_type="session_closed",
            raw_text="SSH terminal session closed",
            structured_payload={"connection_id": connection_id, "user_id": connection.user_id},
            importance_hint=0.52,
            actor_user_id=connection.user_id,
            force_compact=True,
        )

    @database_sync_to_async
    def _resolve_server_secret(self, server_id: int, master_password: str, plain_password: str) -> str:
        """
        Resolve password/passphrase for server authentication.

        - If server has encrypted_password and master_password provided -> decrypt.
        - Else fallback to plain_password provided by user (not stored).
        """
        server = Server.objects.only("id", "encrypted_password", "salt", "auth_method").get(id=server_id)
        if server.auth_method not in ("password", "key_password"):
            return ""
        return get_server_auth_secret(
            server,
            master_password=(master_password or "").strip(),
            fallback_plain=plain_password or "",
        )

    @database_sync_to_async
    def _get_ai_rules_and_forbidden(
        self, user_id: int, server_id: int
    ) -> tuple[list[str], str, list[str], dict[str, Any]]:
        """
        Returns:
          - forbidden_patterns
          - rules_context_text
          - required_checks
          - merged_environment_vars (global/group/server network_config)
        """
        from servers.models import GlobalServerRules, ServerGroupKnowledge, ServerKnowledge

        now = timezone.now()
        server = (
            Server.objects.select_related("group", "user")
            .filter(id=server_id, is_active=True)
            .filter(
                Q(user_id=user_id)
                | (
                    Q(shares__user_id=user_id, shares__is_revoked=False)
                    & (Q(shares__expires_at__isnull=True) | Q(shares__expires_at__gt=now))
                )
            )
            .distinct()
            .first()
        )
        if not server:
            return [], "", [], {}

        share = None
        if server.user_id != user_id:
            share = (
                ServerShare.objects.filter(server_id=server_id, user_id=user_id, is_revoked=False)
                .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
                .first()
            )
        share_context_enabled = bool(share.share_context) if share else True

        global_rules = GlobalServerRules.objects.filter(user_id=server.user_id).first()

        forbidden: list[str] = []
        parts: list[str] = []
        required_checks: list[str] = []
        env_vars: dict[str, Any] = {}

        if global_rules:
            if share_context_enabled:
                ctx = global_rules.get_context_for_ai()
                if ctx:
                    parts.append(ctx)
                required_checks.extend([str(x) for x in (global_rules.required_checks or []) if str(x).strip()])
                env_vars.update(global_rules.environment_vars or {})
            if global_rules.forbidden_commands:
                forbidden.extend([str(x) for x in global_rules.forbidden_commands if x])

        if server.group:
            if share_context_enabled:
                gctx = server.group.get_context_for_ai()
                if gctx:
                    parts.append(gctx)
                env_vars.update(server.group.environment_vars or {})
            if server.group.forbidden_commands:
                forbidden.extend([str(x) for x in server.group.forbidden_commands if x])

        if share_context_enabled:
            try:
                server_ctx = server.get_network_context_summary()
                if server_ctx:
                    parts.append("=== КОНТЕКСТ СЕРВЕРА ===\n" + server_ctx)
            except Exception:
                pass

            # Compact knowledge context to improve AI continuity between runs.
            try:
                knowledge_rows = list(
                    ServerKnowledge.objects.filter(server_id=server.id, is_active=True)
                    .order_by("-updated_at")
                    .values_list("category", "title", "content")[:12]
                )
                if knowledge_rows:
                    k_lines = []
                    for category, title, content in knowledge_rows:
                        t = str(title or "").strip()
                        c = str(content or "").strip().replace("\n", " ")
                        if t or c:
                            k_lines.append(f"- [{category}] {t}: {c[:220]}")
                    if k_lines:
                        parts.append("=== НАКОПЛЕННЫЕ ЗНАНИЯ О СЕРВЕРЕ ===\n" + "\n".join(k_lines))
            except Exception:
                pass

            if server.group_id:
                try:
                    gk_rows = list(
                        ServerGroupKnowledge.objects.filter(group_id=server.group_id, is_active=True)
                        .order_by("-updated_at")
                        .values_list("category", "title", "content")[:8]
                    )
                    if gk_rows:
                        gk_lines = []
                        for category, title, content in gk_rows:
                            t = str(title or "").strip()
                            c = str(content or "").strip().replace("\n", " ")
                            if t or c:
                                gk_lines.append(f"- [{category}] {t}: {c[:220]}")
                        if gk_lines:
                            parts.append("=== ГРУППОВЫЕ ЗНАНИЯ ===\n" + "\n".join(gk_lines))
                except Exception:
                    pass

            # Server-level env vars from network_config have highest priority.
            if isinstance(server.network_config, dict):
                env_vars.update(server.network_config.get("env_vars") or {})
                env_vars.update(server.network_config.get("environment") or {})

        # De-duplicate forbidden patterns (case-insensitive)
        seen: set[str] = set()
        uniq: list[str] = []
        for p in forbidden:
            s = (p or "").strip()
            if not s:
                continue
            k = s.lower()
            if k in seen:
                continue
            seen.add(k)
            uniq.append(s)

        # De-duplicate required checks preserving order
        req_seen: set[str] = set()
        req_uniq: list[str] = []
        for c in required_checks:
            s = str(c or "").strip()
            if not s:
                continue
            k = s.lower()
            if k in req_seen:
                continue
            req_seen.add(k)
            req_uniq.append(s)

        return uniq, "\n\n".join([p for p in parts if p]).strip(), req_uniq, env_vars

    @database_sync_to_async
    def _get_effective_environment_vars(self, user_id: int, server_id: int) -> dict[str, Any]:
        """
        Get merged env vars for shell session.
        Priority: global < group < server network_config(env_vars/environment)
        """
        from servers.models import GlobalServerRules

        now = timezone.now()
        server = (
            Server.objects.select_related("group", "user")
            .filter(id=server_id, is_active=True)
            .filter(
                Q(user_id=user_id)
                | (
                    Q(shares__user_id=user_id, shares__is_revoked=False)
                    & (Q(shares__expires_at__isnull=True) | Q(shares__expires_at__gt=now))
                )
            )
            .distinct()
            .first()
        )
        if not server:
            return {}

        share = None
        if server.user_id != user_id:
            share = (
                ServerShare.objects.filter(server_id=server_id, user_id=user_id, is_revoked=False)
                .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
                .first()
            )
        share_context_enabled = bool(share.share_context) if share else True

        env_vars: dict[str, Any] = {}
        if share_context_enabled:
            global_rules = GlobalServerRules.objects.filter(user_id=server.user_id).first()
            if global_rules:
                env_vars.update(global_rules.environment_vars or {})
            if server.group:
                env_vars.update(server.group.environment_vars or {})

        if isinstance(server.network_config, dict):
            env_vars.update(server.network_config.get("env_vars") or {})
            env_vars.update(server.network_config.get("environment") or {})

        return env_vars

    @database_sync_to_async
    def _log_ai_command_history(
        self,
        user_id: int,
        server_id: int,
        command: str,
        output_snippet: str,
        exit_code: int,
    ) -> None:
        from servers.models import ServerCommandHistory

        ServerCommandHistory.objects.create(
            server_id=server_id,
            user_id=user_id,
            actor_kind=ServerCommandHistory.ACTOR_AGENT,
            source_kind=ServerCommandHistory.SOURCE_AGENT,
            command=command,
            output=output_snippet or "",
            exit_code=exit_code,
        )
