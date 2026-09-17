"""Account linking: codes, /start handling, unlink."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from core_ui.models import UserNotificationPreference
from telegram_hub.models import TelegramAccountLink, TelegramBot, TelegramLinkCode

LINK_CODE_TTL_MINUTES = 10
LINK_CODES_PER_HOUR = 5


class TelegramLinkError(ValueError):
    pass


def _digest_code(code: str) -> str:
    return hashlib.sha256(str(code or "").strip().encode("utf-8")).hexdigest()


def deep_link_for_bot(bot: TelegramBot, code: str) -> str:
    username = str(bot.bot_username or "").strip().lstrip("@")
    if not username:
        return ""
    return f"https://t.me/{username}?start={code}"


@transaction.atomic
def create_link_code(*, user: User, bot: TelegramBot | None = None) -> dict[str, Any]:
    target = bot or TelegramBot.objects.filter(kind=TelegramBot.KIND_PLATFORM, is_active=True).order_by("id").first()
    if target is None:
        raise TelegramLinkError("Platform Telegram bot is not configured")

    since = timezone.now() - timedelta(hours=1)
    recent = TelegramLinkCode.objects.filter(user=user, created_at__gte=since).count()
    if recent >= LINK_CODES_PER_HOUR:
        raise TelegramLinkError(f"Too many link codes (max {LINK_CODES_PER_HOUR} per hour)")

    raw = secrets.token_urlsafe(8)
    code = TelegramLinkCode.objects.create(
        user=user,
        bot=target,
        code_digest=_digest_code(raw),
        expires_at=timezone.now() + timedelta(minutes=LINK_CODE_TTL_MINUTES),
    )
    return {
        "id": code.pk,
        "code": raw,
        "bot_id": target.pk,
        "bot_username": target.bot_username,
        "deep_link": deep_link_for_bot(target, raw),
        "expires_at": code.expires_at.isoformat(),
    }


def serialize_link(link: TelegramAccountLink) -> dict[str, Any]:
    return {
        "id": link.pk,
        "bot_id": link.bot_id,
        "bot_username": link.bot.bot_username if link.bot_id else "",
        "bot_kind": link.bot.kind if link.bot_id else "",
        "telegram_user_id": link.telegram_user_id,
        "chat_id": link.chat_id,
        "username": link.username,
        "status": link.status,
        "linked_at": link.linked_at.isoformat() if link.linked_at else None,
        "last_seen_at": link.last_seen_at.isoformat() if link.last_seen_at else None,
    }


@transaction.atomic
def consume_link_code(
    *,
    bot: TelegramBot,
    code: str,
    telegram_user_id: int,
    chat_id: str,
    username: str = "",
) -> TelegramAccountLink:
    digest = _digest_code(code)
    now = timezone.now()
    row = (
        TelegramLinkCode.objects.select_for_update()
        .select_related("user", "bot")
        .filter(bot=bot, code_digest=digest, used_at__isnull=True)
        .first()
    )
    if row is None:
        raise TelegramLinkError("Invalid or already used link code")
    if row.expires_at <= now:
        raise TelegramLinkError("Link code expired")

    # Personal bots: only owner may link.
    if bot.kind == TelegramBot.KIND_PERSONAL and bot.owner_id and bot.owner_id != row.user_id:
        raise TelegramLinkError("This personal bot can only be linked by its owner")

    row.used_at = now
    row.save(update_fields=["used_at"])

    link, _created = TelegramAccountLink.objects.select_for_update().update_or_create(
        bot=bot,
        telegram_user_id=int(telegram_user_id),
        defaults={
            "user": row.user,
            "chat_id": str(chat_id)[:64],
            "username": str(username or "")[:150],
            "status": TelegramAccountLink.STATUS_LINKED,
            "revoked_at": None,
            "last_seen_at": now,
        },
    )
    # Sync notification preference chat_id for platform bot.
    if bot.kind == TelegramBot.KIND_PLATFORM:
        pref, _ = UserNotificationPreference.objects.get_or_create(user=row.user)
        pref.telegram_chat_id = str(chat_id)[:64]
        pref.telegram_enabled = True
        pref.save(update_fields=["telegram_chat_id", "telegram_enabled", "updated_at"])
    return link


@transaction.atomic
def unlink_account(*, user: User, link_id: int) -> None:
    link = TelegramAccountLink.objects.select_for_update().filter(pk=link_id, user=user).first()
    if link is None:
        raise TelegramLinkError("Link not found")
    link.status = TelegramAccountLink.STATUS_REVOKED
    link.revoked_at = timezone.now()
    link.save(update_fields=["status", "revoked_at"])


def resolve_active_link(*, bot: TelegramBot, telegram_user_id: int) -> TelegramAccountLink | None:
    return (
        TelegramAccountLink.objects.select_related("user", "bot")
        .filter(
            bot=bot,
            telegram_user_id=int(telegram_user_id),
            status=TelegramAccountLink.STATUS_LINKED,
        )
        .first()
    )


def touch_link(link: TelegramAccountLink) -> None:
    link.last_seen_at = timezone.now()
    link.save(update_fields=["last_seen_at"])


def verify_action_callback_sig(
    *,
    action_id: int,
    telegram_user_id: int,
    bot_id: int,
    signature: str,
) -> bool:
    from django.conf import settings

    expected = hmac.new(
        str(settings.SECRET_KEY).encode("utf-8"),
        f"{action_id}:{telegram_user_id}:{bot_id}".encode(),
        hashlib.sha256,
    ).hexdigest()[:16]
    return hmac.compare_digest(expected, str(signature or ""))


def build_action_callback_data(
    *,
    decision: str,
    action_id: int,
    telegram_user_id: int,
    bot_id: int,
) -> str:
    from django.conf import settings

    flag = "c" if decision == "confirm" else "x"
    sig = hmac.new(
        str(settings.SECRET_KEY).encode("utf-8"),
        f"{action_id}:{telegram_user_id}:{bot_id}".encode(),
        hashlib.sha256,
    ).hexdigest()[:16]
    data = f"act:{flag}:{action_id}:{sig}"
    if len(data.encode("utf-8")) > 64:
        raise ValueError("callback data too long")
    return data
