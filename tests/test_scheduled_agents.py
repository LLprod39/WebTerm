from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from core_ui.views.access_views import _apply_access_profile
from servers.agents.agent_dispatch import enqueue_agent_run_dispatch
from servers.agents.scheduled_agents import dispatch_scheduled_agents, is_agent_due
from servers.models import AgentRun, AgentRunDispatch, AgentRunEvent, BackgroundWorkerState, Server, ServerAgent


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
def test_is_agent_due_respects_daily_schedule_config():
    user = User.objects.create_user(username="sched-daily-user", password="x")
    agent = ServerAgent.objects.create(
        user=user,
        name="Daily Scheduled Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect every morning",
        schedule_minutes=1440,
        schedule_config={"mode": "daily", "time": "08:00", "timezone": "UTC"},
        is_enabled=True,
    )

    assert is_agent_due(agent, datetime(2026, 6, 16, 7, 59, tzinfo=UTC)) is False
    assert is_agent_due(agent, datetime(2026, 6, 16, 8, 1, tzinfo=UTC)) is True

    agent.last_run_at = datetime(2026, 6, 16, 8, 0, tzinfo=UTC)
    assert is_agent_due(agent, datetime(2026, 6, 16, 9, 0, tzinfo=UTC)) is False


@pytest.mark.django_db
def test_dispatch_scheduled_agents_launches_due_full_agent(monkeypatch):
    user = User.objects.create_user(username="sched-full-user", password="x")
    _apply_access_profile(user, "pilot_operator")
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

    monkeypatch.setattr("servers.agents.agent_launch.launch_agent_run_background", fake_launch)

    summary = dispatch_scheduled_agents(limit=10)

    assert summary["scanned"] == 1
    assert summary["due"] == 1
    assert summary["launched_agents"] == 1
    assert summary["background_runs"] == 1
    assert summary["runs_created"] == 1
    run = AgentRun.objects.get(agent=agent)
    assert run.status == AgentRun.STATUS_PENDING
    assert AgentRunEvent.objects.filter(run=run, event_type="agent_scheduled_dispatch").exists()
    assert any(item["event_type"] == "agent_scheduled_dispatch" for item in run.report_payload["events"])
    assert captured == {
        "run_id": run.id,
        "agent_id": agent.id,
        "server_ids": [server.id],
        "user_id": user.id,
        "plan_only": False,
    }


@pytest.mark.django_db
def test_dispatch_scheduled_agents_queues_mini_agent(monkeypatch):
    user = User.objects.create_user(username="sched-mini-user", password="x")
    _apply_access_profile(user, "pilot_operator")
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

    monkeypatch.setattr("servers.agents.agent_launch.launch_agent_run_background", fake_launch)

    summary = dispatch_scheduled_agents(limit=10)

    assert summary["launched_agents"] == 1
    assert summary["mini_runs"] == 1
    assert summary["background_runs"] == 1
    assert summary["runs_created"] == 1
    run = AgentRun.objects.get(agent=agent)
    assert run.status == AgentRun.STATUS_PENDING
    assert AgentRunEvent.objects.filter(run=run, event_type="agent_scheduled_dispatch").exists()
    assert any(item["event_type"] == "agent_scheduled_dispatch" for item in run.report_payload["events"])
    assert captured == {
        "run_id": run.id,
        "agent_id": agent.id,
        "server_ids": [server.id],
        "user_id": user.id,
        "plan_only": False,
    }


@pytest.mark.django_db
def test_dispatch_scheduled_agents_skips_active_runs():
    user = User.objects.create_user(username="sched-active-user", password="x")
    _apply_access_profile(user, "pilot_operator")
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


@pytest.mark.django_db
def test_scheduled_agents_worker_updates_background_state():
    call_command("run_scheduled_agents", once=True, worker_key="pytest-scheduled-agents")

    worker_state = BackgroundWorkerState.objects.get(
        worker_kind=BackgroundWorkerState.KIND_SCHEDULED_AGENTS,
        worker_key="pytest-scheduled-agents",
    )
    assert worker_state.status == BackgroundWorkerState.STATUS_IDLE
    assert worker_state.last_started_at is not None
    assert worker_state.last_stopped_at is not None
    assert worker_state.last_cycle_started_at is not None
    assert worker_state.last_cycle_finished_at is not None
    assert worker_state.last_summary["scanned"] == 0
    assert worker_state.last_summary["due"] == 0


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
    run.refresh_from_db()
    assert any(item["event_type"] == "agent_dispatch_enqueued" for item in run.report_payload["events"])

    async def fake_engine_run(self, *, run_record=None):
        target_run = run_record or run
        target_run.status = AgentRun.STATUS_COMPLETED
        target_run.final_report = "worker completed run"
        await sync_to_async(target_run.save)(update_fields=["status", "final_report"])

    monkeypatch.setattr("servers.agents.agent_background.AgentEngine.run", fake_engine_run)

    call_command("run_agent_execution_plane", once=True, worker_key="pytest-exec-plane")

    dispatch.refresh_from_db()
    run.refresh_from_db()
    assert dispatch.status == AgentRunDispatch.STATUS_COMPLETED
    assert run.status == AgentRun.STATUS_COMPLETED
    assert run.final_report == "worker completed run"
    assert AgentRunEvent.objects.filter(run=run, event_type="agent_worker_claimed").exists()
    assert AgentRunEvent.objects.filter(run=run, event_type="agent_dispatch_completed").exists()
    assert run.report_payload["report_state"]["report_ready"] is True
    assert any(item["event_type"] == "agent_dispatch_claimed" for item in run.report_payload["events"])
    assert any(item["event_type"] == "agent_dispatch_completed" for item in run.report_payload["events"])
    worker_state = BackgroundWorkerState.objects.get(
        worker_kind=BackgroundWorkerState.KIND_AGENT_EXECUTION,
        worker_key="pytest-exec-plane",
    )
    assert worker_state.status == BackgroundWorkerState.STATUS_IDLE
    assert "run_agent_execution_plane --worker-key pytest-exec-plane" in worker_state.command
    assert worker_state.last_summary["processed"] >= 1
    assert worker_state.last_summary["completed"] >= 1


@pytest.mark.django_db(transaction=True)
def test_execution_plane_worker_failure_marks_run_failed_with_report_payload(monkeypatch):
    user = User.objects.create_user(username="exec-plane-failure-user", password="x")
    server = _create_server(user, name="exec-plane-failure-node")
    agent = ServerAgent.objects.create(
        user=user,
        name="Execution Plane Failure Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Fail during worker execution",
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
    run.refresh_from_db()
    assert any(item["event_type"] == "agent_dispatch_enqueued" for item in run.report_payload["events"])

    async def fake_engine_run(self, *, run_record=None):
        raise RuntimeError("worker boom")

    monkeypatch.setattr("servers.agents.agent_background.AgentEngine.run", fake_engine_run)

    with pytest.raises(CommandError, match="Execution plane dispatches failed: 1"):
        call_command("run_agent_execution_plane", once=True, worker_key="pytest-exec-plane-failure")

    dispatch.refresh_from_db()
    run.refresh_from_db()
    assert dispatch.status == AgentRunDispatch.STATUS_FAILED
    assert "worker boom" in dispatch.error
    assert run.status == AgentRun.STATUS_FAILED
    assert "worker boom" in run.ai_analysis
    assert run.report_payload["report_state"]["phase"] == "failed"
    assert run.report_payload["report_state"]["report_ready"] is False
    assert run.report_payload["artifacts"] == []
    assert AgentRunEvent.objects.filter(run=run, event_type="agent_dispatch_failed").exists()
    assert AgentRunEvent.objects.filter(run=run, event_type="agent_background_failed").exists()
    assert any(item["event_type"] == "agent_dispatch_claimed" for item in run.report_payload["events"])
    assert any(item["event_type"] == "agent_dispatch_failed" for item in run.report_payload["events"])
    assert any(item["event_type"] == "agent_background_failed" for item in run.report_payload["events"])
    worker_state = BackgroundWorkerState.objects.get(
        worker_kind=BackgroundWorkerState.KIND_AGENT_EXECUTION,
        worker_key="pytest-exec-plane-failure",
    )
    assert worker_state.status == BackgroundWorkerState.STATUS_IDLE
    assert worker_state.last_summary["failed"] >= 1


@pytest.mark.django_db(transaction=True)
def test_execution_plane_worker_crash_records_worker_error(monkeypatch):
    def boom():
        raise RuntimeError("stale cleanup overflow")

    monkeypatch.setattr("servers.management.commands.run_agent_execution_plane.cleanup_stale_agent_runs", boom)

    with pytest.raises(RuntimeError, match="stale cleanup overflow"):
        call_command("run_agent_execution_plane", once=True, worker_key="pytest-exec-plane-crash")

    worker_state = BackgroundWorkerState.objects.get(
        worker_kind=BackgroundWorkerState.KIND_AGENT_EXECUTION,
        worker_key="pytest-exec-plane-crash",
    )
    assert worker_state.status == BackgroundWorkerState.STATUS_ERROR
    assert "RuntimeError: stale cleanup overflow" in worker_state.last_error
