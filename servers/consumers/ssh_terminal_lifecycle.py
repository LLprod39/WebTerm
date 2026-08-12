"""Connection setup, dispatch, and heartbeat behavior."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from typing import Any

from channels.db import database_sync_to_async
from django.conf import settings
from loguru import logger

from servers.consumers.ssh_terminal_constants import (
    _WEUAI_MARKER_PREFIX,
)
from servers.models import Server
from servers.secret_utils import has_saved_server_secret
from servers.services import terminal_input, terminal_nova_context
from servers.services.terminal_ai import preferences as ai_preferences

_TermSize = terminal_input.TerminalSize


class TerminalLifecycleOperations:
    _default_ai_settings = staticmethod(ai_preferences.default_ai_settings)
    _parse_bool = staticmethod(ai_preferences.parse_bool)
    _normalize_pattern_list = staticmethod(ai_preferences.normalize_pattern_list)
    _normalize_int_list = staticmethod(ai_preferences.normalize_int_list)
    _normalize_ai_settings = staticmethod(ai_preferences.normalize_ai_settings)
    _clone_ai_settings = staticmethod(ai_preferences.clone_ai_settings)
    _is_auto_report_enabled = staticmethod(ai_preferences.is_auto_report_enabled)
    _normalize_ai_chat_mode = staticmethod(ai_preferences.normalize_ai_chat_mode)

    async def connect(self):
        self._transport_state.reset_for_connect()
        self._manual_state.reset()
        self._ai_state.run = self._TerminalAiRunControllerCls()
        self._ai_state.session = self._TerminalAiSessionCls()
        self._ai_state.reset_connection_state()
        self._ai_state.settings = self._default_ai_settings()

        user = self.scope.get("user")

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
        self._automation_allowed = await self._user_can_automation(self._user_id)

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

        from servers.services.server_ownership import server_access_group_name

        self._transport_state.access_group_name = server_access_group_name(self.server.id)
        await self.channel_layer.group_add(self._transport_state.access_group_name, self.channel_name)

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
        memory_enabled_now = bool((self._ai_state.settings or {}).get("memory_enabled", True))
        if memory_enabled_now:
            try:
                from servers.services.terminal_ai import load_recent as _load_history

                restored = await _load_history(
                    user_id=self._user_id,
                    server_id=self.server.id,
                    limit=40,
                )
                if restored:
                    self._ai_state.history = list(restored)
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
                "restored_history_count": len(self._ai_state.history or []),
            }
        )

    async def disconnect(self, code):
        access_group_name = self._transport_state.access_group_name
        if access_group_name:
            with contextlib.suppress(Exception):
                await self.channel_layer.group_discard(access_group_name, self.channel_name)
            self._transport_state.access_group_name = ""
        await self._cancel_ai()
        await self._drain_ai_background_tasks()
        await self._disconnect_ssh()

    async def server_access_revoked(self, event):
        """Close a live terminal when server ownership or capability changes."""
        if int(event.get("server_id") or 0) != int(getattr(self.server, "id", 0) or 0):
            return
        await self._safe_send_json(
            {
                "type": "error",
                "code": "server_access_revoked",
                "message": "Доступ к серверу был изменён. Терминальная сессия закрыта.",
            }
        )
        await self._disconnect_ssh()
        await self.close(code=4403)

    async def _drain_ai_background_tasks(self) -> None:
        """Cancel and drain any fire-and-forget AI background tasks (F1-7)."""
        tasks = list(self._ai_state.background_tasks)
        for t in tasks:
            if not t.done():
                t.cancel()
        for t in tasks:
            # Best-effort drain — never raise out of disconnect().
            with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError, Exception):
                await asyncio.wait_for(t, timeout=2.0)
        self._ai_state.background_tasks.clear()

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
            self._ai_state.run.resolve_reply(q_id, text)
            return
        if msg_type == "ai_clear_memory":
            await self._handle_ai_clear_memory()
            return
        if msg_type == "ai_explain_output":
            await self._handle_ai_explain_output(content or {})
            return
        if msg_type == "set_editor_intercept":
            self._transport_state.intercept_editors = bool((content or {}).get("enabled", True))
            return
        if msg_type == "ping":
            if self._transport_state.server_connection_id:
                await self._touch_server_connection(self._transport_state.server_connection_id)
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
        token = self._ai_state.session.marker_token.strip()
        if token:
            return f"{_WEUAI_MARKER_PREFIX}{token}_"
        return _WEUAI_MARKER_PREFIX

    def _with_ai_run_id(self, payload: dict[str, Any]) -> dict[str, Any]:
        msg_type = str((payload or {}).get("type") or "")
        if msg_type.startswith("ai_") and self._ai_state.session.run_id:
            out = dict(payload)
            out.setdefault("run_id", self._ai_state.session.run_id)
            return out
        return payload

    async def _reject_with_error(self, *, code: int, message: str, error_code: str) -> None:
        """Accept briefly so the client receives a structured reject reason, then close."""
        try:
            await self.accept()
            await self.send_json({"type": "error", "message": message, "code": error_code})
        except Exception as exc:
            logger.debug("Terminal WebSocket reject payload send failed: {}", exc)
        finally:
            await self.close(code=code)

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
            terminal_nova_context.terminal_session_payload(self._transport_state.nova_session_context)
        )

    @staticmethod
    def _terminal_session_heartbeat_interval() -> int:
        try:
            interval = int(getattr(settings, "SSH_TERMINAL_SESSION_HEARTBEAT_SECONDS", 30) or 30)
        except Exception:
            interval = 30
        return max(interval, 0)

    def _start_connection_heartbeat(self) -> None:
        if not self._transport_state.server_connection_id:
            return
        interval = self._terminal_session_heartbeat_interval()
        if interval <= 0:
            return
        if self._transport_state.heartbeat_task and not self._transport_state.heartbeat_task.done():
            self._transport_state.heartbeat_task.cancel()
        self._transport_state.heartbeat_task = asyncio.create_task(self._run_connection_heartbeat(interval))

    async def _stop_connection_heartbeat(self) -> None:
        task = self._transport_state.heartbeat_task
        self._transport_state.heartbeat_task = None
        if not task or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _run_connection_heartbeat(self, interval: int) -> None:
        try:
            while self._transport_state.server_connection_id:
                await asyncio.sleep(interval)
                if not self._transport_state.server_connection_id or not (
                    self._transport_state.ssh_conn or self._transport_state.ssh_proc
                ):
                    return
                await self._touch_server_connection(self._transport_state.server_connection_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Terminal connection heartbeat failed")

    async def _send_ai_event(self, payload: dict[str, Any]) -> None:
        # B3: redact secrets from AI-generated text before reaching the client.
        from servers.services.egress_redaction import redact_ai_event

        redact_ai_event(payload)
        await self._safe_send_json(self._with_ai_run_id(payload))
