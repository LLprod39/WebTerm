from __future__ import annotations

import contextlib

import httpx  # noqa: F401  (re-export: tests patch servers.report_delivery.httpx.AsyncClient)
from asgiref.sync import sync_to_async

from core_ui.services.notification_config import load_notification_config
from core_ui.services.user_notifications import resolve_user_telegram_chat_id
from servers.agents.agent_inputs import format_telegram_report_message, normalize_report_delivery
from servers.run_events import record_run_event_async
from telegram_hub.client import TelegramAPIError, TelegramClient, redacted_chat_id


def _redacted_chat_id(chat_id: str) -> str:
    return redacted_chat_id(chat_id)


def _refresh_report_payload(run_id: int) -> None:
    from servers.agents.agent_run_report import refresh_agent_run_report_payload
    from servers.models import AgentRun

    run = AgentRun.objects.select_related("agent", "server").get(id=run_id)
    refresh_agent_run_report_payload(run)


async def _record_delivery_event(run_id: int, event_type: str, payload: dict) -> None:
    await record_run_event_async(run_id, event_type, payload)
    with contextlib.suppress(Exception):
        await sync_to_async(_refresh_report_payload, thread_sensitive=True)(run_id)


def _owner_user(run):
    user = getattr(run, "user", None)
    if user is not None:
        return user
    agent = getattr(run, "agent", None)
    return getattr(agent, "user", None) if agent is not None else None


def resolve_telegram_chat_id(run, telegram: dict, cfg: dict) -> str:
    agent_chat = str(telegram.get("chat_id") or "").strip()
    if agent_chat:
        return agent_chat
    user_chat = resolve_user_telegram_chat_id(_owner_user(run))
    if user_chat:
        return user_chat
    return str(cfg.get("telegram_chat_id") or "").strip()


async def deliver_agent_report_async(run, *, attempt_id: str = "") -> None:
    agent = getattr(run, "agent", None)
    delivery = normalize_report_delivery(getattr(agent, "report_delivery", {}) if agent else {})
    telegram = delivery.get("telegram") or {}
    if not telegram.get("enabled"):
        return

    cfg = load_notification_config()
    bot_token = str(cfg.get("telegram_bot_token") or "").strip()
    chat_id = await sync_to_async(resolve_telegram_chat_id, thread_sensitive=True)(run, telegram, cfg)
    if not bot_token:
        await _record_delivery_event(
            run.id,
            "agent_report_delivery_skipped",
            {
                "channel": "telegram",
                "reason": "telegram_bot_missing",
                "message": "Telegram bot token is not configured.",
                "attempt_id": str(attempt_id or "")[:80],
            },
        )
        return
    if not chat_id:
        await _record_delivery_event(
            run.id,
            "agent_report_delivery_skipped",
            {
                "channel": "telegram",
                "reason": "telegram_chat_missing",
                "message": "Telegram chat id is not configured for this user.",
                "attempt_id": str(attempt_id or "")[:80],
            },
        )
        return

    message = format_telegram_report_message(
        run,
        site_url=str(cfg.get("site_url") or "").strip(),
        include_link=bool(telegram.get("include_link", True)),
    )
    try:
        client = TelegramClient(bot_token, timeout=15)
        await client.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        await _record_delivery_event(
            run.id,
            "agent_report_delivery_sent",
            {
                "channel": "telegram",
                "chat_id": _redacted_chat_id(chat_id),
                "attempt_id": str(attempt_id or "")[:80],
            },
        )
    except TelegramAPIError as exc:
        payload = {
            "channel": "telegram",
            "chat_id": _redacted_chat_id(chat_id),
            "body": str(exc.payload or str(exc))[:300],
            "attempt_id": str(attempt_id or "")[:80],
        }
        if exc.status_code is not None:
            payload["status_code"] = int(exc.status_code)
        else:
            payload["error"] = str(exc)
        await _record_delivery_event(run.id, "agent_report_delivery_failed", payload)
    except Exception as exc:
        await _record_delivery_event(
            run.id,
            "agent_report_delivery_failed",
            {
                "channel": "telegram",
                "chat_id": _redacted_chat_id(chat_id),
                "error": str(exc),
                "attempt_id": str(attempt_id or "")[:80],
            },
        )
