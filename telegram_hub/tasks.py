from __future__ import annotations

import asyncio

from celery import shared_task
from loguru import logger


@shared_task(name="telegram_hub.tasks.telegram_assistant_turn")
def telegram_assistant_turn(link_id: int, text: str, tg_message_id: int | None = None) -> None:
    from telegram_hub.assistant_bridge import run_assistant_turn

    try:
        asyncio.run(
            run_assistant_turn(
                link_id=int(link_id),
                text=str(text or ""),
                tg_message_id=int(tg_message_id) if tg_message_id else None,
            )
        )
    except Exception as exc:
        logger.exception("telegram_assistant_turn failed link_id={}: {}", link_id, exc)


@shared_task(name="telegram_hub.tasks.telegram_deliver_assistant_message")
def telegram_deliver_assistant_message(
    session_id: int,
    assistant_message_id: int | None = None,
    action_ids: list[int] | None = None,
) -> None:
    """Push a completed Operator turn (e.g. async resume) to the linked Telegram chat."""
    from telegram_hub.assistant_bridge import deliver_assistant_message_to_telegram

    try:
        asyncio.run(
            deliver_assistant_message_to_telegram(
                session_id=int(session_id),
                assistant_message_id=int(assistant_message_id) if assistant_message_id else None,
                action_ids=[int(item) for item in (action_ids or [])],
            )
        )
    except Exception as exc:
        logger.exception(
            "telegram_deliver_assistant_message failed session_id={} message_id={}: {}",
            session_id,
            assistant_message_id,
            exc,
        )
