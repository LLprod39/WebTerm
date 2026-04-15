import json
import threading
import time
from datetime import datetime
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from core_ui.models import UserAppPermission
from servers.models import Server
from studio.consumers import PipelineRunConsumer
from studio.management.commands.run_scheduled_pipelines import Command
from studio.models import AgentConfig, MCPServerPool, Pipeline, PipelineRun, PipelineTrigger
from studio.pipeline_executor import PipelineExecutor, _execute_agent_ssh_cmd


def _llm_node(node_id: str) -> dict:
    return {
        "id": node_id,
        "type": "agent/llm_query",
        "position": {"x": 0, "y": 0},
        "data": {
            "prompt": "Summarize the previous step.",
            "provider": "gemini",
        },
    }


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


@pytest.mark.django_db
def test_api_pipeline_run_rejects_non_object_context(client):
    user = User.objects.create_user(username="studio-run-user", password="x")
    _grant_feature(user, "agents")
    pipeline = Pipeline.objects.create(name="Manual Run Validation", owner=user, nodes=[_llm_node("n1")], edges=[])

    client.force_login(user)
    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=json.dumps({"context": ["bad"]}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"] == "context must be a JSON object"


@pytest.mark.django_db
def test_api_trigger_receive_rejects_non_object_payload(client):
    user = User.objects.create_user(username="studio-webhook-user", password="x")
    pipeline = Pipeline.objects.create(
        name="Webhook Validation",
        owner=user,
        nodes=[
            {
                "id": "trigger_webhook",
                "type": "trigger/webhook",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Webhook Start"},
            },
            _llm_node("n1"),
        ],
        edges=[{"id": "e1", "source": "trigger_webhook", "target": "n1"}],
    )
    pipeline.sync_triggers_from_nodes()
    trigger = pipeline.triggers.get(node_id="trigger_webhook")

    response = client.post(
        f"/api/studio/triggers/{trigger.webhook_token}/receive/",
        data="[]",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"] == "Webhook payload must be a JSON object"


@pytest.mark.django_db
def test_api_runs_list_detail_and_stop_include_webhook_runs_for_pipeline_owner(client):
    user = User.objects.create_user(username="studio-runs-user", password="x")
    _grant_feature(user, "agents")
    pipeline = Pipeline.objects.create(name="Run Visibility", owner=user, nodes=[_llm_node("n1")], edges=[])
    run = PipelineRun.objects.create(
        pipeline=pipeline,
        status=PipelineRun.STATUS_RUNNING,
        context={},
        trigger_data={"source": "webhook"},
    )

    client.force_login(user)

    list_response = client.get("/api/studio/runs/")
    assert list_response.status_code == 200
    listed_ids = {item["id"] for item in list_response.json()}
    assert run.id in listed_ids

    detail_response = client.get(f"/api/studio/runs/{run.id}/")
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == run.id

    stop_response = client.post(f"/api/studio/runs/{run.id}/stop/")
    assert stop_response.status_code == 200

    run.refresh_from_db()
    assert run.status == PipelineRun.STATUS_STOPPED
    assert run.runtime_control["stop_requested"] is True


@pytest.mark.django_db
def test_api_run_stop_requests_live_executor(client, monkeypatch):
    user = User.objects.create_user(username="studio-stop-live-user", password="x")
    _grant_feature(user, "studio")
    pipeline = Pipeline.objects.create(name="Run Stop Live", owner=user, nodes=[_llm_node("n1")], edges=[])
    run = PipelineRun.objects.create(
        pipeline=pipeline,
        status=PipelineRun.STATUS_RUNNING,
        context={},
    )

    class DummyExecutor:
        def __init__(self):
            self.stop_requested = False

        def request_stop(self):
            self.stop_requested = True

    executor = DummyExecutor()
    monkeypatch.setattr("studio.views.get_executor_for_run", lambda run_id: executor if run_id == run.id else None)

    client.force_login(user)
    stop_response = client.post(f"/api/studio/runs/{run.id}/stop/")

    assert stop_response.status_code == 200
    assert stop_response.json()["live_executor"] is True
    assert stop_response.json()["runtime_control"]["stop_requested"] is True
    assert executor.stop_requested is True

    run.refresh_from_db()
    assert run.status == PipelineRun.STATUS_STOPPED
    assert run.runtime_control["stop_requested"] is True


@pytest.mark.django_db(transaction=True)
def test_pipeline_executor_honors_db_stop_request_without_live_registry():
    import asyncio

    user = User.objects.create_user(username="studio-db-stop-user", password="x")
    _grant_feature(user, "studio")
    pipeline = Pipeline.objects.create(name="DB Stop", owner=user, nodes=[_llm_node("n1")], edges=[])
    run = PipelineRun.objects.create(
        pipeline=pipeline,
        triggered_by=user,
        status=PipelineRun.STATUS_PENDING,
        context={},
        runtime_control={"stop_requested": True},
    )

    run_obj = PipelineRun.objects.select_related("pipeline", "pipeline__owner", "triggered_by").get(pk=run.pk)
    result = asyncio.run(PipelineExecutor(run_obj).execute(context=run_obj.context))

    result.refresh_from_db()
    assert result.status == PipelineRun.STATUS_STOPPED
    assert result.node_states == {}


@pytest.mark.django_db
def test_execute_agent_ssh_cmd_awaits_async_connect_kwargs(monkeypatch):
    import asyncio

    import asyncssh

    user = User.objects.create_user(username="studio-ssh-cmd-user", password="x")
    _grant_feature(user, "studio", "agents")
    server = Server.objects.create(
        user=user,
        name="SSH Node Server",
        host="ssh-target",
        port=2222,
        username="smoke",
        auth_method="password",
        server_type="ssh",
    )
    pipeline = Pipeline.objects.create(name="SSH Cmd Flow", owner=user, nodes=[], edges=[])
    run = PipelineRun.objects.create(
        pipeline=pipeline,
        triggered_by=user,
        status=PipelineRun.STATUS_PENDING,
        context={"load_user": "smoke-user-01", "run_index": 1},
    )
    node = {
        "id": "ssh",
        "type": "agent/ssh_cmd",
        "data": {
            "server_id": server.id,
            "command": "printf 'PIPELINE_OK {load_user} {run_index}\\n'; whoami",
        },
    }

    captured: dict[str, object] = {}

    async def fake_build_connect_kwargs(_server):
        return {"host": "ssh-target", "port": 2222, "username": "smoke", "password": "smoke-password"}

    async def fake_log_pipeline_ssh_command(**kwargs):
        captured["log"] = kwargs

    class DummyConn:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def run(self, command, timeout=120):
            captured["command"] = command
            captured["timeout"] = timeout
            return SimpleNamespace(stdout="PIPELINE_OK smoke-user-01 1\nsmoke\n", stderr="", exit_status=0)

    def fake_connect(**kwargs):
        captured["connect_kwargs"] = kwargs
        return DummyConn()

    monkeypatch.setattr("servers.monitor._build_connect_kwargs", fake_build_connect_kwargs)
    monkeypatch.setattr("studio.pipeline_executor._log_pipeline_ssh_command", fake_log_pipeline_ssh_command)
    monkeypatch.setattr(Server.objects, "get", lambda *args, **kwargs: server)
    monkeypatch.setattr(asyncssh, "connect", fake_connect)

    result = asyncio.run(_execute_agent_ssh_cmd(node, {"load_user": "smoke-user-01", "run_index": 1}, run))

    assert result["status"] == "completed", result
    assert "PIPELINE_OK smoke-user-01 1" in result["output"]
    assert captured["command"] == "printf 'PIPELINE_OK smoke-user-01 1\\n'; whoami"
    assert captured["timeout"] == 120
    assert isinstance(captured["connect_kwargs"], dict)
    assert captured["connect_kwargs"]["connect_timeout"] == 30


@pytest.mark.django_db(transaction=True)
def test_pipeline_executor_wait_node_honors_stop_request():
    user = User.objects.create_user(username="studio-wait-stop-user", password="x")
    _grant_feature(user, "studio")
    pipeline = Pipeline.objects.create(
        name="Wait Stop",
        owner=user,
        nodes=[
            {
                "id": "wait_1",
                "type": "logic/wait",
                "position": {"x": 0, "y": 0},
                "data": {"wait_minutes": 5},
            }
        ],
        edges=[],
    )
    run = PipelineRun.objects.create(
        pipeline=pipeline,
        triggered_by=user,
        status=PipelineRun.STATUS_PENDING,
        context={},
    )

    holder: dict[str, PipelineExecutor] = {}

    def _target():
        import asyncio

        from django.db import connections

        try:
            run_obj = PipelineRun.objects.select_related("pipeline", "pipeline__owner", "triggered_by").get(pk=run.pk)
            executor = PipelineExecutor(run_obj)
            holder["executor"] = executor
            asyncio.run(executor.execute(context=run_obj.context))
        finally:
            connections.close_all()

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()

    deadline = time.time() + 5
    while "executor" not in holder and time.time() < deadline:
        time.sleep(0.05)

    assert "executor" in holder
    holder["executor"].request_stop()

    thread.join(timeout=5)
    assert thread.is_alive() is False

    run.refresh_from_db()
    assert run.status == PipelineRun.STATUS_STOPPED


@pytest.mark.django_db(transaction=True)
def test_pipeline_run_consumer_access_requires_run_owner():
    import asyncio

    owner = User.objects.create_user(username="studio-ws-owner", password="x")
    outsider = User.objects.create_user(username="studio-ws-outsider", password="x")
    _grant_feature(owner, "studio")
    _grant_feature(outsider, "studio")
    pipeline = Pipeline.objects.create(name="WS Access", owner=owner, nodes=[_llm_node("n1")], edges=[])
    run = PipelineRun.objects.create(pipeline=pipeline, status=PipelineRun.STATUS_PENDING, context={})

    consumer = PipelineRunConsumer()

    assert asyncio.run(consumer._user_can_access_run(owner.id, run.id)) is True
    assert asyncio.run(consumer._user_can_access_run(outsider.id, run.id)) is False


@pytest.mark.django_db
def test_api_pipeline_create_rejects_cycle(client):
    user = User.objects.create_user(username="studio-cycle-user", password="x")
    _grant_feature(user, "agents")
    client.force_login(user)

    response = client.post(
        "/api/studio/pipelines/",
        data=json.dumps(
            {
                "name": "Cycle",
                "nodes": [_llm_node("a"), _llm_node("b")],
                "edges": [
                    {"id": "ab", "source": "a", "target": "b"},
                    {"id": "ba", "source": "b", "target": "a"},
                ],
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "cycle" in response.json()["error"].lower()


@pytest.mark.django_db
def test_api_pipeline_create_rejects_inaccessible_refs(client):
    owner = User.objects.create_user(username="studio-owner", password="x")
    _grant_feature(owner, "agents")
    other = User.objects.create_user(username="studio-other", password="x")
    alien_server = Server.objects.create(
        user=other,
        name="Alien server",
        host="10.0.0.9",
        username="root",
    )
    alien_agent = AgentConfig.objects.create(name="Alien agent", owner=other)
    alien_mcp = MCPServerPool.objects.create(name="Alien MCP", owner=other, transport=MCPServerPool.TRANSPORT_STDIO)

    client.force_login(owner)
    response = client.post(
        "/api/studio/pipelines/",
        data=json.dumps(
            {
                "name": "Bad refs",
                "nodes": [
                    {
                        "id": "react_1",
                        "type": "agent/react",
                        "position": {"x": 0, "y": 0},
                        "data": {
                            "goal": "Inspect environment",
                            "agent_config_id": alien_agent.id,
                            "server_ids": [alien_server.id],
                            "mcp_server_ids": [alien_mcp.id],
                        },
                    }
                ],
                "edges": [],
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 400
    error_text = response.json()["error"]
    assert "agent config" in error_text.lower()
    assert "servers" in error_text.lower()
    assert "mcp" in error_text.lower()


@pytest.mark.django_db
def test_scheduler_fires_new_trigger_when_due(monkeypatch):
    import studio.management.commands.run_scheduled_pipelines as scheduler_module

    user = User.objects.create_user(username="studio-schedule-user", password="x")
    pipeline = Pipeline.objects.create(name="Scheduled Pipeline", owner=user, nodes=[_llm_node("n1")], edges=[])
    trigger = PipelineTrigger.objects.create(
        pipeline=pipeline,
        node_id="schedule_start",
        trigger_type=PipelineTrigger.TYPE_SCHEDULE,
        cron_expression="0 * * * *",
        is_active=True,
    )

    now = timezone.make_aware(datetime(2026, 3, 4, 10, 0, 0))

    class FakeCroniter:
        def __init__(self, expression, base):
            assert expression == "0 * * * *"
            assert base == now

        def get_prev(self, _kind):
            return now.timestamp()

    monkeypatch.setattr(scheduler_module, "croniter", FakeCroniter)
    monkeypatch.setattr(scheduler_module.timezone, "now", lambda: now)

    fired: list[int] = []
    command = Command()
    command._fire_trigger = lambda scheduled_trigger: fired.append(scheduled_trigger.pk)
    command._tick(interval_seconds=60)

    assert fired == [trigger.pk]
