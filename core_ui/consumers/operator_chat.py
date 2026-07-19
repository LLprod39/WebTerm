"""WebSocket consumer for Operator chat streaming.

URL: /ws/operator/<chat_id>/

Client → server:
  {"type": "chat.message", "message": "...", "thinking": true|false|"high"|...}
  {"type": "turn.stop"}
  {"type": "action.confirm", "action_id": 1}
  {"type": "action.cancel", "action_id": 1}
  {"type": "ping"}

Server → client:
  ready | turn_snapshot | token | tool_* | thinking* | confirm_required |
  action_update | usage | turn_done | turn_complete | error | pong

Turns run as background tasks and outlive this socket. Events are fan-out via
channel group so leaving/reopening the page resumes the live dialog.
"""

from __future__ import annotations

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import User
from loguru import logger

from core_ui.access import feature_allowed_for_user
from core_ui.models import AssistantAction, ChatSession
from core_ui.services.operator_turn_runtime import (
    broadcast_operator_event,
    get_active_turn_snapshot,
    is_chat_busy,
    operator_group_name,
    operator_health,
    start_action_turn,
    start_message_turn,
    stop_active_turn,
)


class OperatorChatConsumer(AsyncJsonWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._user_id: int | None = None
        self._chat_id: int | None = None
        self._group: str | None = None

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close()
            return
        self._user_id = user.id
        try:
            self._chat_id = int(self.scope["url_route"]["kwargs"]["chat_id"])
        except (KeyError, TypeError, ValueError):
            await self.close()
            return

        if not await self._has_feature():
            await self.close()
            return
        session = await self._get_session()
        if session is None:
            await self.close()
            return

        self._group = operator_group_name(self._chat_id)
        await self.channel_layer.group_add(self._group, self.channel_name)
        await self.accept()
        health = await operator_health()
        await self.send_json(
            {
                "type": "ready",
                "chat_id": self._chat_id,
                "busy": is_chat_busy(self._chat_id),
                "health": health,
            }
        )

        # Reconnect: restore in-flight / parked turn UI without restarting work
        snapshot = await get_active_turn_snapshot(self._chat_id, self._user_id)
        if snapshot:
            await self.send_json(snapshot)

    async def disconnect(self, code):
        if self._group and getattr(self, "channel_layer", None) is not None:
            try:
                await self.channel_layer.group_discard(self._group, self.channel_name)
            except Exception:  # noqa: BLE001
                logger.debug("operator group_discard failed chat_id={}", self._chat_id)
        # Intentionally do NOT cancel background turns — they keep running.

    async def operator_event(self, message):
        """Channel-layer handler: fan-out operator loop events to this socket."""
        event = message.get("event")
        if isinstance(event, dict):
            await self.send_json(event)

    async def receive_json(self, content, **kwargs):
        msg_type = str((content or {}).get("type") or "")
        if msg_type == "ping":
            await self.send_json({"type": "pong"})
            return
        if msg_type == "chat.message":
            await self._handle_message(content or {})
        elif msg_type == "turn.stop":
            await self._handle_stop()
        elif msg_type == "action.confirm":
            await self._handle_action(
                int((content or {}).get("action_id") or 0),
                confirm=True,
                typed_confirm=str((content or {}).get("typed_confirm") or "").strip() or None,
                thinking=(content or {}).get("thinking"),
            )
        elif msg_type == "action.cancel":
            await self._handle_action(
                int((content or {}).get("action_id") or 0),
                confirm=False,
                thinking=(content or {}).get("thinking"),
            )
        else:
            await self.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})

    async def _handle_message(self, content: dict):
        text = str(content.get("message") or "").strip()
        if not text:
            await self.send_json({"type": "error", "message": "message is required"})
            return
        if self._chat_id is None:
            await self.send_json({"type": "error", "message": "Session not found"})
            return
        if is_chat_busy(self._chat_id):
            await self.send_json({"type": "error", "message": "Turn already in progress"})
            return

        session = await self._get_session()
        user = await self._get_user()
        if session is None or user is None:
            await self.send_json({"type": "error", "message": "Session not found"})
            return

        # Optimistic ack so UI can show thinking before first model token
        await broadcast_operator_event(self._chat_id, {"type": "turn_started", "chat_id": self._chat_id})

        started = start_message_turn(
            chat_id=self._chat_id,
            session=session,
            user=user,
            message=text,
            thinking=content.get("thinking"),
        )
        if not started:
            await self.send_json({"type": "error", "message": "Turn already in progress"})

    async def _handle_stop(self):
        if self._chat_id is None:
            await self.send_json({"type": "error", "message": "Session not found"})
            return
        stopped = await stop_active_turn(self._chat_id, self._user_id)
        if not stopped:
            # Nothing running — still acknowledge so the client can unstick its UI
            await self.send_json({"type": "turn_done", "status": "stopped", "chat_id": self._chat_id})

    async def _handle_action(
        self,
        action_id: int,
        *,
        confirm: bool,
        typed_confirm: str | None = None,
        thinking=None,
    ):
        if action_id <= 0:
            await self.send_json({"type": "error", "message": "action_id is required"})
            return
        if self._chat_id is None:
            await self.send_json({"type": "error", "message": "Session not found"})
            return
        if is_chat_busy(self._chat_id):
            await self.send_json({"type": "error", "message": "Turn already in progress"})
            return

        user = await self._get_user()
        action = await self._get_action(action_id)
        if user is None or action is None:
            await self.send_json({"type": "error", "message": "Action not found"})
            return

        await broadcast_operator_event(
            self._chat_id,
            {"type": "turn_started", "chat_id": self._chat_id, "phase": "action"},
        )
        started = start_action_turn(
            chat_id=self._chat_id,
            action=action,
            confirm=confirm,
            typed_confirm=typed_confirm,
            thinking=thinking,
        )
        if not started:
            await self.send_json({"type": "error", "message": "Turn already in progress"})

    @database_sync_to_async
    def _has_feature(self) -> bool:
        user = User.objects.filter(id=self._user_id).first()
        return bool(user and feature_allowed_for_user(user, "orchestrator"))

    @database_sync_to_async
    def _get_user(self):
        return User.objects.filter(id=self._user_id).first()

    @database_sync_to_async
    def _get_session(self):
        return ChatSession.objects.filter(user_id=self._user_id, pk=self._chat_id).first()

    @database_sync_to_async
    def _get_action(self, action_id: int):
        return (
            AssistantAction.objects.select_related("session", "user", "message")
            .filter(pk=action_id, user_id=self._user_id, session_id=self._chat_id)
            .first()
        )
