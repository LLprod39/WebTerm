from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta
from threading import Event

from asgiref.sync import sync_to_async as _s2a
from django.utils import timezone

from .models import PipelineRun
from .pipeline_notifications import (
    _send_telegram_message,
)
from .pipeline_redaction import (
    redact_pipeline_text as _redact_pipeline_text,
)
from .pipeline_redaction import (
    redacted_all_outputs_text as _redacted_all_outputs_text,
)
from .pipeline_redaction import (
    redacted_mapping_context as _redacted_pipeline_context,
)
from .pipeline_run_state import update_node_state as _update_node_state
from .pipeline_runtime import is_runtime_stop_requested
from .pipeline_telegram import (
    _poll_telegram_reply_message,
)


def resolve_telegram_target(
    config: dict | None,
    *,
    token_keys: tuple[str, ...],
    chat_keys: tuple[str, ...],
) -> tuple[str, str]:
    from .pipeline_notifications import _global_tg_defaults

    node_config = config if isinstance(config, dict) else {}
    global_token, global_chat = _global_tg_defaults()

    def _first_non_empty(keys: tuple[str, ...], fallback: str) -> str:
        for key in keys:
            value = str(node_config.get(key) or "").strip()
            if value:
                return value
        return str(fallback or "").strip()

    return (
        _first_non_empty(token_keys, global_token),
        _first_non_empty(chat_keys, global_chat),
    )


async def execute_logic_telegram_input(
    node: dict,
    context: dict,
    node_outputs: dict[str, dict],
    run: PipelineRun,
    stop_event: Event | None = None,
) -> dict:
    """Wait for a plain-text operator reply in Telegram."""

    config = node.get("data", {})
    node_id = str(node.get("id") or "")
    try:
        timeout_minutes = float(config.get("timeout_minutes", 120) or 120)
    except (TypeError, ValueError):
        timeout_minutes = 120.0
    bot_token, chat_id = resolve_telegram_target(
        config,
        token_keys=("tg_bot_token", "bot_token", "telegram_bot_token"),
        chat_keys=("tg_chat_id", "chat_id", "telegram_chat_id"),
    )
    if not chat_id:
        chat_id = str(context.get("tg_chat_id") or context.get("chat_id") or "").strip()
    parse_mode = str(config.get("parse_mode") or "Markdown").strip() or "Markdown"

    if not bot_token:
        return {
            "status": "failed",
            "error": "tg_bot_token not configured for telegram_input node.",
            "decision": "timeout",
        }
    if not chat_id:
        return {
            "status": "failed",
            "error": "tg_chat_id not configured for telegram_input node.",
            "decision": "timeout",
        }

    all_outputs_text = _redacted_all_outputs_text(node_outputs, max_output_chars=2000)
    subs = _redacted_pipeline_context(context)
    subs["pipeline_name"] = run.pipeline.name
    subs["run_id"] = str(run.pk)
    subs["all_outputs"] = all_outputs_text
    subs["node_label"] = str(config.get("label") or node_id)
    message_template = (
        config.get("message")
        or "📝 *Нужна инструкция оператора*\n\n"
        "*Пайплайн:* {pipeline_name}\n"
        "*Запуск:* {run_id}\n"
        "*Узел:* {node_label}\n\n"
        "{all_outputs}\n\n"
        "Ответьте на это сообщение обычным текстом. Ответ будет передан агенту."
    )
    node_state = dict(run.node_states.get(node_id, {}))
    prompt_message_id = 0
    started_at = timezone.now()

    if node_state.get("status") in {"hibernating", "awaiting_operator_reply"}:
        operator_response = str(node_state.get("operator_response") or "").strip()
        if operator_response:
            return {
                "status": "completed",
                "output": operator_response,
                "decision": "received",
                "response_text": operator_response,
            }
        try:
            prompt_message_id = int(node_state.get("telegram_prompt_message_id") or 0)
        except (TypeError, ValueError):
            prompt_message_id = 0
        started_at_str = node_state.get("started_at")
        if started_at_str:
            with contextlib.suppress(Exception):
                from dateutil.parser import isoparse

                started_at = isoparse(started_at_str)
    else:
        try:
            prompt_message = str(message_template).format_map(subs)
        except (KeyError, ValueError):
            prompt_message = str(message_template)
        prompt_message = _redact_pipeline_text(prompt_message)

        telegram_result = await _send_telegram_message(
            bot_token=bot_token,
            chat_id=chat_id,
            message=prompt_message,
            parse_mode=parse_mode,
            reply_markup={"force_reply": True, "selective": False},
        )
        if telegram_result.get("status") != "completed":
            return {
                "status": "failed",
                "error": str(telegram_result.get("error") or "Не удалось отправить Telegram-сообщение."),
                "decision": "timeout",
            }

        try:
            prompt_message_id = int(telegram_result.get("last_message_id") or 0)
        except (TypeError, ValueError):
            prompt_message_id = 0
        if prompt_message_id <= 0:
            return {
                "status": "failed",
                "error": "Telegram не вернул message_id для ожидания ответа оператора.",
                "decision": "timeout",
            }

        await _update_node_state(
            run,
            node_id,
            {
                "status": "awaiting_operator_reply",
                "telegram_prompt_message_id": prompt_message_id,
                "telegram_chat_id": chat_id,
                "started_at": started_at.isoformat(),
            },
        )

    deadline = started_at + timedelta(minutes=timeout_minutes)
    try:
        poll_interval = max(1, min(int(config.get("poll_interval_seconds") or 2), 30))
    except (TypeError, ValueError):
        poll_interval = 2

    while True:
        fresh_run = await _s2a(lambda: PipelineRun.objects.get(pk=run.pk), thread_sensitive=False)()
        fresh_state = dict(fresh_run.node_states.get(node_id, {}))
        operator_response = str(fresh_state.get("operator_response") or "").strip()
        if operator_response:
            return {
                "status": "completed",
                "output": operator_response,
                "decision": "received",
                "response_text": operator_response,
            }

        if stop_event and stop_event.is_set():
            return {"status": "stopped", "output": "Ожидание ответа оператора отменено", "stopped": True}
        if is_runtime_stop_requested(fresh_run):
            return {"status": "stopped", "output": "Ожидание ответа оператора отменено", "stopped": True}

        reply = await _poll_telegram_reply_message(bot_token, chat_id, prompt_message_id)
        if reply:
            response_text = str(reply.get("text") or "").strip()
            if response_text:
                fresh_state.update(
                    {
                        "status": "awaiting_operator_reply",
                        "operator_response": response_text,
                        "operator_response_message_id": reply.get("message_id"),
                        "operator_response_from": reply.get("from_username") or "",
                        "operator_response_received_at": timezone.now().isoformat(),
                    }
                )
                await _update_node_state(fresh_run, node_id, fresh_state)
                return {
                    "status": "completed",
                    "output": response_text,
                    "decision": "received",
                    "response_text": response_text,
                }

        fresh_run = await _s2a(lambda: PipelineRun.objects.get(pk=run.pk), thread_sensitive=False)()
        if stop_event and stop_event.is_set():
            return {"status": "stopped", "output": "Ожидание ответа оператора отменено", "stopped": True}
        if is_runtime_stop_requested(fresh_run):
            return {"status": "stopped", "output": "Ожидание ответа оператора отменено", "stopped": True}
        if timezone.now() >= deadline:
            return {
                "status": "failed",
                "error": f"Таймаут ожидания ответа оператора — нет ответа в течение {timeout_minutes:.0f} мин.",
                "decision": "timeout",
            }
        await asyncio.sleep(poll_interval)
