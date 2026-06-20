from __future__ import annotations

from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from servers.models import Server
from studio.models import Pipeline, PipelineRun
from studio.pipeline_executor import PipelineExecutor

pytestmark = pytest.mark.django_db(transaction=True)


def _make_user(username: str) -> User:
    return User.objects.create_user(username=username, password="x")


def _make_run(username: str = "agent-node-user") -> PipelineRun:
    owner = _make_user(username)
    pipeline = Pipeline.objects.create(
        name=f"Pipeline for {username}",
        owner=owner,
        nodes=[{"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}}],
        edges=[],
    )
    return PipelineRun.objects.create(
        pipeline=pipeline,
        triggered_by=owner,
        status=PipelineRun.STATUS_PENDING,
        nodes_snapshot=list(pipeline.nodes),
        edges_snapshot=list(pipeline.edges),
        context={},
        entry_node_id="manual",
        routing_state={
            "entry_node_id": "manual",
            "activated_nodes": ["manual"],
            "completed_nodes": [],
            "queued_nodes": [],
            "pending_merges": {},
        },
    )


@pytest.fixture(autouse=True)
def _disable_activity_logging(monkeypatch):
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr("studio.pipeline_agent_runtime.log_user_activity_async", _noop)
    monkeypatch.setattr("studio.pipeline_run_state.log_user_activity_async", _noop)
    monkeypatch.setattr("studio.pipeline_run_state.get_channel_layer", lambda: None)


def test_react_agent_node_executes_with_rendered_goal(monkeypatch):
    run = _make_run("react-node-user")
    server = Server.objects.create(user=run.pipeline.owner, name="react-srv", host="10.0.0.1", username="root")
    captured: dict[str, object] = {}

    async def fake_run_pipeline_react_agent(**kwargs):
        captured.update(
            {
                "goal": kwargs["goal"],
                "servers": [item.name for item in kwargs["servers"]],
                "permission_mode": kwargs["permission_mode"],
            }
        )
        return SimpleNamespace(agent_run_id=101, status="completed", final_report="react ok", ai_analysis="")

    monkeypatch.setattr("studio.pipeline_agent_runtime.run_pipeline_react_agent", fake_run_pipeline_react_agent)

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        {
            "id": "react",
            "type": "agent/react",
            "data": {"server_ids": [server.id], "goal": "Inspect {ticket}", "permission_mode": "PLAN"},
        },
        {"ticket": "INC-42"},
        {},
    )

    assert result["status"] == "completed"
    assert result["output"] == "react ok"
    assert captured["goal"] == "Inspect INC-42"
    assert captured["servers"] == ["react-srv"]
    assert captured["permission_mode"] == "PLAN"


def test_multi_agent_node_executes_with_rendered_goal(monkeypatch):
    run = _make_run("multi-node-user")
    server = Server.objects.create(user=run.pipeline.owner, name="multi-srv", host="10.0.0.2", username="root")
    captured: dict[str, object] = {}

    async def fake_run_pipeline_multi_agent(**kwargs):
        captured.update(
            {
                "goal": kwargs["goal"],
                "servers": [item.name for item in kwargs["servers"]],
                "permission_mode": kwargs["permission_mode"],
            }
        )
        return SimpleNamespace(agent_run_id=202, status="completed", final_report="multi ok", ai_analysis="")

    monkeypatch.setattr("studio.pipeline_agent_runtime.run_pipeline_multi_agent", fake_run_pipeline_multi_agent)

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        {
            "id": "multi",
            "type": "agent/multi",
            "data": {"server_ids": [server.id], "goal": "Coordinate {ticket}", "permission_mode": "SAFE"},
        },
        {"ticket": "INC-77"},
        {},
    )

    assert result["status"] == "completed"
    assert result["output"] == "multi ok"
    assert captured["goal"] == "Coordinate INC-77"
    assert captured["servers"] == ["multi-srv"]
    assert captured["permission_mode"] == "SAFE"
