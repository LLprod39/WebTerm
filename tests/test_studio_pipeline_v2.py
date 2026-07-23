from __future__ import annotations

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from studio.models import Pipeline, PipelineRun
from studio.pipeline_executor import PipelineExecutor
from tests.studio_pipeline_v2_harness import build_run, disable_activity_logging, report_node


@pytest.fixture(autouse=True)
def _disable_activity_logging(monkeypatch):
    disable_activity_logging(monkeypatch)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("entry_node_id", "expected_node_id"),
    [
        ("manual", "manual_task"),
        ("webhook", "webhook_task"),
        ("schedule", "schedule_task"),
    ],
)
def test_pipeline_executor_activates_only_selected_trigger_branch(
    monkeypatch, entry_node_id: str, expected_node_id: str
):
    owner = User.objects.create_user(username=f"trigger-owner-{entry_node_id}", password="x")
    pipeline = Pipeline.objects.create(
        name="Trigger isolated flow",
        owner=owner,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
            {"id": "webhook", "type": "trigger/webhook", "position": {"x": 0, "y": 120}, "data": {"label": "Webhook"}},
            {
                "id": "schedule",
                "type": "trigger/schedule",
                "position": {"x": 0, "y": 240},
                "data": {"label": "Schedule", "cron_expression": "*/5 * * * *"},
            },
            report_node("manual_task"),
            report_node("webhook_task"),
            report_node("schedule_task"),
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

    run = build_run(pipeline, entry_node_id=entry_node_id)
    result = async_to_sync(PipelineExecutor(run).execute)(context=run.context)

    assert result.status == PipelineRun.STATUS_COMPLETED
    assert set(result.node_states) == {expected_node_id}


@pytest.mark.django_db
def test_pipeline_to_list_dict_includes_trigger_summary():
    owner = User.objects.create_user(username="summary-owner", password="x")
    pipeline = Pipeline.objects.create(
        name="Summary flow",
        owner=owner,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
            {"id": "webhook", "type": "trigger/webhook", "position": {"x": 0, "y": 120}, "data": {"label": "Webhook"}},
        ],
        edges=[],
    )
    pipeline.sync_triggers_from_nodes()
    webhook_trigger = pipeline.triggers.get(node_id="webhook")
    webhook_trigger.last_triggered_at = pipeline.updated_at
    webhook_trigger.save(update_fields=["last_triggered_at"])

    payload = pipeline.to_list_dict()

    assert payload["trigger_summary"] == {
        "active_total": 2,
        "active_manual": 1,
        "active_webhook": 1,
        "active_schedule": 0,
        "active_monitoring": 0,
        "last_triggered_at": webhook_trigger.last_triggered_at.isoformat(),
    }


@pytest.mark.django_db(transaction=True)
def test_pipeline_prefers_live_run_over_stale_stopped_run():
    owner = User.objects.create_user(username="live-run-owner", password="x")
    pipeline = Pipeline.objects.create(
        name="Live run flow",
        owner=owner,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
        ],
        edges=[],
    )

    live_run = PipelineRun.objects.create(
        pipeline=pipeline,
        status=PipelineRun.STATUS_RUNNING,
        entry_node_id="manual",
        nodes_snapshot=pipeline.nodes,
        edges_snapshot=[],
        routing_state={"entry_node_id": "manual"},
    )
    stale_run = PipelineRun.objects.create(
        pipeline=pipeline,
        status=PipelineRun.STATUS_STOPPED,
        entry_node_id="manual",
        nodes_snapshot=pipeline.nodes,
        edges_snapshot=[],
        routing_state={"entry_node_id": "manual"},
    )
    stale_run.started_at = None
    stale_run.save(update_fields=["started_at"])

    payload = pipeline.to_list_dict()

    assert pipeline.get_last_run().pk == live_run.pk
    assert payload["last_run"]["id"] == live_run.pk
    assert payload["last_run"]["status"] == PipelineRun.STATUS_RUNNING
    assert stale_run.pk > live_run.pk


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(("passed", "expected"), [(True, "true_branch"), (False, "false_branch")])
def test_pipeline_executor_routes_condition_ports(monkeypatch, passed: bool, expected: str):
    owner = User.objects.create_user(username=f"condition-owner-{passed}", password="x")
    pipeline = Pipeline.objects.create(
        name="Condition flow",
        owner=owner,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {}},
            {
                "id": "cond",
                "type": "logic/condition",
                "position": {"x": 0, "y": 100},
                "data": {"check_type": "always_true"},
            },
            report_node("true_branch"),
            report_node("false_branch"),
        ],
        edges=[
            {"id": "e1", "source": "manual", "target": "cond", "sourceHandle": "out"},
            {"id": "e2", "source": "cond", "target": "true_branch", "sourceHandle": "true"},
            {"id": "e3", "source": "cond", "target": "false_branch", "sourceHandle": "false"},
        ],
    )
    pipeline.sync_triggers_from_nodes()

    async def fake_execute_node(self, node, context, node_outputs):
        if node["id"] == "cond":
            return {"status": "completed", "passed": passed, "output": str(passed).lower()}
        return {"status": "completed", "output": node["id"]}

    monkeypatch.setattr(PipelineExecutor, "_execute_node", fake_execute_node)

    run = build_run(pipeline, entry_node_id="manual")
    result = async_to_sync(PipelineExecutor(run).execute)(context=run.context)

    assert result.status == PipelineRun.STATUS_COMPLETED
    assert expected in result.node_states
    unexpected = "false_branch" if expected == "true_branch" else "true_branch"
    assert unexpected not in result.node_states


@pytest.mark.django_db(transaction=True)
def test_pipeline_executor_routes_error_edge_without_abort(monkeypatch):
    owner = User.objects.create_user(username="error-route-owner", password="x")
    pipeline = Pipeline.objects.create(
        name="Error route flow",
        owner=owner,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {}},
            report_node("action", extra={"on_failure": "continue"}),
            report_node("success_report"),
            report_node("error_report"),
        ],
        edges=[
            {"id": "e1", "source": "manual", "target": "action", "sourceHandle": "out"},
            {"id": "e2", "source": "action", "target": "success_report", "sourceHandle": "success"},
            {"id": "e3", "source": "action", "target": "error_report", "sourceHandle": "error"},
        ],
    )
    pipeline.sync_triggers_from_nodes()

    async def fake_execute_node(self, node, context, node_outputs):
        if node["id"] == "action":
            return {"status": "failed", "error": "boom"}
        return {"status": "completed", "output": node["id"]}

    monkeypatch.setattr(PipelineExecutor, "_execute_node", fake_execute_node)

    run = build_run(pipeline, entry_node_id="manual")
    result = async_to_sync(PipelineExecutor(run).execute)(context=run.context)

    assert result.status == PipelineRun.STATUS_COMPLETED
    assert "error_report" in result.node_states
    assert "success_report" not in result.node_states


@pytest.mark.django_db(transaction=True)
def test_pipeline_executor_abort_stops_after_failed_action(monkeypatch):
    owner = User.objects.create_user(username="abort-owner", password="x")
    pipeline = Pipeline.objects.create(
        name="Abort route flow",
        owner=owner,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {}},
            report_node("action", extra={"on_failure": "abort"}),
            report_node("error_report"),
        ],
        edges=[
            {"id": "e1", "source": "manual", "target": "action", "sourceHandle": "out"},
            {"id": "e2", "source": "action", "target": "error_report", "sourceHandle": "error"},
        ],
    )
    pipeline.sync_triggers_from_nodes()

    async def fake_execute_node(self, node, context, node_outputs):
        if node["id"] == "action":
            return {"status": "failed", "error": "fatal"}
        return {"status": "completed", "output": node["id"]}

    monkeypatch.setattr(PipelineExecutor, "_execute_node", fake_execute_node)

    run = build_run(pipeline, entry_node_id="manual")
    result = async_to_sync(PipelineExecutor(run).execute)(context=run.context)

    assert result.status == PipelineRun.STATUS_FAILED
    assert "error_report" not in result.node_states
    assert "fatal" in result.error


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("decision", "expected"),
    [("approved", "approved_report"), ("rejected", "rejected_report"), ("timeout", "timeout_report")],
)
def test_pipeline_executor_routes_human_approval_ports(monkeypatch, decision: str, expected: str):
    owner = User.objects.create_user(username=f"approval-owner-{decision}", password="x")
    pipeline = Pipeline.objects.create(
        name="Approval flow",
        owner=owner,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {}},
            {
                "id": "approval",
                "type": "logic/human_approval",
                "position": {"x": 0, "y": 100},
                "data": {"timeout_minutes": 5},
            },
            report_node("approved_report"),
            report_node("rejected_report"),
            report_node("timeout_report"),
        ],
        edges=[
            {"id": "e1", "source": "manual", "target": "approval", "sourceHandle": "out"},
            {"id": "e2", "source": "approval", "target": "approved_report", "sourceHandle": "approved"},
            {"id": "e3", "source": "approval", "target": "rejected_report", "sourceHandle": "rejected"},
            {"id": "e4", "source": "approval", "target": "timeout_report", "sourceHandle": "timeout"},
        ],
    )
    pipeline.sync_triggers_from_nodes()

    async def fake_execute_node(self, node, context, node_outputs):
        if node["id"] != "approval":
            return {"status": "completed", "output": node["id"]}
        if decision == "approved":
            return {"status": "completed", "decision": "approved", "output": "approved"}
        return {"status": "failed", "decision": decision, "error": decision}

    monkeypatch.setattr(PipelineExecutor, "_execute_node", fake_execute_node)

    run = build_run(pipeline, entry_node_id="manual")
    result = async_to_sync(PipelineExecutor(run).execute)(context=run.context)

    assert result.status == PipelineRun.STATUS_COMPLETED
    assert expected in result.node_states
    for node_id in {"approved_report", "rejected_report", "timeout_report"} - {expected}:
        assert node_id not in result.node_states


@pytest.mark.django_db(transaction=True)
def test_pipeline_executor_parallel_split_and_merge_all(monkeypatch):
    owner = User.objects.create_user(username="merge-all-owner", password="x")
    pipeline = Pipeline.objects.create(
        name="Merge all flow",
        owner=owner,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "split", "type": "logic/parallel", "position": {"x": 0, "y": 100}, "data": {}},
            report_node("branch_a"),
            report_node("branch_b"),
            {"id": "merge", "type": "logic/merge", "position": {"x": 0, "y": 240}, "data": {"mode": "all"}},
            report_node("after_merge"),
        ],
        edges=[
            {"id": "e1", "source": "manual", "target": "split", "sourceHandle": "out"},
            {"id": "e2", "source": "split", "target": "branch_a", "sourceHandle": "out"},
            {"id": "e3", "source": "split", "target": "branch_b", "sourceHandle": "out"},
            {"id": "e4", "source": "branch_a", "target": "merge", "sourceHandle": "success"},
            {"id": "e5", "source": "branch_b", "target": "merge", "sourceHandle": "success"},
            {"id": "e6", "source": "merge", "target": "after_merge", "sourceHandle": "out"},
        ],
    )
    pipeline.sync_triggers_from_nodes()

    async def fake_execute_node(self, node, context, node_outputs):
        return {"status": "completed", "output": node["id"]}

    monkeypatch.setattr(PipelineExecutor, "_execute_node", fake_execute_node)

    run = build_run(pipeline, entry_node_id="manual")
    result = async_to_sync(PipelineExecutor(run).execute)(context=run.context)

    assert result.status == PipelineRun.STATUS_COMPLETED
    assert "merge" in result.node_states
    assert "after_merge" in result.node_states


@pytest.mark.django_db(transaction=True)
def test_pipeline_executor_merge_any_continues_after_first_success(monkeypatch):
    owner = User.objects.create_user(username="merge-any-owner", password="x")
    pipeline = Pipeline.objects.create(
        name="Merge any flow",
        owner=owner,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "split", "type": "logic/parallel", "position": {"x": 0, "y": 100}, "data": {}},
            report_node("branch_ok"),
            report_node("branch_fail"),
            {"id": "merge", "type": "logic/merge", "position": {"x": 0, "y": 240}, "data": {"mode": "any"}},
            report_node("after_merge"),
        ],
        edges=[
            {"id": "e1", "source": "manual", "target": "split", "sourceHandle": "out"},
            {"id": "e2", "source": "split", "target": "branch_ok", "sourceHandle": "out"},
            {"id": "e3", "source": "split", "target": "branch_fail", "sourceHandle": "out"},
            {"id": "e4", "source": "branch_ok", "target": "merge", "sourceHandle": "success"},
            {"id": "e5", "source": "branch_fail", "target": "merge", "sourceHandle": "success"},
            {"id": "e6", "source": "merge", "target": "after_merge", "sourceHandle": "out"},
        ],
    )
    pipeline.sync_triggers_from_nodes()

    async def fake_execute_node(self, node, context, node_outputs):
        if node["id"] == "branch_fail":
            return {"status": "failed", "error": "branch failed"}
        return {"status": "completed", "output": node["id"]}

    monkeypatch.setattr(PipelineExecutor, "_execute_node", fake_execute_node)

    run = build_run(pipeline, entry_node_id="manual")
    result = async_to_sync(PipelineExecutor(run).execute)(context=run.context)

    assert result.status == PipelineRun.STATUS_COMPLETED
    assert "after_merge" in result.node_states
