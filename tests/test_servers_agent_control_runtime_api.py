import json
from concurrent.futures import Future
from datetime import timedelta
from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from core_ui.models import UserAppPermission
from servers.agent_engine import AgentEngine
from servers.models import AgentRun, AgentRunDispatch, AgentRunEvent, BackgroundWorkerState, Server, ServerAgent


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _create_server(user: User, **kwargs) -> Server:
    return Server.objects.create(
        user=user,
        name=kwargs.pop("name", "srv-01"),
        host=kwargs.pop("host", "10.0.0.11"),
        username=kwargs.pop("username", "root"),
        auth_method=kwargs.pop("auth_method", "password"),
        **kwargs,
    )


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


@pytest.mark.django_db
def test_agent_list_cleans_expired_execution_worker_before_readiness():
    user = User.objects.create_user(username="agent-expired-worker-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)
    server = _create_server(user, name="expired-readiness-srv", server_type="ssh")

    agent = ServerAgent.objects.create(
        user=user,
        name="Expired Worker Agent",
        mode=ServerAgent.MODE_FULL,
        agent_type=ServerAgent.TYPE_CUSTOM,
        goal="Inspect worker expiry",
    )
    agent.servers.set([server])
    expired_at = timezone.now() - timedelta(minutes=5)
    worker = BackgroundWorkerState.objects.create(
        worker_kind=BackgroundWorkerState.KIND_AGENT_EXECUTION,
        worker_key="default",
        status=BackgroundWorkerState.STATUS_RUNNING,
        heartbeat_at=expired_at - timedelta(minutes=1),
        lease_expires_at=expired_at,
    )

    response = client.get("/servers/api/agents/")
    assert response.status_code == 200
    listed = next(item for item in response.json()["agents"] if item["id"] == agent.id)
    readiness = listed["execution_readiness"]
    assert readiness["ready"] is False
    assert readiness["status"] == BackgroundWorkerState.STATUS_STOPPED
    assert readiness["severity"] == "warning"

    worker.refresh_from_db()
    assert worker.status == BackgroundWorkerState.STATUS_STOPPED
    assert worker.last_stopped_at is not None
    assert "lease expired" in worker.last_error


@pytest.mark.django_db
def test_agent_engine_syncs_reply_from_runtime_control():
    user = User.objects.create_user(username="runtime-sync-user", password="x")
    server = _create_server(user, name="sync-srv", server_type="ssh")
    agent = ServerAgent.objects.create(
        user=user,
        name="Sync Agent",
        mode=ServerAgent.MODE_FULL,
        agent_type=ServerAgent.TYPE_CUSTOM,
        goal="Wait for user input",
        ai_prompt="Wait",
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_WAITING,
        pending_question="Continue?",
        runtime_control={
            "stop_requested": False,
            "pause_requested": False,
            "reply_nonce": 1,
            "reply_ack_nonce": 0,
            "reply_text": "Proceed",
        },
    )

    engine = AgentEngine(agent, [server], user)
    engine.run_record = run
    engine.session = SimpleNamespace(user_reply_future=Future())

    async_to_sync(engine._sync_runtime_control)()

    assert engine.session.user_reply_future.done() is True
    assert engine.session.user_reply_future.result() == "Proceed"

    run.refresh_from_db()
    assert run.runtime_control["reply_ack_nonce"] == 1
    assert run.runtime_control["reply_text"] == ""


@pytest.mark.django_db
def test_agent_control_paths_do_not_require_live_engine(monkeypatch):
    user = User.objects.create_user(username="agent-no-engine-user", password="x")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="agent-no-engine-srv", server_type="ssh")
    agent = ServerAgent.objects.create(
        user=user,
        name="No Engine Agent",
        mode=ServerAgent.MODE_FULL,
        agent_type=ServerAgent.TYPE_CUSTOM,
        goal="Wait for input",
        ai_prompt="Wait",
    )
    agent.servers.set([server])

    waiting_run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_WAITING,
        pending_question="Continue?",
    )
    running_run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_RUNNING,
    )
    AgentRun.objects.filter(pk=running_run.pk).update(started_at=timezone.now() - timedelta(seconds=42))

    monkeypatch.setattr("servers.agent_service.get_engine_for_run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("servers.agent_service.get_engine_for_agent", lambda *_args, **_kwargs: None)

    reply = client.post(
        f"/servers/api/agents/runs/{waiting_run.id}/reply/",
        data=_json({"answer": "Proceed without local engine"}),
        content_type="application/json",
    )
    assert reply.status_code == 200
    waiting_run.refresh_from_db()
    assert waiting_run.status == AgentRun.STATUS_RUNNING
    assert waiting_run.runtime_control["reply_nonce"] == 1
    assert waiting_run.runtime_control["reply_ack_nonce"] == 0
    assert waiting_run.runtime_control["reply_text"] == "Proceed without local engine"

    stop = client.post(
        f"/servers/api/agents/{agent.id}/stop/",
        data=_json({"run_id": running_run.id}),
        content_type="application/json",
    )
    assert stop.status_code == 200
    assert stop.json()["stop_signal_sent"] is False
    running_run.refresh_from_db()
    assert running_run.status == AgentRun.STATUS_STOPPED
    assert running_run.duration_ms >= 42_000
    assert running_run.runtime_control["stop_requested"] is True
    assert running_run.runtime_control["pause_requested"] is False


@pytest.mark.django_db
def test_user_owned_null_agent_run_detail_dashboard_and_reply_are_safe():
    user = User.objects.create_user(username="agent-null-run-owner", password="x")
    other = User.objects.create_user(username="agent-null-run-other", password="x")
    _grant_feature(user, "agents")
    _grant_feature(other, "agents")
    client = Client()
    client.force_login(user)
    server = _create_server(user, name="null-agent-run-srv", server_type="ssh")
    run = AgentRun.objects.create(
        agent=None,
        server=server,
        user=user,
        status=AgentRun.STATUS_WAITING,
        pending_question="Continue without attached agent?",
    )

    detail = client.get(f"/servers/api/agents/runs/{run.id}/")
    assert detail.status_code == 200
    detail_payload = detail.json()["run"]
    assert detail_payload["agent_id"] is None
    assert detail_payload["agent_name"] == "Agent"
    assert detail_payload["agent_type"] == ""
    assert detail_payload["agent_mode"] == ""
    assert detail_payload["pending_question"] == "Continue without attached agent?"

    report = client.get(f"/servers/api/agents/runs/{run.id}/report/")
    assert report.status_code == 200
    assert report.json()["run"]["pending_question"] == "Continue without attached agent?"

    dashboard = client.get("/servers/api/agents/dashboard/")
    assert dashboard.status_code == 200
    active = dashboard.json()["active"]
    assert active[0]["id"] == run.id
    assert active[0]["agent_id"] is None
    assert active[0]["agent_name"] == "Agent"
    assert active[0]["pending_question"] == "Continue without attached agent?"

    other_client = Client()
    other_client.force_login(other)
    denied = other_client.post(
        f"/servers/api/agents/runs/{run.id}/reply/",
        data=_json({"answer": "Nope"}),
        content_type="application/json",
    )
    assert denied.status_code == 404

    reply = client.post(
        f"/servers/api/agents/runs/{run.id}/reply/",
        data=_json({"answer": "Proceed"}),
        content_type="application/json",
    )
    assert reply.status_code == 200
    assert reply.json()["success"] is True
    run.refresh_from_db()
    assert run.status == AgentRun.STATUS_RUNNING
    assert run.pending_question == ""
    assert run.runtime_control["reply_text"] == "Proceed"
    assert run.report_payload["run"]["status"] == AgentRun.STATUS_RUNNING
    assert run.report_payload["run"]["pending_question"] == ""
    assert any(item["event_type"] == "agent_user_reply" for item in run.report_payload["events"])


@pytest.mark.django_db
def test_agent_stop_can_target_specific_run():
    user = User.objects.create_user(username="agent-stop-target-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="agent-stop-target-srv", server_type="ssh")
    agent = ServerAgent.objects.create(
        user=user,
        name="Targeted Stop Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Stop only selected run",
    )
    agent.servers.set([server])

    target_run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_RUNNING,
    )
    AgentRun.objects.filter(pk=target_run.pk).update(started_at=timezone.now() - timedelta(seconds=33))
    other_run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_WAITING,
        pending_question="Continue?",
    )

    response = client.post(
        f"/servers/api/agents/{agent.id}/stop/",
        data=_json({"run_id": target_run.id}),
        content_type="application/json",
    )

    assert response.status_code == 200
    target_run.refresh_from_db()
    other_run.refresh_from_db()
    assert target_run.status == AgentRun.STATUS_STOPPED
    assert target_run.duration_ms >= 33_000
    assert target_run.runtime_control["stop_requested"] is True
    assert AgentRunEvent.objects.filter(run=target_run, event_type="agent_control_stop_requested").exists()
    assert other_run.status == AgentRun.STATUS_WAITING
    assert other_run.runtime_control.get("stop_requested", False) is False


@pytest.mark.django_db
def test_agent_stop_cancels_queued_dispatch():
    user = User.objects.create_user(username="agent-stop-queued-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="agent-stop-queued-srv", server_type="ssh")
    agent = ServerAgent.objects.create(
        user=user,
        name="Queued Stop Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Queued execution",
    )
    agent.servers.set([server])

    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_PENDING,
    )
    AgentRun.objects.filter(pk=run.pk).update(started_at=timezone.now() - timedelta(seconds=18))
    dispatch = AgentRunDispatch.objects.create(
        run=run,
        agent=agent,
        user=user,
        dispatch_kind=AgentRunDispatch.KIND_LAUNCH,
        status=AgentRunDispatch.STATUS_QUEUED,
        server_ids=[server.id],
        plan_only=False,
    )

    response = client.post(
        f"/servers/api/agents/{agent.id}/stop/",
        data=_json({"run_id": run.id}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["canceled_dispatches"] == 1
    run.refresh_from_db()
    dispatch.refresh_from_db()
    assert run.status == AgentRun.STATUS_STOPPED
    assert run.duration_ms >= 18_000
    assert dispatch.status == AgentRunDispatch.STATUS_CANCELED
    assert AgentRunEvent.objects.filter(run=run, event_type="agent_dispatch_canceled").exists()
