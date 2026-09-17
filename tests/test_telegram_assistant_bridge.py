"""Telegram assistant bridge tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User

from core_ui.managed_secrets import set_telegram_bot_token
from core_ui.models import AssistantAction, ChatSession, ChatTurnState
from studio.telegram_delivery_service import telegram_bot_token_digest
from telegram_hub.assistant_bridge import (
    _action_card_text,
    get_or_create_telegram_session,
    handle_action_callback,
    parse_key_value_lines,
    peek_playbook_vars_pending,
    run_assistant_turn,
    start_new_telegram_session,
    store_playbook_vars_pending,
    try_consume_playbook_vars_reply,
)
from telegram_hub.models import TelegramAccountLink, TelegramBot
from telegram_hub.services.linking import build_action_callback_data

pytestmark = pytest.mark.django_db(transaction=True)


def _bot_and_link():
    user = User.objects.create_user("bridge-user", password="x")
    bot = TelegramBot.objects.create(
        kind=TelegramBot.KIND_PLATFORM,
        name="Platform",
        token_digest=telegram_bot_token_digest("bridge-token"),
        is_active=True,
        mode=TelegramBot.MODE_ASSISTANT,
    )
    set_telegram_bot_token(bot.pk, "bridge-token")
    link = TelegramAccountLink.objects.create(
        user=user,
        bot=bot,
        telegram_user_id=321,
        chat_id="321",
        username="bridge",
        status=TelegramAccountLink.STATUS_LINKED,
    )
    return user, bot, link


def test_telegram_session_kind_and_new_command():
    _user, _bot, link = _bot_and_link()
    session = get_or_create_telegram_session(link)
    assert session.kind == ChatSession.KIND_TELEGRAM
    session2 = start_new_telegram_session(link)
    assert session2.pk != session.pk
    assert session2.kind == ChatSession.KIND_TELEGRAM


def test_run_assistant_turn_sends_reply(monkeypatch):
    user, bot, link = _bot_and_link()
    sent = []
    actions = []
    deleted = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def send_chat_action(self, **kwargs):
            actions.append(kwargs)
            return None

        async def send_message(self, **kwargs):
            sent.append(kwargs)
            return {"status": "completed", "message_ids": [len(sent)], "last_message_id": len(sent)}

        async def delete_message(self, **kwargs):
            deleted.append(kwargs)
            return None

        async def edit_message_text(self, **kwargs):
            sent.append(kwargs)
            return {}

    def fake_handle(session, user_obj, text, request=None, provider_binding=None):
        user_msg = session.messages.create(role="user", content=text)
        asst = session.messages.create(role="assistant", content=f"echo:{text}")
        return SimpleNamespace(user_message=user_msg, assistant_message=asst, actions=[])

    monkeypatch.setattr("telegram_hub.assistant_bridge.TelegramClient", FakeClient)
    monkeypatch.setattr("telegram_hub.assistant_bridge.handle_user_message", fake_handle)

    import asyncio

    asyncio.run(run_assistant_turn(link_id=link.pk, text="ping", tg_message_id=9))
    assert any("echo:ping" in str(item.get("text")) for item in sent)
    assert any(item.get("action") == "typing" for item in actions)
    assert any("Думаю" in str(item.get("text") or "") for item in sent)
    assert deleted  # status message removed after reply


def test_action_callback_hmac_and_ownership():
    user, bot, link = _bot_and_link()
    session = get_or_create_telegram_session(link)
    action = AssistantAction.objects.create(
        user=user,
        session=session,
        action_type="agents.list",
        title="List",
        status=AssistantAction.STATUS_REQUIRES_CONFIRMATION,
        risk=AssistantAction.RISK_READ,
        requires_confirmation=True,
    )
    data = build_action_callback_data(
        decision="cancel",
        action_id=action.pk,
        telegram_user_id=link.telegram_user_id,
        bot_id=bot.pk,
    )
    result = handle_action_callback(
        bot=bot,
        telegram_user_id=link.telegram_user_id,
        chat_id=link.chat_id,
        callback_data=data,
    )
    assert result.ok is True
    assert any("отмен" in line.lower() for line in result.chat_lines)
    action.refresh_from_db()
    assert action.status == AssistantAction.STATUS_CANCELLED


def test_action_card_text_hides_yaml_and_memory():
    user, _bot, link = _bot_and_link()
    session = get_or_create_telegram_session(link)
    action = AssistantAction.objects.create(
        user=user,
        session=session,
        action_type="operator.create_playbook",
        title="Create playbook",
        description="Draft playbook\n\n⚠ Memory: Canonical Profile | Canonical Human Habits",
        status=AssistantAction.STATUS_REQUIRES_CONFIRMATION,
        risk=AssistantAction.RISK_MUTATING,
        requires_confirmation=True,
        safe_preview={
            "name": "server-info",
            "yaml": "- hosts: all\n  tasks:\n    - setup:\n",
            "playbook_id": 38,
        },
    )
    text = _action_card_text(action)
    assert "Canonical" not in text
    assert "Memory:" not in text
    assert "- hosts: all" not in text
    assert "YAML:" in text
    assert "server-info" in text or "38" in text


def test_confirm_delivers_followup_card(monkeypatch):
    user, bot, link = _bot_and_link()
    session = get_or_create_telegram_session(link)
    action = AssistantAction.objects.create(
        user=user,
        session=session,
        action_type="operator.create_playbook",
        title="Create playbook",
        status=AssistantAction.STATUS_REQUIRES_CONFIRMATION,
        risk=AssistantAction.RISK_MUTATING,
        requires_confirmation=True,
        input_payload={"name": "x"},
    )
    follow = AssistantAction.objects.create(
        user=user,
        session=session,
        action_type="operator.run_playbook",
        title="Run playbook",
        status=AssistantAction.STATUS_REQUIRES_CONFIRMATION,
        risk=AssistantAction.RISK_MUTATING,
        requires_confirmation=True,
        input_payload={"playbook_id": 1, "server_ids": [33]},
    )

    def fake_detailed(act, request=None, typed_confirm=None):
        act.status = AssistantAction.STATUS_COMPLETED
        act.save(update_fields=["status", "updated_at"])
        resume = SimpleNamespace(
            assistant_message=SimpleNamespace(content="Playbook создан."),
            actions=[follow],
        )
        return SimpleNamespace(action=act, resume=resume, resume_error=None, stale_cleared=False)

    monkeypatch.setattr(
        "telegram_hub.assistant_bridge.confirm_action_and_resume_detailed",
        fake_detailed,
    )
    data = build_action_callback_data(
        decision="confirm",
        action_id=action.pk,
        telegram_user_id=link.telegram_user_id,
        bot_id=bot.pk,
    )
    result = handle_action_callback(
        bot=bot,
        telegram_user_id=link.telegram_user_id,
        chat_id=link.chat_id,
        callback_data=data,
    )
    assert result.ok is True
    assert any("создан" in line.lower() for line in result.chat_lines)
    assert len(result.followup_actions) == 1
    assert result.followup_actions[0].pk == follow.pk


def test_stale_pending_cleared_after_failed_confirm(monkeypatch):
    from core_ui.services.assistant_confirm import clear_orphan_awaiting_confirm

    user, _bot, link = _bot_and_link()
    session = get_or_create_telegram_session(link)
    user_msg = session.messages.create(role="user", content="run")
    asst = session.messages.create(role="assistant", content="")
    action = AssistantAction.objects.create(
        user=user,
        session=session,
        action_type="operator.run_playbook",
        title="Run",
        status=AssistantAction.STATUS_FAILED,
        risk=AssistantAction.RISK_MUTATING,
        error="Provide every required runtime variable before running",
        result_payload={"compatibility": {"missing_runtime_variables": ["ansible_user"]}},
    )
    turn = ChatTurnState.objects.create(
        session=session,
        user_message=user_msg,
        assistant_message=asst,
        pending_action=action,
        status=ChatTurnState.STATUS_AWAITING_CONFIRM,
    )
    assert clear_orphan_awaiting_confirm(action) is True
    turn.refresh_from_db()
    assert turn.status == ChatTurnState.STATUS_FAILED
    assert turn.pending_action_id is None


def test_playbook_vars_wizard_roundtrip():
    user, _bot, link = _bot_and_link()
    session = get_or_create_telegram_session(link)
    action = AssistantAction.objects.create(
        user=user,
        session=session,
        action_type="operator.run_playbook",
        title="Run",
        status=AssistantAction.STATUS_FAILED,
        risk=AssistantAction.RISK_MUTATING,
        input_payload={"playbook_id": 38, "server_ids": [33]},
    )
    store_playbook_vars_pending(
        link.pk,
        {
            "action_id": action.pk,
            "missing": ["ansible_user"],
            "input_payload": action.input_payload,
            "session_id": session.pk,
        },
    )
    assert peek_playbook_vars_pending(link.pk)
    assert parse_key_value_lines("ansible_user=root\nfoo: bar") == {
        "ansible_user": "root",
        "foo": "bar",
    }
    result = try_consume_playbook_vars_reply(link=link, text="ansible_user=deploy")
    assert result is not None
    assert result.ok is True
    assert result.followup_actions
    follow = result.followup_actions[0]
    assert follow.input_payload["extra_vars"]["ansible_user"] == "deploy"
    assert peek_playbook_vars_pending(link.pk) is None
