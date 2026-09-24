from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client

from servers.agents.agent_hitl import (
    mark_run_waiting,
    try_store_agent_telegram_reply,
)
from servers.models import AgentRun, ServerAgent
from tests.servers_api_smoke_harness import create_server, grant_feature


def _owner_client(username: str = "hitl-owner") -> tuple[User, Client]:
    user = User.objects.create_user(username=username, password="x")
    grant_feature(user, "agents")
    client = Client()
    client.force_login(user)
    return user, client


def _waiting_run(user: User, *, question: str = "Разрешить бэкап?") -> AgentRun:
    server = create_server(user, name=f"{user.username}-node")
    agent = ServerAgent.objects.create(
        user=user,
        name="HITL agent",
        mode=ServerAgent.MODE_FULL,
        goal="Deploy with approval",
        report_delivery={"telegram": {"enabled": True, "chat_id": "999001"}},
    )
    agent.servers.set([server])
    return AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_RUNNING,
        pending_question="",
    )


@pytest.mark.django_db
def test_report_v2_includes_pending_question_when_waiting():
    user, client = _owner_client("hitl-v2-pending")
    run = _waiting_run(user)
    mark_run_waiting(run.id, "SAFE заблокировал cp. Разрешить?")
    run.refresh_from_db()
    assert run.status == AgentRun.STATUS_WAITING
    assert "SAFE заблокировал" in run.pending_question

    payload = client.get(f"/servers/api/agents/runs/{run.id}/report/v2/").json()
    assert payload["run"]["pending_question"].startswith("SAFE заблокировал")
    assert payload["run"]["status"] == "waiting"
    assert payload["lifecycle"]["status"] == "waiting"


@pytest.mark.django_db
def test_telegram_reply_to_agent_question_arms_and_delivers():
    user, _client = _owner_client("hitl-tg-reply")
    run = _waiting_run(user)
    mark_run_waiting(run.id, "Продолжить?")
    bot_token = "123456:ABC-DEF"
    chat_id = "999001"
    message_id = 42
    from servers.agents.agent_hitl import _tg_reply_cache_key

    cache.set(_tg_reply_cache_key(bot_token=bot_token, chat_id=chat_id, message_id=message_id), run.id, timeout=60)

    with patch("servers.agents.agent_service.get_engine_for_run", return_value=None):
        with patch("servers.agents.agent_service.update_runtime_control") as update_control:
            ok = try_store_agent_telegram_reply(
                bot_token,
                {
                    "text": "да",
                    "chat": {"id": chat_id},
                    "reply_to_message": {"message_id": message_id},
                    "from": {"username": "ops"},
                    "message_id": 43,
                },
            )
            assert ok is True
            update_control.assert_called()

    run.refresh_from_db()
    assert run.status == AgentRun.STATUS_RUNNING
    assert run.pending_question == ""
    assert cache.get(_tg_reply_cache_key(bot_token=bot_token, chat_id=chat_id, message_id=message_id)) is None


@pytest.mark.django_db(transaction=True)
def test_notify_telegram_agent_question_sends_when_enabled():
    import asyncio

    user = User.objects.create_user(username="hitl-tg-send", password="x")
    grant_feature(user, "agents")
    run = _waiting_run(user)
    mark_run_waiting(run.id, "Разрешить?")

    fake_client = MagicMock()
    fake_client.send_message = AsyncMock(
        return_value={"last_message_id": 77, "message_ids": [77], "result": {"message_id": 77}}
    )

    async def _run():
        with patch(
            "servers.agents.agent_hitl.load_notification_config",
            return_value={"telegram_bot_token": "tok", "site_url": "https://app.test"},
        ):
            with patch("servers.agents.agent_hitl.TelegramClient", return_value=fake_client):
                with patch("servers.agents.agent_hitl.record_run_event_async", new_callable=AsyncMock):
                    from servers.agents.agent_hitl import notify_telegram_agent_question

                    await notify_telegram_agent_question(run.id, "Разрешить?")

    asyncio.run(_run())

    fake_client.send_message.assert_awaited()
    call_kwargs = fake_client.send_message.await_args.kwargs
    assert "Разрешить?" in call_kwargs["text"]
    assert call_kwargs["chat_id"] == "999001"
