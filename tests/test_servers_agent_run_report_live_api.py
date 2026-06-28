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
from tests.servers_api_smoke_harness import create_server as _create_server
from tests.servers_api_smoke_harness import grant_feature as _grant_feature
from tests.servers_api_smoke_harness import json_payload as _json

pytestmark = pytest.mark.django_db

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


