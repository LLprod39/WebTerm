"""Durable Telegram update, approval, and operator-reply delivery state."""

from __future__ import annotations

import hmac
from typing import Any

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from studio.approval_models import ApprovalRequest, TelegramBotCursor, TelegramReplyRequest

PipelineRun = django_apps.get_model("studio", "PipelineRun", require_ready=False)


def telegram_bot_token_digest(bot_token: str) -> str:
    return ApprovalRequest.digest_token(str(bot_token or ""))


def telegram_worker_key(bot_token: str) -> str:
    return f"bot-{telegram_bot_token_digest(bot_token)[:16]}"


def telegram_approval_callback_data(decision: str, approval_token: str) -> str:
    normalized = str(decision or "").strip().lower()
    if normalized not in {ApprovalRequest.STATUS_APPROVED, ApprovalRequest.STATUS_REJECTED}:
        raise ValueError("Telegram approval decision must be approved or rejected")
    callback_data = f"approval:{normalized}:{str(approval_token or '').strip()}"
    if len(callback_data.encode("utf-8")) > 64:
        raise ValueError("Telegram approval callback data exceeds 64 bytes")
    return callback_data


def parse_telegram_approval_callback_data(value: object) -> dict[str, str] | None:
    raw = str(value or "").strip()
    if not raw.startswith("approval:"):
        return None
    parts = raw.split(":", 2)
    if len(parts) != 3:
        return None
    _, decision, token = parts
    if decision not in {ApprovalRequest.STATUS_APPROVED, ApprovalRequest.STATUS_REJECTED} or not token:
        return None
    return {"decision": decision, "token": token}


def get_telegram_update_offset(bot_token: str) -> int:
    cursor, _created = TelegramBotCursor.objects.get_or_create(
        bot_token_digest=telegram_bot_token_digest(bot_token),
        defaults={"update_offset": 0},
    )
    return int(cursor.update_offset)


@transaction.atomic
def advance_telegram_update_offset(bot_token: str, update_offset: int) -> int:
    cursor, _created = TelegramBotCursor.objects.select_for_update().get_or_create(
        bot_token_digest=telegram_bot_token_digest(bot_token),
        defaults={"update_offset": 0},
    )
    next_offset = max(int(cursor.update_offset), max(0, int(update_offset)))
    if next_offset != cursor.update_offset:
        cursor.update_offset = next_offset
        cursor.save(update_fields=["update_offset", "updated_at"])
    return next_offset


@transaction.atomic
def record_telegram_approval_callback(
    *,
    bot_token: str,
    callback_data: object,
    chat_id: object,
    from_username: object = "",
) -> tuple[bool, str]:
    parsed = parse_telegram_approval_callback_data(callback_data)
    if parsed is None:
        return False, "Некорректная кнопка подтверждения"

    approval = (
        ApprovalRequest.objects.select_for_update()
        .select_related("run", "run__pipeline")
        .filter(token_digest=ApprovalRequest.digest_token(parsed["token"]))
        .first()
    )
    if approval is None:
        return False, "Запрос подтверждения не найден"
    expected_bot = approval.telegram_bot_token_digest
    actual_bot = telegram_bot_token_digest(bot_token)
    if not expected_bot or not hmac.compare_digest(expected_bot, actual_bot):
        return False, "Эта кнопка предназначена для другого бота"
    if not approval.telegram_chat_id or not hmac.compare_digest(
        approval.telegram_chat_id,
        str(chat_id or "").strip(),
    ):
        return False, "Эта кнопка предназначена для другого чата"
    if approval.status != ApprovalRequest.STATUS_PENDING:
        return True, "Решение уже сохранено"
    if approval.is_expired:
        approval.status = ApprovalRequest.STATUS_EXPIRED
        approval.save(update_fields=["status"])
        return False, "Срок подтверждения истёк"
    if approval.run.status not in {
        PipelineRun.STATUS_PENDING,
        PipelineRun.STATUS_RUNNING,
        PipelineRun.STATUS_HIBERNATING,
    }:
        approval.status = ApprovalRequest.STATUS_EXPIRED
        approval.save(update_fields=["status"])
        return False, "Запуск пайплайна уже завершён"

    username = str(from_username or "").strip()[:150]
    approval.status = parsed["decision"]
    approval.response_text = f"Telegram button by @{username}" if username else "Telegram button"
    approval.decided_at = timezone.now()
    approval.decided_by = None
    approval.save(update_fields=["status", "response_text", "decided_at", "decided_by"])

    run = PipelineRun.objects.select_for_update().get(pk=approval.run_id)
    node_states = dict(run.node_states or {})
    node_state = dict(node_states.get(approval.node_id) or {})
    node_states[approval.node_id] = {
        **node_state,
        "approval_decision": approval.status,
        "approval_response": approval.response_text,
        "approval_source": "telegram_button",
        "approval_request_id": approval.pk,
        "decided_at": approval.decided_at.isoformat(),
    }
    run.node_states = node_states
    run.save(update_fields=["node_states"])
    return True, "Решение сохранено"


@transaction.atomic
def arm_telegram_reply_request(
    *,
    run: PipelineRun,
    node_id: str,
    bot_token: str,
    chat_id: str,
    prompt_message_id: int,
    expires_at,
) -> TelegramReplyRequest:
    request, _created = TelegramReplyRequest.objects.select_for_update().update_or_create(
        run=run,
        node_id=str(node_id),
        defaults={
            "bot_token_digest": telegram_bot_token_digest(bot_token),
            "chat_id": str(chat_id or "").strip()[:64],
            "prompt_message_id": int(prompt_message_id),
            "status": TelegramReplyRequest.STATUS_PENDING,
            "response_text": "",
            "response_message_id": None,
            "response_from": "",
            "expires_at": expires_at,
            "received_at": None,
        },
    )
    return request


@transaction.atomic
def store_telegram_operator_reply(bot_token: str, message: dict[str, Any]) -> bool:
    if not isinstance(message, dict):
        return False
    reply_to = message.get("reply_to_message") or {}
    chat = message.get("chat") or {}
    text = str(message.get("text") or "").strip()
    chat_id = str(chat.get("id") or "").strip()
    try:
        prompt_message_id = int(reply_to.get("message_id"))
    except (TypeError, ValueError):
        prompt_message_id = 0
    if not bot_token or not chat_id or prompt_message_id <= 0 or not text:
        return False

    reply_request = (
        TelegramReplyRequest.objects.select_for_update()
        .select_related("run")
        .filter(
            bot_token_digest=telegram_bot_token_digest(bot_token),
            chat_id=chat_id,
            prompt_message_id=prompt_message_id,
        )
        .first()
    )
    if reply_request is None or reply_request.status != TelegramReplyRequest.STATUS_PENDING:
        return False
    if reply_request.expires_at <= timezone.now():
        reply_request.status = TelegramReplyRequest.STATUS_EXPIRED
        reply_request.save(update_fields=["status"])
        return False
    from_username = str(((message.get("from") or {}) or {}).get("username") or "").strip()[:150]
    try:
        response_message_id = int(message.get("message_id"))
    except (TypeError, ValueError):
        response_message_id = None
    now = timezone.now()
    reply_request.status = TelegramReplyRequest.STATUS_RECEIVED
    reply_request.response_text = text
    reply_request.response_message_id = response_message_id
    reply_request.response_from = from_username
    reply_request.received_at = now
    reply_request.save(update_fields=["status", "response_text", "response_message_id", "response_from", "received_at"])

    run = PipelineRun.objects.select_for_update().get(pk=reply_request.run_id)
    node_states = dict(run.node_states or {})
    node_state = dict(node_states.get(reply_request.node_id) or {})
    node_states[reply_request.node_id] = {
        **node_state,
        "operator_response": text,
        "operator_response_message_id": response_message_id,
        "operator_response_from": from_username,
        "operator_response_received_at": now.isoformat(),
    }
    run.node_states = node_states
    run.save(update_fields=["node_states"])
    return True


def expire_telegram_reply_request(*, run_id: int, node_id: str) -> None:
    TelegramReplyRequest.objects.filter(
        run_id=run_id,
        node_id=str(node_id),
        status=TelegramReplyRequest.STATUS_PENDING,
    ).update(status=TelegramReplyRequest.STATUS_EXPIRED)
