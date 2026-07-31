from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from studio.approval_models import ApprovalRequest, TelegramBotCursor, TelegramReplyRequest
from studio.management.commands.run_telegram_bot import Command
from studio.telegram_delivery_service import (
    advance_telegram_update_offset,
    arm_telegram_reply_request,
    get_telegram_update_offset,
    store_telegram_operator_reply,
    telegram_approval_callback_data,
    telegram_bot_token_digest,
    telegram_worker_key,
)
from tests.studio_node_executor_harness import make_run

pytestmark = pytest.mark.django_db(transaction=True)


def test_telegram_offset_is_monotonic_and_survives_command_restart():
    token = "123456789:durable-offset"

    assert get_telegram_update_offset(token) == 0
    assert advance_telegram_update_offset(token, 42) == 42
    assert advance_telegram_update_offset(token, 12) == 42

    restarted_process = Command()
    assert restarted_process is not None
    assert get_telegram_update_offset(token) == 42
    assert TelegramBotCursor.objects.get(bot_token_digest=telegram_bot_token_digest(token)).update_offset == 42


def test_two_consumers_route_one_hundred_approval_callbacks_without_loss(monkeypatch):
    run = make_run("telegram-approval-burst")
    approver = run.pipeline.owner
    bot_token = "123456789:approval-burst"
    chat_id = "chat-42"
    expires_at = timezone.now() + timedelta(minutes=5)
    raw_tokens = [f"approval-token-{index:03d}" for index in range(100)]
    ApprovalRequest.objects.bulk_create(
        [
            ApprovalRequest(
                run=run,
                node_id=f"approval-{index:03d}",
                token_digest=ApprovalRequest.digest_token(raw_token),
                telegram_bot_token_digest=telegram_bot_token_digest(bot_token),
                telegram_chat_id=chat_id,
                approver=approver,
                requested_by=approver,
                expires_at=expires_at,
            )
            for index, raw_token in enumerate(raw_tokens)
        ]
    )
    monkeypatch.setattr(Command, "_answer_callback_query", lambda *_args, **_kwargs: None)
    consumers = (Command(), Command())

    for index, raw_token in enumerate(raw_tokens):
        result = consumers[index % 2]._handle_update(
            {
                "update_id": 10_000 + index,
                "callback_query": {
                    "data": telegram_approval_callback_data("approved", raw_token),
                    "message": {"chat": {"id": chat_id}},
                    "from": {"username": f"operator_{index}"},
                },
            },
            bot_token,
            run.pipeline,
            None,
        )
        assert result == "approval"

    assert ApprovalRequest.objects.filter(run=run, status=ApprovalRequest.STATUS_APPROVED).count() == 100
    run.refresh_from_db()
    assert sum(1 for state in run.node_states.values() if state.get("approval_source") == "telegram_button") == 100
    assert telegram_worker_key(bot_token) == telegram_worker_key(bot_token)


def test_reply_delivery_uses_direct_request_lookup_beyond_one_hundred_active_nodes():
    run = make_run("telegram-reply-burst")
    token = "123456789:reply-burst"
    expires_at = timezone.now() + timedelta(minutes=5)
    for index in range(125):
        arm_telegram_reply_request(
            run=run,
            node_id=f"reply-{index:03d}",
            bot_token=token,
            chat_id="chat-42",
            prompt_message_id=20_000 + index,
            expires_at=expires_at,
        )

    with CaptureQueriesContext(connection) as queries:
        delivered = store_telegram_operator_reply(
            token,
            {
                "text": "continue deployment",
                "chat": {"id": "chat-42"},
                "message_id": 99_999,
                "reply_to_message": {"message_id": 20_124},
                "from": {"username": "ops_user"},
            },
        )

    assert delivered is True
    assert len(queries) <= 10
    request = TelegramReplyRequest.objects.get(run=run, node_id="reply-124")
    assert request.status == TelegramReplyRequest.STATUS_RECEIVED
    run.refresh_from_db()
    assert run.node_states["reply-124"]["operator_response"] == "continue deployment"
