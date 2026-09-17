"""Personal and admin Telegram hub APIs."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core_ui.context_processors import user_can_feature
from core_ui.decorators import require_any_feature, require_feature
from core_ui.services.notification_config import load_notification_config
from core_ui.services.user_notifications import get_or_create_prefs, resolve_user_telegram_chat_id
from telegram_hub.client import TelegramClient
from telegram_hub.models import TelegramAccountLink, TelegramBot
from telegram_hub.services.bots import (
    TelegramBotError,
    create_personal_bot,
    delete_personal_bot,
    ensure_platform_bot,
    get_bot_token,
    serialize_bot,
    update_personal_bot,
)
from telegram_hub.services.linking import (
    TelegramLinkError,
    create_link_code,
    serialize_link,
    unlink_account,
)


def _json_body(request) -> dict:
    try:
        return json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _err(msg: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": msg}, status=status)


def _personal_bots_allowed() -> bool:
    cfg = load_notification_config()
    return bool(cfg.get("telegram_personal_bots_enabled", True))


def _build_me_telegram_status(request) -> dict:
    cfg = load_notification_config()
    prefs = get_or_create_prefs(request.user)
    platform_bot = (
        TelegramBot.objects.filter(kind=TelegramBot.KIND_PLATFORM, is_active=True)
        .order_by("id")
        .first()
    )
    link = None
    if platform_bot is not None:
        link = (
            TelegramAccountLink.objects.select_related("bot")
            .filter(
                user=request.user,
                bot=platform_bot,
                status=TelegramAccountLink.STATUS_LINKED,
            )
            .order_by("-linked_at")
            .first()
        )

    hub_alive = False
    if platform_bot and platform_bot.last_poll_at:
        hub_alive = platform_bot.last_poll_at >= timezone.now() - timedelta(minutes=2)

    can_notifications = user_can_feature(request.user, "telegram_notifications", request=request)
    can_assistant_feature = user_can_feature(request.user, "telegram_assistant", request=request)
    can_chat = user_can_feature(request.user, "chat", request=request)
    platform_assistant_on = bool(cfg.get("telegram_assistant_enabled", True))
    assistant_allowed = bool(can_assistant_feature and can_chat and platform_assistant_on)
    personal_bots_allowed = bool(assistant_allowed and _personal_bots_allowed())
    bot_configured = bool(
        str(cfg.get("telegram_bot_token") or "").strip()
        or (platform_bot and platform_bot.token_digest)
    )

    return {
        "notifications_allowed": can_notifications,
        "notifications_enabled": bool(prefs.get("telegram_enabled")),
        "chat_id": resolve_user_telegram_chat_id(request.user) or str(prefs.get("telegram_chat_id") or ""),
        "prefs_chat_id": str(prefs.get("telegram_chat_id") or ""),
        "linked": link is not None,
        "bot_username": (platform_bot.bot_username if platform_bot else "") or "",
        "bot_configured": bot_configured,
        "assistant_allowed": assistant_allowed,
        "personal_bots_allowed": personal_bots_allowed,
        "hub_hint": "ok" if hub_alive else "worker_offline",
        "link": serialize_link(link) if link else None,
    }


@login_required
@require_any_feature("telegram_notifications", "telegram_assistant")
@require_http_methods(["GET"])
def api_me_telegram_status(request):
    return JsonResponse(_build_me_telegram_status(request))


@login_required
@require_feature("telegram_assistant")
@require_http_methods(["POST"])
def api_me_telegram_link_codes(request):
    ensure_platform_bot()
    body = _json_body(request)
    bot_id = body.get("bot_id")
    bot = None
    if bot_id:
        bot = TelegramBot.objects.filter(pk=bot_id, is_active=True).first()
        if bot is None:
            return _err("Bot not found", 404)
        if bot.kind == TelegramBot.KIND_PERSONAL and bot.owner_id != request.user.pk:
            return _err("Forbidden", 403)
    try:
        payload = create_link_code(user=request.user, bot=bot)
    except TelegramLinkError as exc:
        return _err(str(exc))
    return JsonResponse(payload, status=201)


@login_required
@require_feature("telegram_assistant")
@require_http_methods(["GET"])
def api_me_telegram_links(request):
    links = TelegramAccountLink.objects.select_related("bot").filter(user=request.user).order_by("-linked_at")
    return JsonResponse({"links": [serialize_link(link) for link in links]})


@login_required
@require_feature("telegram_assistant")
@require_http_methods(["DELETE"])
def api_me_telegram_link_delete(request, link_id: int):
    try:
        unlink_account(user=request.user, link_id=link_id)
    except TelegramLinkError as exc:
        return _err(str(exc), 404)
    return JsonResponse({"ok": True})


@login_required
@require_feature("telegram_assistant")
@require_http_methods(["GET", "POST"])
def api_me_telegram_bots(request):
    if request.method == "GET":
        bots = TelegramBot.objects.filter(owner=request.user, kind=TelegramBot.KIND_PERSONAL).order_by("-id")
        return JsonResponse({"bots": [serialize_bot(bot) for bot in bots]})

    if not _personal_bots_allowed():
        return _err("Personal Telegram bots are disabled by the administrator.", 403)
    data = _json_body(request)
    try:
        bot = create_personal_bot(
            owner=request.user,
            token=str(data.get("token") or data.get("telegram_bot_token") or ""),
            name=str(data.get("name") or ""),
            mode=str(data.get("mode") or TelegramBot.MODE_ASSISTANT),
            system_prompt=str(data.get("system_prompt") or ""),
            provider_binding=data.get("provider_binding") if isinstance(data.get("provider_binding"), dict) else {},
        )
    except TelegramBotError as exc:
        return _err(str(exc))
    return JsonResponse(serialize_bot(bot), status=201)


@login_required
@require_feature("telegram_assistant")
@require_http_methods(["GET", "PATCH", "DELETE"])
def api_me_telegram_bot_detail(request, bot_id: int):
    bot = TelegramBot.objects.filter(pk=bot_id, owner=request.user, kind=TelegramBot.KIND_PERSONAL).first()
    if bot is None:
        return _err("Bot not found", 404)
    if request.method == "GET":
        return JsonResponse(serialize_bot(bot))
    if request.method == "DELETE":
        delete_personal_bot(bot)
        return JsonResponse({"ok": True})
    data = _json_body(request)
    try:
        bot = update_personal_bot(bot, data)
    except TelegramBotError as exc:
        return _err(str(exc))
    return JsonResponse(serialize_bot(bot))


@login_required
@require_feature("telegram_assistant")
@require_http_methods(["POST"])
def api_me_telegram_bot_test(request, bot_id: int):
    bot = TelegramBot.objects.filter(pk=bot_id, owner=request.user, kind=TelegramBot.KIND_PERSONAL).first()
    if bot is None:
        return _err("Bot not found", 404)
    token = get_bot_token(bot)
    if not token:
        return _err("Bot token missing", 400)
    link = (
        TelegramAccountLink.objects.filter(
            user=request.user,
            bot=bot,
            status=TelegramAccountLink.STATUS_LINKED,
        )
        .order_by("-linked_at")
        .first()
    )
    chat_id = link.chat_id if link else ""
    if not chat_id:
        return _err("Сначала привяжите этот бот к своему Telegram через /start <код>.", 400)

    async def _send():
        client = TelegramClient(token, timeout=15)
        return await client.send_message(
            chat_id=chat_id,
            text="✅ Тест личного Telegram-бота WEU Platform успешен.",
        )

    try:
        asyncio.run(_send())
    except Exception as exc:
        return _err(str(exc))
    return JsonResponse({"ok": True, "message": "Test sent"})


@login_required
@require_feature("studio_notifications")
@require_http_methods(["GET"])
def api_studio_telegram_bots(request):
    if not getattr(request.user, "is_staff", False):
        return _err("Admin access required", 403)
    bots = TelegramBot.objects.select_related("owner").order_by("kind", "id")
    return JsonResponse({"bots": [serialize_bot(bot) for bot in bots]})


@login_required
@require_feature("studio_notifications")
@require_http_methods(["PATCH"])
def api_studio_telegram_bot_detail(request, bot_id: int):
    if not getattr(request.user, "is_staff", False):
        return _err("Admin access required", 403)
    bot = TelegramBot.objects.filter(pk=bot_id).first()
    if bot is None:
        return _err("Bot not found", 404)
    data = _json_body(request)
    fields = []
    if "is_active" in data:
        bot.is_active = bool(data.get("is_active"))
        fields.append("is_active")
    if "mode" in data and str(data.get("mode")) in {TelegramBot.MODE_ASSISTANT, TelegramBot.MODE_PIPELINE}:
        bot.mode = str(data.get("mode"))
        fields.append("mode")
    if fields:
        fields.append("updated_at")
        bot.save(update_fields=fields)
    return JsonResponse(serialize_bot(bot))
