import json
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from core_ui.models import UserAppPermission
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
def test_agent_endpoints_crud_run_and_control_flow(monkeypatch):
    user = User.objects.create_user(username="agent-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)
    server = _create_server(user, name="agent-srv", server_type="ssh")
    second_server = _create_server(user, name="agent-srv-2", server_type="ssh")

    templates = client.get("/servers/api/agents/templates/")
    assert templates.status_code == 200
    assert templates.json()["success"] is True

    create_agent = client.post(
        "/servers/api/agents/create/",
        data=_json(
            {
                "mode": "mini",
                "agent_type": "custom",
                "name": "Ops Agent",
                "commands": ["uname -a"],
                "server_ids": [server.id],
            }
        ),
        content_type="application/json",
    )
    assert create_agent.status_code == 200
    assert create_agent.json()["success"] is True
    agent_id = create_agent.json()["id"]

    list_agents = client.get("/servers/api/agents/")
    assert list_agents.status_code == 200
    assert list_agents.json()["success"] is True
    listed_agent = next(item for item in list_agents.json()["agents"] if item["id"] == agent_id)
    assert listed_agent["schedule_state"] == "manual"
    assert listed_agent["server_ids"] == [server.id]
    assert listed_agent["commands"] == ["uname -a"]
    assert listed_agent["tools_config"] == {}
    assert listed_agent["stop_conditions"] == []
    assert listed_agent["schedule_config"]["mode"] == "manual"
    assert listed_agent["skill_slugs"] == []
    assert listed_agent["input_artifacts"] == []
    assert listed_agent["report_delivery"]["telegram"]["enabled"] is False
    from servers.agents.agent_budgets import FULL_DEFAULT_MAX_ITERATIONS, FULL_DEFAULT_SESSION_TIMEOUT_SEC

    assert listed_agent["session_timeout_seconds"] == FULL_DEFAULT_SESSION_TIMEOUT_SEC
    assert listed_agent["max_iterations"] == FULL_DEFAULT_MAX_ITERATIONS
    assert listed_agent["max_connections"] == 5
    # Mini agents use the same execution-plane worker as full/multi.
    assert listed_agent["execution_readiness"]["required"] is True

    update_agent = client.post(
        f"/servers/api/agents/{agent_id}/update/",
        data=_json(
            {
                "name": "Ops Agent v2",
                "max_iterations": 25,
                "server_ids": [second_server.id],
                "schedule_minutes": 30,
                "schedule_config": {"mode": "daily", "time": "08:30", "timezone": "UTC"},
                "session_timeout_seconds": 900,
                "max_connections": 3,
                "tools_config": {"ssh_execute": True, "ask_user": False},
                "stop_conditions": ["report ready"],
                "skill_slugs": ["missing-skill"],
                "input_artifacts": [
                    {
                        "kind": "task_list",
                        "name": "CVE closeout",
                        "content": "",
                        "run_hint": "Use as checklist",
                        "tasks": [
                            {"title": "Close CVE-2026-0001", "details": "Patch api-prod-01 and verify", "done": False},
                        ],
                    }
                ],
                "report_delivery": {
                    "telegram": {"enabled": True, "chat_id": "12345", "format": "brief", "include_link": True}
                },
            }
        ),
        content_type="application/json",
    )
    assert update_agent.status_code == 200
    assert update_agent.json()["success"] is True
    agent = ServerAgent.objects.get(pk=agent_id)
    assert agent.name == "Ops Agent v2"
    assert list(agent.servers.values_list("id", flat=True)) == [second_server.id]
    assert agent.schedule_minutes == 1440
    assert agent.schedule_config["mode"] == "daily"
    assert agent.schedule_config["time"] == "08:30"
    assert agent.input_artifacts[0]["name"] == "CVE closeout"
    assert agent.input_artifacts[0]["tasks"][0]["title"] == "Close CVE-2026-0001"
    assert "Close CVE-2026-0001" in agent.input_artifacts[0]["content"]
    assert agent.report_delivery["telegram"]["enabled"] is True
    assert agent.report_delivery["telegram"]["chat_id"] == "12345"
    assert agent.skill_slugs == []
    assert agent.max_iterations == 25
    assert agent.session_timeout_seconds == 900
    assert agent.max_connections == 3
    assert agent.tools_config == {"ssh_execute": True, "ask_user": False}
    assert agent.stop_conditions == ["report ready"]

    def _build_run(status: str) -> AgentRun:
        return AgentRun.objects.create(
            agent_id=agent_id,
            server=server,
            user=user,
            status=status,
            ai_analysis="ok",
            commands_output=[{"cmd": "uname -a", "stdout": "Linux"}],
        )

    completed_run = _build_run(AgentRun.STATUS_COMPLETED)

    captured_launch: dict[str, object] = {}

    def fake_launch(run_id: int, agent_id: int, server_ids: list[int], user_id: int, *, plan_only: bool = False):
        captured_launch.update(
            {
                "run_id": run_id,
                "agent_id": agent_id,
                "server_ids": server_ids,
                "user_id": user_id,
                "plan_only": plan_only,
            }
        )

    monkeypatch.setattr("servers.agents.agent_launch.launch_agent_run_background", fake_launch)

    run_agent = client.post(
        f"/servers/api/agents/{agent_id}/run/",
        data=_json({}),
        content_type="application/json",
    )
    assert run_agent.status_code == 200
    payload = run_agent.json()
    assert payload["success"] is True
    assert payload["status"] == AgentRun.STATUS_PENDING
    run_id = payload["run_id"]
    assert payload["runs"][0]["run_id"] == run_id
    pending_run = AgentRun.objects.get(pk=run_id)
    assert pending_run.status == AgentRun.STATUS_PENDING
    assert captured_launch["agent_id"] == agent_id
    assert AgentRunEvent.objects.filter(run=pending_run, event_type="agent_manual_dispatch").exists()
    pending_run.refresh_from_db()
    assert any(item["event_type"] == "agent_manual_dispatch" for item in pending_run.report_payload["events"])

    runs = client.get(f"/servers/api/agents/{agent_id}/runs/")
    assert runs.status_code == 200
    assert runs.json()["success"] is True

    run_detail = client.get(f"/servers/api/agents/runs/{run_id}/")
    assert run_detail.status_code == 200
    assert run_detail.json()["success"] is True

    run_log = client.get(f"/servers/api/agents/runs/{completed_run.id}/log/")
    assert run_log.status_code == 200
    assert run_log.json()["success"] is True

    waiting_run = _build_run(AgentRun.STATUS_WAITING)
    waiting_run.pending_question = "Need approval?"
    waiting_run.save(update_fields=["pending_question"])

    answer = "Proceed token=super-secret-token-value"
    reply = client.post(
        f"/servers/api/agents/runs/{waiting_run.id}/reply/",
        data=_json({"answer": answer}),
        content_type="application/json",
    )
    assert reply.status_code == 200
    assert reply.json()["success"] is True
    waiting_run.refresh_from_db()
    assert waiting_run.runtime_control["reply_nonce"] == 1
    assert waiting_run.runtime_control["reply_ack_nonce"] == 0
    assert waiting_run.runtime_control["reply_text"] == answer
    assert waiting_run.status == AgentRun.STATUS_RUNNING
    assert waiting_run.pending_question == ""
    assert AgentRunEvent.objects.filter(run=waiting_run, event_type="agent_user_reply").exists()
    assert waiting_run.report_payload["run"]["status"] == AgentRun.STATUS_RUNNING
    assert waiting_run.report_payload["run"]["pending_question"] == ""
    assert any(item["event_type"] == "agent_user_reply" for item in waiting_run.report_payload["events"])
    serialized_report = _json(waiting_run.report_payload)
    assert "super-secret-token-value" not in serialized_report
    assert "[REDACTED:secret_assignment]" in serialized_report

    running_run = _build_run(AgentRun.STATUS_RUNNING)
    AgentRun.objects.filter(pk=running_run.pk).update(started_at=timezone.now() - timedelta(seconds=75))
    stop = client.post(
        f"/servers/api/agents/{agent_id}/stop/",
        data=_json({"run_id": running_run.id}),
        content_type="application/json",
    )
    assert stop.status_code == 200
    assert stop.json()["success"] is True
    running_run.refresh_from_db()
    assert running_run.status == AgentRun.STATUS_STOPPED
    assert running_run.duration_ms >= 75_000
    assert running_run.runtime_control["stop_requested"] is True
    assert running_run.runtime_control["pause_requested"] is False
    assert AgentRunEvent.objects.filter(run=running_run, event_type="agent_control_stop_requested").exists()

    editable_run = _build_run(AgentRun.STATUS_PLAN_REVIEW)
    editable_run.plan_tasks = [
        {"id": 1, "name": "Check logs", "description": "Inspect journalctl", "status": "pending"}
    ]
    editable_run.save(update_fields=["plan_tasks"])

    update_task = client.post(
        f"/servers/api/agents/runs/{editable_run.id}/tasks/1/update/",
        data=_json({"action": "update", "name": "Check logs and disk"}),
        content_type="application/json",
    )
    assert update_task.status_code == 200
    assert update_task.json()["success"] is True
    assert update_task.json()["plan_tasks"][0]["name"] == "Check logs and disk"

    async def fake_stream_chat(self, prompt: str, model: str = "auto", purpose: str = "chat"):
        assert "Верни ТОЛЬКО JSON-объект" in prompt
        yield '{"name":"Refined task","description":"Updated by AI"}'

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)

    refine_task = client.post(
        f"/servers/api/agents/runs/{editable_run.id}/tasks/1/ai-refine/",
        data=_json({"instruction": "Сделай задачу точнее"}),
        content_type="application/json",
    )
    assert refine_task.status_code == 200
    assert refine_task.json()["success"] is True
    assert refine_task.json()["task"]["name"] == "Refined task"

    dashboard = client.get("/servers/api/agents/dashboard/")
    assert dashboard.status_code == 200
    assert dashboard.json()["success"] is True

    delete_agent = client.post(f"/servers/api/agents/{agent_id}/delete/")
    assert delete_agent.status_code == 200
    assert delete_agent.json()["success"] is True


@pytest.mark.django_db
def test_agent_list_runtime_overview_exposes_queue_and_blockers(settings):
    settings.AGENT_RUN_STALE_SECONDS = 60
    user = User.objects.create_user(username="agent-runtime-overview-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)
    server = _create_server(user, name="runtime-overview-srv", server_type="ssh")

    agent = ServerAgent.objects.create(
        user=user,
        name="Queued Runtime Agent",
        mode=ServerAgent.MODE_FULL,
        agent_type=ServerAgent.TYPE_CUSTOM,
        goal="Expose runtime overview",
        schedule_minutes=5,
        last_run_at=timezone.now() - timedelta(minutes=10),
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_PENDING,
    )
    stale_started_at = timezone.now() - timedelta(minutes=5)
    AgentRun.objects.filter(pk=run.pk).update(started_at=stale_started_at)
    run.refresh_from_db()
    dispatch = AgentRunDispatch.objects.create(
        run=run,
        agent=agent,
        user=user,
        dispatch_kind=AgentRunDispatch.KIND_LAUNCH,
        status=AgentRunDispatch.STATUS_QUEUED,
        server_ids=[server.id],
    )

    response = client.get("/servers/api/agents/")

    assert response.status_code == 200
    overview = response.json()["runtime_overview"]
    assert overview["status"] == "needs_attention"
    assert overview["summary"]["active_runs"] == 1
    assert overview["summary"]["pending_runs"] == 1
    assert overview["summary"]["queued_dispatches"] == 1
    assert overview["schedule"]["due_now"] == 1
    issue_ids = {issue["id"] for issue in overview["issues"]}
    assert "execution_worker_not_ready" in issue_ids
    assert "scheduled_agents_worker_not_ready" in issue_ids
    assert "run_agent_execution_plane" in overview["commands"]["execution_worker"]
    assert "run_scheduled_agents" in overview["commands"]["scheduled_agents_worker"]
    assert "run_ops_supervisor" in overview["commands"]["ops_supervisor"]
    assert overview["items"]["active_runs"][0]["run_id"] == run.id
    assert overview["items"]["active_runs"][0]["agent_name"] == agent.name
    assert overview["items"]["active_runs"][0]["server_name"] == server.name
    assert overview["items"]["active_runs"][0]["is_stale_candidate"] is True
    assert overview["items"]["queued_dispatches"][0]["dispatch_id"] == dispatch.id
    assert overview["items"]["queued_dispatches"][0]["run_id"] == run.id
    assert overview["items"]["queued_dispatches"][0]["queued_age_seconds"] >= 0
    assert overview["items"]["scheduled_due"][0]["agent_id"] == agent.id
    assert overview["items"]["scheduled_due"][0]["active_run_id"] == run.id
    assert overview["items"]["stale_candidates"][0]["run_id"] == run.id


@pytest.mark.django_db
def test_agent_runtime_cleanup_stale_runs_is_user_scoped(settings):
    settings.AGENT_RUN_STALE_SECONDS = 60
    user = User.objects.create_user(username="agent-runtime-cleanup-user", password="x")
    other = User.objects.create_user(username="agent-runtime-cleanup-other", password="x")
    _grant_feature(user, "agents")
    _grant_feature(other, "agents")
    client = Client()
    client.force_login(user)
    server = _create_server(user, name="cleanup-srv", server_type="ssh")
    other_server = _create_server(other, name="cleanup-other-srv", server_type="ssh")

    agent = ServerAgent.objects.create(
        user=user,
        name="Cleanup Agent",
        mode=ServerAgent.MODE_FULL,
        agent_type=ServerAgent.TYPE_CUSTOM,
        goal="Cleanup stale run",
    )
    agent.servers.set([server])
    other_agent = ServerAgent.objects.create(
        user=other,
        name="Other Cleanup Agent",
        mode=ServerAgent.MODE_FULL,
        agent_type=ServerAgent.TYPE_CUSTOM,
        goal="Do not cleanup",
    )
    other_agent.servers.set([other_server])

    stale_at = timezone.now() - timedelta(minutes=5)
    run = AgentRun.objects.create(agent=agent, server=server, user=user, status=AgentRun.STATUS_PENDING)
    other_run = AgentRun.objects.create(
        agent=other_agent, server=other_server, user=other, status=AgentRun.STATUS_PENDING
    )
    AgentRun.objects.filter(pk__in=[run.pk, other_run.pk]).update(started_at=stale_at)
    run.refresh_from_db()
    other_run.refresh_from_db()
    dispatch = AgentRunDispatch.objects.create(
        run=run,
        agent=agent,
        user=user,
        dispatch_kind=AgentRunDispatch.KIND_LAUNCH,
        status=AgentRunDispatch.STATUS_QUEUED,
        server_ids=[server.id],
    )
    other_dispatch = AgentRunDispatch.objects.create(
        run=other_run,
        agent=other_agent,
        user=other,
        dispatch_kind=AgentRunDispatch.KIND_LAUNCH,
        status=AgentRunDispatch.STATUS_QUEUED,
        server_ids=[other_server.id],
    )

    response = client.post(
        "/servers/api/agents/runtime/cleanup-stale/",
        data=_json({"limit": 20}),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["cleanup"]["cleaned"] == 1
    assert payload["cleanup"]["canceled_dispatches"] == 1
    assert payload["cleanup"]["runs"][0]["run_id"] == run.id
    assert payload["runtime_overview"]["summary"]["active_runs"] == 0
    run.refresh_from_db()
    dispatch.refresh_from_db()
    other_run.refresh_from_db()
    other_dispatch.refresh_from_db()
    assert run.status == AgentRun.STATUS_FAILED
    assert "operator cleanup" in run.ai_analysis
    assert dispatch.status == AgentRunDispatch.STATUS_CANCELED
    assert AgentRunEvent.objects.filter(run=run, event_type="agent_stale_cleanup").exists()
    assert any(item["event_type"] == "agent_stale_cleanup" for item in run.report_payload["events"])
    assert other_run.status == AgentRun.STATUS_PENDING
    assert other_dispatch.status == AgentRunDispatch.STATUS_QUEUED


@pytest.mark.django_db
def test_agent_list_exposes_execution_readiness_for_full_agents():
    user = User.objects.create_user(username="agent-readiness-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)
    server = _create_server(user, name="readiness-srv", server_type="ssh")

    agent = ServerAgent.objects.create(
        user=user,
        name="Full Readiness Agent",
        mode=ServerAgent.MODE_FULL,
        agent_type=ServerAgent.TYPE_CUSTOM,
        goal="Inspect worker readiness",
        schedule_minutes=15,
    )
    agent.servers.set([server])

    missing_response = client.get("/servers/api/agents/")
    assert missing_response.status_code == 200
    assert missing_response.json()["worker_states"]["scheduled_agents"]["status"] == "missing"
    listed = next(item for item in missing_response.json()["agents"] if item["id"] == agent.id)
    readiness = listed["execution_readiness"]
    assert readiness["required"] is True
    assert readiness["ready"] is False
    assert readiness["status"] == "missing"
    assert readiness["severity"] == "warning"
    assert "run_agent_execution_plane" in readiness["next_action"]
    assert "run_ops_supervisor" in readiness["supervisor_action"]
    assert "run_ops_supervisor" in readiness["commands"]["ops_supervisor"]

    now = timezone.now()
    BackgroundWorkerState.objects.create(
        worker_kind=BackgroundWorkerState.KIND_AGENT_EXECUTION,
        worker_key="default",
        status=BackgroundWorkerState.STATUS_RUNNING,
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=180),
    )
    ready_response = client.get("/servers/api/agents/")
    assert ready_response.status_code == 200
    assert ready_response.json()["worker_states"]["agent_execution"]["status"] == BackgroundWorkerState.STATUS_RUNNING
    listed = next(item for item in ready_response.json()["agents"] if item["id"] == agent.id)
    assert listed["execution_readiness"]["ready"] is True
    assert listed["execution_readiness"]["severity"] == "success"

    BackgroundWorkerState.objects.create(
        worker_kind=BackgroundWorkerState.KIND_SCHEDULED_AGENTS,
        worker_key="default",
        status=BackgroundWorkerState.STATUS_RUNNING,
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=180),
        last_summary={"scanned": 2, "due": 1, "launched_agents": 1},
    )
    schedule_response = client.get("/servers/api/agents/schedules/")
    assert schedule_response.status_code == 200
    schedule_payload = schedule_response.json()
    assert schedule_payload["worker_states"]["scheduled_agents"]["status"] == BackgroundWorkerState.STATUS_RUNNING
    assert schedule_payload["scheduled_agents_worker"]["last_summary"]["due"] == 1
    assert schedule_payload["execution_readiness"]["ready"] is True
    assert schedule_payload["scheduled_agents"][0]["execution_readiness"]["ready"] is True
