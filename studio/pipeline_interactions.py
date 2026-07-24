from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
from datetime import timedelta
from threading import Event

from asgiref.sync import sync_to_async as _s2a
from django.utils import timezone

from .models import PipelineRun
from .pipeline_interactions_telegram import (
    execute_logic_telegram_input,
    resolve_telegram_target,
)
from .pipeline_notifications import (
    _global_email_defaults,
    _global_site_url,
    _global_tg_defaults,
    _send_telegram_message,
)
from .pipeline_outputs import (
    execute_output_email as _execute_output_email,
)
from .pipeline_outputs import (
    execute_output_telegram as _execute_output_telegram,
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
    _poll_telegram_approval_decision,
    _telegram_approval_callback_data,
)

logger = logging.getLogger(__name__)

__all__ = [
    "_global_email_defaults",
    "_global_site_url",
    "_global_tg_defaults",
    "_send_telegram_message",
    "execute_logic_human_approval",
    "execute_logic_telegram_input",
    "resolve_telegram_target",
]


async def execute_logic_human_approval(
    node: dict,
    context: dict,
    node_outputs: dict[str, dict],
    run: PipelineRun,
    stop_event: Event | None = None,
) -> dict:
    """
    Pause the pipeline and wait for a human approve/reject decision.

    How it works:
    1. Generates a signed one-time token stored in node_states.
    2. Sends an email and/or Telegram message with approve/reject actions.
       APPROVE -> GET /api/studio/runs/<run_id>/approve/<node_id>/?token=...&decision=approved
       REJECT  -> GET /api/studio/runs/<run_id>/approve/<node_id>/?token=...&decision=rejected
       Telegram uses inline callback buttons, so no external browser access is required.
    3. Polls Telegram callbacks and the DB for the decision.
    4. On timeout, returns failed.
    5. If approved, the pipeline continues; if rejected, the run is treated as failed
       (downstream nodes can check {node_id_status} == "failed" with a logic/condition).
    """
    config = node.get("data", {})
    node_id = node["id"]
    timeout_minutes = float(config.get("timeout_minutes", 120))

    g_to, _gh, _gu, _gp, _gf = _global_email_defaults()
    base_url = (config.get("base_url") or "").rstrip("/") or _global_site_url()

    all_outputs_text = _redacted_all_outputs_text(node_outputs, max_output_chars=2000)
    subs = _redacted_pipeline_context(context)

    message_template = config.get(
        "message",
        "🔔 *Требуется подтверждение пайплайна*\n\n"
        "*Пайплайн:* {pipeline_name}\n"
        "*Запуск:* {run_id}\n\n"
        "{all_outputs}\n\n"
        "Пожалуйста, проверьте план выше и примите решение:\n\n"
        "✅ *ОДОБРИТЬ:* {approve_url}\n\n"
        "❌ *ОТКЛОНИТЬ:* {reject_url}",
    )

    approval_token = secrets.token_urlsafe(32)
    approve_url = f"{base_url}/api/studio/runs/{run.pk}/approve/{node_id}/?token={approval_token}&decision=approved"
    reject_url = f"{base_url}/api/studio/runs/{run.pk}/approve/{node_id}/?token={approval_token}&decision=rejected"
    manual_link_only = bool(config.get("manual_link_only", False))
    preview_to_email = (config.get("to_email") or g_to or "").strip()
    preview_tg_bot_token, preview_tg_chat_id = resolve_telegram_target(
        config,
        token_keys=("tg_bot_token", "bot_token", "telegram_bot_token"),
        chat_keys=("tg_chat_id", "chat_id", "telegram_chat_id"),
    )
    if not preview_to_email and not (preview_tg_bot_token and preview_tg_chat_id) and not manual_link_only:
        return {
            "status": "failed",
            "error": "No delivery channel configured for human approval. Set email/Telegram or enable manual_link_only.",
            "decision": "timeout",
            "output": f"Approval links were not armed because delivery is missing.\nApprove: {approve_url}\nReject: {reject_url}",
        }

    subs["pipeline_name"] = run.pipeline.name
    subs["run_id"] = str(run.pk)
    subs["approve_url"] = approve_url
    subs["reject_url"] = reject_url
    subs["all_outputs"] = all_outputs_text
    subs["timeout_minutes"] = str(int(timeout_minutes))

    with contextlib.suppress(KeyError, ValueError):
        message_template.format_map(subs)

    await _update_node_state(
        run,
        node_id,
        {
            "status": "awaiting_approval",
            "approval_token": approval_token,
            "approve_url": approve_url,
            "reject_url": reject_url,
            "started_at": timezone.now().isoformat(),
        },
    )

    to_email = (config.get("to_email") or g_to or "").strip()
    if to_email:
        email_subject_tpl = (config.get("email_subject") or "").strip()
        email_body_tpl = (config.get("email_body") or "").strip()
        if email_subject_tpl:
            try:
                email_subject = email_subject_tpl.format_map(subs)
            except (KeyError, ValueError):
                email_subject = email_subject_tpl
        else:
            email_subject = f"Обновление сервера: нужно ваше решение (запуск #{run.pk})"
        if email_body_tpl:
            try:
                email_body = email_body_tpl.format_map(subs)
            except (KeyError, ValueError):
                email_body = email_body_tpl
        else:
            plan_preview = (all_outputs_text or "").strip()
            if len(plan_preview) > 1200:
                plan_preview = plan_preview[:1200].rstrip() + "\n\n... (полный отчёт в логе пайплайна)"
            email_body = (
                "Здравствуйте.\n\n"
                "Пайплайн собрал план обновлений на сервере и ждёт вашего решения.\n\n"
                "——— Отчёт и план ———\n\n"
                f"{plan_preview}\n\n"
                "——— Что сделать ———\n\n"
                f"ОДОБРИТЬ: {approve_url}\n\n"
                f"ОТКЛОНИТЬ: {reject_url}\n\n"
                f"Ссылка действительна {timeout_minutes:.0f} мин.\n\n"
                "С уважением,\nWEU Pipeline"
            )
        email_node = {
            "id": f"{node_id}_approval_email",
            "data": {
                "to_email": to_email,
                "subject": email_subject,
                "body": email_body,
                "smtp_host": config.get("smtp_host") or "",
                "smtp_port": config.get("smtp_port") or "",
                "smtp_user": config.get("smtp_user") or "",
                "smtp_password": config.get("smtp_password") or "",
                "from_email": config.get("from_email") or "",
                "_redaction_preserve_values": [approve_url, reject_url],
                "_redaction_preserve_context_keys": ["approve_url", "reject_url"],
            },
        }
        try:
            await _execute_output_email(email_node, subs, node_outputs, run)
            logger.info("human_approval node %s: approval email sent to %s", node_id, to_email)
        except Exception as exc:
            logger.warning("human_approval email failed: %s", exc)

    tg_bot_token, tg_chat_id = resolve_telegram_target(
        config,
        token_keys=("tg_bot_token", "bot_token", "telegram_bot_token"),
        chat_keys=("tg_chat_id", "chat_id", "telegram_chat_id"),
    )
    raw_tg_parse_mode = config.get("tg_parse_mode")
    tg_parse_mode = "Markdown" if raw_tg_parse_mode is None else str(raw_tg_parse_mode).strip()
    if tg_bot_token and tg_chat_id:
        telegram_message_template = (
            config.get("telegram_message")
            or "🔔 *Требуется подтверждение пайплайна*\n\n"
            "*Пайплайн:* {pipeline_name}\n"
            "*Запуск:* {run_id}\n\n"
            "{all_outputs}\n\n"
            "Нажмите кнопку ниже, чтобы одобрить или отклонить шаг прямо в Telegram."
        )
        try:
            telegram_message = telegram_message_template.format_map(subs)
        except (KeyError, ValueError):
            telegram_message = str(telegram_message_template)
        tg_node = {
            "id": f"{node_id}_approval_tg",
            "data": {
                "bot_token": tg_bot_token,
                "chat_id": tg_chat_id,
                "message": telegram_message,
                "parse_mode": tg_parse_mode,
                "disable_web_page_preview": True,
                "_redaction_preserve_values": [approve_url, reject_url],
                "_redaction_preserve_context_keys": ["approve_url", "reject_url"],
                "reply_markup": {
                    "inline_keyboard": [
                        [
                            {
                                "text": "✅ Одобрить",
                                "callback_data": _telegram_approval_callback_data("approved", approval_token),
                            },
                            {
                                "text": "❌ Отклонить",
                                "callback_data": _telegram_approval_callback_data("rejected", approval_token),
                            },
                        ]
                    ]
                },
            },
        }
        try:
            await _execute_output_telegram(tg_node, subs, node_outputs, run)
            logger.info("human_approval node %s: Telegram notification sent", node_id)
        except Exception as exc:
            logger.warning("human_approval Telegram failed: %s", exc)

    deadline = timezone.now() + timedelta(minutes=timeout_minutes)
    poll_interval = 2

    while True:
        if stop_event and stop_event.is_set():
            return {"status": "stopped", "output": "Approval wait cancelled by stop request", "stopped": True}
        await asyncio.sleep(poll_interval)

        telegram_callback = None
        if tg_bot_token and tg_chat_id:
            telegram_callback = await _poll_telegram_approval_decision(tg_bot_token, approval_token)

        fresh_run = await _s2a(lambda: PipelineRun.objects.get(pk=run.pk), thread_sensitive=False)()

        node_state = dict(fresh_run.node_states.get(node_id, {}))
        if telegram_callback and not node_state.get("approval_decision"):
            node_state["approval_decision"] = telegram_callback.get("decision")
            node_state["approval_response"] = telegram_callback.get("response_text") or "via Telegram callback"
            node_state["approval_source"] = "telegram_callback"
            node_state["decided_at"] = timezone.now().isoformat()
            await _update_node_state(fresh_run, node_id, node_state)
            if tg_bot_token and tg_chat_id:
                verdict = "approved" if node_state["approval_decision"] == "approved" else "rejected"
                emoji = "✅" if verdict == "approved" else "❌"
                verdict_text = "одобрено" if verdict == "approved" else "отклонено"
                with contextlib.suppress(Exception):
                    await _send_telegram_message(
                        bot_token=tg_bot_token,
                        chat_id=tg_chat_id,
                        message=(
                            f"{emoji} *Решение записано*\n\n"
                            f"*Пайплайн:* {run.pipeline.name}\n"
                            f"*Запуск:* #{run.pk}\n"
                            f"*Узел:* {config.get('label') or node_id}\n"
                            f"*Решение:* {verdict_text}"
                        ),
                    )

        decision = node_state.get("approval_decision")

        if decision == "approved":
            user_response = node_state.get("approval_response", "")
            logger.info("human_approval node %s: APPROVED (response: %r)", node_id, user_response[:100])
            return {
                "status": "completed",
                "output": f"ОДОБРЕНО\n\nКомментарий:\n{user_response}" if user_response else "ОДОБРЕНО",
                "approved": True,
                "decision": "approved",
                "user_response": user_response,
            }

        if decision == "rejected":
            user_response = node_state.get("approval_response", "")
            logger.info("human_approval node %s: REJECTED", node_id)
            return {
                "status": "failed",
                "error": f"ОТКЛОНЕНО оператором.\n\nПричина: {user_response}"
                if user_response
                else "ОТКЛОНЕНО оператором.",
                "approved": False,
                "decision": "rejected",
            }

        if is_runtime_stop_requested(fresh_run):
            return {"status": "stopped", "output": "Approval wait cancelled by stop request", "stopped": True}

        if timezone.now() >= deadline:
            logger.warning("human_approval node %s: TIMEOUT after %.0f min", node_id, timeout_minutes)
            return {
                "status": "failed",
                "error": f"Таймаут подтверждения — нет ответа в течение {timeout_minutes:.0f} мин.",
                "decision": "timeout",
            }
