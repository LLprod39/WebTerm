"""Route Telegram updates for a single bot (sync ORM + async Telegram client)."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from django.core.cache import cache
from django.utils import timezone
from loguru import logger

from core_ui.access import feature_allowed_for_user
from core_ui.services.notification_config import load_notification_config
from core_ui.services.operator_rate_limit import MAX_MESSAGE_CHARS
from studio.telegram_delivery_service import (
    record_telegram_approval_callback,
    store_telegram_operator_reply,
)
from telegram_hub.assistant_bridge import (
    _action_card_text,
    _inline_keyboard_for_action,
    handle_action_callback,
    peek_playbook_vars_pending,
    start_new_telegram_session,
    try_consume_playbook_vars_reply,
    try_typed_confirm_from_reply,
)
from telegram_hub.client import TelegramClient, redacted_chat_id
from telegram_hub.models import TelegramAccountLink, TelegramBot
from telegram_hub.services.bots import get_bot_token
from telegram_hub.services.linking import (
    TelegramLinkError,
    consume_link_code,
    resolve_active_link,
    touch_link,
    unlink_account,
)

INGRESS_LIMIT_PER_MINUTE = 20

BOT_COMMANDS = [
    {"command": "start", "description": "Привязать аккаунт / начать"},
    {"command": "new", "description": "Новая сессия чата"},
    {"command": "status", "description": "Статус привязки"},
    {"command": "whoami", "description": "Кто я на платформе"},
    {"command": "unlink", "description": "Отвязать Telegram"},
    {"command": "help", "description": "Справка"},
]


def _throttle(telegram_user_id: int) -> bool:
    key = f"tg_ingress:{telegram_user_id}"
    count = cache.get(key)
    if count is None:
        cache.set(key, 1, 60)
        return False
    if int(count) >= INGRESS_LIMIT_PER_MINUTE:
        return True
    cache.incr(key)
    return False


def _assistant_globally_enabled() -> bool:
    cfg = load_notification_config()
    return bool(cfg.get("telegram_assistant_enabled", True))


def _run(coro):
    return asyncio.run(coro)


class TelegramUpdateRouter:
    def __init__(self, bot: TelegramBot, client: TelegramClient):
        self.bot = bot
        self.client = client

    def handle_update(self, update: dict[str, Any]) -> str:
        callback = update.get("callback_query") or {}
        if isinstance(callback, dict) and callback:
            return self._handle_callback(callback)

        message = update.get("message") or {}
        if not isinstance(message, dict):
            return "ignored"

        chat = message.get("chat") or {}
        chat_type = str(chat.get("type") or "")
        if chat_type not in {"private", ""} and not self.bot.allow_group_chats:
            return "ignored"

        if message.get("reply_to_message"):
            handled = self._handle_reply(message)
            if handled != "ignored":
                return handled

        text = str(message.get("text") or "").strip()
        if not text:
            return "ignored"

        if text.startswith("/"):
            return self._handle_command(message, text)

        return self._handle_text(message, text)

    def _send(self, chat_id: str | int, text: str, **kwargs) -> None:
        with contextlib.suppress(Exception):
            _run(self.client.send_message(chat_id=chat_id, text=text, **kwargs))

    def _deliver_action_result(
        self,
        *,
        chat_id: str | int,
        telegram_user_id: int,
        result,
        message_id: int | None = None,
    ) -> None:
        if message_id:
            with contextlib.suppress(Exception):
                _run(self.client.edit_message_reply_markup(chat_id=chat_id, message_id=int(message_id)))
        for line in list(getattr(result, "chat_lines", None) or []):
            text = str(line or "").strip()
            if text:
                self._send(chat_id, text)
        for action in list(getattr(result, "followup_actions", None) or []):
            markup = _inline_keyboard_for_action(
                action=action,
                telegram_user_id=int(telegram_user_id),
                bot_id=self.bot.pk,
            )
            self._send(chat_id, _action_card_text(action), reply_markup=markup)

    def _handle_callback(self, callback: dict[str, Any]) -> str:
        data = str(callback.get("data") or "")
        callback_message = callback.get("message") or {}
        callback_chat = callback_message.get("chat") or {}
        callback_from = callback.get("from") or {}
        chat_id = str(callback_chat.get("id") or "")
        from_id = callback_from.get("id")
        callback_id = str(callback.get("id") or "").strip()
        message_id = callback_message.get("message_id")

        if data.startswith("approval:"):
            token = get_bot_token(self.bot)
            accepted, answer = record_telegram_approval_callback(
                bot_token=token,
                callback_data=data,
                chat_id=chat_id,
                from_username=callback_from.get("username") or callback_from.get("first_name") or "",
            )
            if callback_id:
                with contextlib.suppress(Exception):
                    _run(self.client.answer_callback_query(callback_id, answer))
            return "approval" if accepted else "ignored"

        if data.startswith("act:"):
            if callback_id:
                with contextlib.suppress(Exception):
                    _run(self.client.answer_callback_query(callback_id, "Принято…"))
            with contextlib.suppress(Exception):
                _run(self.client.send_chat_action(chat_id=chat_id, action="typing"))
            result = handle_action_callback(
                bot=self.bot,
                telegram_user_id=int(from_id or 0),
                chat_id=chat_id,
                callback_data=data,
                message_id=int(message_id) if message_id else None,
            )
            if chat_id:
                self._deliver_action_result(
                    chat_id=chat_id,
                    telegram_user_id=int(from_id or 0),
                    result=result,
                    message_id=int(message_id) if message_id else None,
                )
            return "action" if result.ok else "ignored"

        return "ignored"

    def _handle_reply(self, message: dict[str, Any]) -> str:
        token = get_bot_token(self.bot)
        if store_telegram_operator_reply(token, message):
            return "reply"

        from servers.agents.agent_hitl import try_store_agent_telegram_reply

        if try_store_agent_telegram_reply(token, message):
            return "agent_reply"

        from_user = message.get("from") or {}
        text = str(message.get("text") or "").strip()
        result = try_typed_confirm_from_reply(
            bot=self.bot,
            telegram_user_id=int(from_user.get("id") or 0),
            text=text,
        )
        if result is not None:
            chat = message.get("chat") or {}
            chat_id = chat.get("id")
            if chat_id:
                self._deliver_action_result(
                    chat_id=chat_id,
                    telegram_user_id=int(from_user.get("id") or 0),
                    result=result,
                )
            return "typed_confirm"
        return "ignored"

    def _handle_command(self, message: dict[str, Any], text: str) -> str:
        chat = message.get("chat") or {}
        from_user = message.get("from") or {}
        chat_id = str(chat.get("id") or "")
        parts = text.split(maxsplit=1)
        cmd = parts[0].split("@")[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "/start":
            if arg:
                try:
                    link = consume_link_code(
                        bot=self.bot,
                        code=arg,
                        telegram_user_id=int(from_user.get("id") or 0),
                        chat_id=chat_id,
                        username=str(from_user.get("username") or ""),
                    )
                    self._send(
                        chat_id,
                        (
                            f"✅ Привязано к аккаунту «{link.user.username}».\n"
                            "Пишите сюда — я отвечу как ассистент платформы.\n"
                            "Команды: /new /status /whoami /unlink /help"
                        ),
                    )
                    return "linked"
                except TelegramLinkError as exc:
                    self._send(chat_id, f"⚠️ {exc}")
                    return "link_failed"
            self._send(
                chat_id,
                (
                    "Чтобы привязать аккаунт, откройте Настройки → Telegram на платформе "
                    "и нажмите «Привязать», либо отправьте /start <код>."
                ),
            )
            return "start_help"

        link = resolve_active_link(bot=self.bot, telegram_user_id=int(from_user.get("id") or 0))
        if cmd == "/help":
            self._send(
                chat_id,
                (
                    "Команды:\n"
                    "/start <код> — привязать аккаунт\n"
                    "/new — новая сессия чата\n"
                    "/status — статус\n"
                    "/whoami — ваш пользователь на платформе\n"
                    "/unlink — отвязать\n"
                    "/help — справка"
                ),
            )
            return "help"

        if link is None:
            self._send(
                chat_id,
                "Аккаунт не привязан. Откройте Настройки → Telegram и создайте код привязки.",
            )
            return "unlinked"

        if cmd == "/status":
            self._send(
                chat_id,
                (
                    f"Бот: @{self.bot.bot_username or self.bot.pk}\n"
                    f"Режим: {self.bot.mode}\n"
                    f"Пользователь: {link.user.username}\n"
                    f"Chat: {redacted_chat_id(link.chat_id)}"
                ),
            )
            return "status"

        if cmd == "/whoami":
            self._send(chat_id, f"Вы: {link.user.username} (id={link.user_id})")
            return "whoami"

        if cmd == "/new":
            from telegram_hub.assistant_bridge import pop_playbook_vars_pending

            pop_playbook_vars_pending(link.pk)
            start_new_telegram_session(link)
            self._send(chat_id, "🆕 Новая сессия чата создана.")
            return "new_session"

        if cmd == "/unlink":
            unlink_account(user=link.user, link_id=link.pk)
            self._send(chat_id, "Отвязано. Можете снова /start <код>.")
            return "unlinked_now"

        return "ignored"

    def _handle_text(self, message: dict[str, Any], text: str) -> str:
        chat = message.get("chat") or {}
        from_user = message.get("from") or {}
        chat_id = str(chat.get("id") or "")
        tg_user_id = int(from_user.get("id") or 0)

        link = resolve_active_link(bot=self.bot, telegram_user_id=tg_user_id)
        if link is None:
            if self.bot.mode == TelegramBot.MODE_PIPELINE and self._chat_allowed(chat_id):
                return self._launch_pipeline(message, text, chat_id, from_user)
            self._send(
                chat_id,
                "Аккаунт не привязан. Откройте Настройки → Telegram и привяжите бота.",
            )
            return "unlinked"

        if not link.user.is_active:
            self._send(chat_id, "Ваш аккаунт на платформе отключён.")
            return "user_inactive"

        if _throttle(tg_user_id):
            self._send(chat_id, "Слишком много сообщений. Подождите минуту.")
            return "throttled"

        touch_link(link)
        text = text[:MAX_MESSAGE_CHARS]

        if peek_playbook_vars_pending(link.pk):
            result = try_consume_playbook_vars_reply(link=link, text=text)
            if result is not None:
                self._deliver_action_result(
                    chat_id=chat_id,
                    telegram_user_id=tg_user_id,
                    result=result,
                )
                return "playbook_vars"

        if self.bot.mode == TelegramBot.MODE_PIPELINE:
            if not self._chat_allowed(chat_id, link=link):
                self._send(chat_id, "Этот чат не в allowlist бота.")
                return "denied"
            return self._launch_pipeline(message, text, chat_id, from_user)

        if not _assistant_globally_enabled():
            self._send(chat_id, "ИИ-ассистент в Telegram временно отключён.")
            return "disabled"
        if not feature_allowed_for_user(link.user, "telegram_assistant") or not feature_allowed_for_user(
            link.user, "chat"
        ):
            self._send(
                chat_id,
                "Нет доступа к ИИ-ассистенту в Telegram. Попросите администратора выдать право telegram_assistant.",
            )
            return "forbidden"

        if self.bot.kind == TelegramBot.KIND_PERSONAL and self.bot.owner_id != link.user_id:
            self._send(chat_id, "Этот бот доступен только владельцу.")
            return "denied"

        from telegram_hub.tasks import telegram_assistant_turn

        with contextlib.suppress(Exception):
            _run(self.client.send_chat_action(chat_id=chat_id, action="typing"))
        telegram_assistant_turn.delay(
            link.pk,
            text,
            int(message.get("message_id") or 0) or None,
        )
        return "assistant_queued"

    def _chat_allowed(self, chat_id: str, *, link: TelegramAccountLink | None = None) -> bool:
        allowed = [str(x).strip() for x in (self.bot.allowed_chat_ids or []) if str(x).strip()]
        if allowed:
            return chat_id in allowed
        return link is not None

    def _launch_pipeline(self, message: dict, text: str, chat_id: str, from_user: dict) -> str:
        from app.runtime_limits import get_pipeline_run_limit_error
        from studio.models import Pipeline, PipelineTrigger
        from studio.pipeline.pipeline_runtime_context import (
            validate_pipeline_entry_branch,
            validate_pipeline_runtime_context,
        )
        from studio.pipeline.pipeline_validation import validate_pipeline_definition
        from studio.services.telegram_bot_pipeline import TELEGRAM_BOT_PIPELINE_NAME
        from studio.trigger_dispatch import (
            create_pipeline_run,
            launch_pipeline_run_async,
            pipeline_run_creation_error_details,
        )

        pipeline = self.bot.pipeline
        if pipeline is None and self.bot.kind == TelegramBot.KIND_PLATFORM:
            # Legacy default: the Studio "Telegram Bot — Server Agent" pipeline (platform bot only).
            pipeline = Pipeline.objects.filter(name=TELEGRAM_BOT_PIPELINE_NAME).order_by("-id").first()
        if pipeline is None:
            self._send(chat_id, "Pipeline для Telegram-бота не настроен.")
            return "no_pipeline"

        trigger = (
            pipeline.triggers.filter(trigger_type=PipelineTrigger.TYPE_WEBHOOK, is_active=True).order_by("id").first()
        )
        if trigger is None:
            self._send(chat_id, "У pipeline нет активного webhook-триггера.")
            return "no_trigger"

        context = {
            "user_task": text,
            "tg_chat_id": chat_id,
            "tg_user_name": str(from_user.get("first_name") or from_user.get("username") or "User"),
            "tg_message_id": str(message.get("message_id") or ""),
        }
        limit_error = get_pipeline_run_limit_error(pipeline.owner)
        if limit_error:
            self._send(chat_id, "Лимит запусков pipeline исчерпан.")
            return "limit"

        errors = validate_pipeline_definition(
            nodes=pipeline.nodes,
            edges=pipeline.edges,
            owner=pipeline.owner,
            graph_version=pipeline.graph_version,
        )
        if errors:
            logger.warning("telegram pipeline validation failed: {}", errors[:2])
            return "invalid"
        branch_errors = validate_pipeline_entry_branch(pipeline.nodes, pipeline.edges, trigger.node_id)
        if branch_errors:
            return "invalid"
        context_errors = validate_pipeline_runtime_context(
            pipeline.nodes,
            context,
            edges=pipeline.edges,
            entry_node_id=trigger.node_id,
        )
        if context_errors:
            return "invalid"

        try:
            run = create_pipeline_run(
                pipeline=pipeline,
                trigger=trigger,
                context=context,
                trigger_data={
                    "source": "telegram_hub",
                    "chat_id": chat_id,
                    "text": text[:500],
                    "bot_id": self.bot.pk,
                },
                entry_node_id=trigger.node_id,
            )
        except ValueError as exc:
            logger.warning("pipeline run creation failed: {}", pipeline_run_creation_error_details(exc)[:2])
            return "create_failed"
        trigger.last_triggered_at = timezone.now()
        trigger.save(update_fields=["last_triggered_at"])
        launch_pipeline_run_async(run)
        return "launched"
