"""Per-user notification preference helpers."""

from __future__ import annotations

from django.contrib.auth.models import User

from core_ui.models import UserNotificationPreference


def serialize_prefs(pref: UserNotificationPreference) -> dict:
    return {
        "telegram_chat_id": str(pref.telegram_chat_id or "").strip(),
        "telegram_enabled": bool(pref.telegram_enabled),
        "updated_at": pref.updated_at.isoformat() if pref.updated_at else None,
    }


def get_or_create_prefs(user: User) -> dict:
    pref, _ = UserNotificationPreference.objects.get_or_create(user=user)
    return serialize_prefs(pref)


def update_prefs(user: User, data: dict) -> dict:
    pref, _ = UserNotificationPreference.objects.get_or_create(user=user)
    if "telegram_chat_id" in data:
        pref.telegram_chat_id = str(data.get("telegram_chat_id") or "").strip()[:64]
    if "telegram_enabled" in data:
        pref.telegram_enabled = bool(data.get("telegram_enabled"))
    pref.save()
    return serialize_prefs(pref)


def resolve_user_telegram_chat_id(user: User | None) -> str:
    if user is None or not getattr(user, "pk", None):
        return ""
    # Prefer linked Telegram account on the platform bot.
    try:
        from telegram_hub.models import TelegramAccountLink, TelegramBot

        link = (
            TelegramAccountLink.objects.filter(
                user_id=user.pk,
                status=TelegramAccountLink.STATUS_LINKED,
                bot__kind=TelegramBot.KIND_PLATFORM,
                bot__is_active=True,
            )
            .order_by("-linked_at")
            .first()
        )
        if link and link.chat_id:
            return str(link.chat_id).strip()
    except Exception:  # noqa: S110 — hub tables may be absent before migration; fall back to prefs
        pass

    pref = UserNotificationPreference.objects.filter(user_id=user.pk).first()
    if not pref or not pref.telegram_enabled:
        return ""
    return str(pref.telegram_chat_id or "").strip()
