"""Bridge Telegram messages into the platform Operator chat loop."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import Any

from django.core.cache import cache
from django.db import transaction
from loguru import logger

from core_ui.models import AssistantAction, ChatSession
from core_ui.services.assistant_chat import AssistantActionError, handle_user_message
from core_ui.services.assistant_confirm import (
    cancel_action_and_resume_detailed,
    confirm_action_and_resume_detailed,
)
from studio.pipeline.pipeline_telegram import _redact_telegram_text
from telegram_hub.channel_presenter import (
    action_card_text as _action_card_text,
    inline_keyboard_for_action as _inline_keyboard_for_action,
    present_assistant_reply,
    send_presented_messages,
)
from telegram_hub.client import TelegramClient
from telegram_hub.models import TelegramAccountLink, TelegramBot, TelegramChatBinding
from telegram_hub.services.bots import get_bot_token
from telegram_hub.services.linking import verify_action_callback_sig

_VARS_PENDING_TTL = 15 * 60
_YAML_KEYS = {"yaml", "source_yaml", "content", "playbook_yaml", "body"}


def _sanitize_telegram_assistant_reply(text: str, metadata: dict[str, Any] | None = None) -> str:
    """Sanitize assistant prose for Telegram (tech dumps / card pointers + digest)."""
    from core_ui.services.operator_channel import finalize_telegram_assistant_text

    return finalize_telegram_assistant_text(text, metadata)


def _lock_key(link_id: int) -> str:
    return f"tg_assistant_turn:{link_id}"


def _vars_pending_key(link_id: int) -> str:
    return f"tg_playbook_vars:{link_id}"


def acquire_turn_lock(link_id: int, *, ttl: int = 180) -> bool:
    return bool(cache.add(_lock_key(link_id), "1", ttl))


def release_turn_lock(link_id: int) -> None:
    cache.delete(_lock_key(link_id))


@transaction.atomic
def get_or_create_telegram_session(link: TelegramAccountLink) -> ChatSession:
    binding = (
        TelegramChatBinding.objects.select_related("chat_session")
        .filter(link=link, is_active=True)
        .order_by("-updated_at")
        .first()
    )
    if binding and binding.chat_session_id:
        session = binding.chat_session
        bot_prompt = str(link.bot.system_prompt or "")[:4000]
        pinned = dict(session.pinned_context or {})
        if pinned.get("system_prompt", "") != bot_prompt:
            pinned["system_prompt"] = bot_prompt
            session.pinned_context = pinned
            session.save(update_fields=["pinned_context", "updated_at"])
        return session

    bot = link.bot
    from core_ui.ai_model_policy import stored_operational_provider_binding

    session = ChatSession.objects.create(
        user=link.user,
        title=f"Telegram · @{bot.bot_username or bot.name or bot.pk}",
        kind=ChatSession.KIND_TELEGRAM,
        pinned_context={
            "channel": "telegram",
            "bot_id": bot.pk,
            "telegram_user_id": link.telegram_user_id,
            "chat_id": link.chat_id,
            "system_prompt": str(bot.system_prompt or "")[:4000],
        },
        provider_binding=stored_operational_provider_binding(link.user, bot.provider_binding),
    )
    TelegramChatBinding.objects.filter(link=link, is_active=True).update(is_active=False)
    TelegramChatBinding.objects.create(link=link, chat_session=session, is_active=True)
    return session


@transaction.atomic
def start_new_telegram_session(link: TelegramAccountLink) -> ChatSession:
    TelegramChatBinding.objects.filter(link=link, is_active=True).update(is_active=False)
    return get_or_create_telegram_session(link)


def store_playbook_vars_pending(link_id: int, payload: dict[str, Any]) -> None:
    cache.set(_vars_pending_key(link_id), payload, _VARS_PENDING_TTL)


def pop_playbook_vars_pending(link_id: int) -> dict[str, Any] | None:
    key = _vars_pending_key(link_id)
    payload = cache.get(key)
    if payload:
        cache.delete(key)
    return payload if isinstance(payload, dict) else None


def peek_playbook_vars_pending(link_id: int) -> dict[str, Any] | None:
    payload = cache.get(_vars_pending_key(link_id))
    return payload if isinstance(payload, dict) else None


def parse_key_value_lines(text: str) -> dict[str, str]:
    """Parse `key=value` / `key: value` lines from a Telegram reply."""
    result: dict[str, str] = {}
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        sep = "=" if "=" in line else (":" if ":" in line else "")
        if not sep:
            continue
        key, _, value = line.partition(sep)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            result[key] = value
    return result


def missing_runtime_variables_from_action(action: AssistantAction) -> list[str]:
    from servers.services.playbook_compatibility_analysis import is_user_required_runtime_variable

    payload = action.result_payload if isinstance(action.result_payload, dict) else {}
    compat = payload.get("compatibility") if isinstance(payload.get("compatibility"), dict) else {}
    missing = compat.get("missing_runtime_variables")
    candidates: list[str] = []
    if isinstance(missing, list) and missing:
        candidates = [str(item) for item in missing if str(item).strip()]
    else:
        message = str(action.error or "")
        marker = "Required runtime values are missing:"
        if marker in message:
            tail = message.split(marker, 1)[1]
            candidates = [part.strip() for part in tail.split(",") if part.strip()]
    return [name for name in candidates if is_user_required_runtime_variable(name)]


def is_missing_runtime_vars_error(action: AssistantAction) -> bool:
    err = (action.error or "").lower()
    if "required runtime variable" not in err and not missing_runtime_variables_from_action(action):
        return False
    # Only open the Telegram wizard when at least one real user-supplied var remains.
    return bool(missing_runtime_variables_from_action(action))


def _user_facing_resume_error(raw: str | None) -> str:
    text = str(raw or "").strip()
    low = text.lower()
    if "single thread executor" in low or "would deadlock" in low:
        return (
            "Не удалось продолжить диалог после подтверждения. "
            "Сессию разблокировали — повторите запрос или отправьте /new."
        )
    if not text:
        return "Не удалось продолжить диалог после подтверждения."
    # Keep short; avoid dumping internal stack fragments.
    return text[:300]

@dataclass
class TelegramActionResult:
    ok: bool
    toast: str
    chat_lines: list[str] = field(default_factory=list)
    followup_actions: list[AssistantAction] = field(default_factory=list)


def _resume_followups(resume: Any) -> tuple[str, list[AssistantAction]]:
    if resume is None:
        return "", []
    reply = ""
    assistant_message = getattr(resume, "assistant_message", None)
    if assistant_message is not None:
        reply = _sanitize_telegram_assistant_reply(
            str(getattr(assistant_message, "content", "") or ""),
            getattr(assistant_message, "metadata", None)
            if isinstance(getattr(assistant_message, "metadata", None), dict)
            else None,
        )
        reply = _redact_telegram_text(reply, limit=12000)
    actions = [
        action
        for action in list(getattr(resume, "actions", None) or [])
        if getattr(action, "status", None) == AssistantAction.STATUS_REQUIRES_CONFIRMATION
    ]
    return reply, actions


def _outcome_to_telegram_result(
    *,
    outcome,
    cancelled: bool = False,
    link: TelegramAccountLink | None = None,
) -> TelegramActionResult:
    action = outcome.action
    chat_lines: list[str] = []
    followups: list[AssistantAction] = []

    if action.status == AssistantAction.STATUS_RUNNING:
        return TelegramActionResult(
            ok=True,
            toast="Выполняется…",
            chat_lines=["⏳ Действие выполняется…"],
        )

    if action.status == AssistantAction.STATUS_REQUIRES_CONFIRMATION and action.error:
        return TelegramActionResult(ok=False, toast="Нужно подтверждение", chat_lines=[f"⚠️ {action.error}"])

    if cancelled:
        toast = "Отменено"
        chat_lines.append("❌ Действие отменено.")
    elif action.status == AssistantAction.STATUS_COMPLETED:
        toast = "Готово"
        chat_lines.append("✅ Действие выполнено.")
        target = str(action.target_url or "").strip()
        if target:
            chat_lines.append(target)
    elif action.status == AssistantAction.STATUS_FAILED:
        toast = "Ошибка"
        chat_lines.append(f"⚠️ {action.error or 'Не удалось выполнить действие'}")
    else:
        toast = "Готово"
        chat_lines.append(f"Статус: {action.status}")

    if outcome.resume_error:
        chat_lines.append(f"⚠️ {_user_facing_resume_error(outcome.resume_error)}")
    if outcome.stale_cleared:
        chat_lines.append("Сессия разблокирована (зависшее подтверждение снято).")

    resume_text, resume_actions = _resume_followups(outcome.resume)
    if resume_text.strip():
        # Avoid duplicating a short status line already covered above.
        if resume_text.strip() not in {"", chat_lines[-1] if chat_lines else None}:
            chat_lines.append(resume_text.strip())
    followups.extend(resume_actions)

    if (
        link is not None
        and action.status == AssistantAction.STATUS_FAILED
        and action.action_type == "operator.run_playbook"
        and is_missing_runtime_vars_error(action)
    ):
        missing = missing_runtime_variables_from_action(action)
        if missing:
            store_playbook_vars_pending(
                link.pk,
                {
                    "action_id": action.pk,
                    "missing": missing,
                    "input_payload": dict(action.input_payload or {}),
                    "session_id": action.session_id,
                },
            )
            keys = ", ".join(missing)
            chat_lines.append(
                "Нужны runtime-переменные playbook.\n"
                f"Ответьте сообщением в формате key=value (по одной на строку).\n"
                f"Ожидаются: {keys}"
            )
            toast = "Нужны переменные"

    ok = action.status in {
        AssistantAction.STATUS_COMPLETED,
        AssistantAction.STATUS_RUNNING,
        AssistantAction.STATUS_CANCELLED,
    }
    if cancelled:
        ok = True
    if action.status == AssistantAction.STATUS_FAILED and is_missing_runtime_vars_error(action):
        # Session is usable after resume/stale clear; treat as handled UX path.
        ok = True
    return TelegramActionResult(ok=ok, toast=toast, chat_lines=chat_lines, followup_actions=followups)


def try_consume_playbook_vars_reply(
    *,
    link: TelegramAccountLink,
    text: str,
) -> TelegramActionResult | None:
    pending = peek_playbook_vars_pending(link.pk)
    if not pending:
        return None
    parsed = parse_key_value_lines(text)
    if not parsed:
        missing = pending.get("missing") or []
        keys = ", ".join(str(item) for item in missing) if missing else "key=value"
        return TelegramActionResult(
            ok=False,
            toast="Формат key=value",
            chat_lines=[
                "Не распознал переменные. Пришлите строки вида:\n"
                "ansible_user=root\n"
                f"Ожидаются: {keys}"
            ],
        )

    pop_playbook_vars_pending(link.pk)
    base_input = dict(pending.get("input_payload") or {})
    existing = base_input.get("extra_vars") if isinstance(base_input.get("extra_vars"), dict) else {}
    base_input["extra_vars"] = {**existing, **parsed}

    session = None
    session_id = pending.get("session_id")
    if session_id:
        session = ChatSession.objects.filter(pk=session_id, user=link.user).first()
    if session is None:
        session = get_or_create_telegram_session(link)

    action = AssistantAction.objects.create(
        user=link.user,
        session=session,
        action_type="operator.run_playbook",
        title="Run playbook",
        description="Повторный запуск с runtime-переменными из Telegram.",
        status=AssistantAction.STATUS_REQUIRES_CONFIRMATION,
        risk=AssistantAction.RISK_MUTATING,
        required_feature="servers",
        requires_confirmation=True,
        input_payload=base_input,
        safe_preview={k: v for k, v in base_input.items() if k not in _YAML_KEYS},
    )
    return TelegramActionResult(
        ok=True,
        toast="Переменные приняты",
        chat_lines=["Переменные сохранены. Подтвердите запуск:"],
        followup_actions=[action],
    )


async def _typing_keepalive(client: TelegramClient, chat_id: str, stop: asyncio.Event) -> None:
    """Telegram typing indicators expire ~5s — refresh until the turn finishes."""
    while not stop.is_set():
        with contextlib.suppress(Exception):
            await client.send_chat_action(chat_id=chat_id, action="typing")
        try:
            await asyncio.wait_for(stop.wait(), timeout=4.0)
        except asyncio.TimeoutError:
            continue


def _run_operator_turn_sync(link: TelegramAccountLink, text: str):
    """
    Run Django ORM + Operator loop off the asyncio event loop.

    Must NOT be wrapped in sync_to_async(thread_sensitive=True): nested
    sync_to_async inside the Operator/LLM path deadlocks Celery workers
    ("Single thread executor already being used").
    """
    from core_ui.ai_model_policy import operational_provider_binding

    session = get_or_create_telegram_session(link)
    result = handle_user_message(
        session,
        link.user,
        text,
        request=None,
        provider_binding=operational_provider_binding(link.user, link.bot.provider_binding),
    )
    return session, result


async def run_assistant_turn(
    *,
    link_id: int,
    text: str,
    tg_message_id: int | None = None,
) -> None:
    link = await asyncio.to_thread(
        lambda: TelegramAccountLink.objects.select_related("user", "bot").filter(pk=link_id).first()
    )
    if link is None or link.status != TelegramAccountLink.STATUS_LINKED:
        return
    bot = link.bot
    token = await asyncio.to_thread(get_bot_token, bot)
    if not token:
        return
    client = TelegramClient(token, timeout=30)
    chat_id = link.chat_id

    if not await asyncio.to_thread(acquire_turn_lock, link_id):
        await client.send_message(chat_id=chat_id, text="⏳ Предыдущий запрос ещё обрабатывается…")
        return

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(_typing_keepalive(client, chat_id, stop_typing))
    status_message_id: int | None = None
    try:
        with contextlib.suppress(Exception):
            status = await client.send_message(chat_id=chat_id, text="⏳ Думаю…")
            mid = status.get("last_message_id")
            if isinstance(mid, int):
                status_message_id = mid

        try:
            _session, result = await asyncio.to_thread(_run_operator_turn_sync, link, text)
        except AssistantActionError as exc:
            if status_message_id is not None:
                with contextlib.suppress(Exception):
                    await client.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_message_id,
                        text=f"⚠️ {exc.message}",
                    )
                    status_message_id = None
            else:
                await client.send_message(chat_id=chat_id, text=f"⚠️ {exc.message}")
            return
        except Exception as exc:
            logger.exception("telegram assistant turn failed: {}", exc)
            if status_message_id is not None:
                with contextlib.suppress(Exception):
                    await client.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_message_id,
                        text=f"⚠️ Ошибка ассистента: {exc}",
                    )
                    status_message_id = None
            else:
                await client.send_message(chat_id=chat_id, text=f"⚠️ Ошибка ассистента: {exc}")
            return

        # Annotate user message metadata.
        if getattr(result, "user_message", None) is not None:
            user_msg = result.user_message
            meta = dict(user_msg.metadata or {})
            meta.update({"channel": "telegram", "tg_message_id": tg_message_id})
            user_msg.metadata = meta
            await asyncio.to_thread(user_msg.save, update_fields=["metadata"])

        assistant_message = getattr(result, "assistant_message", None)
        content = getattr(assistant_message, "content", "") if assistant_message is not None else ""
        metadata = (
            getattr(assistant_message, "metadata", None)
            if assistant_message is not None and isinstance(getattr(assistant_message, "metadata", None), dict)
            else None
        )
        outgoing = present_assistant_reply(
            content=str(content or ""),
            metadata=metadata,
            actions=list(result.actions or []),
            telegram_user_id=int(link.telegram_user_id),
            bot_id=bot.pk,
            user_message=str(text or ""),
        )
        if outgoing:
            if status_message_id is not None:
                with contextlib.suppress(Exception):
                    await client.delete_message(chat_id=chat_id, message_id=status_message_id)
                    status_message_id = None
            await send_presented_messages(client, chat_id=chat_id, messages=outgoing)
        elif status_message_id is not None:
            with contextlib.suppress(Exception):
                await client.delete_message(chat_id=chat_id, message_id=status_message_id)
                status_message_id = None
    finally:
        stop_typing.set()
        typing_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await typing_task
        if status_message_id is not None:
            with contextlib.suppress(Exception):
                await client.delete_message(chat_id=chat_id, message_id=status_message_id)
        await asyncio.to_thread(release_turn_lock, link_id)


def handle_action_callback(
    *,
    bot: TelegramBot,
    telegram_user_id: int,
    chat_id: str,
    callback_data: str,
    message_id: int | None = None,
) -> TelegramActionResult:
    raw = str(callback_data or "").strip()
    if not raw.startswith("act:"):
        return TelegramActionResult(ok=False, toast="unknown")
    parts = raw.split(":")
    if len(parts) != 4:
        return TelegramActionResult(ok=False, toast="Некорректная кнопка", chat_lines=["⚠️ Некорректная кнопка"])
    _, flag, action_id_s, sig = parts
    try:
        action_id = int(action_id_s)
    except (TypeError, ValueError):
        return TelegramActionResult(ok=False, toast="Некорректная кнопка", chat_lines=["⚠️ Некорректная кнопка"])
    if not verify_action_callback_sig(
        action_id=action_id,
        telegram_user_id=int(telegram_user_id),
        bot_id=bot.pk,
        signature=sig,
    ):
        return TelegramActionResult(ok=False, toast="Подпись недействительна", chat_lines=["⚠️ Подпись недействительна"])

    link = (
        TelegramAccountLink.objects.select_related("user", "bot")
        .filter(
            bot=bot,
            telegram_user_id=int(telegram_user_id),
            status=TelegramAccountLink.STATUS_LINKED,
        )
        .first()
    )
    if link is None:
        return TelegramActionResult(ok=False, toast="Не привязан", chat_lines=["⚠️ Аккаунт не привязан"])

    action = AssistantAction.objects.filter(pk=action_id, user_id=link.user_id).first()
    if action is None:
        return TelegramActionResult(ok=False, toast="Не найдено", chat_lines=["⚠️ Действие не найдено"])

    if flag == "c":
        outcome = confirm_action_and_resume_detailed(action, request=None)
        return _outcome_to_telegram_result(outcome=outcome, link=link)
    if flag == "x":
        outcome = cancel_action_and_resume_detailed(action, request=None)
        return _outcome_to_telegram_result(outcome=outcome, cancelled=True, link=link)
    return TelegramActionResult(ok=False, toast="Неизвестно", chat_lines=["⚠️ Неизвестное решение"])


def try_typed_confirm_from_reply(
    *,
    bot: TelegramBot,
    telegram_user_id: int,
    text: str,
) -> TelegramActionResult | None:
    """If user replies with a typed confirm token for a pending dangerous action."""
    link = (
        TelegramAccountLink.objects.select_related("user", "bot")
        .filter(
            bot=bot,
            telegram_user_id=int(telegram_user_id),
            status=TelegramAccountLink.STATUS_LINKED,
        )
        .first()
    )
    if link is None:
        return None
    token = str(text or "").strip()
    if not token:
        return None
    action = (
        AssistantAction.objects.filter(
            user_id=link.user_id,
            status=AssistantAction.STATUS_REQUIRES_CONFIRMATION,
            risk=AssistantAction.RISK_DANGEROUS,
        )
        .order_by("-id")
        .first()
    )
    if action is None:
        return None
    outcome = confirm_action_and_resume_detailed(action, request=None, typed_confirm=token)
    return _outcome_to_telegram_result(outcome=outcome, link=link)


async def deliver_assistant_message_to_telegram(
    *,
    session_id: int,
    assistant_message_id: int | None = None,
    action_ids: list[int] | None = None,
) -> None:
    """Deliver an Operator assistant message (+ confirm cards) to the Telegram binding."""
    from core_ui.models import ChatMessage

    binding = (
        await asyncio.to_thread(
            lambda: TelegramChatBinding.objects.select_related("link", "link__bot", "link__user", "chat_session")
            .filter(chat_session_id=session_id, is_active=True)
            .first()
        )
    )
    if binding is None or binding.link is None:
        return
    link = binding.link
    if link.status != TelegramAccountLink.STATUS_LINKED:
        return
    bot = link.bot
    token = await asyncio.to_thread(get_bot_token, bot)
    if not token:
        return

    message = None
    if assistant_message_id:
        message = await asyncio.to_thread(
            lambda: ChatMessage.objects.filter(pk=assistant_message_id, session_id=session_id).first()
        )
    content = getattr(message, "content", "") if message is not None else ""
    metadata = getattr(message, "metadata", None) if message is not None else None
    if not isinstance(metadata, dict):
        metadata = None

    actions: list[AssistantAction] = []
    ids = [int(item) for item in (action_ids or []) if item]
    if ids:
        actions = await asyncio.to_thread(
            lambda: list(
                AssistantAction.objects.filter(
                    pk__in=ids,
                    user_id=link.user_id,
                    status=AssistantAction.STATUS_REQUIRES_CONFIRMATION,
                )
            )
        )

    outgoing = present_assistant_reply(
        content=str(content or ""),
        metadata=metadata,
        actions=actions,
        telegram_user_id=int(link.telegram_user_id),
        bot_id=bot.pk,
    )
    if not outgoing:
        return
    client = TelegramClient(token, timeout=30)
    await send_presented_messages(client, chat_id=link.chat_id, messages=outgoing)


def enqueue_telegram_delivery_for_session(
    *,
    session_id: int,
    assistant_message_id: int | None = None,
    action_ids: list[int] | None = None,
) -> bool:
    """Enqueue Celery delivery when the session is bound to Telegram. Returns True if queued."""
    from core_ui.models import ChatSession
    from core_ui.services.operator_channel import is_telegram_session

    session = ChatSession.objects.filter(pk=session_id).first()
    if not is_telegram_session(session):
        return False
    binding_exists = TelegramChatBinding.objects.filter(chat_session_id=session_id, is_active=True).exists()
    if not binding_exists:
        return False
    from telegram_hub.tasks import telegram_deliver_assistant_message

    telegram_deliver_assistant_message.delay(
        int(session_id),
        int(assistant_message_id) if assistant_message_id else None,
        [int(item) for item in (action_ids or [])],
    )
    return True
