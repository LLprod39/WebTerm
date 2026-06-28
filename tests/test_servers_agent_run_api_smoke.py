import hashlib
import io
import json
import zipfile
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.utils import timezone

from app.runtime_limits import get_terminal_session_limit_error
from servers.agent_run_report import refresh_agent_run_report_payload
from servers.models import (
    AgentRun,
    AgentRunArtifact,
    AgentRunDispatch,
    AgentRunEvent,
    BackgroundWorkerState,
    ServerAgent,
    ServerConnection,
)
from tests.servers_api_smoke_harness import (
    create_server as _create_server,
)
from tests.servers_api_smoke_harness import (
    grant_feature as _grant_feature,
)
from tests.servers_api_smoke_harness import (
    json_payload as _json,
)


@pytest.mark.django_db
def test_agent_run_events_endpoint_returns_persisted_events():
    user = User.objects.create_user(username="events-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="events-node")
    agent = ServerAgent.objects.create(
        user=user,
        name="Eventful Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect the server",
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_RUNNING,
    )
    AgentRunEvent.objects.create(
        run=run,
        event_type="agent_background_started",
        message="Background worker started",
        payload={"server_ids": [server.id]},
    )
    AgentRunEvent.objects.create(
        run=run,
        event_type="agent_task_start",
        task_id=7,
        message="Check nginx",
        payload={"task_id": 7, "name": "Check nginx"},
    )

    response = client.get(f"/servers/api/agents/runs/{run.id}/events/?limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["total"] == 2
    assert [item["event_type"] for item in payload["events"]] == [
        "agent_background_started",
        "agent_task_start",
    ]
    assert payload["events"][1]["task_id"] == 7
    assert payload["events"][1]["message"] == "Check nginx"
    assert payload["events"][1]["title"] == "Check nginx"
    assert payload["events"][1]["phase"] == "executing"
    assert payload["events"][1]["category"] == "task"
    assert payload["events"][1]["important"] is True


@pytest.mark.django_db
@pytest.mark.parametrize("mode", [ServerAgent.MODE_MINI, ServerAgent.MODE_FULL, ServerAgent.MODE_MULTI])
def test_agent_run_report_endpoint_returns_structured_payload_for_agent_modes(mode):
    user = User.objects.create_user(username=f"report-{mode}-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name=f"report-{mode}-node")
    agent = ServerAgent.objects.create(
        user=user,
        name=f"{mode.title()} Report Agent",
        mode=mode,
        goal="Inspect and summarize the server",
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_COMPLETED,
        duration_ms=61000,
        final_report=(
            "# Итоговый отчет\n\n"
            "## Что произошло\n"
            "- Агент собрал состояние сервера.\n\n"
            "## Ключевые находки\n"
            "- nginx активен.\n\n"
            "## Рекомендации\n"
            "- Повторить проверку завтра.\n"
        ),
        commands_output=[
            {
                "cmd": "systemctl is-active nginx",
                "stdout": "active\n",
                "stderr": "",
                "exit_code": 0,
                "duration_ms": 250,
            }
        ],
        plan_tasks=[
            {
                "id": 1,
                "name": "Collect service state",
                "description": "Check nginx status",
                "status": "done",
                "result": "nginx is active",
            }
        ]
        if mode == ServerAgent.MODE_MULTI
        else [],
        report_payload={},
    )
    AgentRunEvent.objects.create(
        run=run,
        event_type="agent_completed",
        message="Agent finished",
        payload={"status": "completed"},
    )

    response = client.get(f"/servers/api/agents/runs/{run.id}/report/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["run"]["id"] == run.id
    assert payload["run"]["agent_mode"] == mode
    assert payload["report"]["schema_version"] == 1
    assert payload["report"]["title"] == agent.name
    assert payload["report"]["root_cause"] is None
    assert payload["report"]["kpis"]
    assert payload["report_state"]["report_ready"] is True
    assert payload["report_state"]["artifacts_ready"] is True
    assert payload["artifact_state"]["ready"] is True
    assert payload["event_summary"]["total"] == 1
    assert payload["event_summary"]["important"] == 1
    assert payload["event_summary"]["latest_important"]["event_type"] == "agent_completed"
    assert payload["event_groups"][0]["phase"] == "ready"
    assert payload["event_groups"][0]["count"] == 1
    assert payload["events"][0]["event_type"] == "agent_completed"
    assert payload["events"][0]["title"]
    assert payload["events"][0]["summary"]
    assert payload["events"][0]["phase"]
    assert payload["artifacts"][0]["name"] == "final-report.md"


@pytest.mark.django_db
def test_agent_run_report_refresh_persists_artifacts_and_downloads_for_owner():
    user = User.objects.create_user(username="report-artifact-owner", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="artifact-report-node")
    agent = ServerAgent.objects.create(
        user=user,
        name="Artifact Report Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect and produce artifacts",
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_COMPLETED,
        final_report="# Final\n\n## Что произошло\n- Агент завершил проверку.\n",
        commands_output=[
            {
                "cmd": "uptime",
                "stdout": "up 1 day\n",
                "stderr": "",
                "exit_code": 0,
                "duration_ms": 10,
            }
        ],
        report_payload={},
    )
    AgentRunEvent.objects.create(run=run, event_type="agent_completed", message="Done", payload={"status": "completed"})

    payload = refresh_agent_run_report_payload(run)
    run.refresh_from_db()

    assert AgentRunArtifact.objects.filter(run=run).count() == 5
    assert payload["artifacts"][0]["name"] == "final-report.md"
    assert payload["artifacts"][0]["download_kind"] == "server"
    assert payload["artifacts"][0]["content"] == ""
    assert payload["artifacts"][0]["download_url"]
    assert payload["artifacts"][0]["checksum_sha256"]
    assert payload["artifacts"][-1]["name"] == "artifact-manifest.json"
    assert payload["artifact_state"]["bundle_ready"] is True
    assert payload["artifact_state"]["bundle_download_url"] == f"/servers/api/agents/runs/{run.id}/artifacts/download-all/"
    assert payload["artifact_state"]["artifact_count"] == 5
    assert payload["artifact_state"]["manifest_ready"] is True

    response = client.get(payload["artifacts"][0]["download_url"])
    assert response.status_code == 200
    assert "attachment" in response.headers["Content-Disposition"]
    assert "final-report.md" in response.headers["Content-Disposition"]
    assert "# Final" in response.content.decode()

    bundle = client.get(payload["artifact_state"]["bundle_download_url"])
    assert bundle.status_code == 200
    assert bundle.headers["Content-Type"] == "application/zip"
    assert f"agent-run-{run.id}-artifacts.zip" in bundle.headers["Content-Disposition"]
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        names = set(archive.namelist())
        assert {"final-report.md", "run-context.json", "commands-output.json", "events.json", "artifact-manifest.json"} <= names
        final_report = archive.read("final-report.md")
        assert "# Final" in final_report.decode()
        manifest = json.loads(archive.read("artifact-manifest.json").decode())
        manifest_by_name = {item["name"]: item for item in manifest["artifacts"]}
        assert manifest["artifact_count"] == 4
        assert manifest_by_name["final-report.md"]["checksum_sha256"] == hashlib.sha256(final_report).hexdigest()


@pytest.mark.django_db
def test_agent_run_artifact_download_blocks_other_user():
    owner = User.objects.create_user(username="artifact-owner", password="x")
    other = User.objects.create_user(username="artifact-other", password="x")
    _grant_feature(owner, "agents")
    _grant_feature(other, "agents")
    client = Client()
    client.force_login(other)

    server = _create_server(owner, name="artifact-private-node")
    agent = ServerAgent.objects.create(
        user=owner,
        name="Private Artifact Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Private report",
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=owner,
        status=AgentRun.STATUS_COMPLETED,
        final_report="# Private\n\nSecret report body\n",
        report_payload={},
    )
    payload = refresh_agent_run_report_payload(run)

    response = client.get(payload["artifacts"][0]["download_url"])
    assert response.status_code == 404
    bundle_response = client.get(payload["artifact_state"]["bundle_download_url"])
    assert bundle_response.status_code == 404


@pytest.mark.django_db
def test_agent_run_report_delivery_retry_endpoint_sends_and_refreshes_payload(monkeypatch):
    user = User.objects.create_user(username="report-delivery-retry-owner", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="delivery-retry-node")
    agent = ServerAgent.objects.create(
        user=user,
        name="Delivery Retry Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect and deliver report",
        report_delivery={"telegram": {"enabled": True, "chat_id": "123456789", "include_link": True}},
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_COMPLETED,
        final_report="# Final\n\n## Что произошло\n- Агент завершил проверку.\n",
        report_payload={},
    )
    captured: dict[str, object] = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return SimpleNamespace(status_code=200, text="ok")

    monkeypatch.setattr(
        "servers.report_delivery.load_notification_config",
        lambda: {"telegram_bot_token": "bot-token-secret", "telegram_chat_id": "", "site_url": "http://127.0.0.1:9000"},
    )
    monkeypatch.setattr("servers.report_delivery.httpx.AsyncClient", FakeAsyncClient)

    response = client.post(f"/servers/api/agents/runs/{run.id}/report/deliver/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["delivery_state"]["status"] == "sent"
    assert payload["delivery_state"]["target"] == "***6789"
    assert payload["delivery_state"]["event"]["event_type"] == "agent_report_delivery_sent"
    assert captured["json"]["chat_id"] == "123456789"
    assert "bot-token-secret" not in str(payload)


@pytest.mark.django_db
def test_agent_run_report_delivery_retry_endpoint_requires_ready_report():
    user = User.objects.create_user(username="report-delivery-not-ready", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="delivery-not-ready-node")
    agent = ServerAgent.objects.create(
        user=user,
        name="Delivery Not Ready Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect and deliver report",
        report_delivery={"telegram": {"enabled": True, "chat_id": "123456789", "include_link": True}},
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(agent=agent, server=server, user=user, status=AgentRun.STATUS_RUNNING, report_payload={})

    response = client.post(f"/servers/api/agents/runs/{run.id}/report/deliver/")
    assert response.status_code == 409
    payload = response.json()
    assert payload["success"] is False
    assert payload["delivery_state"]["status"] == "waiting_report"


@pytest.mark.django_db
def test_agent_run_report_delivery_retry_endpoint_blocks_other_user():
    owner = User.objects.create_user(username="report-delivery-owner", password="x")
    other = User.objects.create_user(username="report-delivery-other", password="x")
    _grant_feature(owner, "agents")
    _grant_feature(other, "agents")
    client = Client()
    client.force_login(other)

    server = _create_server(owner, name="delivery-private-node")
    agent = ServerAgent.objects.create(
        user=owner,
        name="Private Delivery Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Private report",
        report_delivery={"telegram": {"enabled": True, "chat_id": "123456789", "include_link": True}},
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=owner,
        status=AgentRun.STATUS_COMPLETED,
        final_report="# Private\n",
        report_payload={},
    )

    response = client.post(f"/servers/api/agents/runs/{run.id}/report/deliver/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_agent_run_report_read_fallback_does_not_persist_old_artifacts():
    user = User.objects.create_user(username="artifact-fallback-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="artifact-fallback-node")
    agent = ServerAgent.objects.create(
        user=user,
        name="Fallback Artifact Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Read legacy report",
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_COMPLETED,
        final_report="# Legacy\n\nReadable report\n",
        report_payload={},
    )

    response = client.get(f"/servers/api/agents/runs/{run.id}/report/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["artifacts"][0]["name"] == "final-report.md"
    assert payload["artifacts"][0]["download_kind"] == "inline"
    assert AgentRunArtifact.objects.filter(run=run).count() == 0
    run.refresh_from_db()
    assert run.report_payload == {}
