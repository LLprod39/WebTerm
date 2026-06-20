import json
from concurrent.futures import Future
from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.test import Client

from core_ui.models import UserAppPermission
from servers.agent_engine import AgentEngine
from servers.models import AgentRun, AgentRunDispatch, AgentRunEvent, Server, ServerAgent


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
    assert listed_agent["session_timeout_seconds"] == 600
    assert listed_agent["max_connections"] == 5

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
                "report_delivery": {"telegram": {"enabled": True, "chat_id": "12345", "format": "brief", "include_link": True}},
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

    async def fake_run_agent_on_all_servers(_agent, _user):
        return [completed_run]

    monkeypatch.setattr("servers.agent_service.run_agent_on_all_servers", fake_run_agent_on_all_servers)

    run_agent = client.post(
        f"/servers/api/agents/{agent_id}/run/",
        data=_json({}),
        content_type="application/json",
    )
    assert run_agent.status_code == 200
    assert run_agent.json()["success"] is True
    run_id = run_agent.json()["runs"][0]["run_id"]
    assert AgentRunEvent.objects.filter(run=completed_run, event_type="agent_manual_dispatch").exists()

    runs = client.get(f"/servers/api/agents/{agent_id}/runs/")
    assert runs.status_code == 200
    assert runs.json()["success"] is True

    run_detail = client.get(f"/servers/api/agents/runs/{run_id}/")
    assert run_detail.status_code == 200
    assert run_detail.json()["success"] is True

    run_log = client.get(f"/servers/api/agents/runs/{run_id}/log/")
    assert run_log.status_code == 200
    assert run_log.json()["success"] is True

    waiting_run = _build_run(AgentRun.STATUS_WAITING)
    waiting_run.pending_question = "Need approval?"
    waiting_run.save(update_fields=["pending_question"])

    reply = client.post(
        f"/servers/api/agents/runs/{waiting_run.id}/reply/",
        data=_json({"answer": "Proceed"}),
        content_type="application/json",
    )
    assert reply.status_code == 200
    assert reply.json()["success"] is True
    waiting_run.refresh_from_db()
    assert waiting_run.runtime_control["reply_nonce"] == 1
    assert waiting_run.runtime_control["reply_ack_nonce"] == 0
    assert waiting_run.runtime_control["reply_text"] == "Proceed"
    assert waiting_run.status == AgentRun.STATUS_RUNNING
    assert waiting_run.pending_question == ""
    assert AgentRunEvent.objects.filter(run=waiting_run, event_type="agent_user_reply").exists()

    running_run = _build_run(AgentRun.STATUS_RUNNING)
    stop = client.post(f"/servers/api/agents/{agent_id}/stop/")
    assert stop.status_code == 200
    assert stop.json()["success"] is True
    running_run.refresh_from_db()
    assert running_run.status == AgentRun.STATUS_STOPPED
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

    stop = client.post(f"/servers/api/agents/{agent.id}/stop/")
    assert stop.status_code == 200
    assert stop.json()["stop_signal_sent"] is False
    running_run.refresh_from_db()
    assert running_run.status == AgentRun.STATUS_STOPPED
    assert running_run.runtime_control["stop_requested"] is True
    assert running_run.runtime_control["pause_requested"] is False


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
    assert dispatch.status == AgentRunDispatch.STATUS_CANCELED
    assert AgentRunEvent.objects.filter(run=run, event_type="agent_dispatch_canceled").exists()
