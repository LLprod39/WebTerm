import pytest
from django.contrib.auth.models import User
from django.test import Client

from app.background_workers import (
    STUDIO_MONITOR_WORKER,
    STUDIO_PIPELINE_EXECUTION_WORKER,
    STUDIO_SCHEDULED_PIPELINES_WORKER,
    STUDIO_TELEGRAM_BOT_WORKER,
)
from app.worker_state import heartbeat_background_worker
from core_ui.models import UserAppPermission
from studio.models import MCPServerPool, Pipeline

pytestmark = pytest.mark.django_db


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


def _node(node_id: str, node_type: str, data: dict | None = None) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "position": {"x": 0, "y": 0},
        "data": data or {},
    }


def test_readiness_endpoint_returns_empty_ready_report():
    user = User.objects.create_user(username="readiness-empty", password="x")
    _grant_feature(user, "studio_pipelines")
    client = Client()
    client.force_login(user)

    response = client.get("/api/studio/readiness/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == 1
    assert payload["status"] == "ready"
    assert payload["summary"]["node_type_count"] >= 30
    assert payload["summary"]["pipeline_count"] == 0
    assert payload["worker_requirements"] == []
    assert payload["pipelines"] == []


def test_readiness_reports_trigger_without_downstream_nodes():
    user = User.objects.create_user(username="readiness-invalid", password="x")
    _grant_feature(user, "studio_pipelines")
    pipeline = Pipeline.objects.create(
        owner=user,
        name="Empty schedule branch",
        graph_version=2,
        nodes=[
            _node(
                "schedule",
                "trigger/schedule",
                {"label": "Schedule", "cron_expression": "*/5 * * * *"},
            ),
        ],
        edges=[],
    )
    pipeline.sync_triggers_from_nodes()
    client = Client()
    client.force_login(user)

    response = client.get("/api/studio/readiness/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "not_ready"
    item = payload["pipelines"][0]
    assert item["id"] == pipeline.id
    assert item["status"] == "error"
    assert any("no downstream executable nodes" in error for error in item["errors"])
    assert item["issues"][0]["code"] == "trigger_without_downstream"
    assert item["issues"][0]["node_ids"] == ["schedule"]
    assert "Connect this trigger" in item["issues"][0]["next_action"]
    assert item["triggers"][0]["issues"][0]["code"] == "trigger_without_downstream"


def test_readiness_endpoint_can_scope_to_pipeline_id():
    user = User.objects.create_user(username="readiness-api-scope", password="x")
    _grant_feature(user, "studio_pipelines")
    broken = Pipeline.objects.create(
        owner=user,
        name="Broken scoped pipeline",
        graph_version=2,
        nodes=[_node("manual", "trigger/manual")],
        edges=[],
    )
    broken.sync_triggers_from_nodes()
    ready = Pipeline.objects.create(
        owner=user,
        name="Ready ignored pipeline",
        graph_version=2,
        nodes=[_node("manual", "trigger/manual"), _node("report", "output/report")],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )
    ready.sync_triggers_from_nodes()
    heartbeat_background_worker(STUDIO_PIPELINE_EXECUTION_WORKER, lease_seconds=180)
    client = Client()
    client.force_login(user)

    payload = client.get(f"/api/studio/readiness/?pipeline_id={ready.id}").json()

    assert payload["status"] == "ready"
    assert payload["scope"] == {"active_only": False, "pipeline_ids": [ready.id]}
    assert [item["id"] for item in payload["pipelines"]] == [ready.id]
    assert payload["summary"]["pipeline_count"] == 1


def test_readiness_endpoint_rejects_invalid_pipeline_id():
    user = User.objects.create_user(username="readiness-api-bad-scope", password="x")
    _grant_feature(user, "studio_pipelines")
    client = Client()
    client.force_login(user)

    response = client.get("/api/studio/readiness/?pipeline_id=bad")

    assert response.status_code == 400
    assert response.json()["error"] == "pipeline_id must be an integer"


def test_readiness_endpoint_reports_missing_pipeline_id():
    user = User.objects.create_user(username="readiness-api-missing-scope", password="x")
    _grant_feature(user, "studio_pipelines")
    client = Client()
    client.force_login(user)

    payload = client.get("/api/studio/readiness/?pipeline_id=999999").json()

    assert payload["status"] == "not_ready"
    assert payload["scope"]["missing_pipeline_ids"] == [999999]
    assert payload["summary"]["missing_pipeline_count"] == 1
    assert payload["issues"][0]["code"] == "pipeline_not_found"


def test_readiness_endpoint_can_scope_to_entry_node_branch(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    user = User.objects.create_user(username="readiness-api-entry-scope", password="x")
    _grant_feature(user, "studio_pipelines")
    pipeline = Pipeline.objects.create(
        owner=user,
        name="Branch scoped readiness",
        graph_version=2,
        nodes=[
            _node("manual", "trigger/manual"),
            _node("webhook", "trigger/webhook", {"webhook_payload_map": {}}),
            _node("report", "output/report"),
            _node("webhook_llm", "agent/llm_query", {"provider": "gemini", "prompt": "Summarize"}),
        ],
        edges=[
            {"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"},
            {"id": "e2", "source": "webhook", "target": "webhook_llm", "sourceHandle": "out"},
        ],
    )
    pipeline.sync_triggers_from_nodes()
    heartbeat_background_worker(STUDIO_PIPELINE_EXECUTION_WORKER, lease_seconds=180)
    client = Client()
    client.force_login(user)

    manual_payload = client.get(f"/api/studio/readiness/?pipeline_id={pipeline.id}&entry_node_id=manual").json()
    webhook_payload = client.get(f"/api/studio/readiness/?pipeline_id={pipeline.id}&entry_node_id=webhook").json()

    assert manual_payload["status"] == "ready"
    assert manual_payload["scope"]["entry_node_id"] == "manual"
    assert manual_payload["summary"]["integration_error_count"] == 0
    assert manual_payload["pipelines"][0]["triggers"][0]["node_id"] == "manual"
    assert webhook_payload["status"] == "not_ready"
    assert webhook_payload["pipelines"][0]["issues"][0]["code"] == "llm_credentials_missing"


def test_readiness_lists_required_workers_and_runtime_context():
    user = User.objects.create_user(username="readiness-workers", password="x")
    _grant_feature(user, "studio_pipelines")
    pipeline = Pipeline.objects.create(
        owner=user,
        name="Prod automation",
        graph_version=2,
        nodes=[
            _node("schedule", "trigger/schedule", {"cron_expression": "*/5 * * * *"}),
            _node("monitoring", "trigger/monitoring", {"monitoring_filters": {}}),
            _node("join", "logic/merge", {"mode": "any"}),
            _node("report", "output/report", {"template": "Customer: {customer_name}"}),
            _node(
                "operator_reply",
                "logic/telegram_input",
                {"message": "Need action for {customer_name}?", "bot_token": "token", "chat_id": "123"},
            ),
        ],
        edges=[
            {"id": "e-schedule-join", "source": "schedule", "target": "join", "sourceHandle": "out"},
            {"id": "e-monitoring-join", "source": "monitoring", "target": "join", "sourceHandle": "out"},
            {"id": "e-join-report", "source": "join", "target": "report", "sourceHandle": "out"},
            {"id": "e-report-reply", "source": "report", "target": "operator_reply", "sourceHandle": "success"},
        ],
    )
    pipeline.sync_triggers_from_nodes()
    client = Client()
    client.force_login(user)

    response = client.get("/api/studio/readiness/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["summary"]["pipeline_warning_count"] == 1
    assert payload["summary"]["worker_not_ready_count"] == 4
    workers = {item["worker"]: item for item in payload["worker_requirements"]}
    assert set(workers) == {"monitor", "pipeline-execution", "scheduled-pipelines", "telegram-bot"}
    assert workers["monitor"]["command"] == "python manage.py run_monitor"
    assert workers["monitor"]["worker_kind"] == STUDIO_MONITOR_WORKER
    assert workers["monitor"]["ready"] is False
    assert workers["monitor"]["state"]["status"] == "missing"
    assert workers["monitor"]["issues"][0]["code"] == "worker_not_running"
    assert workers["scheduled-pipelines"]["required_by"] == 1
    assert workers["pipeline-execution"]["command"] == "python manage.py run_pipeline_execution_plane"
    assert workers["telegram-bot"]["command"] == "python manage.py run_telegram_bot"
    item = payload["pipelines"][0]
    assert item["status"] == "warning"
    assert "Some triggers require runtime context before launch." in item["warnings"]
    assert {trigger["type"] for trigger in item["triggers"]} == {"monitoring", "schedule"}
    assert all(trigger["required_context_fields"] == ["customer_name"] for trigger in item["triggers"])
    assert all(trigger["unresolved_context_fields"] == ["customer_name"] for trigger in item["triggers"])
    assert any(issue["code"] == "runtime_context_required" for issue in item["issues"])


def test_readiness_treats_monitoring_context_as_supplied():
    user = User.objects.create_user(username="readiness-monitoring-context", password="x")
    _grant_feature(user, "studio_pipelines")
    pipeline = Pipeline.objects.create(
        owner=user,
        name="Monitoring supplied context",
        graph_version=2,
        nodes=[
            _node("monitoring", "trigger/monitoring", {"monitoring_filters": {}}),
            _node("report", "output/report", {"template": "{server_name} {container_name} {alert_id}"}),
        ],
        edges=[{"id": "e1", "source": "monitoring", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()
    client = Client()
    client.force_login(user)

    payload = client.get("/api/studio/readiness/").json()

    item = payload["pipelines"][0]
    assert item["status"] == "ready"
    trigger = item["triggers"][0]
    assert trigger["required_context_fields"] == ["alert_id", "container_name", "server_name"]
    assert trigger["unresolved_context_fields"] == []
    assert not any(issue["code"] == "runtime_context_required" for issue in item["issues"])


def test_readiness_treats_webhook_payload_map_as_supplied_context():
    user = User.objects.create_user(username="readiness-webhook-context", password="x")
    _grant_feature(user, "studio_pipelines")
    pipeline = Pipeline.objects.create(
        owner=user,
        name="Webhook supplied context",
        graph_version=2,
        nodes=[
            _node("webhook", "trigger/webhook", {"webhook_payload_map": {"ticket_id": "ticket.id"}}),
            _node("report", "output/report", {"template": "Ticket {ticket_id}"}),
        ],
        edges=[{"id": "e1", "source": "webhook", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()
    client = Client()
    client.force_login(user)

    payload = client.get("/api/studio/readiness/").json()

    item = payload["pipelines"][0]
    assert item["status"] == "ready"
    trigger = item["triggers"][0]
    assert trigger["required_context_fields"] == ["ticket_id"]
    assert trigger["supplied_context_fields"] == ["ticket_id"]
    assert trigger["unresolved_context_fields"] == []
    assert item["issues"] == []


def test_readiness_marks_required_workers_ready_when_heartbeating():
    user = User.objects.create_user(username="readiness-workers-running", password="x")
    _grant_feature(user, "studio_pipelines")
    pipeline = Pipeline.objects.create(
        owner=user,
        name="Running worker automation",
        graph_version=2,
        nodes=[
            _node("schedule", "trigger/schedule", {"cron_expression": "*/5 * * * *"}),
            _node("monitoring", "trigger/monitoring", {"monitoring_filters": {}}),
            _node("join", "logic/merge", {"mode": "any"}),
            _node("report", "output/report", {"template": "ok"}),
            _node(
                "operator_reply",
                "logic/telegram_input",
                {"message": "Need action?", "bot_token": "token", "chat_id": "123"},
            ),
        ],
        edges=[
            {"id": "e-schedule-join", "source": "schedule", "target": "join", "sourceHandle": "out"},
            {"id": "e-monitoring-join", "source": "monitoring", "target": "join", "sourceHandle": "out"},
            {"id": "e-join-report", "source": "join", "target": "report", "sourceHandle": "out"},
            {"id": "e-report-reply", "source": "report", "target": "operator_reply", "sourceHandle": "success"},
        ],
    )
    pipeline.sync_triggers_from_nodes()
    for worker_kind in (
        STUDIO_MONITOR_WORKER,
        STUDIO_PIPELINE_EXECUTION_WORKER,
        STUDIO_SCHEDULED_PIPELINES_WORKER,
        STUDIO_TELEGRAM_BOT_WORKER,
    ):
        heartbeat_background_worker(worker_kind, lease_seconds=180)
    client = Client()
    client.force_login(user)

    response = client.get("/api/studio/readiness/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["summary"]["worker_not_ready_count"] == 0
    assert all(item["ready"] is True for item in payload["worker_requirements"])


def test_readiness_reports_missing_integration_requirements(monkeypatch):
    monkeypatch.setattr("studio.pipeline.pipeline_notifications.load_notification_config", lambda: {})
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "PIPELINE_NOTIFY_EMAIL"):
        monkeypatch.delenv(key, raising=False)
    user = User.objects.create_user(username="readiness-integrations-missing", password="x")
    _grant_feature(user, "studio_pipelines")
    pipeline = Pipeline.objects.create(
        owner=user,
        name="Missing integrations",
        graph_version=2,
        nodes=[
            _node("manual", "trigger/manual"),
            _node("llm", "agent/llm_query", {"provider": "openai", "prompt": "Summarize"}),
            _node("telegram", "output/telegram", {"message": "Done"}),
            _node("email", "output/email", {"subject": "Done"}),
            _node("mcp", "agent/mcp_call", {"tool_name": "ping"}),
        ],
        edges=[
            {"id": "e1", "source": "manual", "target": "llm", "sourceHandle": "out"},
            {"id": "e2", "source": "llm", "target": "telegram", "sourceHandle": "success"},
            {"id": "e3", "source": "telegram", "target": "email", "sourceHandle": "success"},
            {"id": "e4", "source": "email", "target": "mcp", "sourceHandle": "success"},
        ],
    )
    pipeline.sync_triggers_from_nodes()
    client = Client()
    client.force_login(user)

    response = client.get("/api/studio/readiness/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "not_ready"
    item = payload["pipelines"][0]
    assert item["status"] == "error"
    assert payload["summary"]["integration_error_count"] >= 4
    requirements = {req["name"]: req for req in item["integration_requirements"]}
    assert requirements["LLM provider: openai"]["severity"] == "error"
    assert requirements["Telegram bot token"]["severity"] == "error"
    assert requirements["Email recipient"]["severity"] == "error"
    assert requirements["MCP server"]["severity"] == "error"
    assert requirements["Telegram chat"]["severity"] == "warning"
    issue_codes = {issue["code"] for issue in item["issues"]}
    assert {
        "llm_credentials_missing",
        "telegram_token_missing",
        "email_recipient_missing",
        "mcp_server_missing",
    } <= issue_codes
    assert requirements["MCP server"]["issue"]["code"] == "mcp_server_missing"
    assert "Select an owner-accessible MCP server" in requirements["MCP server"]["issue"]["next_action"]


def test_readiness_marks_configured_integrations_ready(monkeypatch):
    monkeypatch.setattr("studio.pipeline.pipeline_notifications.load_notification_config", lambda: {})
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    user = User.objects.create_user(username="readiness-integrations-ready", password="x", is_staff=True)
    _grant_feature(user, "studio_pipelines")
    mcp = MCPServerPool.objects.create(
        owner=user,
        name="Ready MCP",
        transport=MCPServerPool.TRANSPORT_SSE,
        url="http://127.0.0.1:8765/mcp",
        last_test_ok=True,
    )
    pipeline = Pipeline.objects.create(
        owner=user,
        name="Ready integrations",
        graph_version=2,
        nodes=[
            _node("manual", "trigger/manual"),
            _node("llm", "agent/llm_query", {"provider": "openai", "prompt": "Summarize"}),
            _node("telegram", "output/telegram", {"message": "Done", "bot_token": "token", "chat_id": "123"}),
            _node("email", "output/email", {"to_email": "ops@example.test", "subject": "Done"}),
            _node("mcp", "agent/mcp_call", {"mcp_server_id": mcp.id, "tool_name": "ping"}),
        ],
        edges=[
            {"id": "e1", "source": "manual", "target": "llm", "sourceHandle": "out"},
            {"id": "e2", "source": "llm", "target": "telegram", "sourceHandle": "success"},
            {"id": "e3", "source": "telegram", "target": "email", "sourceHandle": "success"},
            {"id": "e4", "source": "email", "target": "mcp", "sourceHandle": "success"},
        ],
    )
    pipeline.sync_triggers_from_nodes()
    heartbeat_background_worker(STUDIO_PIPELINE_EXECUTION_WORKER, lease_seconds=180)
    client = Client()
    client.force_login(user)

    response = client.get("/api/studio/readiness/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["summary"]["integration_error_count"] == 0
    assert payload["summary"]["integration_warning_count"] == 0
    assert payload["summary"]["issue_count"] == 0
    assert payload["pipelines"][0]["issues"] == []
    assert {req["severity"] for req in payload["pipelines"][0]["integration_requirements"]} == {"ready"}
