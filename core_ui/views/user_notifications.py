"""API for the current user's personal Telegram destination."""

from __future__ import annotations

import asyncio
import json

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from core_ui.services import user_notifications as prefs_service
from core_ui.services.notification_config import load_notification_config
from telegram_hub.client import TelegramClient


def _json_body(request) -> dict:
    try:
        return json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _rate_limited(user_id: int, action: str, *, limit: int = 5, window: int = 60) -> bool:
    key = f"tg_test_rl:{action}:{user_id}"
    count = cache.get(key)
    if count is None:
        cache.set(key, 1, window)
        return False
    if int(count) >= limit:
        return True
    cache.incr(key)
    return False


@login_required
@require_feature("telegram_notifications")
@require_http_methods(["GET", "PUT", "PATCH"])
def api_my_notifications(request):
    """GET/PUT /api/me/notifications/ — personal Telegram chat destination."""
    if request.method == "GET":
        return JsonResponse(prefs_service.get_or_create_prefs(request.user))
    data = _json_body(request)
    return JsonResponse(prefs_service.update_prefs(request.user, data))


@login_required
@require_feature("telegram_notifications")
@require_http_methods(["POST"])
def api_my_notifications_test_telegram(request):
    """POST /api/me/notifications/test-telegram/ — test via platform bot + my chat id."""
    if _rate_limited(request.user.pk, "me"):
        return JsonResponse({"error": "Слишком много тестовых сообщений. Подождите минуту."}, status=429)

    prefs = prefs_service.get_or_create_prefs(request.user)
    body = _json_body(request)
    chat_id = str(body.get("telegram_chat_id") or prefs.get("telegram_chat_id") or "").strip()
    if not chat_id:
        return JsonResponse({"error": "Укажите свой Telegram chat ID."}, status=400)
    if prefs.get("telegram_enabled") is False and "telegram_chat_id" not in body:
        return JsonResponse({"error": "Личные Telegram-уведомления выключены."}, status=400)

    cfg = load_notification_config()
    bot_token = str(cfg.get("telegram_bot_token") or "").strip()
    if not bot_token:
        return JsonResponse(
            {"error": "Бот платформы ещё не настроен. Попросите администратора указать токен бота."},
            status=400,
        )

    async def _send():
        client = TelegramClient(bot_token, timeout=15)
        return await client.send_message(
            chat_id=chat_id,
            text="✅ WEU Platform — ваш личный Telegram настроен. Сюда будут приходить отчёты агентов.",
            disable_web_page_preview=True,
        )

    try:
        asyncio.run(_send())
        return JsonResponse({"ok": True, "message": f"Тест отправлен в chat {chat_id}"})
    except Exception as exc:
        return JsonResponse({"error": f"Не удалось отправить: {exc}"}, status=400)
