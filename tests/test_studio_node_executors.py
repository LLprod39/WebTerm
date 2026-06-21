from __future__ import annotations

import pytest
from asgiref.sync import async_to_sync

from servers.models import Server
from studio.models import Pipeline, PipelineRun
from studio.pipeline_executor import PipelineExecutor
from studio.pipeline_validation import KNOWN_NODE_TYPES
from tests.studio_node_executor_harness import (
    RUNTIME_COVERED_NODE_TYPES,
    disable_activity_logging,
    make_user,
)

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _disable_activity_logging(monkeypatch):
    disable_activity_logging(monkeypatch)


def test_runtime_coverage_matches_known_node_types():
    assert RUNTIME_COVERED_NODE_TYPES == KNOWN_NODE_TYPES


@pytest.mark.parametrize(
    ("entry_node_id", "expected_node_id"),
    [
        ("manual", "manual_task"),
        ("webhook", "webhook_task"),
        ("schedule", "schedule_task"),
    ],
)
def test_trigger_nodes_start_only_selected_branch(monkeypatch, entry_node_id: str, expected_node_id: str):
    owner = make_user(f"trigger-owner-{entry_node_id}")
    pipeline = Pipeline.objects.create(
        name="Trigger coverage flow",
        owner=owner,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "webhook", "type": "trigger/webhook", "position": {"x": 0, "y": 100}, "data": {}},
            {
                "id": "schedule",
                "type": "trigger/schedule",
                "position": {"x": 0, "y": 200},
                "data": {"cron_expression": "*/5 * * * *"},
            },
            {"id": "manual_task", "type": "output/report", "position": {"x": 120, "y": 0}, "data": {}},
            {"id": "webhook_task", "type": "output/report", "position": {"x": 120, "y": 100}, "data": {}},
            {"id": "schedule_task", "type": "output/report", "position": {"x": 120, "y": 200}, "data": {}},
        ],
        edges=[
            {"id": "e1", "source": "manual", "target": "manual_task", "sourceHandle": "out"},
            {"id": "e2", "source": "webhook", "target": "webhook_task", "sourceHandle": "out"},
            {"id": "e3", "source": "schedule", "target": "schedule_task", "sourceHandle": "out"},
        ],
    )
    pipeline.sync_triggers_from_nodes()

    async def fake_execute_node(self, node, context, node_outputs):
        return {"status": "completed", "output": node["id"]}

    monkeypatch.setattr(PipelineExecutor, "_execute_node", fake_execute_node)

    run = PipelineRun.objects.create(
        pipeline=pipeline,
        status=PipelineRun.STATUS_PENDING,
        nodes_snapshot=list(pipeline.nodes),
        edges_snapshot=list(pipeline.edges),
        context={},
        entry_node_id=entry_node_id,
        routing_state={
            "entry_node_id": entry_node_id,
            "activated_nodes": [entry_node_id],
            "completed_nodes": [],
            "queued_nodes": [],
            "pending_merges": {},
        },
    )

    result = async_to_sync(PipelineExecutor(run).execute)(context=run.context)

    assert result.status == PipelineRun.STATUS_COMPLETED
    assert set(result.node_states) == {expected_node_id}


def test_pipeline_executor_records_execution_policy_summary(monkeypatch):
    owner = make_user("policy-summary-owner")
    pipeline = Pipeline.objects.create(
        name="Policy summary flow",
        owner=owner,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {}},
            {
                "id": "notify",
                "type": "output/webhook",
                "position": {"x": 120, "y": 0},
                "data": {"url": "https://ops.example.test/hook?token=secret-token"},
            },
        ],
        edges=[{"id": "e1", "source": "manual", "target": "notify", "sourceHandle": "out"}],
    )

    async def fake_execute_node(self, node, context, node_outputs):
        return {"status": "completed", "output": node["id"]}

    monkeypatch.setattr(PipelineExecutor, "_execute_node", fake_execute_node)

    run = PipelineRun.objects.create(
        pipeline=pipeline,
        status=PipelineRun.STATUS_PENDING,
        nodes_snapshot=list(pipeline.nodes),
        edges_snapshot=list(pipeline.edges),
        context={},
        trigger_data={"source": "manual"},
        entry_node_id="manual",
    )

    result = async_to_sync(PipelineExecutor(run).execute)(context=run.context)

    assert result.status == PipelineRun.STATUS_COMPLETED
    summary = result.trigger_data["execution_policy"]
    assert summary["level"] == "review"
    assert summary["by_action_class"]["external"] == 1
    assert summary["items"][0]["command"] == "https://ops.example.test/hook?token=%5Bredacted%5D"
    assert summary["items"][0]["audit_metadata"]["policy_source"] == "studio_graph_validation"
    assert "secret-token" not in str(summary["items"][0]["audit_metadata"])


def test_monitoring_trigger_node_starts_selected_branch(monkeypatch):
    owner = make_user("trigger-owner-monitoring")
    server = Server.objects.create(user=owner, name="monitor-srv", host="10.0.0.9", username="root")
    pipeline = Pipeline.objects.create(
        name="Monitoring trigger coverage flow",
        owner=owner,
        nodes=[
            {
                "id": "monitoring",
                "type": "trigger/monitoring",
                "position": {"x": 0, "y": 0},
                "data": {"monitoring_filters": {"server_ids": [server.id], "alert_types": ["service"]}},
            },
            {"id": "monitoring_task", "type": "output/report", "position": {"x": 120, "y": 0}, "data": {}},
        ],
        edges=[
            {"id": "e1", "source": "monitoring", "target": "monitoring_task", "sourceHandle": "out"},
        ],
    )
    pipeline.sync_triggers_from_nodes()

    async def fake_execute_node(self, node, context, node_outputs):
        return {"status": "completed", "output": node["id"]}

    monkeypatch.setattr(PipelineExecutor, "_execute_node", fake_execute_node)

    run = PipelineRun.objects.create(
        pipeline=pipeline,
        status=PipelineRun.STATUS_PENDING,
        nodes_snapshot=list(pipeline.nodes),
        edges_snapshot=list(pipeline.edges),
        context={"server_name": server.name, "container_name": "demo"},
        entry_node_id="monitoring",
        routing_state={
            "entry_node_id": "monitoring",
            "activated_nodes": ["monitoring"],
            "completed_nodes": [],
            "queued_nodes": [],
            "pending_merges": {},
        },
    )

    result = async_to_sync(PipelineExecutor(run).execute)(context=run.context)

    assert result.status == PipelineRun.STATUS_COMPLETED
    assert set(result.node_states) == {"monitoring_task"}
