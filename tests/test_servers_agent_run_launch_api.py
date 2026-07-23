from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.utils import timezone

from app.runtime_limits import get_terminal_session_limit_error
from servers.models import (
    AgentRun,
    AgentRunDispatch,
    AgentRunEvent,
    ServerAgent,
    ServerConnection,
)
from tests.servers_api_smoke_harness import create_server as _create_server
from tests.servers_api_smoke_harness import grant_feature as _grant_feature
from tests.servers_api_smoke_harness import json_payload as _json


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("mode", "extra_fields"),
    [
        (ServerAgent.MODE_FULL, {"goal": "Inspect the server", "ai_prompt": "Check the host"}),
        (ServerAgent.MODE_MINI, {"commands": ["uname -a"], "ai_prompt": "Summarize"}),
    ],
)
def test_agent_run_launches_in_background(monkeypatch, mode, extra_fields):
    user = User.objects.create_user(username=f"agent-user-{mode}", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user)
    agent = ServerAgent.objects.create(
        user=user,
        name=f"{mode} Agent",
        mode=mode,
        agent_type=ServerAgent.TYPE_CUSTOM,
        **extra_fields,
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
    assert AgentRunDispatch.objects.filter(run=run).count() == 0  # fake_launch skips real enqueue
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
        captured.update(
            {
                "run_id": run_id,
                "agent_id": agent_id,
                "server_ids": server_ids,
                "user_id": user_id,
            }
        )

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
