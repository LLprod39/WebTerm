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


@pytest.mark.django_db
def test_agent_run_report_endpoint_live_run_does_not_expose_final_artifacts():
    user = User.objects.create_user(username="report-live-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="live-report-node")
    agent = ServerAgent.objects.create(
        user=user,
        name="Live Report Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect the server",
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_PENDING,
        started_at=timezone.now(),
        final_report="",
        ai_analysis="",
        report_payload={},
    )
    AgentRunEvent.objects.create(
        run=run,
        event_type="agent_dispatch_enqueued",
        message="Queued for launch worker execution",
        payload={"server_ids": [server.id]},
    )

    response = client.get(f"/servers/api/agents/runs/{run.id}/report/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["report_state"]["report_ready"] is False
    assert payload["report_state"]["artifacts_ready"] is False
    assert payload["artifact_state"]["ready"] is False
    assert payload["report"]["markdown"] == ""
    assert payload["artifacts"] == []
    assert payload["events"][0]["title"] == "Поставлен в очередь"


@pytest.mark.django_db
def test_agent_run_report_endpoint_explains_queued_run_without_worker(settings):
    settings.AGENT_RUN_STALE_SECONDS = 60
    user = User.objects.create_user(username="report-worker-missing-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="worker-missing-node")
    agent = ServerAgent.objects.create(
        user=user,
        name="Worker Missing Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect the server",
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_PENDING,
        report_payload={},
    )
    AgentRun.objects.filter(pk=run.pk).update(started_at=timezone.now() - timedelta(minutes=5))
    run.refresh_from_db()
    AgentRunDispatch.objects.create(
        run=run,
        agent=agent,
        user=user,
        dispatch_kind=AgentRunDispatch.KIND_LAUNCH,
        status=AgentRunDispatch.STATUS_QUEUED,
        server_ids=[server.id],
    )

    response = client.get(f"/servers/api/agents/runs/{run.id}/report/")
    assert response.status_code == 200
    payload = response.json()
    execution_state = payload["report_state"]["execution_state"]
    assert execution_state["status"] == "worker_missing"
    assert execution_state["severity"] == "warning"
    assert execution_state["title"] == "Запуск завис в очереди"
    assert execution_state["dispatch"]["status"] == AgentRunDispatch.STATUS_QUEUED
    assert execution_state["worker"]["status"] == "missing"
    assert execution_state["worker_ready"] is False
    assert execution_state["is_stale_candidate"] is True
    assert execution_state["can_cleanup"] is True
    assert execution_state["runtime_age_ms"] >= 60_000
    assert execution_state["stale_after_ms"] == 60_000
    assert "Очистите stale run" in execution_state["next_action"]
    assert "run_agent_execution_plane" in execution_state["commands"]["execution_worker"]
    assert "run_ops_supervisor" in execution_state["commands"]["ops_supervisor"]
    assert payload["report_state"]["current_step"] == "Запуск завис в очереди"


@pytest.mark.django_db
def test_agent_run_report_endpoint_explains_claimed_run_with_worker_heartbeat():
    user = User.objects.create_user(username="report-worker-claimed-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="worker-claimed-node")
    agent = ServerAgent.objects.create(
        user=user,
        name="Worker Claimed Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect the server",
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_RUNNING,
        report_payload={},
    )
    now = timezone.now()
    AgentRunDispatch.objects.create(
        run=run,
        agent=agent,
        user=user,
        dispatch_kind=AgentRunDispatch.KIND_LAUNCH,
        status=AgentRunDispatch.STATUS_CLAIMED,
        server_ids=[server.id],
        claimed_at=now,
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=180),
        claimed_by="pytest-agent-worker",
        attempt_count=1,
    )
    BackgroundWorkerState.objects.create(
        worker_kind=BackgroundWorkerState.KIND_AGENT_EXECUTION,
        worker_key="pytest-agent-worker",
        status=BackgroundWorkerState.STATUS_RUNNING,
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=180),
    )

    response = client.get(f"/servers/api/agents/runs/{run.id}/report/")
    assert response.status_code == 200
    payload = response.json()
    execution_state = payload["report_state"]["execution_state"]
    assert execution_state["status"] == "claimed"
    assert execution_state["severity"] == "success"
    assert execution_state["worker_ready"] is True
    assert execution_state["lease_expired"] is False
    assert execution_state["worker"]["worker_key"] == "pytest-agent-worker"
    assert execution_state["dispatch"]["claimed_by"] == "pytest-agent-worker"


@pytest.mark.django_db
def test_agent_run_report_endpoint_uses_current_events_over_saved_snapshot():
    user = User.objects.create_user(username="report-stale-event-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="stale-event-node")
    agent = ServerAgent.objects.create(
        user=user,
        name="Stale Event Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect events",
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_COMPLETED,
        final_report="## Что произошло\n- Проверка завершена.\n",
        report_payload={
            "events": [
                {
                    "id": 999,
                    "run_id": 0,
                    "event_type": "old_snapshot_event",
                    "task_id": None,
                    "message": "old",
                    "payload": {},
                    "created_at": timezone.now().isoformat(),
                    "severity": "info",
                    "source": "old",
                    "title": "Old snapshot",
                    "summary": "Old snapshot",
                    "phase": "activity",
                    "category": "agent",
                    "important": True,
                }
            ],
            "report": {"markdown": "## Что произошло\n- Проверка завершена.\n"},
        },
    )
    AgentRunEvent.objects.create(
        run=run,
        event_type="agent_report",
        message="Final report generated",
        payload={"interim": False, "message": "Final report generated"},
    )

    response = client.get(f"/servers/api/agents/runs/{run.id}/report/")
    assert response.status_code == 200
    payload = response.json()
    event_types = [item["event_type"] for item in payload["events"]]
    assert event_types == ["agent_report"]
    assert "old_snapshot_event" not in event_types
    assert payload["events"][0]["title"] == "Формирование отчёта"


@pytest.mark.django_db
def test_agent_stop_refreshes_structured_report_payload():
    user = User.objects.create_user(username="report-stop-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="stop-report-node")
    agent = ServerAgent.objects.create(
        user=user,
        name="Stop Report Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Long running check",
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_RUNNING,
        report_payload={},
    )
    AgentRun.objects.filter(pk=run.pk).update(started_at=timezone.now() - timedelta(seconds=64))

    response = client.post(
        f"/servers/api/agents/{agent.id}/stop/",
        data=_json({"run_id": run.id}),
        content_type="application/json",
    )
    assert response.status_code == 200
    run.refresh_from_db()
    assert run.status == AgentRun.STATUS_STOPPED
    assert run.duration_ms >= 64_000
    assert run.report_payload["run"]["duration_ms"] >= 64_000
    assert run.report_payload["report_state"]["phase"] == "stopped"
    assert run.report_payload["report_state"]["report_ready"] is False
    assert run.report_payload["artifacts"] == []
    assert any(item["event_type"] == "agent_control_stop_requested" for item in run.report_payload["events"])


@pytest.mark.django_db
def test_agent_run_report_endpoint_blocks_other_user():
    owner = User.objects.create_user(username="report-owner", password="x")
    other = User.objects.create_user(username="report-other", password="x")
    _grant_feature(owner, "agents")
    _grant_feature(other, "agents")
    client = Client()
    client.force_login(other)

    server = _create_server(owner, name="private-report-node")
    agent = ServerAgent.objects.create(
        user=owner,
        name="Private Report Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect private server",
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=owner,
        status=AgentRun.STATUS_COMPLETED,
        final_report="Private report",
    )

    response = client.get(f"/servers/api/agents/runs/{run.id}/report/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_agent_run_report_endpoint_fallback_redacts_and_promotes_failures():
    user = User.objects.create_user(username="report-failure-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="failure-report-node")
    agent = ServerAgent.objects.create(
        user=user,
        name="Failure Report Agent",
        mode=ServerAgent.MODE_MULTI,
        goal="Find deployment blockers",
        allow_multi_server=True,
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_COMPLETED,
        ai_analysis="Deployment check complete.",
        final_report="## Что произошло\n- Проверка завершена.\n",
        commands_output=[
            {
                "cmd": "deploy --dry-run",
                "stdout": "token=super-secret-token-value\n",
                "stderr": "package lock still active\n",
                "exit_code": 100,
                "duration_ms": 1200,
            }
        ],
        plan_tasks=[
            {
                "id": 7,
                "name": "Validate package manager",
                "description": "Check apt/dpkg health",
                "status": "failed",
                "error": "dpkg lock could not be cleared",
            }
        ],
        report_payload={},
    )

    response = client.get(f"/servers/api/agents/runs/{run.id}/report/")
    assert response.status_code == 200
    payload = response.json()
    serialized = _json(payload)
    assert "super-secret-token-value" not in serialized
    assert "[REDACTED:secret_assignment]" in serialized
    assert payload["logs"][0]["exit_code"] == 100
    assert any("кодом 100" in item["title"] for item in payload["report"]["findings"])
    assert any("Validate package manager" in item["title"] for item in payload["report"]["findings"])
    assert payload["report"]["risks"]
    assert payload["report"]["recommendations"]


@pytest.mark.django_db
def test_full_agent_run_launches_in_background(monkeypatch):
    user = User.objects.create_user(username="full-agent-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user)
    agent = ServerAgent.objects.create(
        user=user,
        name="Full Agent",
        mode=ServerAgent.MODE_FULL,
        agent_type=ServerAgent.TYPE_CUSTOM,
        goal="Inspect the server",
        ai_prompt="Check the host",
    )
    agent.servers.set([server])

    captured: dict[str, object] = {}

    def fake_launch(run_id: int, agent_id: int, server_ids: list[int], user_id: int, *, plan_only: bool = False):
        captured.update({
            "run_id": run_id,
            "agent_id": agent_id,
            "server_ids": server_ids,
            "user_id": user_id,
            "plan_only": plan_only,
        })

    monkeypatch.setattr("servers.agent_launch.launch_agent_run_background", fake_launch)

    response = client.post(
        f"/servers/api/agents/{agent.id}/run/",
        data=_json({}),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["run_id"] == payload["runs"][0]["run_id"]
    assert payload["status"] == AgentRun.STATUS_PENDING

    run = AgentRun.objects.get(pk=payload["run_id"])
    assert run.status == AgentRun.STATUS_PENDING
    assert captured == {
        "run_id": run.id,
        "agent_id": agent.id,
        "server_ids": [server.id],
        "user_id": user.id,
        "plan_only": False,
    }

    duplicate = client.post(
        f"/servers/api/agents/{agent.id}/run/",
        data=_json({}),
        content_type="application/json",
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["success"] is False


@pytest.mark.django_db
@override_settings(AGENT_ACTIVE_RUNS_PER_USER_LIMIT=1, AGENT_ACTIVE_RUNS_GLOBAL_LIMIT=0)
def test_full_agent_run_enforces_user_active_run_limit(monkeypatch):
    user = User.objects.create_user(username="agent-limit-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user)
    first_agent = ServerAgent.objects.create(
        user=user,
        name="First Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect server",
    )
    second_agent = ServerAgent.objects.create(
        user=user,
        name="Second Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect another server",
    )
    first_agent.servers.set([server])
    second_agent.servers.set([server])

    AgentRun.objects.create(
        agent=first_agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_RUNNING,
    )

    monkeypatch.setattr(
        "servers.agent_launch.launch_agent_run_background",
        lambda **_kwargs: pytest.fail("launch_agent_run_background should not run when the active-run limit is hit"),
    )

    response = client.post(
        f"/servers/api/agents/{second_agent.id}/run/",
        data=_json({}),
        content_type="application/json",
    )

    assert response.status_code == 429
    payload = response.json()
    assert payload["success"] is False
    assert payload["code"] == "agent_user_limit_reached"
    assert payload["limit"] == 1
    assert payload["active"] == 1


@pytest.mark.django_db
def test_multi_agent_run_launches_without_plan_only(monkeypatch):
    user = User.objects.create_user(username="multi-launch-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user)
    agent = ServerAgent.objects.create(
        user=user,
        name="Cluster Health",
        mode=ServerAgent.MODE_MULTI,
        agent_type=ServerAgent.TYPE_MULTI_HEALTH,
        goal="Inspect the cluster",
        ai_prompt="Run cluster-wide checks",
        allow_multi_server=True,
    )
    agent.servers.set([server])

    captured: dict[str, object] = {}

    def fake_launch(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("servers.agent_launch.launch_agent_run_background", fake_launch)

    response = client.post(
        f"/servers/api/agents/{agent.id}/run/",
        data=_json({}),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["status"] == AgentRun.STATUS_PENDING
    assert captured["plan_only"] is False


@pytest.mark.django_db
@override_settings(SSH_TERMINAL_SESSIONS_PER_USER_LIMIT=1, SSH_TERMINAL_SESSIONS_GLOBAL_LIMIT=0)
def test_terminal_session_limit_helper_enforces_user_limit():
    user = User.objects.create_user(username="terminal-limit-user", password="x")
    server = _create_server(user, name="term-limit-srv")
    ServerConnection.objects.create(
        server=server,
        user=user,
        connection_id="term-existing-1",
        status="connected",
    )

    error = get_terminal_session_limit_error(user)

    assert error is not None
    assert error["code"] == "terminal_user_limit_reached"
    assert error["scope"] == "user"
    assert error["limit"] == 1


@pytest.mark.django_db
def test_multi_agent_approve_plan_launches_in_background(monkeypatch):
    user = User.objects.create_user(username="multi-approve-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user)
    agent = ServerAgent.objects.create(
        user=user,
        name="Multi Agent",
        mode=ServerAgent.MODE_MULTI,
        agent_type=ServerAgent.TYPE_MULTI_HEALTH,
        goal="Check all systems",
        ai_prompt="Prepare a plan",
        allow_multi_server=True,
    )
    agent.servers.set([server])

    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_PLAN_REVIEW,
        plan_tasks=[{"id": 1, "name": "Check logs", "description": "Inspect logs", "status": "pending"}],
    )

    captured: dict[str, object] = {}

    def fake_launch(run_id: int, agent_id: int, server_ids: list[int], user_id: int):
        captured.update({
            "run_id": run_id,
            "agent_id": agent_id,
            "server_ids": server_ids,
            "user_id": user_id,
        })

    monkeypatch.setattr("servers.agent_service.launch_plan_execution_background", fake_launch)

    response = client.post(f"/servers/api/agents/runs/{run.id}/approve-plan/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["run_id"] == run.id
    assert payload["status"] == AgentRun.STATUS_PENDING

    run.refresh_from_db()
    assert run.status == AgentRun.STATUS_PENDING
    assert AgentRunEvent.objects.filter(run=run, event_type="agent_plan_approved").exists()
    assert captured == {
        "run_id": run.id,
        "agent_id": agent.id,
        "server_ids": [server.id],
        "user_id": user.id,
    }


@pytest.mark.django_db
def test_agent_schedule_overview_and_dispatch_api(monkeypatch):
    user = User.objects.create_user(username="agent-schedule-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="agent-schedule-srv", server_type="ssh")
    agent = ServerAgent.objects.create(
        user=user,
        name="Scheduled Deploy Operator",
        mode=ServerAgent.MODE_FULL,
        agent_type=ServerAgent.TYPE_DEPLOY_WATCHER,
        goal="Verify deploy health",
        schedule_minutes=15,
        is_enabled=True,
        last_run_at=timezone.now() - timedelta(minutes=20),
    )
    agent.servers.set([server])

    captured: dict[str, object] = {}

    def fake_launch(run_id: int, agent_id: int, server_ids: list[int], user_id: int, *, plan_only: bool = False):
        captured.update(
            {
                "run_id": run_id,
                "agent_id": agent_id,
                "server_ids": server_ids,
                "user_id": user_id,
                "plan_only": plan_only,
            }
        )

    monkeypatch.setattr("servers.agent_launch.launch_agent_run_background", fake_launch)

    overview = client.get("/servers/api/agents/schedules/")
    assert overview.status_code == 200
    overview_payload = overview.json()
    assert overview_payload["success"] is True
    assert "execution_plane" in overview_payload
    assert overview_payload["summary"]["total_scheduled"] == 1
    assert overview_payload["summary"]["due_now"] == 1
    scheduled_agent = overview_payload["scheduled_agents"][0]
    assert scheduled_agent["id"] == agent.id
    assert scheduled_agent["schedule_state"] == "due"
    assert scheduled_agent["due_now"] is True
    assert scheduled_agent["next_due_at"] is not None

    dispatch = client.post(
        "/servers/api/agents/schedules/dispatch/",
        data=_json({"limit": 10}),
        content_type="application/json",
    )
    assert dispatch.status_code == 200
    dispatch_payload = dispatch.json()
    assert dispatch_payload["success"] is True
    assert dispatch_payload["summary"]["launched_agents"] == 1
    assert dispatch_payload["summary"]["runs_created"] == 1

    run = AgentRun.objects.get(agent=agent)
    assert run.status == AgentRun.STATUS_PENDING
    assert AgentRunEvent.objects.filter(run=run, event_type="agent_scheduled_dispatch").exists()
    assert captured == {
        "run_id": run.id,
        "agent_id": agent.id,
        "server_ids": [server.id],
        "user_id": user.id,
        "plan_only": False,
    }
