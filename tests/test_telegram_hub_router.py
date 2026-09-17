"""Telegram hub router unit tests."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from core_ui.managed_secrets import set_telegram_bot_token
from core_ui.models import UserAppPermission
from studio.telegram_delivery_service import telegram_bot_token_digest
from telegram_hub.client import TelegramClient
from telegram_hub.models import TelegramBot
from telegram_hub.router import TelegramUpdateRouter
from telegram_hub.services.linking import consume_link_code, create_link_code

pytestmark = pytest.mark.django_db(transaction=True)


class FakeClient(TelegramClient):
    def __init__(self):
        self.bot_token = "fake"
        self.base_url = "https://example.invalid"
        self.timeout = 5
        self.sent: list[dict] = []

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return {"status": "completed", "message_ids": [1], "last_message_id": 1, "chunks_sent": 1}

    async def answer_callback_query(self, *args, **kwargs):
        return None

    async def edit_message_reply_markup(self, **kwargs):
        return None


def test_router_rejects_unlinked_assistant_message():
    bot = TelegramBot.objects.create(
        kind=TelegramBot.KIND_PLATFORM,
        name="Platform",
        token_digest=telegram_bot_token_digest("t1"),
        is_active=True,
        mode=TelegramBot.MODE_ASSISTANT,
    )
    set_telegram_bot_token(bot.pk, "t1")
    client = FakeClient()
    router = TelegramUpdateRouter(bot, client)

    result = router.handle_update(
        {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "text": "hello",
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 42, "username": "x"},
            },
        }
    )
    assert result == "unlinked"
    assert client.sent


def test_router_queues_assistant_for_linked_user(monkeypatch):
    user = User.objects.create_user("router-user", password="x")
    UserAppPermission.objects.create(user=user, feature="telegram_assistant", allowed=True)
    UserAppPermission.objects.create(user=user, feature="chat", allowed=True)
    bot = TelegramBot.objects.create(
        kind=TelegramBot.KIND_PLATFORM,
        name="Platform",
        token_digest=telegram_bot_token_digest("t2"),
        is_active=True,
        mode=TelegramBot.MODE_ASSISTANT,
    )
    set_telegram_bot_token(bot.pk, "t2")
    payload = create_link_code(user=user, bot=bot)
    consume_link_code(bot=bot, code=payload["code"], telegram_user_id=7, chat_id="7")

    called = {}

    class FakeDelay:
        def delay(self, link_id, text, message_id=None):
            called["link_id"] = link_id
            called["text"] = text

    monkeypatch.setattr("telegram_hub.tasks.telegram_assistant_turn", FakeDelay())

    client = FakeClient()
    router = TelegramUpdateRouter(bot, client)
    result = router.handle_update(
        {
            "update_id": 2,
            "message": {
                "message_id": 11,
                "text": "list servers",
                "chat": {"id": 7, "type": "private"},
                "from": {"id": 7, "username": "x"},
            },
        }
    )
    assert result == "assistant_queued"
    assert called["text"] == "list servers"


def test_router_ignores_group_chats_by_default():
    bot = TelegramBot.objects.create(
        kind=TelegramBot.KIND_PLATFORM,
        name="Platform",
        token_digest=telegram_bot_token_digest("t3"),
        is_active=True,
        mode=TelegramBot.MODE_ASSISTANT,
        allow_group_chats=False,
    )
    client = FakeClient()
    router = TelegramUpdateRouter(bot, client)
    result = router.handle_update(
        {
            "update_id": 3,
            "message": {
                "message_id": 12,
                "text": "hello",
                "chat": {"id": -100, "type": "group"},
                "from": {"id": 1},
            },
        }
    )
    assert result == "ignored"
