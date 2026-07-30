from __future__ import annotations

from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from servers.models import Server
from studio.models import Pipeline, PipelineRun
from studio.pipeline.pipeline_executor import PipelineExecutor

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

    monkeypatch.setattr("studio.pipeline.pipeline_agent_runtime.log_user_activity_async", _noop)
    monkeypatch.setattr("studio.pipeline.pipeline_run_state.log_user_activity_async", _noop)
    monkeypatch.setattr("studio.pipeline.pipeline_run_state.get_channel_layer", lambda: None)


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
        return SimpleNamespace(
            agent_run_id=101,
            status="completed",
            final_report="react ok",
            ai_analysis="",
            outcome="success",
            outcome_reason="Agent returned a final answer",
            tool_call_count=2,
            failed_task_count=0,
            verification_summary="",
            plan_summary={},
        )

    monkeypatch.setattr(
        "studio.pipeline.pipeline_agent_runtime.run_pipeline_react_agent", fake_run_pipeline_react_agent
    )

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
    assert result["outcome"] == "success"
    assert result["output"] == "react ok"
    assert result["tool_call_count"] == 2
    assert captured["goal"] == "Inspect INC-42"
    assert captured["servers"] == ["react-srv"]
    assert captured["permission_mode"] == "PLAN"


def test_react_agent_node_partial_defaults_to_failed(monkeypatch):
    run = _make_run("react-partial-user")
    server = Server.objects.create(user=run.pipeline.owner, name="react-partial", host="10.0.0.8", username="root")

    async def fake_run_pipeline_react_agent(**kwargs):
        return SimpleNamespace(
            agent_run_id=111,
            status="completed",
            final_report="partial report",
            ai_analysis="",
            outcome="partial",
            outcome_reason="Max iterations exhausted without proven completion",
            tool_call_count=4,
            failed_task_count=0,
            verification_summary="",
            plan_summary={},
        )

    monkeypatch.setattr(
        "studio.pipeline.pipeline_agent_runtime.run_pipeline_react_agent", fake_run_pipeline_react_agent
    )

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        {
            "id": "react",
            "type": "agent/react",
            "data": {"server_ids": [server.id], "goal": "Diagnose service"},
        },
        {},
        {},
    )

    assert result["status"] == "failed"
    assert result["outcome"] == "partial"
    assert result["output"] == "partial report"
    assert "Max iterations" in result["error"]


def test_react_agent_node_partial_can_continue_as_success(monkeypatch):
    run = _make_run("react-partial-ok-user")
    server = Server.objects.create(user=run.pipeline.owner, name="react-partial-ok", host="10.0.0.9", username="root")

    async def fake_run_pipeline_react_agent(**kwargs):
        return SimpleNamespace(
            agent_run_id=112,
            status="completed",
            final_report="partial ok",
            ai_analysis="",
            outcome="partial",
            outcome_reason="partial work",
            tool_call_count=1,
            failed_task_count=0,
            verification_summary="",
            plan_summary={},
        )

    monkeypatch.setattr(
        "studio.pipeline.pipeline_agent_runtime.run_pipeline_react_agent", fake_run_pipeline_react_agent
    )

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        {
            "id": "react",
            "type": "agent/react",
            "data": {
                "server_ids": [server.id],
                "goal": "Diagnose service",
                "on_partial": "success",
            },
        },
        {},
        {},
    )

    assert result["status"] == "completed"
    assert result["outcome"] == "partial"
    assert result["error"] == ""


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
        return SimpleNamespace(
            agent_run_id=202,
            status="completed",
            final_report="multi ok",
            ai_analysis="",
            outcome="success",
            outcome_reason="All multi-agent tasks completed",
            tool_call_count=3,
            failed_task_count=0,
            verification_summary="",
            plan_summary={"total": 2, "done": 2, "failed": 0, "skipped": 0, "pending": 0},
        )

    monkeypatch.setattr(
        "studio.pipeline.pipeline_agent_runtime.run_pipeline_multi_agent", fake_run_pipeline_multi_agent
    )

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
    assert result["outcome"] == "success"
    assert result["output"] == "multi ok"
    assert result["plan_summary"]["done"] == 2
    assert captured["goal"] == "Coordinate INC-77"
    assert captured["servers"] == ["multi-srv"]
    assert captured["permission_mode"] == "SAFE"


def test_react_agent_empty_allowlist_fails(monkeypatch):
    run = _make_run("react-allowlist-user")
    server = Server.objects.create(user=run.pipeline.owner, name="react-al", host="10.0.1.1", username="root")
    called = {"value": False}

    async def fake_run_pipeline_react_agent(**kwargs):
        called["value"] = True
        return SimpleNamespace(agent_run_id=1, status="completed", final_report="x", ai_analysis="", outcome="success")

    monkeypatch.setattr(
        "studio.pipeline.pipeline_agent_runtime.run_pipeline_react_agent", fake_run_pipeline_react_agent
    )

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        {
            "id": "react",
            "type": "agent/react",
            "data": {
                "server_ids": [server.id],
                "goal": "Do work",
                "tools_mode": "allowlist",
                "allowed_tools": [],
            },
        },
        {},
        {},
    )
    assert result["status"] == "failed"
    assert "allowlist" in result["error"]
    assert called["value"] is False


def test_react_agent_passes_unattended_for_schedule_trigger(monkeypatch):
    run = _make_run("react-unatt-user")
    server = Server.objects.create(user=run.pipeline.owner, name="react-un", host="10.0.1.2", username="root")
    captured: dict[str, object] = {}

    async def fake_run_pipeline_react_agent(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            agent_run_id=700,
            status="completed",
            final_report="ok",
            ai_analysis="",
            outcome="success",
            outcome_reason="",
            tool_call_count=1,
            failed_task_count=0,
            verification_summary="",
            plan_summary={},
            policy_blocked_count=0,
            disconnected_servers=[],
        )

    monkeypatch.setattr(
        "studio.pipeline.pipeline_agent_runtime.run_pipeline_react_agent", fake_run_pipeline_react_agent
    )
    monkeypatch.setattr("studio.pipeline.pipeline_agent_runtime._pipeline_trigger_type", lambda _run: "schedule")

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        {
            "id": "react",
            "type": "agent/react",
            "data": {"server_ids": [server.id], "goal": "Diagnose"},
        },
        {},
        {},
    )
    assert result["status"] == "completed"
    assert captured.get("unattended") is True
    assert captured.get("pipeline_run_id") == run.pk


def test_multi_agent_passes_instructions(monkeypatch):
    run = _make_run("multi-instr-user")
    server = Server.objects.create(user=run.pipeline.owner, name="multi-in", host="10.0.1.3", username="root")
    captured: dict[str, object] = {}

    async def fake_run_pipeline_multi_agent(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            agent_run_id=701,
            status="completed",
            final_report="ok",
            ai_analysis="",
            outcome="success",
            outcome_reason="",
            tool_call_count=1,
            failed_task_count=0,
            verification_summary="",
            plan_summary={"total": 1, "done": 1, "failed": 0},
            policy_blocked_count=0,
            disconnected_servers=[],
        )

    monkeypatch.setattr(
        "studio.pipeline.pipeline_agent_runtime.run_pipeline_multi_agent", fake_run_pipeline_multi_agent
    )

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        {
            "id": "multi",
            "type": "agent/multi",
            "data": {
                "server_ids": [server.id],
                "goal": "Coordinate",
                "instructions": "Prefer read-only checks first",
            },
        },
        {},
        {},
    )
    assert result["status"] == "completed"
    assert captured.get("instructions") == "Prefer read-only checks first"


def test_react_agent_requires_non_empty_goal(monkeypatch):
    run = _make_run("react-empty-goal-user")
    server = Server.objects.create(user=run.pipeline.owner, name="react-empty", host="10.0.0.4", username="root")
    called = {"value": False}

    async def fake_run_pipeline_react_agent(**kwargs):
        called["value"] = True
        return SimpleNamespace(
            agent_run_id=1,
            status="completed",
            final_report="should not run",
            ai_analysis="",
            outcome="success",
            outcome_reason="",
            tool_call_count=0,
            failed_task_count=0,
            verification_summary="",
            plan_summary={},
        )

    monkeypatch.setattr(
        "studio.pipeline.pipeline_agent_runtime.run_pipeline_react_agent", fake_run_pipeline_react_agent
    )

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        {
            "id": "react",
            "type": "agent/react",
            "data": {"server_ids": [server.id], "goal": "   "},
        },
        {},
        {},
    )

    assert result["status"] == "failed"
    assert "Goal is required" in result["error"]
    assert called["value"] is False


def test_react_agent_injects_upstream_outputs_into_goal(monkeypatch):
    run = _make_run("react-upstream-user")
    server = Server.objects.create(user=run.pipeline.owner, name="react-up", host="10.0.0.5", username="root")
    captured: dict[str, object] = {}

    async def fake_run_pipeline_react_agent(**kwargs):
        captured["goal"] = kwargs["goal"]
        return SimpleNamespace(
            agent_run_id=501,
            status="completed",
            final_report="ok",
            ai_analysis="",
            outcome="success",
            outcome_reason="",
            tool_call_count=1,
            failed_task_count=0,
            verification_summary="",
            plan_summary={},
        )

    monkeypatch.setattr(
        "studio.pipeline.pipeline_agent_runtime.run_pipeline_react_agent", fake_run_pipeline_react_agent
    )

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        {
            "id": "react",
            "type": "agent/react",
            "data": {"server_ids": [server.id], "goal": "Fix the issue"},
        },
        {},
        {
            "diag": {"status": "completed", "output": "disk is 98% full on /var"},
        },
    )

    assert result["status"] == "completed"
    goal = str(captured["goal"])
    assert "Fix the issue" in goal
    assert "Context from previous pipeline steps" in goal
    assert "disk is 98% full" in goal


def test_react_agent_can_disable_upstream_injection(monkeypatch):
    run = _make_run("react-no-up-user")
    server = Server.objects.create(user=run.pipeline.owner, name="react-noup", host="10.0.0.6", username="root")
    captured: dict[str, object] = {}

    async def fake_run_pipeline_react_agent(**kwargs):
        captured["goal"] = kwargs["goal"]
        return SimpleNamespace(
            agent_run_id=502,
            status="completed",
            final_report="ok",
            ai_analysis="",
            outcome="success",
            outcome_reason="",
            tool_call_count=1,
            failed_task_count=0,
            verification_summary="",
            plan_summary={},
        )

    monkeypatch.setattr(
        "studio.pipeline.pipeline_agent_runtime.run_pipeline_react_agent", fake_run_pipeline_react_agent
    )

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        {
            "id": "react",
            "type": "agent/react",
            "data": {
                "server_ids": [server.id],
                "goal": "Only the goal",
                "include_upstream_outputs": False,
            },
        },
        {},
        {
            "diag": {"status": "completed", "output": "secret upstream text"},
        },
    )

    assert result["status"] == "completed"
    assert captured["goal"] == "Only the goal"


def test_multi_agent_node_failed_tasks_map_to_partial_failed(monkeypatch):
    run = _make_run("multi-partial-user")
    server = Server.objects.create(user=run.pipeline.owner, name="multi-partial", host="10.0.0.3", username="root")

    async def fake_run_pipeline_multi_agent(**kwargs):
        return SimpleNamespace(
            agent_run_id=303,
            status="completed",
            final_report="mixed",
            ai_analysis="",
            outcome="partial",
            outcome_reason="Mixed multi-agent results: 1 done, 1 failed",
            tool_call_count=2,
            failed_task_count=1,
            verification_summary="",
            plan_summary={"total": 2, "done": 1, "failed": 1, "skipped": 0, "pending": 0},
        )

    monkeypatch.setattr(
        "studio.pipeline.pipeline_agent_runtime.run_pipeline_multi_agent", fake_run_pipeline_multi_agent
    )

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        {
            "id": "multi",
            "type": "agent/multi",
            "data": {"server_ids": [server.id], "goal": "Coordinate work"},
        },
        {},
        {},
    )

    assert result["status"] == "failed"
    assert result["outcome"] == "partial"
    assert result["failed_task_count"] == 1
    assert result["plan_summary"]["failed"] == 1
