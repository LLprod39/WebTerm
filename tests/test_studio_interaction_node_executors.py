from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.auth.models import User

from studio.models import ApprovalRequest, PipelineRun
from studio.pipeline.pipeline_executor import PipelineExecutor, _poll_telegram_approval_decision
from tests.studio_node_executor_harness import FakeHttpResponse, disable_activity_logging, make_run

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _disable_activity_logging(monkeypatch):
    disable_activity_logging(monkeypatch)


def test_human_approval_node_returns_approved_decision(monkeypatch):
    run = make_run("approval-node-user")
    User.objects.create_user(username="approval-node-approver", email="ops@example.com", password="x")
    node = {
        "id": "approval",
        "type": "logic/human_approval",
        "data": {
            "timeout_minutes": 1,
            "to_email": "ops@example.com",
            "base_url": "http://localhost:9000",
        },
    }
    node_outputs = {"plan": {"status": "completed", "output": "Deploy package A"}}

    async def fake_output_email(*args, **kwargs):
        return {"status": "completed", "output": "email sent"}

    async def fake_output_telegram(*args, **kwargs):
        return {"status": "completed", "output": "telegram sent"}

    async def fake_sleep(seconds: float) -> None:
        def _approve() -> None:
            ApprovalRequest.objects.filter(run=run, node_id="approval").update(
                status=ApprovalRequest.STATUS_APPROVED,
                response_text="Ship it",
            )

        await sync_to_async(_approve, thread_sensitive=True)()

    monkeypatch.setattr("studio.pipeline.pipeline_interactions._execute_output_email", fake_output_email)
    monkeypatch.setattr("studio.pipeline.pipeline_interactions._execute_output_telegram", fake_output_telegram)
    monkeypatch.setattr("studio.pipeline.pipeline_interactions.asyncio.sleep", fake_sleep)

    result = async_to_sync(PipelineExecutor(run)._execute_node)(node, {}, node_outputs)

    assert result["status"] == "completed"
    assert result["decision"] == "approved"
    assert "Ship it" in result["output"]


def test_human_approval_node_sends_telegram_confirmation_link(monkeypatch):
    run = make_run("approval-telegram-user")
    User.objects.create_user(username="approval-telegram-approver", password="x", is_staff=True)
    node = {
        "id": "approval_gate",
        "type": "logic/human_approval",
        "data": {
            "timeout_minutes": 1,
            "base_url": "http://localhost:9000",
            "tg_bot_token": "bot-123",
            "tg_chat_id": "chat-42",
            "tg_parse_mode": "",
        },
    }
    captured: dict[str, object] = {}

    async def fake_output_email(*args, **kwargs):
        return {"status": "completed", "output": "email sent"}

    async def fake_output_telegram(tg_node, *_args, **_kwargs):
        captured["data"] = tg_node["data"]
        return {"status": "completed", "output": "telegram sent"}

    async def fake_sleep(_seconds: float) -> None:
        await sync_to_async(
            lambda: ApprovalRequest.objects.filter(run=run, node_id="approval_gate").update(
                status=ApprovalRequest.STATUS_APPROVED,
                response_text="Подтверждено из Telegram",
            ),
            thread_sensitive=True,
        )()

    async def fake_send_telegram_message(**_kwargs):
        return {"status": "completed", "output": "decision confirmation sent"}

    monkeypatch.setattr("studio.pipeline.pipeline_interactions._execute_output_email", fake_output_email)
    monkeypatch.setattr("studio.pipeline.pipeline_interactions._execute_output_telegram", fake_output_telegram)
    monkeypatch.setattr("studio.pipeline.pipeline_interactions._send_telegram_message", fake_send_telegram_message)
    monkeypatch.setattr("studio.pipeline.pipeline_interactions.asyncio.sleep", fake_sleep)

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        node,
        {},
        {"plan": {"status": "completed", "output": "Ready"}},
    )

    assert result["status"] == "completed"
    assert result["decision"] == "approved"
    assert "Подтверждено из Telegram" in result["output"]
    reply_markup = captured["data"]["reply_markup"]
    assert captured["data"]["parse_mode"] == ""
    assert reply_markup["inline_keyboard"][0][0]["text"] == "Review approval request"
    assert reply_markup["inline_keyboard"][0][0]["url"].startswith(
        f"http://localhost:9000/api/studio/runs/{run.id}/approve/approval_gate/?token="
    )
    assert "callback_data" not in reply_markup["inline_keyboard"][0][0]
    raw_token = parse_qs(urlparse(reply_markup["inline_keyboard"][0][0]["url"]).query)["token"][0]
    approval = ApprovalRequest.objects.get(run=run, node_id="approval_gate")
    assert approval.token_matches(raw_token)
    assert raw_token != approval.token_digest
    run.refresh_from_db()
    assert "approval_token" not in run.node_states["approval_gate"]
    assert "approve_url" not in run.node_states["approval_gate"]


def test_human_approval_node_uses_global_telegram_defaults_when_node_fields_blank(monkeypatch):
    run = make_run("approval-global-telegram-user")
    User.objects.create_user(username="approval-global-telegram-approver", password="x", is_staff=True)
    node = {
        "id": "approval_gate",
        "type": "logic/human_approval",
        "data": {
            "timeout_minutes": 1,
            "base_url": "http://localhost:9000",
        },
    }
    captured: dict[str, object] = {}

    async def fake_output_email(*args, **kwargs):
        return {"status": "completed", "output": "email skipped"}

    async def fake_output_telegram(tg_node, *_args, **_kwargs):
        captured["data"] = tg_node["data"]
        return {"status": "completed", "output": "telegram sent"}

    async def fake_sleep(_seconds: float) -> None:
        await sync_to_async(
            lambda: ApprovalRequest.objects.filter(run=run, node_id="approval_gate").update(
                status=ApprovalRequest.STATUS_APPROVED,
                response_text="Подтверждено через глобальные настройки",
            ),
            thread_sensitive=True,
        )()

    async def fake_send_telegram_message(**_kwargs):
        return {"status": "completed", "output": "decision confirmation sent"}

    monkeypatch.setattr("studio.pipeline.pipeline_notifications._global_tg_defaults", lambda: ("global-bot", "global-chat"))
    monkeypatch.setattr("studio.pipeline.pipeline_interactions._global_email_defaults", lambda: ("", "", "", "", ""))
    monkeypatch.setattr("studio.pipeline.pipeline_interactions._execute_output_email", fake_output_email)
    monkeypatch.setattr("studio.pipeline.pipeline_interactions._execute_output_telegram", fake_output_telegram)
    monkeypatch.setattr("studio.pipeline.pipeline_interactions._send_telegram_message", fake_send_telegram_message)
    monkeypatch.setattr("studio.pipeline.pipeline_interactions.asyncio.sleep", fake_sleep)

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        node,
        {},
        {"plan": {"status": "completed", "output": "Ready"}},
    )

    assert result["status"] == "completed"
    assert result["decision"] == "approved"
    assert captured["data"]["bot_token"] == "global-bot"
    assert captured["data"]["chat_id"] == "global-chat"


def test_human_approval_node_fails_closed_without_distinct_approver(monkeypatch):
    run = make_run("approval-missing-approver-user")
    node = {
        "id": "approval_gate",
        "type": "logic/human_approval",
        "data": {
            "timeout_minutes": 1,
            "to_email": "external-only@example.com",
            "base_url": "http://localhost:9000",
        },
    }

    result = async_to_sync(PipelineExecutor(run)._execute_node)(node, {}, {})

    assert result["status"] == "failed"
    assert "distinct active approver" in result["error"]
    assert not ApprovalRequest.objects.filter(run=run).exists()


def test_poll_telegram_approval_decision_consumes_callback_updates(monkeypatch):
    import studio.pipeline.pipeline_executor as executor_module

    executor_module._TELEGRAM_UPDATE_OFFSETS.clear()
    executor_module._TELEGRAM_UPDATE_LOCKS.clear()
    executor_module._TELEGRAM_PENDING_CALLBACKS.clear()
    executor_module._TELEGRAM_PENDING_REPLIES.clear()

    captured: dict[str, object] = {"calls": []}

    class FakeHttpClient:
        def __init__(self, timeout: int = 15) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict):
            captured["calls"].append((url, json))
            if url.endswith("/getUpdates"):
                return FakeHttpResponse(
                    status_code=200,
                    text='{"ok": true}',
                )
            return FakeHttpResponse(status_code=200, text='{"ok": true}')

    monkeypatch.setattr("studio.pipeline.pipeline_telegram.httpx.AsyncClient", FakeHttpClient)

    def fake_json_response(self):
        return {
            "ok": True,
            "result": [
                {
                    "update_id": 7001,
                    "callback_query": {
                        "id": "cbq-1",
                        "data": "approval:approved:token-xyz",
                        "from": {"username": "ops_user"},
                    },
                }
            ],
        }

    monkeypatch.setattr(FakeHttpResponse, "json", fake_json_response, raising=False)

    result = async_to_sync(_poll_telegram_approval_decision)("bot-123", "token-xyz")

    assert result is not None
    assert result["decision"] == "approved"
    assert result["response_text"] == "через кнопку в Telegram"
    calls = captured["calls"]
    assert any(url.endswith("/getUpdates") for url, _payload in calls)
    assert any(url.endswith("/answerCallbackQuery") for url, _payload in calls)


def test_telegram_input_node_returns_operator_reply(monkeypatch):
    run = make_run("telegram-input-user")
    node = {
        "id": "operator_input",
        "type": "logic/telegram_input",
        "data": {
            "tg_bot_token": "bot-123",
            "tg_chat_id": "chat-42",
            "timeout_minutes": 5,
            "message": "Что делаем с {container_name}?",
            "parse_mode": "",
        },
    }
    sent_messages: list[dict[str, object]] = []

    async def fake_send_telegram_message(**kwargs):
        sent_messages.append(kwargs)
        return {
            "status": "completed",
            "output": "sent",
            "message_ids": [111],
            "last_message_id": 111,
        }

    async def fake_poll_reply(_bot_token: str, _chat_id: str, reply_to_message_id: int):
        assert reply_to_message_id == 111
        return {
            "text": "Попробуй docker compose up -d mini-prod-mcp-demo",
            "chat_id": "chat-42",
            "message_id": 222,
            "reply_to_message_id": reply_to_message_id,
            "from_username": "ops_user",
        }

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("studio.pipeline.pipeline_interactions_telegram._send_telegram_message", fake_send_telegram_message)
    monkeypatch.setattr("studio.pipeline.pipeline_interactions_telegram._poll_telegram_reply_message", fake_poll_reply)
    monkeypatch.setattr("studio.pipeline.pipeline_interactions_telegram.asyncio.sleep", fake_sleep)

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        node,
        {"container_name": "mini-prod-mcp-demo"},
        {"restart_container": {"status": "failed", "error": "exit 1", "output": "status=exited"}},
    )

    assert result["status"] == "completed"
    assert result["decision"] == "received"
    assert "docker compose up -d mini-prod-mcp-demo" in result["output"]
    assert sent_messages[0]["reply_markup"] == {"force_reply": True, "selective": False}
    run.refresh_from_db()
    assert run.node_states["operator_input"]["operator_response"] == "Попробуй docker compose up -d mini-prod-mcp-demo"


def test_telegram_input_node_uses_global_telegram_defaults_when_node_fields_blank(monkeypatch):
    run = make_run("telegram-input-global-user")
    node = {
        "id": "operator_input",
        "type": "logic/telegram_input",
        "data": {
            "timeout_minutes": 5,
            "message": "Что делаем с {container_name}?",
            "parse_mode": "",
        },
    }
    captured: dict[str, object] = {}

    async def fake_send_telegram_message(**kwargs):
        captured.update(kwargs)
        return {
            "status": "completed",
            "output": "sent",
            "message_ids": [111],
            "last_message_id": 111,
        }

    async def fake_poll_reply(*_args, **_kwargs):
        await sync_to_async(
            lambda: PipelineRun.objects.filter(pk=run.pk).update(runtime_control={"stop_requested": True}),
            thread_sensitive=True,
        )()
        return None

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("studio.pipeline.pipeline_notifications._global_tg_defaults", lambda: ("global-bot", "global-chat"))
    monkeypatch.setattr("studio.pipeline.pipeline_interactions_telegram._send_telegram_message", fake_send_telegram_message)
    monkeypatch.setattr("studio.pipeline.pipeline_interactions_telegram._poll_telegram_reply_message", fake_poll_reply)
    monkeypatch.setattr("studio.pipeline.pipeline_interactions_telegram.asyncio.sleep", fake_sleep)

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        node,
        {"container_name": "mini-prod-mcp-demo"},
        {"restart_container": {"status": "failed", "error": "exit 1", "output": "status=exited"}},
    )

    assert result["status"] == "stopped"
    assert captured["bot_token"] == "global-bot"
    assert captured["chat_id"] == "global-chat"
    assert "mini-prod-mcp-demo" in str(captured["message"])


def test_telegram_input_node_prefers_operator_reply_over_stale_stopped_status(monkeypatch):
    run = make_run("telegram-input-stale-stop-user")
    node = {
        "id": "operator_input",
        "type": "logic/telegram_input",
        "data": {
            "tg_bot_token": "bot-123",
            "tg_chat_id": "chat-42",
            "timeout_minutes": 5,
            "message": "Что делаем с {container_name}?",
            "parse_mode": "",
        },
    }

    async def fake_send_telegram_message(**_kwargs):
        return {
            "status": "completed",
            "output": "sent",
            "message_ids": [111],
            "last_message_id": 111,
        }

    async def fake_poll_reply(_bot_token: str, _chat_id: str, reply_to_message_id: int):
        assert reply_to_message_id == 111
        await sync_to_async(
            lambda: PipelineRun.objects.filter(pk=run.pk).update(status=PipelineRun.STATUS_STOPPED),
            thread_sensitive=True,
        )()
        return {
            "text": "Сделай docker start mini-prod-mcp-demo",
            "chat_id": "chat-42",
            "message_id": 222,
            "reply_to_message_id": reply_to_message_id,
            "from_username": "ops_user",
        }

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("studio.pipeline.pipeline_interactions_telegram._send_telegram_message", fake_send_telegram_message)
    monkeypatch.setattr("studio.pipeline.pipeline_interactions_telegram._poll_telegram_reply_message", fake_poll_reply)
    monkeypatch.setattr("studio.pipeline.pipeline_interactions_telegram.asyncio.sleep", fake_sleep)

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        node,
        {"container_name": "mini-prod-mcp-demo"},
        {"restart_container": {"status": "failed", "error": "exit 1", "output": "status=exited"}},
    )

    assert result["status"] == "completed"
    assert result["decision"] == "received"
    assert "docker start mini-prod-mcp-demo" in result["output"]


def test_telegram_input_node_stops_only_on_runtime_stop_request(monkeypatch):
    run = make_run("telegram-input-runtime-stop-user")
    node = {
        "id": "operator_input",
        "type": "logic/telegram_input",
        "data": {
            "tg_bot_token": "bot-123",
            "tg_chat_id": "chat-42",
            "timeout_minutes": 5,
            "message": "Что делаем с {container_name}?",
            "parse_mode": "",
        },
    }
    poll_calls = {"count": 0}

    async def fake_send_telegram_message(**_kwargs):
        return {
            "status": "completed",
            "output": "sent",
            "message_ids": [111],
            "last_message_id": 111,
        }

    async def fake_poll_reply(_bot_token: str, _chat_id: str, reply_to_message_id: int):
        assert reply_to_message_id == 111
        poll_calls["count"] += 1
        await sync_to_async(
            lambda: PipelineRun.objects.filter(pk=run.pk).update(runtime_control={"stop_requested": True}),
            thread_sensitive=True,
        )()
        return None

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("studio.pipeline.pipeline_interactions_telegram._send_telegram_message", fake_send_telegram_message)
    monkeypatch.setattr("studio.pipeline.pipeline_interactions_telegram._poll_telegram_reply_message", fake_poll_reply)
    monkeypatch.setattr("studio.pipeline.pipeline_interactions_telegram.asyncio.sleep", fake_sleep)

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        node,
        {"container_name": "mini-prod-mcp-demo"},
        {"restart_container": {"status": "failed", "error": "exit 1", "output": "status=exited"}},
    )

    assert poll_calls["count"] == 1
    assert result["status"] == "stopped"
    assert result["stopped"] is True
