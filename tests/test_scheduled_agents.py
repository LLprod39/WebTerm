from __future__ import annotations

from datetime import timedelta

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone

from servers.agent_dispatch import enqueue_agent_run_dispatch
from servers.models import AgentRun, AgentRunDispatch, AgentRunEvent, BackgroundWorkerState, Server, ServerAgent
from servers.scheduled_agents import dispatch_scheduled_agents, is_agent_due


def _create_server(user: User, **kwargs) -> Server:
    return Server.objects.create(
        user=user,
        name=kwargs.pop("name", "sched-srv"),
        host=kwargs.pop("host", "10.11.0.12"),
        username=kwargs.pop("username", "root"),
        auth_method=kwargs.pop("auth_method", "password"),
        **kwargs,
    )


@pytest.mark.django_db
def test_is_agent_due_respects_schedule_and_last_run_at():
    user = User.objects.create_user(username="sched-due-user", password="x")
    agent = ServerAgent.objects.create(
        user=user,
        name="Scheduled Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect infrastructure",
        schedule_minutes=15,
        is_enabled=True,
    )
    now = timezone.now()

    assert is_agent_due(agent, now) is True

    agent.last_run_at = now - timedelta(minutes=5)
    assert is_agent_due(agent, now) is False

    agent.last_run_at = now - timedelta(minutes=16)
    assert is_agent_due(agent, now) is True


@pytest.mark.django_db
def test_dispatch_scheduled_agents_launches_due_full_agent(monkeypatch):
    user = User.objects.create_user(username="sched-full-user", password="x")
    server = _create_server(user, name="scheduled-full-node")
    agent = ServerAgent.objects.create(
        user=user,
        name="Scheduled Full Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect scheduled host",
        schedule_minutes=10,
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

    summary = dispatch_scheduled_agents(limit=10)

    assert summary["scanned"] == 1
    assert summary["due"] == 1
    assert summary["launched_agents"] == 1
    assert summary["background_runs"] == 1
    assert summary["runs_created"] == 1
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


@pytest.mark.django_db
def test_dispatch_scheduled_agents_runs_mini_agent_inline(monkeypatch):
    user = User.objects.create_user(username="sched-mini-user", password="x")
    server = _create_server(user, name="scheduled-mini-node")
    agent = ServerAgent.objects.create(
        user=user,
        name="Scheduled Mini Agent",
        mode=ServerAgent.MODE_MINI,
        agent_type=ServerAgent.TYPE_CUSTOM,
        commands=["uname -a"],
        schedule_minutes=5,
        is_enabled=True,
        last_run_at=timezone.now() - timedelta(minutes=7),
    )
    agent.servers.set([server])

    async def fake_run_agent_on_all_servers(agent_obj, user_obj):
        run = await sync_to_async(AgentRun.objects.create)(
            agent=agent_obj,
            server=server,
            user=user_obj,
            status=AgentRun.STATUS_COMPLETED,
            ai_analysis="scheduled mini ok",
        )
        agent_obj.last_run_at = timezone.now()
        await sync_to_async(agent_obj.save)(update_fields=["last_run_at"])
        return [run]

    monkeypatch.setattr("servers.scheduled_agents.run_agent_on_all_servers", fake_run_agent_on_all_servers)

    summary = dispatch_scheduled_agents(limit=10)

    assert summary["launched_agents"] == 1
    assert summary["mini_runs"] == 1
    assert summary["runs_created"] == 1
    run = AgentRun.objects.get(agent=agent)
    assert run.status == AgentRun.STATUS_COMPLETED
    assert AgentRunEvent.objects.filter(run=run, event_type="agent_scheduled_dispatch").exists()


@pytest.mark.django_db
def test_dispatch_scheduled_agents_skips_active_runs():
    user = User.objects.create_user(username="sched-active-user", password="x")
    server = _create_server(user, name="scheduled-active-node")
    agent = ServerAgent.objects.create(
        user=user,
        name="Scheduled Active Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Keep running",
        schedule_minutes=5,
        is_enabled=True,
        last_run_at=timezone.now() - timedelta(minutes=10),
    )
    agent.servers.set([server])
    AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_RUNNING,
    )

    summary = dispatch_scheduled_agents(limit=10)

    assert summary["due"] == 1
    assert summary["launched_agents"] == 0
    assert summary["skipped"] == 1
    assert summary["skip_reasons"]["active_run"] == 1


@pytest.mark.django_db(transaction=True)
def test_execution_plane_worker_processes_queued_dispatch(monkeypatch):
    user = User.objects.create_user(username="exec-plane-user", password="x")
    server = _create_server(user, name="exec-plane-node")
    agent = ServerAgent.objects.create(
        user=user,
        name="Execution Plane Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect server",
        is_enabled=True,
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_PENDING,
    )
    dispatch = enqueue_agent_run_dispatch(
        run=run,
        agent_id=agent.id,
        user_id=user.id,
        server_ids=[server.id],
        plan_only=False,
    )

    async def fake_engine_run(self, *, run_record=None):
        target_run = run_record or run
        target_run.status = AgentRun.STATUS_COMPLETED
        target_run.final_report = "worker completed run"
        await sync_to_async(target_run.save)(update_fields=["status", "final_report"])

    monkeypatch.setattr("servers.agent_background.AgentEngine.run", fake_engine_run)

    call_command("run_agent_execution_plane", once=True, worker_key="pytest-exec-plane")

    dispatch.refresh_from_db()
    run.refresh_from_db()
    assert dispatch.status == AgentRunDispatch.STATUS_COMPLETED
    assert run.status == AgentRun.STATUS_COMPLETED
    assert run.final_report == "worker completed run"
    assert AgentRunEvent.objects.filter(run=run, event_type="agent_worker_claimed").exists()
    worker_state = BackgroundWorkerState.objects.get(
        worker_kind=BackgroundWorkerState.KIND_AGENT_EXECUTION,
        worker_key="pytest-exec-plane",
    )
    assert worker_state.status == BackgroundWorkerState.STATUS_IDLE
    assert worker_state.last_summary["processed"] >= 1
    assert worker_state.last_summary["completed"] >= 1
