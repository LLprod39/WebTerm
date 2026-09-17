"""Shared Telegram Bot API client used by hub, notifications, and delivery."""

from __future__ import annotations

import asyncio
import contextlib
import html
from typing import Any

import httpx

TELEGRAM_MAX_MESSAGE_CHARS = 4096
TELEGRAM_SAFE_CHUNK = 4000


class TelegramAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class TelegramClient:
    def __init__(self, bot_token: str, *, timeout: float = 30.0):
        self.bot_token = str(bot_token or "").strip()
        if not self.bot_token:
            raise ValueError("Telegram bot token is required")
        self.timeout = timeout
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    async def _call(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        *,
        poll_timeout: float | None = None,
    ) -> dict[str, Any]:
        timeout = self.timeout
        if poll_timeout is not None:
            timeout = float(poll_timeout) + 10.0
        retries = 0
        while True:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(f"{self.base_url}/{method}", json=payload or {})
            if resp.status_code == 429 and retries < 3:
                retries += 1
                retry_after = 1.0
                with contextlib.suppress(Exception):
                    data = resp.json()
                    parameters = data.get("parameters") or {}
                    retry_after = float(parameters.get("retry_after") or 1)
                await asyncio.sleep(max(0.5, min(retry_after, 30.0)))
                continue
            if resp.status_code == 401:
                raise TelegramAPIError("Telegram Unauthorized", status_code=401, payload=resp.text[:300])
            if resp.status_code != 200:
                raise TelegramAPIError(
                    f"Telegram API error {resp.status_code}: {str(resp.text or '')[:200]}",
                    status_code=resp.status_code,
                    payload=str(resp.text or "")[:300],
                )
            data: Any = None
            with contextlib.suppress(Exception):
                data = resp.json()
            if not isinstance(data, dict):
                # Non-JSON 200 (e.g. test doubles / proxies): treat as success without payload.
                return {}
            if data.get("ok") is False:
                description = str(data.get("description") or data)
                raise TelegramAPIError(description, status_code=resp.status_code, payload=data)
            result = data.get("result")
            return result if isinstance(result, dict) else {"result": result}

    async def get_me(self) -> dict[str, Any]:
        return await self._call("getMe")

    async def get_updates(
        self,
        *,
        offset: int = 0,
        timeout: int = 25,
        allowed_updates: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        payload = {
            "offset": int(offset),
            "timeout": max(5, min(30, int(timeout))),
            "allowed_updates": allowed_updates or ["message", "callback_query"],
        }
        timeout_s = float(payload["timeout"])
        async with httpx.AsyncClient(timeout=timeout_s + 10) as client:
            resp = await client.post(f"{self.base_url}/getUpdates", json=payload)
        if resp.status_code == 401:
            raise TelegramAPIError("Telegram Unauthorized", status_code=401, payload=resp.text[:300])
        if resp.status_code != 200:
            raise TelegramAPIError(
                f"Telegram API error {resp.status_code}: {str(resp.text or '')[:200]}",
                status_code=resp.status_code,
                payload=str(resp.text or "")[:300],
            )
        data = resp.json()
        if not isinstance(data, dict) or not data.get("ok"):
            raise TelegramAPIError(
                str((data or {}).get("description") if isinstance(data, dict) else data), payload=data
            )
        result = data.get("result") or []
        return [item for item in result if isinstance(item, dict)]

    async def send_message(
        self,
        *,
        chat_id: str | int,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
        disable_web_page_preview: bool = True,
        reply_to_message_id: int | None = None,
    ) -> dict[str, Any]:
        message = str(text or "")
        chunks = [message[i : i + TELEGRAM_SAFE_CHUNK] for i in range(0, len(message), TELEGRAM_SAFE_CHUNK)] or [""]
        sent: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks):
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": disable_web_page_preview,
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if reply_to_message_id and index == 0:
                payload["reply_to_message_id"] = int(reply_to_message_id)
            if reply_markup and index == len(chunks) - 1:
                payload["reply_markup"] = reply_markup
            result = await self._call("sendMessage", payload)
            sent.append(result)
        last = sent[-1] if sent else {}
        message_ids = []
        for item in sent:
            mid = item.get("message_id")
            if isinstance(mid, int):
                message_ids.append(mid)
        return {
            "status": "completed",
            "message_ids": message_ids,
            "last_message_id": message_ids[-1] if message_ids else None,
            "result": last,
            "chunks_sent": len(sent),
        }

    async def send_chat_action(self, *, chat_id: str | int, action: str = "typing") -> None:
        with contextlib.suppress(Exception):
            await self._call("sendChatAction", {"chat_id": chat_id, "action": action})

    async def delete_message(self, *, chat_id: str | int, message_id: int) -> None:
        with contextlib.suppress(Exception):
            await self._call("deleteMessage", {"chat_id": chat_id, "message_id": int(message_id)})

    async def edit_message_text(
        self,
        *,
        chat_id: str | int,
        message_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
        disable_web_page_preview: bool = True,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": int(message_id),
            "text": str(text or "")[:TELEGRAM_MAX_MESSAGE_CHARS],
            "disable_web_page_preview": disable_web_page_preview,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return await self._call("editMessageText", payload)

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str = "",
        *,
        show_alert: bool = False,
    ) -> None:
        payload: dict[str, Any] = {
            "callback_query_id": str(callback_query_id),
            "text": str(text or "")[:200],
            "show_alert": bool(show_alert),
        }
        await self._call("answerCallbackQuery", payload)

    async def edit_message_reply_markup(
        self,
        *,
        chat_id: str | int,
        message_id: int,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": int(message_id),
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        else:
            payload["reply_markup"] = {"inline_keyboard": []}
        with contextlib.suppress(Exception):
            await self._call("editMessageReplyMarkup", payload)

    async def set_my_commands(self, commands: list[dict[str, str]]) -> None:
        await self._call("setMyCommands", {"commands": commands})


def escape_html(value: str) -> str:
    return html.escape(str(value or ""), quote=False)


def mask_bot_token(token: str) -> str:
    value = str(token or "").strip()
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return "••••" + value[-4:]


def redacted_chat_id(chat_id: str | int) -> str:
    value = str(chat_id or "").strip()
    if not value:
        return ""
    if len(value) <= 4:
        return "***"
    return f"***{value[-4:]}"
