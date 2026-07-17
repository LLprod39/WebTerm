"""WebSocket consumer for Operator chat streaming.

URL: /ws/operator/<chat_id>/

Client → server:
  {"type": "chat.message", "message": "..."}
  {"type": "action.confirm", "action_id": 1}
  {"type": "action.cancel", "action_id": 1}
  {"type": "ping"}

Server → client:
  token | tool_started | tool_result | confirm_required | action_update |
  usage | turn_done | error | pong | turn_started | thinking
"""

from __future__ import annotations

import asyncio

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import User
from loguru import logger

from core_ui.access import feature_allowed_for_user
from core_ui.models import AssistantAction, ChatSession
from core_ui.services.assistant_chat import cancel_action, execute_action, serialize_action
from core_ui.services.operator_loop import handle_operator_message, resume_after_action


class OperatorChatConsumer(AsyncJsonWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._user_id: int | None = None
        self._chat_id: int | None = None
        self._busy = False

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

        await self.accept()
        await self.send_json({"type": "ready", "chat_id": self._chat_id})

    async def receive_json(self, content, **kwargs):
        msg_type = str((content or {}).get("type") or "")
        if msg_type == "ping":
            await self.send_json({"type": "pong"})
            return
        if self._busy:
            await self.send_json({"type": "error", "message": "Turn already in progress"})
            return
        if msg_type == "chat.message":
            await self._handle_message(str((content or {}).get("message") or ""))
        elif msg_type == "action.confirm":
            await self._handle_action(
                int((content or {}).get("action_id") or 0),
                confirm=True,
                typed_confirm=str((content or {}).get("typed_confirm") or "").strip() or None,
            )
        elif msg_type == "action.cancel":
            await self._handle_action(int((content or {}).get("action_id") or 0), confirm=False)
        else:
            await self.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})

    async def _handle_message(self, message: str):
        text = (message or "").strip()
        if not text:
            await self.send_json({"type": "error", "message": "message is required"})
            return
        session = await self._get_session()
        user = await self._get_user()
        if session is None or user is None:
            await self.send_json({"type": "error", "message": "Session not found"})
            return
        self._busy = True
        try:

            async def on_event(event: dict):
                await self.send_json(event)

            # Hard wall so a hung Ollama call cannot pin the socket forever
            result = await asyncio.wait_for(
                handle_operator_message(session, user, text, on_event=on_event),
                timeout=180,
            )
            await self.send_json(
                {
                    "type": "turn_complete",
                    "status": result.status,
                    "assistant_message_id": result.assistant_message.pk if result.assistant_message else None,
                    "user_message_id": result.user_message.pk if result.user_message else None,
                    "actions": [serialize_action(a) for a in result.actions if a],
                }
            )
        except asyncio.TimeoutError:
            await self.send_json(
                {
                    "type": "error",
                    "message": "Оператор завис на ответе модели (таймаут 180с). Попробуй ещё раз короче.",
                }
            )
        except ValueError as exc:
            await self.send_json({"type": "error", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.exception("operator ws message failed: {}", exc)
            await self.send_json({"type": "error", "message": str(exc) or "Operator turn failed"})
        finally:
            self._busy = False

    async def _handle_action(self, action_id: int, *, confirm: bool, typed_confirm: str | None = None):
        if action_id <= 0:
            await self.send_json({"type": "error", "message": "action_id is required"})
            return
        user = await self._get_user()
        action = await self._get_action(action_id)
        if user is None or action is None:
            await self.send_json({"type": "error", "message": "Action not found"})
            return
        self._busy = True
        try:
            if confirm:
                action = await database_sync_to_async(execute_action)(
                    action, confirmed=True, typed_confirm=typed_confirm
                )
            else:
                action = await database_sync_to_async(cancel_action)(action)
            await self.send_json({"type": "action_update", "action": serialize_action(action)})

            if confirm and action.status == action.STATUS_REQUIRES_CONFIRMATION and action.error:
                await self.send_json({"type": "error", "message": action.error})
                return

            async def on_event(event: dict):
                await self.send_json(event)

            result = await resume_after_action(
                action=action,
                on_event=on_event,
                cancelled=not confirm,
            )
            if result is not None:
                await self.send_json(
                    {
                        "type": "turn_complete",
                        "status": result.status,
                        "assistant_message_id": result.assistant_message.pk if result.assistant_message else None,
                        "actions": [serialize_action(a) for a in result.actions if a],
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("operator ws action failed: {}", exc)
            await self.send_json({"type": "error", "message": str(exc) or "Action failed"})
        finally:
            self._busy = False

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
