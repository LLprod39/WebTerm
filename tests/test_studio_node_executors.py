from __future__ import annotations

from email import message_from_string
from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.auth.models import User

from servers.models import Server, ServerAlert
from studio.models import MCPServerPool, Pipeline, PipelineRun
from studio.pipeline_executor import (
    PipelineExecutor,
    _execute_registry_node,
    _poll_telegram_approval_decision,
)
from studio.pipeline_validation import KNOWN_NODE_TYPES

pytestmark = pytest.mark.django_db(transaction=True)


RUNTIME_COVERED_NODE_TYPES = {
    "trigger/manual",
    "trigger/webhook",
    "trigger/schedule",
    "trigger/monitoring",
    "agent/react",
    "agent/multi",
    "agent/ssh_cmd",
    "agent/llm_query",
    "agent/mcp_call",
    "ops/server_snapshot",
    "ops/log_query",
    "ops/file_action",
    "ops/package_action",
    "ops/disk_cleanup",
    "ops/backup_restore_check",
    "ops/service_action",
    "ops/docker_action",
    "ops/process_action",
    "ops/http_check",
    "ops/alert_update",
    "logic/condition",
    "logic/parallel",
    "logic/merge",
    "logic/wait",
    "logic/human_approval",
    "logic/telegram_input",
    "output/report",
    "output/webhook",
    "output/email",
    "output/telegram",
}


class _Decision:
    def __init__(
        self,
        *,
        allowed: bool = True,
        reason: str = "",
        sandbox_profile: str = "ops_exec",
        notes: list[str] | None = None,
    ) -> None:
        self.allowed = allowed
        self.reason = reason
        self.sandbox_profile = sandbox_profile
        self.notes = list(notes or [])


class _PermissionEngine:
    def __init__(self, mode: str | None = None) -> None:
        self.mode = mode

    def evaluate(self, spec, payload):
        return _Decision()

    def record_success(self, spec, payload, output) -> None:
        return None

    def verification_summary(self) -> str:
        return "verified"


class _SandboxManager:
    def validate(self, spec, payload, sandbox_profile):
        return _Decision()


class _HookManager:
    async def post_tool_use(self, tool_name: str, output: str) -> str:
        return output


class _FakeSMTP:
    sent_messages: list[dict[str, str]] = []

    def __init__(self, host: str, port: int, timeout: int = 30) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def ehlo(self) -> None:
        return None

    def starttls(self) -> None:
        return None

    def login(self, username: str, password: str) -> None:
        return None

    def sendmail(self, from_email: str, recipients: list[str], message: str) -> None:
        self.__class__.sent_messages.append(
            {
                "from_email": from_email,
                "recipients": ",".join(recipients),
                "message": message,
            }
        )


class _FakeLoop:
    async def run_in_executor(self, executor, func):
        return func()


class _FakeHttpResponse:
    def __init__(self, status_code: int = 200, text: str = "ok") -> None:
        self.status_code = status_code
        self.text = text


def _make_user(username: str, *, is_staff: bool = False) -> User:
    return User.objects.create_user(username=username, password="x", is_staff=is_staff)


def _make_run(username: str = "node-suite-user") -> PipelineRun:
    owner = _make_user(username)
    pipeline = Pipeline.objects.create(
        name=f"Pipeline for {username}",
        owner=owner,
        nodes=[{"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}}],
        edges=[],
    )
    return PipelineRun.objects.create(
        pipeline=pipeline,
        triggered_by=owner,
        status=PipelineRun.STATUS_PENDING,
        nodes_snapshot=list(pipeline.nodes),
        edges_snapshot=list(pipeline.edges),
        context={},
        entry_node_id="manual",
        routing_state={
            "entry_node_id": "manual",
            "activated_nodes": ["manual"],
            "completed_nodes": [],
            "queued_nodes": [],
            "pending_merges": {},
        },
    )


@pytest.fixture(autouse=True)
def _disable_activity_logging(monkeypatch):
    async def _noop(*args, **kwargs):
        return None
    monkeypatch.setattr("studio.pipeline_agent_runtime.log_user_activity_async", _noop)
    monkeypatch.setattr("studio.pipeline_run_state.log_user_activity_async", _noop)
    monkeypatch.setattr("studio.pipeline_run_state.get_channel_layer", lambda: None)


def test_runtime_coverage_matches_known_node_types():
    assert RUNTIME_COVERED_NODE_TYPES == KNOWN_NODE_TYPES


@pytest.mark.parametrize(
    ("entry_node_id", "expected_node_id"),
    [
        ("manual", "manual_task"),
        ("webhook", "webhook_task"),
        ("schedule", "schedule_task"),
    ],
)
def test_trigger_nodes_start_only_selected_branch(monkeypatch, entry_node_id: str, expected_node_id: str):
    owner = _make_user(f"trigger-owner-{entry_node_id}")
    pipeline = Pipeline.objects.create(
        name="Trigger coverage flow",
        owner=owner,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "webhook", "type": "trigger/webhook", "position": {"x": 0, "y": 100}, "data": {}},
            {
                "id": "schedule",
                "type": "trigger/schedule",
                "position": {"x": 0, "y": 200},
                "data": {"cron_expression": "*/5 * * * *"},
            },
            {"id": "manual_task", "type": "output/report", "position": {"x": 120, "y": 0}, "data": {}},
            {"id": "webhook_task", "type": "output/report", "position": {"x": 120, "y": 100}, "data": {}},
            {"id": "schedule_task", "type": "output/report", "position": {"x": 120, "y": 200}, "data": {}},
        ],
        edges=[
            {"id": "e1", "source": "manual", "target": "manual_task", "sourceHandle": "out"},
            {"id": "e2", "source": "webhook", "target": "webhook_task", "sourceHandle": "out"},
            {"id": "e3", "source": "schedule", "target": "schedule_task", "sourceHandle": "out"},
        ],
    )
    pipeline.sync_triggers_from_nodes()

    async def fake_execute_node(self, node, context, node_outputs):
        return {"status": "completed", "output": node["id"]}

    monkeypatch.setattr(PipelineExecutor, "_execute_node", fake_execute_node)

    run = PipelineRun.objects.create(
        pipeline=pipeline,
        status=PipelineRun.STATUS_PENDING,
        nodes_snapshot=list(pipeline.nodes),
        edges_snapshot=list(pipeline.edges),
        context={},
        entry_node_id=entry_node_id,
        routing_state={
            "entry_node_id": entry_node_id,
            "activated_nodes": [entry_node_id],
            "completed_nodes": [],
            "queued_nodes": [],
            "pending_merges": {},
        },
    )

    result = async_to_sync(PipelineExecutor(run).execute)(context=run.context)

    assert result.status == PipelineRun.STATUS_COMPLETED
    assert set(result.node_states) == {expected_node_id}


def test_pipeline_executor_records_execution_policy_summary(monkeypatch):
    owner = _make_user("policy-summary-owner")
    pipeline = Pipeline.objects.create(
        name="Policy summary flow",
        owner=owner,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {}},
            {
                "id": "notify",
                "type": "output/webhook",
                "position": {"x": 120, "y": 0},
                "data": {"url": "https://ops.example.test/hook?token=secret-token"},
            },
        ],
        edges=[{"id": "e1", "source": "manual", "target": "notify", "sourceHandle": "out"}],
    )

    async def fake_execute_node(self, node, context, node_outputs):
        return {"status": "completed", "output": node["id"]}

    monkeypatch.setattr(PipelineExecutor, "_execute_node", fake_execute_node)

    run = PipelineRun.objects.create(
        pipeline=pipeline,
        status=PipelineRun.STATUS_PENDING,
        nodes_snapshot=list(pipeline.nodes),
        edges_snapshot=list(pipeline.edges),
        context={},
        trigger_data={"source": "manual"},
        entry_node_id="manual",
    )

    result = async_to_sync(PipelineExecutor(run).execute)(context=run.context)

    assert result.status == PipelineRun.STATUS_COMPLETED
    summary = result.trigger_data["execution_policy"]
    assert summary["level"] == "review"
    assert summary["by_action_class"]["external"] == 1
    assert summary["items"][0]["command"] == "https://ops.example.test/hook?token=%5Bredacted%5D" and summary["items"][0]["audit_metadata"]["policy_source"] == "studio_graph_validation" and "secret-token" not in str(summary["items"][0]["audit_metadata"])


def test_monitoring_trigger_node_starts_selected_branch(monkeypatch):
    owner = _make_user("trigger-owner-monitoring")
    server = Server.objects.create(user=owner, name="monitor-srv", host="10.0.0.9", username="root")
    pipeline = Pipeline.objects.create(
        name="Monitoring trigger coverage flow",
        owner=owner,
        nodes=[
            {
                "id": "monitoring",
                "type": "trigger/monitoring",
                "position": {"x": 0, "y": 0},
                "data": {"monitoring_filters": {"server_ids": [server.id], "alert_types": ["service"]}},
            },
            {"id": "monitoring_task", "type": "output/report", "position": {"x": 120, "y": 0}, "data": {}},
        ],
        edges=[
            {"id": "e1", "source": "monitoring", "target": "monitoring_task", "sourceHandle": "out"},
        ],
    )
    pipeline.sync_triggers_from_nodes()

    async def fake_execute_node(self, node, context, node_outputs):
        return {"status": "completed", "output": node["id"]}

    monkeypatch.setattr(PipelineExecutor, "_execute_node", fake_execute_node)

    run = PipelineRun.objects.create(
        pipeline=pipeline,
        status=PipelineRun.STATUS_PENDING,
        nodes_snapshot=list(pipeline.nodes),
        edges_snapshot=list(pipeline.edges),
        context={"server_name": server.name, "container_name": "demo"},
        entry_node_id="monitoring",
        routing_state={
            "entry_node_id": "monitoring",
            "activated_nodes": ["monitoring"],
            "completed_nodes": [],
            "queued_nodes": [],
            "pending_merges": {},
        },
    )

    result = async_to_sync(PipelineExecutor(run).execute)(context=run.context)

    assert result.status == PipelineRun.STATUS_COMPLETED
    assert set(result.node_states) == {"monitoring_task"}


def test_parallel_node_dispatch_returns_gateway():
    run = _make_run("parallel-node-user")
    executor = PipelineExecutor(run)

    result = async_to_sync(executor._execute_node)(
        {"id": "parallel", "type": "logic/parallel", "data": {}},
        {},
        {},
    )

    assert result == {"status": "completed", "output": "параллельное разветвление"}


def test_condition_node_evaluates_status_failed():
    run = _make_run("condition-node-user")
    executor = PipelineExecutor(run)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "condition",
            "type": "logic/condition",
            "data": {"source_node_id": "prep", "check_type": "status_failed"},
        },
        {},
        {"prep": {"status": "failed", "output": "boom"}},
    )

    assert result["status"] == "completed"
    assert result["passed"] is True
    assert result["output"] == "True"


def test_condition_node_evaluates_contains_case_insensitive():
    run = _make_run("condition-contains-user")
    executor = PipelineExecutor(run)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "condition",
            "type": "logic/condition",
            "data": {"source_node_id": "prep", "check_type": "contains", "check_value": "HEALTHY"},
        },
        {},
        {"prep": {"status": "completed", "output": "service is healthy"}},
    )

    assert result["status"] == "completed"
    assert result["passed"] is True
    assert result["output"] == "True"


def test_merge_node_returns_selected_mode():
    run = _make_run("merge-node-user")
    executor = PipelineExecutor(run)

    result = async_to_sync(executor._execute_node)(
        {"id": "merge", "type": "logic/merge", "data": {"mode": "any"}},
        {},
        {},
    )

    assert result == {"status": "completed", "output": "объединение: любая ветка"}


def test_merge_node_coerces_invalid_mode_to_all():
    run = _make_run("merge-invalid-mode-user")
    executor = PipelineExecutor(run)

    result = async_to_sync(executor._execute_node)(
        {"id": "merge", "type": "logic/merge", "data": {"mode": "invalid"}},
        {},
        {},
    )

    assert result == {"status": "completed", "output": "объединение: все ветки"}


def test_wait_node_completes_after_sleep_loop(monkeypatch):
    run = _make_run("wait-node-user")
    executor = PipelineExecutor(run)
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr("studio.pipeline_logic.asyncio.sleep", fake_sleep)

    result = async_to_sync(executor._execute_node)(
        {"id": "wait", "type": "logic/wait", "data": {"wait_minutes": 0.1}},
        {},
        {},
    )

    assert result["status"] == "completed"
    assert result["output"] == "⏱️ Ожидание завершено: 0.1 мин."
    assert len(sleep_calls) == 6


def test_wait_node_respects_executor_stop_event(monkeypatch):
    run = _make_run("wait-stop-user")
    executor = PipelineExecutor(run)
    executor.request_stop()

    async def fake_sleep(seconds: float) -> None:
        raise AssertionError("wait should stop before sleeping")

    monkeypatch.setattr("studio.pipeline_logic.asyncio.sleep", fake_sleep)

    result = async_to_sync(executor._execute_node)(
        {"id": "wait", "type": "logic/wait", "data": {"wait_minutes": 0.1}},
        {},
        {},
    )

    assert result == {"status": "stopped", "output": "Wait cancelled by stop request", "stopped": True}


def test_human_approval_node_returns_approved_decision(monkeypatch):
    run = _make_run("approval-node-user")
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
            fresh_run = PipelineRun.objects.get(pk=run.pk)
            node_state = dict(fresh_run.node_states.get("approval", {}))
            node_state["approval_decision"] = "approved"
            node_state["approval_response"] = "Ship it"
            fresh_run.node_states["approval"] = node_state
            fresh_run.save(update_fields=["node_states"])

        await sync_to_async(_approve, thread_sensitive=True)()

    monkeypatch.setattr("studio.pipeline_interactions._execute_output_email", fake_output_email)
    monkeypatch.setattr("studio.pipeline_interactions._execute_output_telegram", fake_output_telegram)
    monkeypatch.setattr("studio.pipeline_interactions.asyncio.sleep", fake_sleep)

    result = async_to_sync(PipelineExecutor(run)._execute_node)(node, {}, node_outputs)

    assert result["status"] == "completed"
    assert result["decision"] == "approved"
    assert "Ship it" in result["output"]


def test_human_approval_node_sends_telegram_callback_buttons(monkeypatch):
    run = _make_run("approval-telegram-user")
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

    async def fake_poll(*_args, **_kwargs):
        return {"decision": "approved", "response_text": "Подтверждено из Telegram"}

    async def fake_sleep(_seconds: float) -> None:
        return None

    async def fake_send_telegram_message(**_kwargs):
        return {"status": "completed", "output": "decision confirmation sent"}

    monkeypatch.setattr("studio.pipeline_interactions._execute_output_email", fake_output_email)
    monkeypatch.setattr("studio.pipeline_interactions._execute_output_telegram", fake_output_telegram)
    monkeypatch.setattr("studio.pipeline_interactions._poll_telegram_approval_decision", fake_poll)
    monkeypatch.setattr("studio.pipeline_interactions._send_telegram_message", fake_send_telegram_message)
    monkeypatch.setattr("studio.pipeline_interactions.asyncio.sleep", fake_sleep)

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
    assert reply_markup["inline_keyboard"][0][0]["text"] == "✅ Одобрить"
    assert reply_markup["inline_keyboard"][0][0]["callback_data"].startswith("approval:approved:")
    assert reply_markup["inline_keyboard"][0][1]["text"] == "❌ Отклонить"
    assert reply_markup["inline_keyboard"][0][1]["callback_data"].startswith("approval:rejected:")


def test_human_approval_node_uses_global_telegram_defaults_when_node_fields_blank(monkeypatch):
    run = _make_run("approval-global-telegram-user")
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

    async def fake_poll(*_args, **_kwargs):
        return {"decision": "approved", "response_text": "Подтверждено через глобальные настройки"}

    async def fake_sleep(_seconds: float) -> None:
        return None

    async def fake_send_telegram_message(**_kwargs):
        return {"status": "completed", "output": "decision confirmation sent"}

    monkeypatch.setattr("studio.pipeline_interactions._global_tg_defaults", lambda: ("global-bot", "global-chat"))
    monkeypatch.setattr("studio.pipeline_interactions._global_email_defaults", lambda: ("", "", "", "", ""))
    monkeypatch.setattr("studio.pipeline_interactions._execute_output_email", fake_output_email)
    monkeypatch.setattr("studio.pipeline_interactions._execute_output_telegram", fake_output_telegram)
    monkeypatch.setattr("studio.pipeline_interactions._poll_telegram_approval_decision", fake_poll)
    monkeypatch.setattr("studio.pipeline_interactions._send_telegram_message", fake_send_telegram_message)
    monkeypatch.setattr("studio.pipeline_interactions.asyncio.sleep", fake_sleep)

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        node,
        {},
        {"plan": {"status": "completed", "output": "Ready"}},
    )

    assert result["status"] == "completed"
    assert result["decision"] == "approved"
    assert captured["data"]["bot_token"] == "global-bot"
    assert captured["data"]["chat_id"] == "global-chat"


def test_poll_telegram_approval_decision_consumes_callback_updates(monkeypatch):
    import studio.pipeline_executor as executor_module

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
                return _FakeHttpResponse(
                    status_code=200,
                    text='{"ok": true}',
                )
            return _FakeHttpResponse(status_code=200, text='{"ok": true}')

    monkeypatch.setattr("studio.pipeline_telegram.httpx.AsyncClient", FakeHttpClient)

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

    monkeypatch.setattr(_FakeHttpResponse, "json", fake_json_response, raising=False)

    result = async_to_sync(_poll_telegram_approval_decision)("bot-123", "token-xyz")

    assert result is not None
    assert result["decision"] == "approved"
    assert result["response_text"] == "через кнопку в Telegram"
    calls = captured["calls"]
    assert any(url.endswith("/getUpdates") for url, _payload in calls)
    assert any(url.endswith("/answerCallbackQuery") for url, _payload in calls)


def test_telegram_input_node_returns_operator_reply(monkeypatch):
    run = _make_run("telegram-input-user")
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

    monkeypatch.setattr("studio.pipeline_interactions._send_telegram_message", fake_send_telegram_message)
    monkeypatch.setattr("studio.pipeline_interactions._poll_telegram_reply_message", fake_poll_reply)
    monkeypatch.setattr("studio.pipeline_interactions.asyncio.sleep", fake_sleep)

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
    run = _make_run("telegram-input-global-user")
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

    monkeypatch.setattr("studio.pipeline_interactions._global_tg_defaults", lambda: ("global-bot", "global-chat"))
    monkeypatch.setattr("studio.pipeline_interactions._send_telegram_message", fake_send_telegram_message)
    monkeypatch.setattr("studio.pipeline_interactions._poll_telegram_reply_message", fake_poll_reply)
    monkeypatch.setattr("studio.pipeline_interactions.asyncio.sleep", fake_sleep)

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
    run = _make_run("telegram-input-stale-stop-user")
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

    monkeypatch.setattr("studio.pipeline_interactions._send_telegram_message", fake_send_telegram_message)
    monkeypatch.setattr("studio.pipeline_interactions._poll_telegram_reply_message", fake_poll_reply)
    monkeypatch.setattr("studio.pipeline_interactions.asyncio.sleep", fake_sleep)

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        node,
        {"container_name": "mini-prod-mcp-demo"},
        {"restart_container": {"status": "failed", "error": "exit 1", "output": "status=exited"}},
    )

    assert result["status"] == "completed"
    assert result["decision"] == "received"
    assert "docker start mini-prod-mcp-demo" in result["output"]


def test_telegram_input_node_stops_only_on_runtime_stop_request(monkeypatch):
    run = _make_run("telegram-input-runtime-stop-user")
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

    monkeypatch.setattr("studio.pipeline_interactions._send_telegram_message", fake_send_telegram_message)
    monkeypatch.setattr("studio.pipeline_interactions._poll_telegram_reply_message", fake_poll_reply)
    monkeypatch.setattr("studio.pipeline_interactions.asyncio.sleep", fake_sleep)

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        node,
        {"container_name": "mini-prod-mcp-demo"},
        {"restart_container": {"status": "failed", "error": "exit 1", "output": "status=exited"}},
    )

    assert poll_calls["count"] == 1
    assert result["status"] == "stopped"
    assert result["stopped"] is True


def test_react_agent_node_executes_with_rendered_goal(monkeypatch):
    run = _make_run("react-node-user")
    server = Server.objects.create(user=run.pipeline.owner, name="react-srv", host="10.0.0.1", username="root")
    captured: dict[str, object] = {}

    async def fake_run_pipeline_react_agent(**kwargs):
        captured.update({"goal": kwargs["goal"], "servers": [item.name for item in kwargs["servers"]], "permission_mode": kwargs["permission_mode"]})
        return SimpleNamespace(agent_run_id=101, status="completed", final_report="react ok", ai_analysis="")

    monkeypatch.setattr("studio.pipeline_agent_runtime.run_pipeline_react_agent", fake_run_pipeline_react_agent)

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        {
            "id": "react",
            "type": "agent/react",
            "data": {"server_ids": [server.id], "goal": "Inspect {ticket}", "permission_mode": "PLAN"},
        },
        {"ticket": "INC-42"},
        {},
    )

    assert result["status"] == "completed"
    assert result["output"] == "react ok"
    assert captured["goal"] == "Inspect INC-42"
    assert captured["servers"] == ["react-srv"]
    assert captured["permission_mode"] == "PLAN"


def test_multi_agent_node_executes_with_rendered_goal(monkeypatch):
    run = _make_run("multi-node-user")
    server = Server.objects.create(user=run.pipeline.owner, name="multi-srv", host="10.0.0.2", username="root")
    captured: dict[str, object] = {}

    async def fake_run_pipeline_multi_agent(**kwargs):
        captured.update({"goal": kwargs["goal"], "servers": [item.name for item in kwargs["servers"]], "permission_mode": kwargs["permission_mode"]})
        return SimpleNamespace(agent_run_id=202, status="completed", final_report="multi ok", ai_analysis="")

    monkeypatch.setattr("studio.pipeline_agent_runtime.run_pipeline_multi_agent", fake_run_pipeline_multi_agent)

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        {
            "id": "multi",
            "type": "agent/multi",
            "data": {"server_ids": [server.id], "goal": "Coordinate {ticket}", "permission_mode": "SAFE"},
        },
        {"ticket": "INC-77"},
        {},
    )

    assert result["status"] == "completed"
    assert result["output"] == "multi ok"
    assert captured["goal"] == "Coordinate INC-77"
    assert captured["servers"] == ["multi-srv"]
    assert captured["permission_mode"] == "SAFE"


def test_ssh_cmd_node_runs_preflight_command_and_verification(monkeypatch):
    run = _make_run("ssh-node-user")
    server = Server.objects.create(user=run.pipeline.owner, name="ssh-srv", host="10.0.0.3", username="root")
    calls: list[str] = []
    connect_kwargs_seen: dict[str, object] = {}

    class FakeConnection:
        async def run(self, command_text: str, timeout: int = 120):
            calls.append(command_text)
            return SimpleNamespace(stdout=f"ran {command_text}", stderr="", exit_status=0)

    class FakeConnectContext:
        async def __aenter__(self):
            return FakeConnection()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    async def fake_get_server_connect_kwargs(server_obj, *, connect_timeout=30):
        return {"host": server_obj.host, "username": server_obj.username, "connect_timeout": connect_timeout}

    async def fake_log_pipeline_ssh_command(*args, **kwargs):
        return None

    def fake_connect(**kwargs):
        connect_kwargs_seen.update(kwargs)
        return FakeConnectContext()

    monkeypatch.setattr("studio.pipeline_agent_runtime.PermissionEngine", _PermissionEngine)
    monkeypatch.setattr("studio.pipeline_agent_runtime.SandboxManager", _SandboxManager)
    monkeypatch.setattr("studio.pipeline_agent_runtime.HookManager", _HookManager)
    monkeypatch.setattr("studio.pipeline_agent_runtime._log_pipeline_ssh_command", fake_log_pipeline_ssh_command)
    monkeypatch.setattr("studio.pipeline_agent_runtime.get_server_connect_kwargs", fake_get_server_connect_kwargs)
    monkeypatch.setattr("asyncssh.connect", fake_connect)

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        {
            "id": "ssh",
            "type": "agent/ssh_cmd",
            "data": {
                "server_id_context_key": "target_server_id",
                "command": "echo {ticket}",
                "preflight_commands": ["echo preflight"],
                "verification_commands": ["echo verify"],
            },
        },
        {"ticket": "INC-55", "target_server_id": server.id},
        {},
    )

    assert result["status"] == "completed"
    assert result["exit_code"] == 0
    assert result["verification_summary"] == "verified"
    assert calls == ["echo preflight", "echo INC-55", "echo verify"]
    assert connect_kwargs_seen["connect_timeout"] == 30


def test_llm_query_node_streams_response_with_context(monkeypatch):
    run = _make_run("llm-node-user")
    captured: dict[str, object] = {}

    async def fake_load_server_memory(owner, config, context):
        return "SERVER MEMORY"

    async def fake_load_operational_recipes(owner, config, context, *, role_slug, query):
        return "OPERATIONAL RECIPES"

    class FakeLLMProvider:
        async def stream_chat(self, full_prompt, *, model, specific_model=None, purpose):
            captured["prompt"] = full_prompt
            captured["model"] = model
            captured["specific_model"] = specific_model
            captured["purpose"] = purpose
            for chunk in ["part-1 ", "part-2"]:
                yield chunk

    monkeypatch.setattr("studio.pipeline_agent_llm._load_pipeline_server_memory", fake_load_server_memory)
    monkeypatch.setattr("studio.pipeline_agent_llm._load_pipeline_operational_recipes", fake_load_operational_recipes)
    monkeypatch.setattr("app.core.llm.LLMProvider", FakeLLMProvider)

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        {
            "id": "llm",
            "type": "agent/llm_query",
            "data": {
                "prompt": "Summarize incident {ticket}",
                "system_prompt": "SYSTEM",
                "provider": "gemini",
                "include_all_outputs": True,
            },
        },
        {"ticket": "INC-88"},
        {"prep": {"status": "completed", "output": "CPU at 99%"}},
    )

    assert result["status"] == "completed"
    assert result["output"] == "part-1 part-2"
    assert "Summarize incident INC-88" in str(captured["prompt"])
    assert "CPU at 99%" in str(captured["prompt"])
    assert "SERVER MEMORY" in str(captured["prompt"])
    assert captured["model"] == "gemini"


def test_mcp_call_node_executes_tool_and_tracks_execution(monkeypatch):
    run = _make_run("mcp-node-user")
    mcp_server = MCPServerPool.objects.create(
        owner=run.pipeline.owner,
        name="Demo MCP",
        transport=MCPServerPool.TRANSPORT_SSE,
        url="http://localhost:8765/sse",
    )
    executor = PipelineExecutor(run)
    captured: dict[str, object] = {}

    async def fake_call_mcp_tool(server_obj, tool_name: str, arguments: dict):
        captured["server_name"] = server_obj.name
        captured["tool_name"] = tool_name
        captured["arguments"] = arguments
        return {"content": [{"type": "text", "text": "pong"}]}

    monkeypatch.setattr("studio.pipeline_agent_mcp.PermissionEngine", _PermissionEngine)
    monkeypatch.setattr("studio.pipeline_agent_mcp.SandboxManager", _SandboxManager)
    monkeypatch.setattr("studio.pipeline_agent_mcp.HookManager", _HookManager)
    monkeypatch.setattr("studio.pipeline_agent_mcp.call_mcp_tool", fake_call_mcp_tool)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "mcp",
            "type": "agent/mcp_call",
            "data": {
                "mcp_server_id": mcp_server.id,
                "tool_name": "ping",
                "arguments": {"ticket": "{ticket}"},
            },
        },
        {"ticket": "INC-101"},
        {},
    )

    assert result["status"] == "completed"
    assert "pong" in result["output"]
    assert captured["server_name"] == "Demo MCP"
    assert captured["tool_name"] == "ping"
    assert captured["arguments"] == {"ticket": "INC-101"}
    assert executor._executed_mcp_tools == {"ping"}


def test_output_report_node_updates_run_summary():
    run = _make_run("report-node-user")
    executor = PipelineExecutor(run)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "report",
            "type": "output/report",
            "data": {"template": "Ticket {ticket}: {prep_output}"},
        },
        {"ticket": "INC-303"},
        {"prep": {"status": "completed", "output": "ready"}},
    )

    run.refresh_from_db()
    assert result["status"] == "completed"
    assert result["output"] == "Ticket INC-303: ready"
    assert run.summary == "Ticket INC-303: ready"


def test_output_report_node_redacts_secret_outputs_in_summary():
    run = _make_run("report-redaction-user")
    executor = PipelineExecutor(run)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "report",
            "type": "output/report",
            "data": {"template": "Ticket {ticket}: {prep_output}"},
        },
        {"ticket": "INC-304"},
        {"prep": {"status": "completed", "output": "ready password=super-secret"}},
    )

    run.refresh_from_db()
    assert result["status"] == "completed"
    assert "super-secret" not in result["output"]
    assert "super-secret" not in run.summary
    assert "[REDACTED:secret_assignment]" in run.summary


def test_output_report_node_auto_report_redacts_node_outputs():
    run = _make_run("report-auto-redaction-user")
    executor = PipelineExecutor(run)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "report",
            "type": "output/report",
            "data": {},
        },
        {},
        {
            "prep": {
                "status": "failed",
                "output": "stdout password=super-secret",
                "error": "stderr api_key=hidden-key",
            }
        },
    )

    run.refresh_from_db()
    assert result["status"] == "completed"
    assert "super-secret" not in result["output"]
    assert "hidden-key" not in result["output"]
    assert "[REDACTED:secret_assignment]" in run.summary
    assert run.summary.count("[REDACTED:secret_assignment]") >= 2


def test_output_webhook_node_posts_payload(monkeypatch):
    run = _make_run("webhook-node-user")
    executor = PipelineExecutor(run)
    captured: dict[str, object] = {}

    class FakeHttpClient:
        def __init__(self, timeout: int = 30) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict | None = None):
            captured["url"], captured["json"], captured["headers"] = url, json, headers or {}
            return _FakeHttpResponse(status_code=204)

    monkeypatch.setattr("studio.executor.nodes.output_webhook.httpx.AsyncClient", FakeHttpClient)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "webhook_out",
            "type": "output/webhook",
            "data": {
                "url": "https://example.com/hook",
                "extra_payload": {"kind": "smoke"},
                "headers": {"X-Ticket": "{ticket}"},
                "timeout_seconds": 7,
            },
        },
        {"ticket": "INC-404"},
        {"prep": {"status": "completed", "output": "done"}},
    )

    assert result["status"] == "completed"
    assert result["http_status"] == 204
    assert captured["url"] == "https://example.com/hook"
    assert captured["json"]["kind"] == "smoke"
    assert captured["json"]["outputs"]["prep"]["output"] == "done"
    assert captured["json"]["context"]["ticket"] == "INC-404"
    assert captured["headers"] == {"X-Ticket": "INC-404"}
    assert captured["timeout"] == 7


def test_output_webhook_node_redacts_secret_payload(monkeypatch):
    run = _make_run("webhook-redaction-user")
    executor = PipelineExecutor(run)
    captured: dict[str, object] = {}

    class FakeHttpClient:
        def __init__(self, timeout: int = 30) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict | None = None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers or {}
            return _FakeHttpResponse(status_code=204)

    monkeypatch.setattr("studio.executor.nodes.output_webhook.httpx.AsyncClient", FakeHttpClient)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "webhook_out",
            "type": "output/webhook",
            "data": {"url": "https://example.com/hook", "extra_payload": {"note": "{prep_output}"}},
        },
        {"ticket": "INC-405"},
        {"prep": {"status": "completed", "output": "done password=super-secret"}},
    )

    assert result["status"] == "completed"
    payload_text = str(captured["json"])
    assert "super-secret" not in payload_text
    assert "[REDACTED:secret_assignment]" in payload_text


def test_output_webhook_node_can_fail_on_non_2xx(monkeypatch):
    run = _make_run("webhook-non-2xx-user")
    executor = PipelineExecutor(run)

    class FakeHttpClient:
        def __init__(self, timeout: int = 30) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict | None = None):
            return _FakeHttpResponse(status_code=503)

    monkeypatch.setattr("studio.executor.nodes.output_webhook.httpx.AsyncClient", FakeHttpClient)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "webhook_out",
            "type": "output/webhook",
            "data": {"url": "https://example.com/hook", "fail_on_non_2xx": True},
        },
        {},
        {},
    )

    assert result["status"] == "failed"
    assert result["http_status"] == 503
    assert result["error"] == "Webhook returned HTTP 503"


def test_ops_server_snapshot_node_uses_context_server_id(monkeypatch):
    run = _make_run("ops-snapshot-user")
    server = Server.objects.create(user=run.pipeline.owner, name="ops-srv", host="10.0.0.8", username="root")

    async def fake_secret(_server):
        return ""

    async def fake_overview(_server, *, secret=""):
        return {"summary": {"status": "ok"}}

    async def fake_disk(_server, *, secret=""):
        return {"summary": {"critical_mounts": 0}}

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.get_linux_ui_overview", fake_overview)
    monkeypatch.setattr("studio.executor.nodes.ops.get_linux_ui_disk", fake_disk)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "snapshot",
            "type": "ops/server_snapshot",
            "data": {"server_id_context_key": "target_server_id", "sections": ["overview", "disk"]},
        },
        {"target_server_id": server.id},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert "ops-srv" in result["output"]
    assert result["snapshot"]["sections"]["overview"]["summary"]["status"] == "ok"


def test_ops_log_query_node_collects_and_filters_service_logs(monkeypatch):
    run = _make_run("ops-log-query-user")
    server = Server.objects.create(user=run.pipeline.owner, name="logs-srv", host="10.0.0.9", username="root")

    async def fake_secret(_server):
        return ""

    async def fake_logs(_server, *, secret="", source="journal", lines=120, service=""):
        return {
            "source": source,
            "service": service,
            "lines": lines,
            "available": True,
            "content": "ok boot\nERROR failed auth\nwarning slow request",
        }

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.get_linux_ui_logs", fake_logs)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "log_query",
            "type": "ops/log_query",
            "data": {
                "server_id_context_key": "target_server_id",
                "source": "service",
                "service": "nginx",
                "lines": 60,
                "filter_text": "failed",
            },
        },
        {"target_server_id": server.id},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert "logs-srv" in result["output"]
    assert result["logs"]["source"] == "service"
    assert result["logs"]["service"] == "nginx"
    assert result["logs"]["match_count"] == 1
    assert result["logs"]["matched_lines"] == ["ERROR failed auth"]


def test_ops_file_action_node_reads_text_file(monkeypatch):
    run = _make_run("ops-file-read-user")
    server = Server.objects.create(user=run.pipeline.owner, name="file-srv", host="10.0.0.10", username="root")

    async def fake_secret(_server):
        return ""

    async def fake_read_text_file(_server, *, secret="", path="", max_bytes=131072):
        return {
            "path": path,
            "filename": "os-release",
            "size": 24,
            "encoding": "utf-8",
            "content": "NAME=Demo Linux\nVERSION=1",
        }

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.read_text_file", fake_read_text_file)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "file_read",
            "type": "ops/file_action",
            "data": {
                "server_id_context_key": "target_server_id",
                "action": "read",
                "path": "/etc/os-release",
                "max_bytes": 65536,
            },
        },
        {"target_server_id": server.id},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert result["file"]["action"] == "read"
    assert result["file"]["content"] == "NAME=Demo Linux\nVERSION=1"


def test_ops_file_action_node_writes_text_file_without_echoing_content(monkeypatch):
    run = _make_run("ops-file-write-user")
    server = Server.objects.create(user=run.pipeline.owner, name="file-srv", host="10.0.0.11", username="root")
    captured: dict[str, object] = {}

    async def fake_secret(_server):
        return ""

    async def fake_write_text_file(_server, *, secret="", path="", content="", max_bytes=131072):
        captured["path"] = path
        captured["content"] = content
        return {
            "path": path,
            "filename": "app.conf",
            "size": len(content.encode("utf-8")),
            "encoding": "utf-8",
            "content": content,
        }

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.write_text_file", fake_write_text_file)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "file_write",
            "type": "ops/file_action",
            "data": {
                "server_id": server.id,
                "action": "write",
                "path": "/etc/app/app.conf",
                "content": "token={secret_value}",
            },
        },
        {"secret_value": "redacted-at-output-boundary"},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert captured == {"path": "/etc/app/app.conf", "content": "token=redacted-at-output-boundary"}
    assert result["file"]["action"] == "write"
    assert "content" not in result["file"]
    assert "content_sha256" in result["file"]


def test_ops_package_action_lists_updates(monkeypatch):
    run = _make_run("ops-package-list-user")
    server = Server.objects.create(user=run.pipeline.owner, name="pkg-srv", host="10.0.0.12", username="root")

    async def fake_secret(_server):
        return ""

    async def fake_packages(_server, *, secret=""):
        return {
            "package_manager": "apt",
            "installed": [{"name": "curl", "version": "1.0"}],
            "updates": ["curl/stable 1.1 amd64"],
            "summary": {"installed_common": 1, "update_candidates": 1},
        }

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.get_linux_ui_packages", fake_packages)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "packages",
            "type": "ops/package_action",
            "data": {"server_id": server.id, "action": "list_updates"},
        },
        {},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert result["packages"]["package_manager"] == "apt"
    assert result["packages"]["summary"]["update_candidates"] == 1


def test_ops_package_action_runs_explicit_install_and_verifies(monkeypatch):
    run = _make_run("ops-package-install-user")
    server = Server.objects.create(user=run.pipeline.owner, name="pkg-srv", host="10.0.0.13", username="root")
    captured: dict[str, object] = {}

    async def fake_secret(_server):
        return ""

    async def fake_capabilities(_server, *, secret=""):
        return {"package_manager": "apt"}

    async def fake_run_command_result(_server, *, secret="", command=""):
        captured["command"] = command
        return {"stdout": "installed curl\n__ACTION_EXIT__=0\n", "stderr": "", "exit_code": 0}

    async def fake_packages(_server, *, secret=""):
        return {"package_manager": "apt", "installed": [], "updates": [], "summary": {"update_candidates": 0}}

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.get_linux_ui_capabilities", fake_capabilities)
    monkeypatch.setattr("studio.executor.nodes.ops._run_command_result", fake_run_command_result)
    monkeypatch.setattr("studio.executor.nodes.ops.get_linux_ui_packages", fake_packages)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "package_install",
            "type": "ops/package_action",
            "data": {"server_id": server.id, "action": "install", "packages": ["curl"], "verify": True},
        },
        {},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert "apt-get install -y -- curl" in str(captured["command"])
    assert result["package_action"]["packages"] == ["curl"]
    assert result["package_action"]["success"] is True


def test_ops_disk_cleanup_inspects_disk_state(monkeypatch):
    run = _make_run("ops-disk-inspect-user")
    server = Server.objects.create(user=run.pipeline.owner, name="disk-srv", host="10.0.0.14", username="root")

    async def fake_secret(_server):
        return ""

    async def fake_disk(_server, *, secret=""):
        return {
            "summary": {"critical_mounts": 1, "cleanup_candidates": 3},
            "mounts": [],
            "top_directories": [],
            "large_logs": [],
            "cleanup_candidates": ["/tmp/old"],
        }

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.get_linux_ui_disk", fake_disk)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "disk",
            "type": "ops/disk_cleanup",
            "data": {"server_id": server.id, "action": "inspect"},
        },
        {},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert result["disk"]["summary"]["cleanup_candidates"] == 3
    assert result["disk"]["action"] == "inspect"


def test_ops_disk_cleanup_runs_tmp_cleanup_and_verifies(monkeypatch):
    run = _make_run("ops-disk-cleanup-user")
    server = Server.objects.create(user=run.pipeline.owner, name="disk-clean-srv", host="10.0.0.15", username="root")
    captured: dict[str, object] = {}

    async def fake_secret(_server):
        return ""

    async def fake_disk(_server, *, secret=""):
        return {
            "summary": {"critical_mounts": 0, "cleanup_candidates": 0},
            "mounts": [],
            "top_directories": [],
            "large_logs": [],
            "cleanup_candidates": [],
        }

    async def fake_run_command_result(_server, *, secret="", command=""):
        captured["command"] = command
        return {"stdout": "__PLAN__\n/tmp/old\n__ACTION__\nremoved=/tmp/old\n__ACTION_EXIT__=0\n", "stderr": "", "exit_code": 0}

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.get_linux_ui_disk", fake_disk)
    monkeypatch.setattr("studio.executor.nodes.ops._run_command_result", fake_run_command_result)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "disk_cleanup",
            "type": "ops/disk_cleanup",
            "data": {"server_id": server.id, "action": "tmp_cleanup", "min_age_days": 10, "max_entries": 25, "dry_run": False},
        },
        {},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert "find /tmp /var/tmp -xdev -mindepth 1 -mtime +10" in str(captured["command"])
    assert result["disk_cleanup"]["success"] is True
    assert result["disk_cleanup"]["dry_run"] is False


def test_ops_backup_restore_check_inspects_latest_backup(monkeypatch):
    run = _make_run("ops-backup-check-user")
    server = Server.objects.create(user=run.pipeline.owner, name="backup-srv", host="10.0.0.16", username="root")

    async def fake_secret(_server):
        return ""

    async def fake_run_command_result(_server, *, secret="", command=""):
        return {
            "stdout": "__FILES__\n9999999999\t1048576\t/var/backups/app.tar.gz\n__VERIFY__\nverification=skipped\n",
            "stderr": "",
            "exit_code": 0,
        }

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops._run_command_result", fake_run_command_result)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "backup_check",
            "type": "ops/backup_restore_check",
            "data": {"server_id": server.id, "action": "inspect", "path": "/var/backups", "max_age_hours": 24},
        },
        {},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert result["backup_restore_check"]["summary"]["latest_path"] == "/var/backups/app.tar.gz"
    assert result["backup_restore_check"]["verification"]["requested"] is False


def test_ops_backup_restore_check_verifies_latest_archive(monkeypatch):
    run = _make_run("ops-backup-verify-user")
    server = Server.objects.create(user=run.pipeline.owner, name="backup-verify-srv", host="10.0.0.17", username="root")
    captured: dict[str, object] = {}

    async def fake_secret(_server):
        return ""

    async def fake_run_command_result(_server, *, secret="", command=""):
        captured["command"] = command
        return {
            "stdout": "__FILES__\n9999999999\t1048576\t/var/backups/app.tar.gz\n__VERIFY__\nlatest=/var/backups/app.tar.gz\nverification_exit=0\n",
            "stderr": "",
            "exit_code": 0,
        }

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops._run_command_result", fake_run_command_result)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "backup_verify",
            "type": "ops/backup_restore_check",
            "data": {"server_id": server.id, "action": "verify_latest", "path": "/var/backups", "max_depth": 3},
        },
        {},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert 'find "$BACKUP_DIR" -maxdepth "$MAX_DEPTH"' in str(captured["command"])
    assert result["backup_restore_check"]["verification"]["success"] is True


def test_ops_http_check_node_passes_expected_status(monkeypatch):
    run = _make_run("ops-http-user")
    captured: dict[str, object] = {}

    class FakeHttpClient:
        def __init__(self, timeout: int = 15, follow_redirects: bool = True) -> None:
            self.timeout = timeout
            self.follow_redirects = follow_redirects

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def request(self, method: str, url: str):
            captured["method"] = method
            captured["url"] = url
            return SimpleNamespace(status_code=204, text="healthy")

    monkeypatch.setattr("studio.executor.nodes.ops.httpx.AsyncClient", FakeHttpClient)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "http_check",
            "type": "ops/http_check",
            "data": {"url": "https://example.test/health", "method": "GET", "expected_status": [204], "body_contains": "healthy"},
        },
        {},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert captured == {"method": "GET", "url": "https://example.test/health"}
    assert result["http_check"]["status_code"] == 204


def test_ops_alert_update_resolves_owned_alert():
    run = _make_run("ops-alert-user")
    server = Server.objects.create(user=run.pipeline.owner, name="alert-srv", host="10.0.0.12", username="root")
    alert = ServerAlert.objects.create(
        server=server,
        alert_type=ServerAlert.TYPE_SERVICE,
        severity=ServerAlert.SEVERITY_CRITICAL,
        title="Service down",
        message="nginx failed",
    )

    result = async_to_sync(_execute_registry_node)(
        {"id": "resolve_alert", "type": "ops/alert_update", "data": {"alert_id_context_key": "alert_id", "action": "resolve"}},
        {"alert_id": alert.id},
        {},
        run,
    )

    alert.refresh_from_db()
    assert result["status"] == "completed"
    assert alert.is_resolved is True
    assert result["alert"]["alert_id"] == alert.id


def test_output_email_node_sends_rendered_message(monkeypatch):
    run = _make_run("email-node-user")
    executor = PipelineExecutor(run)
    _FakeSMTP.sent_messages = []

    monkeypatch.setattr("studio.executor.nodes.output_email._global_email_defaults", lambda: ("ops@example.com", "smtp.example.com", "", "", ""))
    monkeypatch.setattr("studio.executor.nodes.output_email.asyncio.get_event_loop", lambda: _FakeLoop())
    monkeypatch.setattr("smtplib.SMTP", _FakeSMTP)
    monkeypatch.setattr("smtplib.SMTP_SSL", _FakeSMTP)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "email_out",
            "type": "output/email",
            "data": {"subject": "Run {ticket}", "body": "Body: {prep_output}"},
        },
        {"ticket": "INC-505"},
        {"prep": {"status": "completed", "output": "email ready"}},
    )

    assert result["status"] == "completed"
    assert "ops@example.com" in result["output"]
    assert len(_FakeSMTP.sent_messages) == 1
    parsed_message = message_from_string(_FakeSMTP.sent_messages[0]["message"])
    plain_parts = [
        (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8")
        for part in parsed_message.walk()
        if part.get_content_type() == "text/plain"
    ]
    assert any("Body: email ready" in part for part in plain_parts)


def test_output_email_node_redacts_secret_body_and_preserves_approval_links(monkeypatch):
    run = _make_run("email-redaction-user")
    executor = PipelineExecutor(run)
    _FakeSMTP.sent_messages = []
    approval_url = "http://localhost/api/studio/runs/1/approve/node/?token=approval-secret&decision=approved"

    monkeypatch.setattr("studio.executor.nodes.output_email._global_email_defaults", lambda: ("ops@example.com", "smtp.example.com", "", "", ""))
    monkeypatch.setattr("studio.executor.nodes.output_email.asyncio.get_event_loop", lambda: _FakeLoop())
    monkeypatch.setattr("smtplib.SMTP", _FakeSMTP)
    monkeypatch.setattr("smtplib.SMTP_SSL", _FakeSMTP)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "email_out",
            "type": "output/email",
            "data": {
                "subject": "Run {ticket}",
                "body": "Approve: {approval_url}\nBody: {prep_output}",
                "_redaction_preserve_values": [approval_url],
                "_redaction_preserve_context_keys": ["approval_url"],
            },
        },
        {"ticket": "INC-506", "approval_url": approval_url},
        {"prep": {"status": "completed", "output": "email password=super-secret"}},
    )

    assert result["status"] == "completed"
    parsed_message = message_from_string(_FakeSMTP.sent_messages[0]["message"])
    plain_parts = [
        (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8")
        for part in parsed_message.walk()
        if part.get_content_type() == "text/plain"
    ]
    body = "\n".join(plain_parts)
    assert approval_url in body
    assert "super-secret" not in body
    assert "[REDACTED:secret_assignment]" in body


def test_output_email_node_fails_on_smtp_error(monkeypatch):
    run = _make_run("email-error-user")
    executor = PipelineExecutor(run)

    class BrokenSMTP(_FakeSMTP):
        def sendmail(self, from_email: str, recipients: list[str], message: str) -> None:
            raise RuntimeError("smtp down")

    monkeypatch.setattr("studio.executor.nodes.output_email._global_email_defaults", lambda: ("ops@example.com", "smtp.example.com", "", "", ""))
    monkeypatch.setattr("studio.executor.nodes.output_email.asyncio.get_event_loop", lambda: _FakeLoop())
    monkeypatch.setattr("smtplib.SMTP", BrokenSMTP)
    monkeypatch.setattr("smtplib.SMTP_SSL", BrokenSMTP)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "email_out",
            "type": "output/email",
            "data": {"subject": "Run {ticket}", "body": "Body"},
        },
        {"ticket": "INC-507"},
        {},
    )

    assert result["status"] == "failed"
    assert result["error"] == "SMTP error: smtp down"


def test_output_telegram_node_sends_rendered_message(monkeypatch):
    run = _make_run("telegram-node-user")
    executor = PipelineExecutor(run)
    captured: dict[str, object] = {}

    class FakeHttpClient:
        def __init__(self, timeout: int = 30) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict):
            captured["url"] = url
            captured["json"] = json
            return _FakeHttpResponse(status_code=200)

    monkeypatch.setattr("studio.executor.nodes.output_telegram._global_tg_defaults", lambda: ("token-123", "chat-9"))
    monkeypatch.setattr("studio.executor.nodes.output_telegram.httpx.AsyncClient", FakeHttpClient)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "telegram_out",
            "type": "output/telegram",
            "data": {"message": "Pipeline {pipeline_name} run {run_id}\nTicket {ticket}\n{all_outputs}"},
        },
        {"ticket": "INC-606"},
        {"prep": {"status": "completed", "output": "telegram ready"}},
    )

    assert result["status"] == "completed"
    assert "chat-9" in result["output"]
    assert captured["url"] == "https://api.telegram.org/bottoken-123/sendMessage"
    assert "Pipeline Pipeline for telegram-node-user run" in str(captured["json"]["text"])
    assert "INC-606" in str(captured["json"]["text"])
    assert "telegram ready" in str(captured["json"]["text"])


def test_output_telegram_node_redacts_secret_message(monkeypatch):
    run = _make_run("telegram-redaction-user")
    executor = PipelineExecutor(run)
    captured: dict[str, object] = {}

    class FakeHttpClient:
        def __init__(self, timeout: int = 30) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict):
            captured["json"] = json
            return _FakeHttpResponse(status_code=200)

    monkeypatch.setattr("studio.executor.nodes.output_telegram._global_tg_defaults", lambda: ("token-123", "chat-9"))
    monkeypatch.setattr("studio.executor.nodes.output_telegram.httpx.AsyncClient", FakeHttpClient)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "telegram_out",
            "type": "output/telegram",
            "data": {"message": "Pipeline {pipeline_name}\n{all_outputs}\nDirect {prep_output}"},
        },
        {},
        {"prep": {"status": "completed", "output": "telegram password=super-secret"}},
    )

    assert result["status"] == "completed"
    text = str(captured["json"]["text"])
    assert "super-secret" not in text
    assert "[REDACTED:secret_assignment]" in text


def test_output_telegram_node_fails_on_api_error(monkeypatch):
    run = _make_run("telegram-api-error-user")
    executor = PipelineExecutor(run)

    class FakeHttpClient:
        def __init__(self, timeout: int = 30) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict):
            return _FakeHttpResponse(status_code=400, text="bad request")

    monkeypatch.setattr("studio.executor.nodes.output_telegram._global_tg_defaults", lambda: ("token-123", "chat-9"))
    monkeypatch.setattr("studio.executor.nodes.output_telegram.httpx.AsyncClient", FakeHttpClient)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "telegram_out",
            "type": "output/telegram",
            "data": {"message": "Pipeline {pipeline_name}"},
        },
        {},
        {},
    )

    assert result["status"] == "failed"
    assert result["error"] == "Telegram API error 400: bad request"
