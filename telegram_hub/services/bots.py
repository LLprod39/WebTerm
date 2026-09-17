"""Bot token helpers and platform bot provisioning."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from core_ui.managed_secrets import delete_telegram_bot_token, get_telegram_bot_token, set_telegram_bot_token
from core_ui.services.notification_config import load_notification_config
from studio.telegram_delivery_service import telegram_bot_token_digest
from telegram_hub.client import TelegramAPIError, TelegramClient, mask_bot_token
from telegram_hub.models import TelegramBot


class TelegramBotError(ValueError):
    pass


def digest_token(token: str) -> str:
    return telegram_bot_token_digest(token)


def serialize_bot(bot: TelegramBot, *, include_token_mask: bool = False) -> dict[str, Any]:
    payload = {
        "id": bot.pk,
        "kind": bot.kind,
        "name": bot.name,
        "bot_username": bot.bot_username,
        "bot_user_id": bot.bot_user_id,
        "is_active": bot.is_active,
        "mode": bot.mode,
        "pipeline_id": bot.pipeline_id,
        "system_prompt": bot.system_prompt,
        "provider_binding": bot.provider_binding or {},
        "allow_group_chats": bot.allow_group_chats,
        "allowed_chat_ids": bot.allowed_chat_ids or [],
        "last_poll_at": bot.last_poll_at.isoformat() if bot.last_poll_at else None,
        "last_error": bot.last_error,
        "owner_id": bot.owner_id,
        "created_at": bot.created_at.isoformat() if bot.created_at else None,
        "updated_at": bot.updated_at.isoformat() if bot.updated_at else None,
        "has_token": bool(bot.token_digest),
    }
    if include_token_mask:
        token = get_telegram_bot_token(bot.pk)
        payload["telegram_bot_token"] = mask_bot_token(token)
    return payload


def get_bot_token(bot: TelegramBot) -> str:
    return get_telegram_bot_token(bot.pk)


def validate_token_via_get_me(token: str) -> dict[str, Any]:
    async def _run():
        client = TelegramClient(token, timeout=15)
        return await client.get_me()

    try:
        return asyncio.run(_run())
    except TelegramAPIError as exc:
        raise TelegramBotError(f"Invalid Telegram bot token: {exc}") from exc
    except Exception as exc:
        raise TelegramBotError(f"Failed to validate Telegram bot token: {exc}") from exc


def _default_platform_mode() -> str:
    """Legacy installs with the Studio Telegram pipeline keep pipeline mode; otherwise assistant."""
    try:
        from studio.models import Pipeline
        from studio.services.telegram_bot_pipeline import TELEGRAM_BOT_PIPELINE_NAME

        if Pipeline.objects.filter(name=TELEGRAM_BOT_PIPELINE_NAME).exists():
            return TelegramBot.MODE_PIPELINE
    except Exception:  # noqa: S110 — studio tables may be unavailable during early bootstrap
        pass
    return TelegramBot.MODE_ASSISTANT


def _refresh_bot_profile(bot: TelegramBot, raw_token: str) -> None:
    """Best-effort getMe outside any transaction (network call)."""
    from django.conf import settings as dj_settings

    if getattr(dj_settings, "TESTING", False):
        return
    try:
        me = validate_token_via_get_me(raw_token)
    except TelegramBotError as exc:
        bot.last_error = str(exc)[:500]
        bot.save(update_fields=["last_error", "updated_at"])
        return
    bot.bot_username = str(me.get("username") or "")[:64]
    bot.bot_user_id = int(me.get("id")) if me.get("id") is not None else bot.bot_user_id
    bot.last_error = ""
    bot.save(update_fields=["bot_username", "bot_user_id", "last_error", "updated_at"])


def ensure_platform_bot(*, token: str | None = None, mode: str | None = None) -> TelegramBot | None:
    """Create or refresh the platform TelegramBot from notification config / env.

    Idempotent and cheap on the hot path: the encrypted token is only rewritten
    when the digest changes, and getMe is only called when the profile is missing
    or the token changed.
    """
    cfg = load_notification_config()
    raw_token = (token or "").strip() or str(cfg.get("telegram_bot_token") or "").strip()
    if not raw_token:
        raw_token = (os.getenv("TELEGRAM_BOT_POLL_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not raw_token:
        return TelegramBot.objects.filter(kind=TelegramBot.KIND_PLATFORM).order_by("id").first()

    digest = digest_token(raw_token)
    token_changed = False
    with transaction.atomic():
        bot = TelegramBot.objects.filter(kind=TelegramBot.KIND_PLATFORM).order_by("id").first()
        if bot is None:
            bot = TelegramBot.objects.filter(token_digest=digest).first()
        if bot is None:
            bot = TelegramBot.objects.create(
                kind=TelegramBot.KIND_PLATFORM,
                owner=None,
                name="Platform bot",
                token_digest=digest,
                mode=mode or _default_platform_mode(),
            )
            token_changed = True
        else:
            fields: list[str] = []
            if bot.token_digest != digest:
                bot.token_digest = digest
                token_changed = True
                fields.append("token_digest")
            if bot.kind != TelegramBot.KIND_PLATFORM or bot.owner_id is not None:
                bot.kind = TelegramBot.KIND_PLATFORM
                bot.owner = None
                fields.extend(["kind", "owner"])
            if mode and bot.mode != mode:
                bot.mode = mode
                fields.append("mode")
            if not bot.name:
                bot.name = "Platform bot"
                fields.append("name")
            if fields:
                bot.save(update_fields=[*fields, "updated_at"])
        if token_changed or not get_telegram_bot_token(bot.pk):
            set_telegram_bot_token(bot.pk, raw_token)

    if token_changed or not bot.bot_username:
        _refresh_bot_profile(bot, raw_token)
    return bot


@transaction.atomic
def create_personal_bot(
    *,
    owner: User,
    token: str,
    name: str = "",
    mode: str = TelegramBot.MODE_ASSISTANT,
    system_prompt: str = "",
    provider_binding: dict | None = None,
) -> TelegramBot:
    raw = str(token or "").strip()
    if not raw:
        raise TelegramBotError("Bot token is required")
    digest = digest_token(raw)
    if TelegramBot.objects.filter(token_digest=digest).exists():
        raise TelegramBotError("This bot token is already registered")
    platform_token = str(load_notification_config().get("telegram_bot_token") or "").strip()
    if platform_token and digest_token(platform_token) == digest:
        raise TelegramBotError("This token belongs to the platform bot")

    me = validate_token_via_get_me(raw)
    bot = TelegramBot.objects.create(
        owner=owner,
        kind=TelegramBot.KIND_PERSONAL,
        name=(name or str(me.get("first_name") or me.get("username") or "My bot"))[:120],
        bot_username=str(me.get("username") or "")[:64],
        bot_user_id=int(me.get("id")) if me.get("id") is not None else None,
        token_digest=digest,
        is_active=True,
        mode=mode if mode in {TelegramBot.MODE_ASSISTANT, TelegramBot.MODE_PIPELINE} else TelegramBot.MODE_ASSISTANT,
        system_prompt=str(system_prompt or ""),
        provider_binding=provider_binding or {},
    )
    set_telegram_bot_token(bot.pk, raw)
    return bot


@transaction.atomic
def update_personal_bot(bot: TelegramBot, data: dict) -> TelegramBot:
    fields: list[str] = []
    if "name" in data:
        bot.name = str(data.get("name") or "")[:120]
        fields.append("name")
    if "mode" in data:
        mode = str(data.get("mode") or "").strip()
        if mode in {TelegramBot.MODE_ASSISTANT, TelegramBot.MODE_PIPELINE}:
            bot.mode = mode
            fields.append("mode")
    if "system_prompt" in data:
        bot.system_prompt = str(data.get("system_prompt") or "")
        fields.append("system_prompt")
    if "provider_binding" in data and isinstance(data.get("provider_binding"), dict):
        bot.provider_binding = data["provider_binding"]
        fields.append("provider_binding")
    if "is_active" in data:
        bot.is_active = bool(data.get("is_active"))
        fields.append("is_active")
    if "allow_group_chats" in data:
        bot.allow_group_chats = bool(data.get("allow_group_chats"))
        fields.append("allow_group_chats")
    if "allowed_chat_ids" in data and isinstance(data.get("allowed_chat_ids"), list):
        bot.allowed_chat_ids = [str(x).strip() for x in data["allowed_chat_ids"] if str(x).strip()]
        fields.append("allowed_chat_ids")
    if "pipeline_id" in data:
        pipeline_id = data.get("pipeline_id")
        if pipeline_id:
            from studio.models import Pipeline

            # Personal bots may only trigger pipelines owned by the bot owner.
            pipeline = Pipeline.objects.filter(pk=int(pipeline_id)).first()
            if pipeline is None:
                raise TelegramBotError("Pipeline not found")
            if bot.owner_id is not None and pipeline.owner_id != bot.owner_id:
                raise TelegramBotError("Pipeline belongs to another user")
            bot.pipeline_id = pipeline.pk
        else:
            bot.pipeline_id = None
        fields.append("pipeline_id")
    if "token" in data and str(data.get("token") or "").strip():
        raw = str(data["token"]).strip()
        digest = digest_token(raw)
        conflict = TelegramBot.objects.filter(token_digest=digest).exclude(pk=bot.pk).exists()
        if conflict:
            raise TelegramBotError("This bot token is already registered")
        me = validate_token_via_get_me(raw)
        bot.token_digest = digest
        bot.bot_username = str(me.get("username") or "")[:64]
        bot.bot_user_id = int(me.get("id")) if me.get("id") is not None else bot.bot_user_id
        bot.last_error = ""
        fields.extend(["token_digest", "bot_username", "bot_user_id", "last_error"])
        set_telegram_bot_token(bot.pk, raw)
    if fields:
        fields.append("updated_at")
        bot.save(update_fields=list(dict.fromkeys(fields)))
    return bot


@transaction.atomic
def delete_personal_bot(bot: TelegramBot) -> None:
    bot_id = bot.pk
    bot.delete()
    delete_telegram_bot_token(bot_id)


def mark_bot_unauthorized(bot: TelegramBot, error: str) -> None:
    bot.is_active = False
    bot.last_error = str(error or "Unauthorized")[:500]
    bot.save(update_fields=["is_active", "last_error", "updated_at"])


def touch_bot_poll(bot: TelegramBot, *, error: str = "") -> None:
    bot.last_poll_at = timezone.now()
    bot.last_error = str(error or "")[:500]
    bot.save(update_fields=["last_poll_at", "last_error", "updated_at"])


def list_active_bots_for_polling() -> list[TelegramBot]:
    ensure_platform_bot()
    return list(TelegramBot.objects.filter(is_active=True).order_by("id"))
