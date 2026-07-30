from __future__ import annotations

import contextlib

import httpx
from asgiref.sync import sync_to_async

from core_ui.services.notification_config import load_notification_config
from servers.agents.agent_inputs import format_telegram_report_message, normalize_report_delivery
from servers.run_events import record_run_event_async


def _redacted_chat_id(chat_id: str) -> str:
    value = str(chat_id or "").strip()
    if not value:
        return ""
    if len(value) <= 4:
        return "***"
    return f"***{value[-4:]}"


def _refresh_report_payload(run_id: int) -> None:
    from servers.agents.agent_run_report import refresh_agent_run_report_payload
    from servers.models import AgentRun

    run = AgentRun.objects.select_related("agent", "server").get(id=run_id)
    refresh_agent_run_report_payload(run)


async def _record_delivery_event(run_id: int, event_type: str, payload: dict) -> None:
    await record_run_event_async(run_id, event_type, payload)
    with contextlib.suppress(Exception):
        await sync_to_async(_refresh_report_payload, thread_sensitive=True)(run_id)


async def deliver_agent_report_async(run) -> None:
    agent = getattr(run, "agent", None)
    delivery = normalize_report_delivery(getattr(agent, "report_delivery", {}) if agent else {})
    telegram = delivery.get("telegram") or {}
    if not telegram.get("enabled"):
        return

    cfg = load_notification_config()
    bot_token = str(cfg.get("telegram_bot_token") or "").strip()
    chat_id = str(telegram.get("chat_id") or cfg.get("telegram_chat_id") or "").strip()
    if not bot_token or not chat_id:
        await _record_delivery_event(
            run.id,
            "agent_report_delivery_skipped",
            {
                "channel": "telegram",
                "reason": "telegram_not_configured",
                "message": "Telegram bot token or chat id is not configured.",
            },
        )
        return

    message = format_telegram_report_message(
        run,
        site_url=str(cfg.get("site_url") or "").strip(),
        include_link=bool(telegram.get("include_link", True)),
    )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
        if response.status_code == 200:
            await _record_delivery_event(
                run.id,
                "agent_report_delivery_sent",
                {"channel": "telegram", "chat_id": _redacted_chat_id(chat_id)},
            )
            return
        await _record_delivery_event(
            run.id,
            "agent_report_delivery_failed",
            {
                "channel": "telegram",
                "chat_id": _redacted_chat_id(chat_id),
                "status_code": response.status_code,
                "body": response.text[:300],
            },
        )
    except Exception as exc:
        await _record_delivery_event(
            run.id,
            "agent_report_delivery_failed",
            {"channel": "telegram", "chat_id": _redacted_chat_id(chat_id), "error": str(exc)},
        )
