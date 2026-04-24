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
from typing import Any

import asyncssh
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from loguru import logger

from app.runtime_limits import get_terminal_session_limit_error
from core_ui.activity import log_user_activity_async
from core_ui.audit import audit_context
from core_ui.context_processors import user_can_feature
from servers.memory_heuristics import (
    is_trivial_memory_command,
    normalize_memory_command_text,
)
from servers.models import Server, ServerConnection
from servers.secret_utils import get_server_auth_secret, has_saved_server_secret
from servers.services.command_history import (
    get_recent_session_command_activity,
    save_command_history_entry,
)
from servers.services.editor_intercept import detect_editor_command, is_interactive_tui_command
from servers.services.terminal_ai.session_context import (
    apply_successful_command_context,
    build_initial_session_context,
    build_nova_context_bundle,
    build_session_probe_command,
)
from servers.ssh_host_keys import build_server_connect_kwargs, ensure_server_known_hosts


@dataclass(frozen=True)
class _TermSize:
    cols: int
    rows: int

_WEUAI_MARKER_PREFIX = "__WEUAI_EXIT_"

# Regex to detect commands that produce infinite/continuous output or need user input
_STREAMING_CMD_RE = re.compile(
    r"(?:"
    r"\btail\s+.*-[a-zA-Z]*[fF]\b"  # tail -f / -F / -fq
    r"|\btail\s+--follow\b"
    r"|\bjournalctl\s+.*(?:-[a-zA-Z]*[fF]\b|--follow\b)"  # journalctl -f/-fu/--follow
    r"|\bdocker\s+logs?\s+.*(?:-[a-zA-Z]*[fF]\b|--follow\b)"  # docker logs -f/--follow
    r"|\bkubectl\s+logs?\s+.*-[a-zA-Z]*[fF]\b"  # kubectl logs -f
    r"|\bpodman\s+logs?\s+.*(?:-[a-zA-Z]*[fF]\b|--follow\b)"
    r"|\bwatch\s+"  # watch anything
    r"|\btcpdump\b"
    r"|\bstrace\b"
    r"|\bping\s+(?!.*-c\s*\d)"  # ping without -c count
    r")",
    re.IGNORECASE,
)
_INTERACTIVE_CMDS = {
    "top",
    "htop",
    "iotop",
    "iftop",
    "nethogs",
    "vim",
    "vi",
    "nano",
    "less",
    "more",
    "man",
    "pstree",
    "glances",
}

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

    @staticmethod
    def _default_ai_settings() -> dict[str, Any]:
        return {
            "memory_enabled": True,
            "memory_ttl_requests": 6,
            "auto_report": "auto",
            "confirm_dangerous_commands": True,
            "allowlist_patterns": [],
            "blocklist_patterns": [],
            "dry_run": False,
            "extra_target_server_ids": [],
            "nova_session_context_enabled": True,
            "nova_recent_activity_enabled": True,
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

    @staticmethod
    def _normalize_int_list(raw_value: Any) -> list[int]:
        values = raw_value if isinstance(raw_value, list) else []
        normalized: list[int] = []
        seen: set[int] = set()
        for item in values:
            try:
                value = int(item)
            except (TypeError, ValueError):
                continue
            if value <= 0 or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized[:5]

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
            "dry_run": self._parse_bool(incoming.get("dry_run"), bool(defaults["dry_run"])),
            "extra_target_server_ids": self._normalize_int_list(incoming.get("extra_target_server_ids")),
            "nova_session_context_enabled": self._parse_bool(
                incoming.get("nova_session_context_enabled"),
                bool(defaults["nova_session_context_enabled"]),
            ),
            "nova_recent_activity_enabled": self._parse_bool(
                incoming.get("nova_recent_activity_enabled"),
                bool(defaults["nova_recent_activity_enabled"]),
            ),
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
            "dry_run": bool(base.get("dry_run", False)),
            "extra_target_server_ids": SSHTerminalConsumer._normalize_int_list(base.get("extra_target_server_ids")),
            "nova_session_context_enabled": bool(base.get("nova_session_context_enabled", True)),
            "nova_recent_activity_enabled": bool(base.get("nova_recent_activity_enabled", True)),
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
                    current_cwd = str((self._nova_session_context or {}).get("cwd") or "")
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

    @staticmethod
    def _should_use_manual_command_marker(command: str) -> bool:
        normalized = normalize_memory_command_text(command)
        if not normalized:
            return False
        stripped = normalized.strip()
        lowered = stripped.lower()
        if not stripped:
            return False
        # Full-screen TUI programs (nano, vim, less, top, man, htop, tmux, …)
        # take over the pty and read stdin directly. If we append an exit-code
        # marker command after launching them, those bytes are injected into
        # the running TUI as keystrokes instead of being executed by the shell,
        # which corrupts its state and leaves the terminal "frozen" for the
        # user (Ctrl+X / arrow keys stop working until they close the tab).
        if is_interactive_tui_command(stripped):
            return False
        if "<<" in stripped:
            return False
        if stripped.endswith("\\"):
            return False
        if re.search(r"(?:&&|\|\||\|)\s*$", stripped):
            return False
        if re.match(r"^\s*(if|for|while|until|case|select|function)\b", lowered):
            return False
        if re.search(r"\b(?:then|do|else|elif|in)\s*$", lowered):
            return False
        return not (stripped.count("'") % 2 or stripped.count('"') % 2 or stripped.count("`") % 2)

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

    async def _capture_terminal_input(self, data: str) -> list[str]:
        if int(getattr(self, "_input_capture_suppress", 0) or 0) > 0:
            return []

        cleaned = self._strip_terminal_input_sequences(data)
        if not cleaned:
            return []

        completed_commands: list[str] = []
        for char in cleaned:
            if char in ("\r", "\n"):
                command = str(getattr(self, "_manual_input_buffer", "") or "").strip()
                self._manual_input_buffer = ""
                if command:
                    completed_commands.append(command)
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
        return completed_commands

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
                "cwd": str((self._nova_session_context or {}).get("cwd") or ""),
                "context_before": dict(self._nova_session_context or {}),
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
        save_command_history_entry(
            server_id=server_id,
            user_id=user_id,
            session_id=session_id,
            cwd=cwd,
            command=command,
            output=output or "",
            exit_code=exit_code,
        )

    async def _probe_nova_session_context(self, merged_env: dict[str, Any]) -> dict[str, Any]:
        fallback_host = str(getattr(self.server, "host", "") or "") if self.server else ""
        if not self._ssh_conn:
            return build_initial_session_context("", merged_env=merged_env, fallback_host=fallback_host)
        output = ""
        try:
            result = await asyncio.wait_for(
                self._ssh_conn.run(build_session_probe_command(), check=False),
                timeout=3.0,
            )
            output = f"{result.stdout or ''}\n{result.stderr or ''}"
        except Exception:
            output = ""
        return build_initial_session_context(output, merged_env=merged_env, fallback_host=fallback_host)

    def _append_nova_recent_activity(
        self,
        *,
        command: str,
        cwd: str,
        exit_code: int | None,
        source: str,
    ) -> None:
        if not command:
            return
        entries = list(getattr(self, "_nova_recent_activity", []) or [])
        entries.append(
            {
                "command": str(command or "")[:2000],
                "cwd": str(cwd or "")[:500],
                "exit_code": exit_code,
                "source": str(source or "live_session")[:40],
            }
        )
        self._nova_recent_activity = entries[-12:]

    async def _collect_nova_context_bundle(self):
        include_session_context = bool((self._ai_settings or {}).get("nova_session_context_enabled", True))
        include_recent_activity = bool((self._ai_settings or {}).get("nova_recent_activity_enabled", True))
        persisted_activity: list[dict[str, Any]] = []
        if include_recent_activity and self.server:
            try:
                persisted_activity = await database_sync_to_async(
                    get_recent_session_command_activity,
                    thread_sensitive=True,
                )(
                    server_id=self.server.id,
                    session_id=self._server_connection_id or "",
                    limit=8,
                )
            except Exception:
                persisted_activity = []
        return build_nova_context_bundle(
            snapshot=getattr(self, "_nova_session_context", {}) or {},
            live_activity=list(getattr(self, "_nova_recent_activity", []) or []),
            persisted_activity=persisted_activity,
            include_session_context=include_session_context,
            include_recent_activity=include_recent_activity,
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
        raw = str(mode or "").strip().lower()
        if raw in ("auto", "smart", "adaptive_auto", "recommended"):
            return "auto"
        if raw in ("step", "step_by_step", "step-by-step", "sequential", "adaptive"):
            return "step"
        if raw in ("fast", "plan", "batch"):
            return "fast"
        if raw in ("agent", "nova", "react", "interactive"):
            return "agent"
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
            {
                "type": "ai_response",
                "mode": "answer",
                "assistant_text": "🧹 Память текущего чата очищена.",
                "commands": [],
                "execution_mode": str(getattr(self, "_ai_execution_mode", "step")),
            }
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
                {
                    "type": "ai_error",
                    "message": "Нужна команда и её вывод для объяснения.",
                }
            )
            return

        from app.core.llm import LLMProvider
        from servers.services.terminal_ai import build_explain_output_prompt

        prompt = build_explain_output_prompt(
            command=cmd,
            output=output,
            exit_code=exit_code,
            user_question=question,
        )

        await self._send_ai_event(
            {"type": "ai_status", "status": "explaining", "id": cmd_id}
        )

        try:
            llm = LLMProvider()
            text = ""
            # A6: route to the same cheap bucket as chat/report.
            async with _TERMINAL_AI_LLM_SEMAPHORE:
                # TODO: add json_mode=True
                async for chunk in llm.stream_chat(prompt, model="auto", purpose="terminal_chat"):
                    text += chunk
                    if len(text) > 4000:
                        break
            await self._send_ai_event(
                {
                    "type": "ai_explanation",
                    "id": cmd_id,
                    "cmd": cmd,
                    "explanation": (text or "").strip(),
                }
            )
        finally:
            await self._send_ai_event({"type": "ai_status", "status": "idle"})

    async def _handle_ai_generate_report(self, content: dict[str, Any]):
        force_regenerate = self._parse_bool((content or {}).get("force"), False)
        async with self._ai_lock:
            if self._ai_task and not self._ai_task.done():
                await self._send_ai_event(
                    {"type": "ai_error", "message": "Дождитесь завершения текущего запуска ассистента."}
                )
                return
            done_items = list(self._ai_last_done_items or [])
            user_message = str(self._ai_user_message or "")
            cached_report = "" if force_regenerate else str(self._ai_last_report or "")

        if not done_items:
            await self._send_ai_event(
                {"type": "ai_error", "message": "Нет завершённых команд для формирования отчёта."}
            )
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
        # F2-6: single-source policy decision (allowed / confirm / reason / risk / exec_mode).
        from servers.services.terminal_ai import decide_command_policy

        clean_cmd = str(cmd or "").strip()
        verdict = decide_command_policy(
            clean_cmd,
            forbidden_patterns=forbidden_patterns,
            allowlist_patterns=allowlist_patterns,
            chat_mode=getattr(self, "_ai_chat_mode", "agent"),
            confirm_dangerous_commands=confirm_dangerous_commands,
        )
        blocked = not verdict.allowed
        # F2-8: trust LLM-provided exec_mode only when valid; otherwise fall
        # back to policy-picked default. For v1 we keep execution on PTY —
        # the value is an informational hint for the orchestrator / UI.
        resolved_exec_mode = (exec_mode or verdict.exec_mode or "pty").strip().lower()
        if resolved_exec_mode not in {"pty", "direct"}:
            resolved_exec_mode = verdict.exec_mode
        return {
            "id": int(item_id),
            "cmd": clean_cmd,
            "why": str(why or "").strip(),
            # forbidden => hard block, dangerous/ask_mode => explicit confirm
            "requires_confirm": verdict.requires_confirm,
            "blocked": blocked,
            "reason": verdict.reason,
            "status": "blocked" if blocked else "pending",
            "streaming": self._is_streaming_command(clean_cmd),
            # F2-5: expose risk categories/reasons for UI tooltips & audit logs.
            "risk_categories": list(verdict.risk_categories),
            "risk_reasons": list(verdict.risk_reasons),
            # F2-8: hybrid executor hint.
            "exec_mode": resolved_exec_mode,
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

                # 4.2: parallel batch detection ──────────────────────────
                batch_indices: list[int] = []
                plan_snapshot: list[dict[str, Any]] = []
                async with self._ai_lock:
                    if not self._ai_plan or self._ai_plan_index >= len(self._ai_plan):
                        break
                    if not step_mode and self._ssh_conn:
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

                # F2-8 v2: route safe stateless commands through a non-PTY
                # channel so the interactive shell is not polluted by
                # diagnostic reads (df -h, ps aux, systemctl status…).
                item_exec_mode = str(item.get("exec_mode") or "pty").strip().lower()
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
                            {
                                "type": "ai_direct_output",
                                "id": item_id,
                                "cmd": cmd,
                                "output": output_snippet,
                                "exit_code": 0,
                                "dry_run": True,
                            }
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
                            {
                                "type": "ai_status",
                                "status": "analyzing_error",
                                "cmd": cmd,
                                "exit_code": exit_code,
                            }
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
        from servers.services.snapshot_service import (
            MAX_SNAPSHOT_BYTES,
            detect_target_file,
            save_snapshot,
        )

        file_path = detect_target_file(cmd)
        if not file_path:
            return
        try:
            # Read file content (non-PTY, short timeout)
            result = await asyncio.wait_for(
                self._ssh_conn.run(
                    f"cat {file_path} 2>/dev/null",
                    check=False,
                ),
                timeout=self.SNAPSHOT_READ_TIMEOUT_SEC,
            )
            content = str(result.stdout or "")
            if len(content.encode("utf-8", errors="replace")) > MAX_SNAPSHOT_BYTES:
                logger.debug(
                    "Snapshot skipped: file %s too large (%d bytes)",
                    file_path,
                    len(content),
                )
                return
            await database_sync_to_async(save_snapshot)(
                server_id=self.server.id,
                user_id=self._user_id,
                command=cmd,
                file_path=file_path,
                content=content,
            )
            logger.debug("Snapshot saved for %s before cmd_id=%s", file_path, cmd_id)
        except Exception as exc:
            logger.debug("Snapshot capture failed for %s: %s", file_path, exc)

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
        # F2-3: forwarder — canonical impl in servers.services.terminal_ai.memory
        from servers.services.terminal_ai import select_memory_candidate_commands

        return select_memory_candidate_commands(commands_with_output)

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
        from app.core.llm import LLMProvider
        from servers.services.terminal_ai import (
            RecoveryDecision,
            build_recovery_prompt,
            parse_or_repair,
        )

        prompt = build_recovery_prompt(
            cmd=cmd,
            exit_code=exit_code,
            output=output or "",
            remaining_cmds=remaining_cmds or [],
            user_reply=user_reply,
        )

        llm = LLMProvider()
        out = ""
        # A4: recovery — 1-shot JSON decision, route to cheap bucket.
        async with _TERMINAL_AI_LLM_SEMAPHORE:
            # TODO: add json_mode=True
            async for chunk in llm.stream_chat(prompt, model="auto", purpose="terminal_recovery", json_mode=True):
                out += chunk
                if len(out) > 3000:
                    break

        decision, err = parse_or_repair(out, RecoveryDecision)
        if decision is None:
            logger.warning("_ai_handle_error parse failed: %s, output: %.200s", err, out)
            return {"action": "skip", "why": "Не удалось разобрать ответ LLM — пропускаю команду"}
        return decision.model_dump()

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
        from app.core.llm import LLMProvider
        from servers.services.terminal_ai import (
            StepDecision,
            build_step_decision_prompt,
            parse_or_repair,
        )

        prompt = build_step_decision_prompt(
            user_goal=user_goal,
            last_cmd=last_cmd,
            exit_code=exit_code,
            output=output or "",
            remaining_cmds=remaining_cmds or [],
            user_reply=user_reply,
        )

        llm = LLMProvider()
        out = ""
        # A4: step decision — next/stop JSON, route to cheap bucket.
        async with _TERMINAL_AI_LLM_SEMAPHORE:
            async for chunk in llm.stream_chat(prompt, model="auto", purpose="terminal_step_decision", json_mode=True):
                out += chunk
                if len(out) > 5000:
                    break

        decision, err = parse_or_repair(out, StepDecision)
        if decision is None:
            logger.warning("_ai_step_decide_next parse failed: %s, output: %.200s", err, out)
            return {"action": "continue"}
        return decision.model_dump()

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
        from servers.services.terminal_ai.agent.tools import ServerTarget

        extras: dict[str, Any] = {}
        ids_raw = (self._ai_settings or {}).get("extra_target_server_ids") or []
        try:
            ids = [int(x) for x in ids_raw if int(x)]
        except (TypeError, ValueError):
            return extras
        if not ids or not self._user_id:
            return extras

        # Keep extras modest — more than this runs into SSH connection
        # limits on common servers.
        ids = ids[:5]

        try:
            servers_allowed = await self._list_user_accessible_servers(
                user_id=self._user_id, server_ids=ids
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("agent extras lookup failed: %s", exc)
            return extras

        for srv in servers_allowed:
            # Skip the primary — it's already represented.
            if self.server and int(srv["id"]) == int(self.server.id):
                continue
            name = f"srv-{srv['id']}"
            extras[name] = ServerTarget(
                name=name,
                server_id=int(srv["id"]),
                display_name=str(srv.get("name") or ""),
                host=str(srv.get("host") or ""),
                read_only=bool(srv.get("ai_read_only")),
                is_primary=False,
                description=str(srv.get("description") or ""),
            )
        return extras

    async def _ai_build_agent_memory_context(self, server_ids: list[int]) -> str:
        """Render a layered-memory prompt block for the agent.

        Loads :class:`ServerMemoryCard` for every authorised target in
        one batched query and renders them via
        :func:`render_server_cards_prompt`. Everything here is
        best-effort — an empty string is returned on any error so the
        agent simply starts without prior knowledge instead of crashing.
        """
        ids = [int(sid) for sid in server_ids if sid]
        if not ids:
            return ""
        try:
            from asgiref.sync import sync_to_async

            from app.agent_kernel.memory.server_cards import (
                render_server_cards_prompt,
            )
            from servers.adapters.memory_store import DjangoServerMemoryStore

            store = DjangoServerMemoryStore()
            cards = await sync_to_async(
                store._get_server_cards_batch_sync, thread_sensitive=True
            )(ids)
            # Primary first — its card is the most useful context. The
            # batch loader doesn't guarantee order, so resort by the
            # requested id sequence.
            cards_by_id = {int(getattr(c, "server_id", 0) or 0): c for c in cards}
            ordered = [cards_by_id[sid] for sid in ids if sid in cards_by_id]
            if not ordered:
                return ""
            # max_cards mirrors agent_engine's default so we don't blow
            # the prompt window on sessions with many extras.
            return render_server_cards_prompt(ordered, max_cards=3, max_records=6)
        except Exception as exc:  # noqa: BLE001 — memory read is best-effort
            logger.warning("agent memory context load failed: %s", exc)
            return ""

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
            known_hosts = await ensure_server_known_hosts(server)
            connect_kwargs = build_server_connect_kwargs(
                server,
                secret=secret or "",
                known_hosts=known_hosts,
                connect_timeout=max(
                    1, int(getattr(settings, "SSH_CONNECT_TIMEOUT_SECONDS", 10) or 10)
                ),
                login_timeout=max(
                    1, int(getattr(settings, "SSH_LOGIN_TIMEOUT_SECONDS", 20) or 20)
                ),
                keepalive_interval=max(
                    1,
                    int(getattr(settings, "SSH_KEEPALIVE_INTERVAL_SECONDS", 20) or 20),
                ),
                keepalive_count_max=max(
                    1, int(getattr(settings, "SSH_KEEPALIVE_COUNT_MAX", 3) or 3)
                ),
            )
            return await asyncssh.connect(**connect_kwargs)
        except Exception as exc:  # noqa: BLE001 — never crash the agent
            logger.warning("agent open_target(server_id=%s) failed: %s", server_id, exc)
            return None

    @database_sync_to_async
    def _load_server_for_agent(self, server_id: int) -> Any | None:
        """Fetch a server model the user is authorised to access."""
        from servers.models import Server, ServerShare

        user_id = self._user_id
        if not user_id:
            return None
        # Same ACL as _list_user_accessible_servers — kept as two
        # round-trips here because we also need the model instance.
        own = Server.objects.filter(user_id=user_id, id=server_id).first()
        if own:
            return own
        if ServerShare.objects.filter(
            shared_with_id=user_id, server_id=server_id
        ).exists():
            return Server.objects.filter(id=server_id).first()
        group_allowed = Server.objects.filter(
            id=server_id, group__members__user_id=user_id
        ).first()
        return group_allowed

    @database_sync_to_async
    def _list_user_accessible_servers(
        self, *, user_id: int, server_ids: list[int]
    ) -> list[dict]:
        """Return server metadata for ids the user can access.

        Checks ownership, direct shares, and group membership — same
        ACL the terminal-open flow uses.
        """
        from servers.models import Server, ServerGroupMember, ServerShare

        own_ids = set(
            Server.objects.filter(user_id=user_id, id__in=server_ids).values_list(
                "id", flat=True
            )
        )
        shared_ids = set(
            ServerShare.objects.filter(
                shared_with_id=user_id, server_id__in=server_ids
            ).values_list("server_id", flat=True)
        )
        group_server_ids = set(
            Server.objects.filter(
                id__in=server_ids,
                group__members__user_id=user_id,
            ).values_list("id", flat=True)
        )
        allowed = own_ids | shared_ids | group_server_ids
        _ = ServerGroupMember  # noqa: F841 — keep import grouped with model
        rows = Server.objects.filter(id__in=allowed).values(
            "id", "name", "host", "ai_read_only", "description"
        )
        return list(rows)

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
        from app.core.llm import LLMProvider
        from servers.services.terminal_ai import (
            TerminalPlanResponse,
            build_planner_prompt_parts,
            parse_or_repair,
        )

        logger.debug(
            "Terminal AI plan_commands: server_id=%s run_id=%s",
            getattr(self.server, "id", None),
            getattr(self, "_ai_run_id", ""),
        )

        system_prompt, user_prompt = build_planner_prompt_parts(
            user_message=user_message,
            rules_context=rules_context,
            terminal_tail=terminal_tail,
            history=history,
            unavailable_cmds=unavailable_cmds,
            chat_mode=chat_mode,
            execution_mode=execution_mode,
            # A5: dry-run flag surfaces in the planner prompt so the LLM
            # can mention it to the user via ``assistant_text``.
            dry_run=dry_run,
        )

        llm = LLMProvider()
        out = ""
        async with _TERMINAL_AI_LLM_SEMAPHORE:
            async for chunk in llm.stream_chat(user_prompt, model="auto", purpose="terminal_planning", system_prompt=system_prompt, json_mode=True):
                out += chunk
                if len(out) > 20000:
                    break

        if (out or "").strip().lower().startswith("error:"):
            raise ValueError(out.strip())

        plan, err = parse_or_repair(out, TerminalPlanResponse)
        if plan is None:
            logger.warning("_ai_plan_commands parse failed: %s, output: %.200s", err, out)
            # Fallback: keep backward-compat with legacy JSON extraction so that
            # minor schema deviations do not lose the entire plan.
            try:
                return self._extract_json_object(out)
            except Exception:
                return {
                    "mode": "answer",
                    "execution_mode": execution_mode if execution_mode != "auto" else "step",
                    "assistant_text": ("Не удалось разобрать ответ модели. Попробуйте переформулировать запрос."),
                    "commands": [],
                }
        payload = plan.model_dump()
        payload["commands"] = [
            {
                "cmd": c["cmd"],
                "why": c.get("why", ""),
                # F2-8: preserve exec_mode hint if planner supplied one.
                "exec_mode": c.get("exec_mode", "pty"),
            }
            for c in payload.get("commands", [])
        ]
        return payload

    @staticmethod
    def _compute_report_status(done_items: list[dict[str, Any]]) -> str:
        # F2-3: forwarder — canonical impl in servers.services.terminal_ai.reporter
        from servers.services.terminal_ai import compute_report_status

        return compute_report_status(done_items)

    @staticmethod
    def _build_fallback_report(done_items: list[dict[str, Any]]) -> str:
        # F2-3: forwarder — canonical impl in servers.services.terminal_ai.reporter
        from servers.services.terminal_ai import build_fallback_report

        return build_fallback_report(done_items)

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

        Untrusted output/user_message is sanitised by
        :func:`servers.services.terminal_ai.prompts.build_report_prompt`
        before embedding into the prompt (F1-1 / F1-2).
        """
        from app.core.llm import LLMProvider
        from servers.services.terminal_ai import build_report_prompt

        prompt = build_report_prompt(
            user_message=user_message,
            commands_with_output=commands_with_output or [],
        )

        llm = LLMProvider()
        out = ""
        # A4: run report — short narrative summary, route to cheap bucket.
        async with _TERMINAL_AI_LLM_SEMAPHORE:
            async for chunk in llm.stream_chat(prompt, model="auto", purpose="terminal_report"):
                out += chunk
                if len(out) > 12000:
                    break
        return (out or "").strip()

    @staticmethod
    def _sanitize_memory_line(text: str) -> str:
        # F2-3: forwarder — canonical impl in servers.services.terminal_ai.memory
        from servers.services.terminal_ai import sanitize_memory_line

        return sanitize_memory_line(text)

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
                memory_obj = await self._ai_extract_server_memory(
                    user_message=user_message,
                    commands_with_output=commands_with_output,
                    report=report,
                )
                summary = str(memory_obj.get("summary") or "").strip()
                facts = memory_obj.get("facts") or []
                issues = memory_obj.get("issues") or []
                if summary or facts or issues:
                    await self._save_ai_server_profile(
                        user_id=user_id,
                        server_id=server_id,
                        summary=summary,
                        facts=facts,
                        issues=issues,
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
        from app.core.llm import LLMProvider
        from servers.services.terminal_ai import (
            MemoryExtraction,
            build_memory_extraction_prompt,
            parse_or_repair,
        )

        prompt = build_memory_extraction_prompt(
            user_message=user_message,
            commands_with_output=commands_with_output or [],
            report=report,
        )

        llm = LLMProvider()
        out = ""
        async with _TERMINAL_AI_LLM_SEMAPHORE:
            async for chunk in llm.stream_chat(prompt, model="auto", purpose="memory_extraction"):
                out += chunk
                if len(out) > 7000:
                    break

        extraction, err = parse_or_repair(out, MemoryExtraction)
        if extraction is None:
            logger.warning("_ai_extract_server_memory parse failed: %s, output: %.200s", err, out)
            return {"summary": "", "facts": [], "issues": []}

        def _clean_list(items: list[str], limit: int) -> list[str]:
            seen: set[str] = set()
            cleaned: list[str] = []
            for it in items or []:
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

        return {
            "summary": self._sanitize_memory_line(extraction.summary),
            "facts": _clean_list(extraction.facts, 8),
            "issues": _clean_list(extraction.issues, 4),
        }

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
        # F2-6: thin forwarder to the CommandPolicy service. Kept for
        # backward compatibility with any call sites that still reference
        # this method directly; new code should call ``decide_command_policy``.
        from servers.services.terminal_ai import decide_command_policy

        verdict = decide_command_policy(
            cmd,
            forbidden_patterns=forbidden_patterns,
            allowlist_patterns=allowlist_patterns,
            chat_mode="agent",  # ask_mode handled at plan-item layer
            confirm_dangerous_commands=confirm_dangerous_commands,
        )
        return verdict.reason

    @staticmethod
    def _matches_patterns(cmd: str, patterns: list[str]) -> bool:
        # F2-6: forwarder — canonical impl in services.terminal_ai.policy
        from servers.services.terminal_ai import match_patterns

        return match_patterns(cmd, patterns)

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

        # Nova: tear down any cached extra-target connections so we
        # don't leak SSH sessions when the user closes the terminal.
        for name, conn in list(getattr(self, "_agent_extra_conns", {}).items()):
            try:
                conn.close()
                await asyncio.wait_for(conn.wait_closed(), timeout=5)
            except Exception as exc:  # noqa: BLE001
                logger.debug("agent extra conn %s close failed: %s", name, exc)
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
                    with contextlib.suppress(Exception):
                        markers.append((int(m.group(1)), int(m.group(2))))
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

    def _append_manual_output(self, text: str):
        if not text:
            return
        if getattr(self, "_manual_active_cmd_id", None) is None:
            return
        clean = self._strip_ansi_and_controls(text)
        if not clean:
            return
        self._manual_active_output = (self._manual_active_output or "") + clean
        if len(self._manual_active_output) > 12000:
            self._manual_active_output = self._manual_active_output[-12000:]

    async def _finalize_manual_terminal_command(self, cmd_id: int, exit_code: int) -> None:
        pending = list(getattr(self, "_manual_pending_commands", []) or [])
        if not pending:
            return

        item = next((entry for entry in pending if int(entry.get("id") or 0) == int(cmd_id)), None)
        if item is None:
            return

        raw_output = (
            self._manual_active_output if int(getattr(self, "_manual_active_cmd_id", 0) or 0) == int(cmd_id) else ""
        )
        clean_output = self._normalize_manual_command_output(str(item.get("command") or ""), raw_output)
        await database_sync_to_async(self._persist_manual_terminal_command_result, thread_sensitive=True)(
            user_id=int(item.get("user_id") or 0),
            server_id=int(item.get("server_id") or 0),
            session_id=str(item.get("session_id") or ""),
            command=str(item.get("command") or ""),
            output=clean_output,
            exit_code=int(exit_code),
            cwd=str(item.get("cwd") or ""),
        )
        self._append_nova_recent_activity(
            command=str(item.get("command") or ""),
            cwd=str(item.get("cwd") or ""),
            exit_code=int(exit_code),
            source="live_session",
        )
        self._nova_session_context = apply_successful_command_context(
            getattr(self, "_nova_session_context", {}) or dict(item.get("context_before") or {}),
            command=str(item.get("command") or ""),
            exit_code=int(exit_code),
        )

        self._manual_pending_commands = [entry for entry in pending if int(entry.get("id") or 0) != int(cmd_id)]
        if int(getattr(self, "_manual_active_cmd_id", 0) or 0) == int(cmd_id):
            self._manual_active_cmd_id = None
            self._manual_active_output = ""
        if self._manual_active_cmd_id is None and self._manual_pending_commands:
            self._manual_active_cmd_id = int(self._manual_pending_commands[0].get("id") or 0) or None
            self._manual_active_output = ""

    @staticmethod
    def _normalize_manual_command_output(command: str, output: str) -> str:
        clean = SSHTerminalConsumer._strip_ansi_and_controls(output or "").replace("\r", "")
        lines = clean.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        if lines:
            first = lines[0].strip()
            if first == command.strip():
                lines.pop(0)
        normalized = "\n".join(lines).strip()
        return normalized[-12000:]

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
        from app.agent_kernel.memory.redaction import redact_text
        from servers.models import ServerCommandHistory

        # B3: redact secrets from output before persisting so that tokens,
        # passwords, connection strings etc. are never stored verbatim in
        # ServerCommandHistory (and downstream memory extraction).
        safe_output = redact_text(output_snippet or "").text

        ServerCommandHistory.objects.create(
            server_id=server_id,
            user_id=user_id,
            actor_kind=ServerCommandHistory.ACTOR_AGENT,
            source_kind=ServerCommandHistory.SOURCE_AGENT,
            command=command,
            output=safe_output,
            exit_code=exit_code,
        )
