from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from typing import Any

import httpx
from django.utils import timezone

from app.agent_kernel.memory.redaction import sanitize_observation_text
from studio.models import PipelineRun

logger = logging.getLogger(__name__)

_TELEGRAM_UPDATE_OFFSETS: dict[str, int] = {}
_TELEGRAM_UPDATE_LOCKS: dict[str, threading.Lock] = {}
_TELEGRAM_PENDING_CALLBACKS: dict[str, dict[str, Any]] = {}
_TELEGRAM_PENDING_REPLIES: dict[str, list[dict[str, Any]]] = {}


def _telegram_approval_callback_data(decision: str, approval_token: str) -> str:
    return f"approval:{decision}:{approval_token}"


def _parse_telegram_approval_callback_data(value: str) -> dict[str, str] | None:
    raw = str(value or "").strip()
    if not raw.startswith("approval:"):
        return None
    parts = raw.split(":", 2)
    if len(parts) != 3:
        return None
    _, decision, token = parts
    if decision not in {"approved", "rejected"} or not token:
        return None
    return {"decision": decision, "token": token}


def _telegram_reply_key(chat_id: str, reply_to_message_id: int) -> str:
    return f"{chat_id}:{reply_to_message_id}"


def _telegram_update_lock(bot_token: str) -> threading.Lock:
    lock = _TELEGRAM_UPDATE_LOCKS.get(bot_token)
    if lock is None:
        lock = threading.Lock()
        _TELEGRAM_UPDATE_LOCKS[bot_token] = lock
    return lock


def _pop_telegram_reply(chat_id: str, reply_to_message_id: int) -> dict[str, Any] | None:
    key = _telegram_reply_key(chat_id, reply_to_message_id)
    queued = _TELEGRAM_PENDING_REPLIES.get(key) or []
    if not queued:
        return None
    item = queued.pop(0)
    if queued:
        _TELEGRAM_PENDING_REPLIES[key] = queued
    else:
        _TELEGRAM_PENDING_REPLIES.pop(key, None)
    return item


async def _poll_telegram_updates(bot_token: str) -> None:
    if not bot_token:
        return

    lock = _telegram_update_lock(bot_token)
    await asyncio.to_thread(lock.acquire)
    try:
        offset = int(_TELEGRAM_UPDATE_OFFSETS.get(bot_token, 0) or 0)
        base_url = f"https://api.telegram.org/bot{bot_token}"
        max_update_id = offset - 1

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"{base_url}/getUpdates",
                    json={
                        "offset": offset,
                        "timeout": 0,
                        "allowed_updates": ["callback_query", "message"],
                    },
                )
                if response.status_code != 200:
                    logger.warning(
                        "Telegram polling failed for configured bot: %s %s",
                        response.status_code,
                        _redact_telegram_text(response.text, limit=200),
                    )
                    return

                payload = response.json()
                if not payload.get("ok"):
                    logger.warning("Telegram polling returned not-ok payload for configured bot")
                    return

                for update in payload.get("result") or []:
                    try:
                        update_id = int(update.get("update_id"))
                    except (TypeError, ValueError):
                        update_id = None
                    if update_id is not None:
                        max_update_id = max(max_update_id, update_id)

                    callback = update.get("callback_query") or {}
                    parsed = _parse_telegram_approval_callback_data(callback.get("data"))
                    callback_id = str(callback.get("id") or "").strip()
                    if callback_id and parsed:
                        with contextlib.suppress(Exception):
                            await client.post(
                                f"{base_url}/answerCallbackQuery",
                                json={"callback_query_id": callback_id, "text": "Решение получено"},
                            )
                    if parsed:
                        _TELEGRAM_PENDING_CALLBACKS[parsed["token"]] = {
                            "decision": parsed["decision"],
                            "response_text": "через кнопку в Telegram",
                            "callback_query_id": callback_id,
                            "callback_from": ((callback.get("from") or {}) or {}).get("username") or "",
                        }

                    message = update.get("message") or {}
                    if not isinstance(message, dict):
                        continue
                    reply_to = message.get("reply_to_message") or {}
                    chat = message.get("chat") or {}
                    text = str(message.get("text") or "").strip()
                    chat_id = str(chat.get("id") or "").strip()
                    try:
                        reply_to_message_id = int(reply_to.get("message_id"))
                    except (TypeError, ValueError):
                        reply_to_message_id = 0
                    if not chat_id or reply_to_message_id <= 0 or not text:
                        continue
                    key = _telegram_reply_key(chat_id, reply_to_message_id)
                    _TELEGRAM_PENDING_REPLIES.setdefault(key, []).append(
                        {
                            "text": text,
                            "chat_id": chat_id,
                            "message_id": message.get("message_id"),
                            "reply_to_message_id": reply_to_message_id,
                            "from_username": ((message.get("from") or {}) or {}).get("username") or "",
                        }
                    )
        except Exception as exc:
            logger.warning("Telegram polling error for configured bot: %s", exc)
            return
        finally:
            next_offset = max_update_id + 1
            if next_offset > offset:
                _TELEGRAM_UPDATE_OFFSETS[bot_token] = next_offset
    finally:
        lock.release()


async def _poll_telegram_approval_decision(bot_token: str, approval_token: str) -> dict[str, Any] | None:
    if not bot_token or not approval_token:
        return None

    cached = _TELEGRAM_PENDING_CALLBACKS.pop(approval_token, None)
    if cached:
        return cached

    await _poll_telegram_updates(bot_token)
    return _TELEGRAM_PENDING_CALLBACKS.pop(approval_token, None)


async def _poll_telegram_reply_message(bot_token: str, chat_id: str, reply_to_message_id: int) -> dict[str, Any] | None:
    if not bot_token or not chat_id or reply_to_message_id <= 0:
        return None

    cached = _pop_telegram_reply(chat_id, reply_to_message_id)
    if cached:
        return cached

    await _poll_telegram_updates(bot_token)
    return _pop_telegram_reply(chat_id, reply_to_message_id)


def store_telegram_operator_reply(bot_token: str, message: dict[str, Any]) -> bool:
    """Persist a Telegram reply into the matching running pipeline node state."""
    if not isinstance(message, dict):
        return False
    reply_to = message.get("reply_to_message") or {}
    chat = message.get("chat") or {}
    text = str(message.get("text") or "").strip()
    chat_id = str(chat.get("id") or "").strip()
    try:
        reply_to_message_id = int(reply_to.get("message_id"))
    except (TypeError, ValueError):
        reply_to_message_id = 0
    if not chat_id or reply_to_message_id <= 0 or not text:
        return False

    runs = list(
        PipelineRun.objects.filter(status__in=[PipelineRun.STATUS_RUNNING, PipelineRun.STATUS_HIBERNATING])
        .order_by("-created_at")
        .only("id", "node_states")[:100]
    )
    for run in runs:
        node_states = run.node_states if isinstance(run.node_states, dict) else {}
        for node_id, state in node_states.items():
            if not isinstance(state, dict):
                continue
            if state.get("status") not in {"hibernating", "awaiting_operator_reply"}:
                continue
            if str(state.get("telegram_chat_id") or "") != chat_id:
                continue
            try:
                prompt_message_id = int(state.get("telegram_prompt_message_id") or 0)
            except (TypeError, ValueError):
                prompt_message_id = 0
            if prompt_message_id != reply_to_message_id:
                continue
            stored_token = str(state.get("bot_token") or "").strip()
            if stored_token and bot_token and stored_token != bot_token:
                continue
            next_state = dict(state)
            next_state.update(
                {
                    "operator_response": text,
                    "operator_response_message_id": message.get("message_id"),
                    "operator_response_from": ((message.get("from") or {}) or {}).get("username") or "",
                    "operator_response_received_at": timezone.now().isoformat(),
                }
            )
            node_states[str(node_id)] = next_state
            PipelineRun.objects.filter(pk=run.pk).update(node_states=node_states)
            return True
    return False


def _redact_telegram_text(value: Any, *, limit: int | None = None) -> str:
    redacted = sanitize_observation_text(str(value or "")).text
    if limit is not None:
        return redacted[: max(0, int(limit))]
    return redacted
