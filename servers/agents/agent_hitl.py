"""Human-in-the-loop helpers for agent ask_user / gate approval waits."""

from __future__ import annotations

import contextlib
import hashlib
from typing import Any

from asgiref.sync import sync_to_async
from django.core.cache import cache
from loguru import logger

from core_ui.services.notification_config import load_notification_config
from servers.agents.agent_inputs import normalize_report_delivery
from servers.models import AgentRun
from servers.report_delivery import resolve_telegram_chat_id
from servers.run_events import record_run_event_async
from telegram_hub.client import TelegramAPIError, TelegramClient, redacted_chat_id

_TG_REPLY_CACHE_PREFIX = "agent_hitl_tg_reply"
_TG_REPLY_TTL_SECONDS = 60 * 60 * 24 * 7  # keep until answered or week elapses


def _token_digest(bot_token: str) -> str:
    return hashlib.sha256(str(bot_token or "").encode("utf-8")).hexdigest()[:32]


def _tg_reply_cache_key(*, bot_token: str, chat_id: str, message_id: int) -> str:
    return f"{_TG_REPLY_CACHE_PREFIX}:{_token_digest(bot_token)}:{chat_id}:{int(message_id)}"


def mark_run_waiting(run_id: int, question: str) -> None:
    """Persist STATUS_WAITING + pending_question so Web/Telegram can answer."""
    from servers.agents.agent_run_report import refresh_agent_run_report_payload

    run = AgentRun.objects.select_related("agent", "server", "user").filter(pk=run_id).first()
    if run is None:
        return
    text = str(question or "").strip()
    if not text:
        return
    # Do not clobber terminal / stopped runs.
    if run.status in {
        AgentRun.STATUS_COMPLETED,
        AgentRun.STATUS_FAILED,
        AgentRun.STATUS_STOPPED,
    }:
        return
    run.status = AgentRun.STATUS_WAITING
    run.pending_question = text[:8000]
    run.save(update_fields=["status", "pending_question"])
    with contextlib.suppress(Exception):
        refresh_agent_run_report_payload(run)


def clear_run_waiting(run_id: int, *, resume: bool = True) -> None:
    from servers.agents.agent_run_report import refresh_agent_run_report_payload

    run = AgentRun.objects.select_related("agent", "server").filter(pk=run_id).first()
    if run is None:
        return
    if run.status != AgentRun.STATUS_WAITING and not run.pending_question:
        return
    fields = ["pending_question"]
    run.pending_question = ""
    if resume and run.status == AgentRun.STATUS_WAITING:
        run.status = AgentRun.STATUS_RUNNING
        fields.append("status")
    run.save(update_fields=fields)
    with contextlib.suppress(Exception):
        refresh_agent_run_report_payload(run)


def format_telegram_question_message(run: AgentRun, question: str, *, site_url: str = "") -> str:
    agent_name = ""
    if run.agent_id and run.agent:
        agent_name = str(run.agent.name or "").strip()
    title = agent_name or f"Агент #{run.agent_id or '—'}"
    lines = [
        f"❓ <b>{_html_escape(title)}</b> ждёт ответа",
        f"Запуск #{run.id}",
        "",
        _html_escape(str(question or "").strip())[:3500],
        "",
        "Ответьте <b>да</b> / <b>нет</b> или текстом — ответом на это сообщение.",
    ]
    base = str(site_url or "").rstrip("/")
    if base:
        lines.append(f'<a href="{base}/agents/run/{run.id}">Открыть в WebTerm</a>')
    return "\n".join(lines)


def _html_escape(value: str) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


async def notify_telegram_agent_question(run_id: int, question: str) -> None:
    """Send ask_user prompt to Telegram when agent report_delivery.telegram is enabled."""
    run = await sync_to_async(
        lambda: AgentRun.objects.select_related("agent", "server", "user").filter(pk=run_id).first(),
        thread_sensitive=True,
    )()
    if run is None:
        return
    agent = getattr(run, "agent", None)
    delivery = normalize_report_delivery(getattr(agent, "report_delivery", {}) if agent else {})
    telegram = delivery.get("telegram") or {}
    if not telegram.get("enabled"):
        return

    cfg = load_notification_config()
    bot_token = str(cfg.get("telegram_bot_token") or "").strip()
    chat_id = await sync_to_async(resolve_telegram_chat_id, thread_sensitive=True)(run, telegram, cfg)
    if not bot_token or not chat_id:
        await record_run_event_async(
            run_id,
            "agent_question_delivery_skipped",
            {
                "channel": "telegram",
                "reason": "telegram_not_configured" if not bot_token else "telegram_chat_missing",
                "message": "Telegram not configured for agent question delivery.",
            },
        )
        return

    text = format_telegram_question_message(
        run,
        question,
        site_url=str(cfg.get("site_url") or "").strip(),
    )
    try:
        client = TelegramClient(bot_token, timeout=15)
        result = await client.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        message_id = 0
        if isinstance(result, dict):
            try:
                message_id = int(
                    result.get("last_message_id")
                    or (result.get("message_ids") or [None])[-1]
                    or (result.get("result") or {}).get("message_id")
                    or result.get("message_id")
                    or 0
                )
            except (TypeError, ValueError, IndexError):
                message_id = 0
        if message_id > 0:
            cache.set(
                _tg_reply_cache_key(bot_token=bot_token, chat_id=str(chat_id), message_id=message_id),
                int(run_id),
                timeout=_TG_REPLY_TTL_SECONDS,
            )
        await record_run_event_async(
            run_id,
            "agent_question_delivery_sent",
            {
                "channel": "telegram",
                "chat_id": redacted_chat_id(chat_id),
                "message_id": message_id or None,
            },
        )
    except TelegramAPIError as exc:
        await record_run_event_async(
            run_id,
            "agent_question_delivery_failed",
            {
                "channel": "telegram",
                "chat_id": redacted_chat_id(chat_id),
                "error": str(exc)[:300],
                "status_code": exc.status_code,
            },
        )
    except Exception as exc:
        logger.debug("Telegram agent question notify failed for run {}: {}", run_id, exc)
        await record_run_event_async(
            run_id,
            "agent_question_delivery_failed",
            {
                "channel": "telegram",
                "chat_id": redacted_chat_id(chat_id),
                "error": str(exc)[:300],
            },
        )


def try_store_agent_telegram_reply(bot_token: str, message: dict[str, Any]) -> bool:
    """If message is a reply to an armed agent question, deliver it to the waiting run."""
    if not isinstance(message, dict):
        return False
    reply_to = message.get("reply_to_message") or {}
    chat = message.get("chat") or {}
    text = str(message.get("text") or "").strip()
    chat_id = str(chat.get("id") or "").strip()
    try:
        prompt_message_id = int(reply_to.get("message_id") or 0)
    except (TypeError, ValueError):
        prompt_message_id = 0
    if not bot_token or not chat_id or prompt_message_id <= 0 or not text:
        return False

    cache_key = _tg_reply_cache_key(bot_token=bot_token, chat_id=chat_id, message_id=prompt_message_id)
    run_id = cache.get(cache_key)
    if run_id is None:
        return False
    try:
        run_id = int(run_id)
    except (TypeError, ValueError):
        cache.delete(cache_key)
        return False

    from servers.agents.agent_service import reply_to_agent_run_for_user

    run = AgentRun.objects.select_related("user", "agent").filter(pk=run_id).first()
    if run is None or run.user_id is None:
        cache.delete(cache_key)
        return False

    result = reply_to_agent_run_for_user(
        run_id=run_id,
        user=run.user,
        answer=text,
        source="telegram",
    )
    if result.get("ok"):
        cache.delete(cache_key)
        return True
    # Stale arm (already answered / not waiting) — drop the key.
    if result.get("status") == 404:
        cache.delete(cache_key)
    return False


async def on_agent_question_event(run_id: int, data: dict[str, Any] | None) -> None:
    """Central hook: persist waiting + optional Telegram notify."""
    question = str((data or {}).get("question") or "").strip()
    if not question:
        return
    await sync_to_async(mark_run_waiting, thread_sensitive=True)(run_id, question)
    with contextlib.suppress(Exception):
        await notify_telegram_agent_question(run_id, question)
