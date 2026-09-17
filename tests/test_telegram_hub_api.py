"""Telegram hub linking + bots API tests."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client

from core_ui.managed_secrets import set_telegram_bot_token
from core_ui.models import UserAppPermission
from studio.telegram_delivery_service import telegram_bot_token_digest
from telegram_hub.models import TelegramAccountLink, TelegramBot
from telegram_hub.services.linking import (
    TelegramLinkError,
    consume_link_code,
    create_link_code,
    unlink_account,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _grant(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(user=user, feature=feature, defaults={"allowed": True})


def _deny(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(user=user, feature=feature, defaults={"allowed": False})


def _platform_bot(token: str = "123456:platform-token") -> TelegramBot:
    bot = TelegramBot.objects.create(
        kind=TelegramBot.KIND_PLATFORM,
        name="Platform",
        bot_username="platform_bot",
        token_digest=telegram_bot_token_digest(token),
        is_active=True,
        mode=TelegramBot.MODE_ASSISTANT,
    )
    set_telegram_bot_token(bot.pk, token)
    return bot


def test_link_code_is_single_use_and_expires():
    user = User.objects.create_user("tg-user", password="x")
    bot = _platform_bot()
    payload = create_link_code(user=user, bot=bot)
    link = consume_link_code(
        bot=bot,
        code=payload["code"],
        telegram_user_id=42,
        chat_id="42",
        username="alice",
    )
    assert link.user_id == user.pk
    assert link.status == TelegramAccountLink.STATUS_LINKED

    with pytest.raises(TelegramLinkError):
        consume_link_code(bot=bot, code=payload["code"], telegram_user_id=43, chat_id="43")


def test_unlink_and_user_deactivate_revokes_link():
    user = User.objects.create_user("tg-user2", password="x")
    bot = _platform_bot("123456:platform-token-2")
    payload = create_link_code(user=user, bot=bot)
    link = consume_link_code(
        bot=bot,
        code=payload["code"],
        telegram_user_id=99,
        chat_id="99",
        username="bob",
    )
    unlink_account(user=user, link_id=link.pk)
    link.refresh_from_db()
    assert link.status == TelegramAccountLink.STATUS_REVOKED

    payload2 = create_link_code(user=user, bot=bot)
    link2 = consume_link_code(
        bot=bot,
        code=payload2["code"],
        telegram_user_id=100,
        chat_id="100",
    )
    user.is_active = False
    user.save()
    link2.refresh_from_db()
    assert link2.status == TelegramAccountLink.STATUS_REVOKED


def test_me_telegram_apis_require_feature(monkeypatch):
    user = User.objects.create_user("tg-api", password="x")
    _deny(user, "telegram_assistant", "telegram_notifications")
    client = Client()
    client.force_login(user)

    resp = client.post("/api/me/telegram/link-codes/", data="{}", content_type="application/json")
    assert resp.status_code == 403

    _grant(user, "telegram_assistant", "chat")
    bot = _platform_bot("123456:platform-token-3")

    resp = client.post("/api/me/telegram/link-codes/", data="{}", content_type="application/json")
    assert resp.status_code == 201
    body = resp.json()
    assert "code" in body
    assert body["bot_id"] == bot.pk

    resp = client.get("/api/me/telegram/links/")
    assert resp.status_code == 200
    assert resp.json()["links"] == []


def test_me_telegram_status_aggregate():
    user = User.objects.create_user("tg-status", password="x")
    _deny(user, "telegram_assistant", "telegram_notifications")
    client = Client()
    client.force_login(user)

    resp = client.get("/api/me/telegram/status/")
    assert resp.status_code == 403

    _grant(user, "telegram_notifications", "telegram_assistant", "chat")
    bot = _platform_bot("123456:platform-token-status")
    bot.last_poll_at = None
    bot.save(update_fields=["last_poll_at"])

    resp = client.get("/api/me/telegram/status/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["notifications_allowed"] is True
    assert body["assistant_allowed"] is True
    assert body["linked"] is False
    assert body["bot_username"] == "platform_bot"
    assert body["hub_hint"] == "worker_offline"
    assert body["personal_bots_allowed"] is True

    payload = create_link_code(user=user, bot=bot)
    consume_link_code(
        bot=bot,
        code=payload["code"],
        telegram_user_id=777,
        chat_id="777",
        username="linked_user",
    )

    resp = client.get("/api/me/telegram/status/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["linked"] is True
    assert body["chat_id"] == "777"
    assert body["link"]["telegram_user_id"] == 777


def test_create_personal_bot_respects_admin_flag(monkeypatch, tmp_path):
    from core_ui.services.notification_config import save_notification_config

    user = User.objects.create_user("tg-bot-flag", password="x")
    _grant(user, "telegram_assistant", "chat")
    client = Client()
    client.force_login(user)

    config_file = tmp_path / "notif.json"
    monkeypatch.setenv("NOTIFICATION_CONFIG_PATH", str(config_file))
    save_notification_config({"telegram_personal_bots_enabled": False})

    monkeypatch.setattr(
        "telegram_hub.services.bots.validate_token_via_get_me",
        lambda token: {"id": 556, "username": "blocked_bot", "first_name": "Bot"},
    )

    resp = client.post(
        "/api/me/telegram/bots/",
        data='{"token":"123456:blocked-secret","name":"Mine"}',
        content_type="application/json",
    )
    assert resp.status_code == 403


def test_create_personal_bot_validates_token(monkeypatch):
    user = User.objects.create_user("tg-bot-owner", password="x")
    _grant(user, "telegram_assistant", "chat")
    client = Client()
    client.force_login(user)

    monkeypatch.setattr(
        "telegram_hub.services.bots.validate_token_via_get_me",
        lambda token: {"id": 555, "username": "my_assistant_bot", "first_name": "Bot"},
    )

    resp = client.post(
        "/api/me/telegram/bots/",
        data='{"token":"123456:personal-secret","name":"Mine"}',
        content_type="application/json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["bot_username"] == "my_assistant_bot"
    assert body["kind"] == "personal"
    assert "token" not in body
    assert body["has_token"] is True

    # Duplicate token rejected
    resp2 = client.post(
        "/api/me/telegram/bots/",
        data='{"token":"123456:personal-secret"}',
        content_type="application/json",
    )
    assert resp2.status_code == 400


def test_mask_bot_token_helper():
    from telegram_hub.client import mask_bot_token

    assert mask_bot_token("1234567890:ABCDEF") == "••••CDEF"
    assert mask_bot_token("") == ""
