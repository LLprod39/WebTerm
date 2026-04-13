from __future__ import annotations

import json

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.test import Client

from core_ui.models import UserAppPermission
from studio.management.commands.run_scheduled_pipelines import Command as RunScheduledPipelinesCommand
from studio.keycloak_provisioning import (
    build_keycloak_edges,
    build_keycloak_nodes,
    build_keycloak_ops_edges,
    build_keycloak_ops_nodes,
)
from studio.mcp_showcase import build_showcase_edges, build_showcase_nodes
from studio.models import MCPServerPool, Pipeline, PipelineRun
from studio.pipeline_executor import PipelineExecutor
from studio.pipeline_validation import validate_pipeline_definition
from studio.webhook_smoke import (
    WEBHOOK_SMOKE_CRITICAL_PAYLOAD,
    WEBHOOK_SMOKE_NORMAL_PAYLOAD,
    build_webhook_smoke_edges,
    build_webhook_smoke_nodes,
    ensure_webhook_smoke_pipeline,
)


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


def _report_node(node_id: str, label: str | None = None, *, extra: dict | None = None) -> dict:
    return {
        "id": node_id,
        "type": "output/report",
        "position": {"x": 0, "y": 0},
        "data": {"label": label or node_id, **(extra or {})},
    }


def _build_run(pipeline: Pipeline, *, entry_node_id: str, context: dict | None = None) -> PipelineRun:
    return PipelineRun.objects.create(
        pipeline=pipeline,
        status=PipelineRun.STATUS_PENDING,
        nodes_snapshot=json.loads(json.dumps(pipeline.nodes or [])),
        edges_snapshot=json.loads(json.dumps(pipeline.edges or [])),
        context=dict(context or {}),
        entry_node_id=entry_node_id,
        routing_state={
            "entry_node_id": entry_node_id,
            "activated_nodes": [entry_node_id],
            "completed_nodes": [],
            "queued_nodes": [],
            "pending_merges": {},
        },
    )


@pytest.fixture(autouse=True)
def _disable_activity_logging(monkeypatch):
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr("studio.pipeline_executor.log_user_activity_async", _noop)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("entry_node_id", "expected_node_id"),
    [
        ("manual", "manual_task"),
        ("webhook", "webhook_task"),
        ("schedule", "schedule_task"),
    ],
)
def test_pipeline_executor_activates_only_selected_trigger_branch(monkeypatch, entry_node_id: str, expected_node_id: str):
    owner = User.objects.create_user(username=f"trigger-owner-{entry_node_id}", password="x")
    pipeline = Pipeline.objects.create(
        name="Trigger isolated flow",
        owner=owner,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
            {"id": "webhook", "type": "trigger/webhook", "position": {"x": 0, "y": 120}, "data": {"label": "Webhook"}},
            {"id": "schedule", "type": "trigger/schedule", "position": {"x": 0, "y": 240}, "data": {"label": "Schedule", "cron_expression": "*/5 * * * *"}},
            _report_node("manual_task"),
            _report_node("webhook_task"),
            _report_node("schedule_task"),
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

    run = _build_run(pipeline, entry_node_id=entry_node_id)
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
            {"id": "cond", "type": "logic/condition", "position": {"x": 0, "y": 100}, "data": {"check_type": "always_true"}},
            _report_node("true_branch"),
            _report_node("false_branch"),
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

    run = _build_run(pipeline, entry_node_id="manual")
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
            _report_node("action", extra={"on_failure": "continue"}),
            _report_node("success_report"),
            _report_node("error_report"),
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

    run = _build_run(pipeline, entry_node_id="manual")
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
            _report_node("action", extra={"on_failure": "abort"}),
            _report_node("error_report"),
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

    run = _build_run(pipeline, entry_node_id="manual")
    result = async_to_sync(PipelineExecutor(run).execute)(context=run.context)

    assert result.status == PipelineRun.STATUS_FAILED
    assert "error_report" not in result.node_states
    assert "fatal" in result.error


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(("decision", "expected"), [("approved", "approved_report"), ("rejected", "rejected_report"), ("timeout", "timeout_report")])
def test_pipeline_executor_routes_human_approval_ports(monkeypatch, decision: str, expected: str):
    owner = User.objects.create_user(username=f"approval-owner-{decision}", password="x")
    pipeline = Pipeline.objects.create(
        name="Approval flow",
        owner=owner,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "approval", "type": "logic/human_approval", "position": {"x": 0, "y": 100}, "data": {"timeout_minutes": 5}},
            _report_node("approved_report"),
            _report_node("rejected_report"),
            _report_node("timeout_report"),
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

    run = _build_run(pipeline, entry_node_id="manual")
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
            _report_node("branch_a"),
            _report_node("branch_b"),
            {"id": "merge", "type": "logic/merge", "position": {"x": 0, "y": 240}, "data": {"mode": "all"}},
            _report_node("after_merge"),
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

    run = _build_run(pipeline, entry_node_id="manual")
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
            _report_node("branch_ok"),
            _report_node("branch_fail"),
            {"id": "merge", "type": "logic/merge", "position": {"x": 0, "y": 240}, "data": {"mode": "any"}},
            _report_node("after_merge"),
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

    run = _build_run(pipeline, entry_node_id="manual")
    result = async_to_sync(PipelineExecutor(run).execute)(context=run.context)

    assert result.status == PipelineRun.STATUS_COMPLETED
    assert "after_merge" in result.node_states


@pytest.mark.django_db
def test_validation_allows_merge_with_single_remaining_input():
    user = User.objects.create_user(username="merge-single-user", password="x")

    errors = validate_pipeline_definition(
        nodes=[
            {"id": "webhook", "type": "trigger/webhook", "position": {"x": 0, "y": 0}, "data": {"label": "Webhook"}},
            {"id": "merge", "type": "logic/merge", "position": {"x": 180, "y": 0}, "data": {"mode": "any"}},
            _report_node("report"),
        ],
        edges=[
            {"id": "e1", "source": "webhook", "target": "merge", "sourceHandle": "out"},
            {"id": "e2", "source": "merge", "target": "report", "sourceHandle": "out"},
        ],
        owner=user,
        graph_version=2,
    )

    assert errors == []


@pytest.mark.django_db
def test_api_run_approve_resolves_normalized_node_id_and_sends_telegram_confirmation(monkeypatch):
    user = User.objects.create_user(username="approval-link-user", password="x")
    pipeline = Pipeline.objects.create(
        name="Approval link flow",
        owner=user,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {}},
            {
                "id": "approval_gate",
                "type": "logic/human_approval",
                "position": {"x": 180, "y": 0},
                "data": {
                    "label": "Approval Gate",
                    "tg_bot_token": "bot-123",
                    "tg_chat_id": "chat-42",
                },
            },
        ],
        edges=[{"id": "e1", "source": "manual", "target": "approval_gate", "sourceHandle": "out"}],
    )
    run = _build_run(pipeline, entry_node_id="manual")
    run.node_states = {
        "approval_gate": {
            "status": "awaiting_approval",
            "approval_token": "tok-123",
        }
    }
    run.save(update_fields=["node_states"])

    captured: dict[str, object] = {}

    def fake_post(url: str, json: dict, timeout: int):
        captured["url"] = url
        captured["json"] = json

        class _Resp:
            status_code = 200
            text = "ok"

        return _Resp()

    monkeypatch.setattr("studio.views.httpx.post", fake_post)
    client = Client()

    response = client.get(f"/api/studio/runs/{run.id}/approve/approvalgate/?token=tok-123&decision=approved")

    assert response.status_code == 200
    run.refresh_from_db()
    assert run.node_states["approval_gate"]["approval_decision"] == "approved"
    assert captured["url"] == "https://api.telegram.org/botbot-123/sendMessage"
    assert "Решение записано" in str(captured["json"]["text"])


@pytest.mark.django_db
def test_manual_run_auto_selects_only_manual_trigger(monkeypatch):
    user = User.objects.create_user(username="manual-api-user", password="x")
    _grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)
    monkeypatch.setattr("studio.views._launch_pipeline_run_async", lambda _run: None)

    pipeline = Pipeline.objects.create(
        name="Manual API flow",
        owner=user,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
            _report_node("report"),
        ],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=_json({"context": {"ticket": "INC-1"}}),
        content_type="application/json",
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["entry_node_id"] == "manual"
    assert payload["trigger_type"] == "manual"
    assert payload["trigger_id"] is not None


@pytest.mark.django_db
def test_create_pipeline_without_nodes_seeds_manual_draft():
    user = User.objects.create_user(username="draft-create-user", password="x")
    _grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)

    response = client.post(
        "/api/studio/pipelines/",
        data=_json({"name": "Draft Pipeline", "nodes": [], "edges": []}),
        content_type="application/json",
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["graph_version"] == 2
    assert len(payload["nodes"]) == 1
    assert payload["nodes"][0]["type"] == "trigger/manual"
    assert payload["nodes"][0]["id"] == "manual_start"


@pytest.mark.django_db
def test_manual_run_requires_entry_node_when_multiple_manual_triggers(monkeypatch):
    user = User.objects.create_user(username="manual-multi-user", password="x")
    _grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)
    monkeypatch.setattr("studio.views._launch_pipeline_run_async", lambda _run: None)

    pipeline = Pipeline.objects.create(
        name="Multiple manual triggers",
        owner=user,
        nodes=[
            {"id": "manual_a", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual A"}},
            {"id": "manual_b", "type": "trigger/manual", "position": {"x": 0, "y": 120}, "data": {"label": "Manual B"}},
            _report_node("report_a"),
            _report_node("report_b"),
        ],
        edges=[
            {"id": "e1", "source": "manual_a", "target": "report_a", "sourceHandle": "out"},
            {"id": "e2", "source": "manual_b", "target": "report_b", "sourceHandle": "out"},
        ],
    )
    pipeline.sync_triggers_from_nodes()

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=_json({"context": {}}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "entry_node_id" in response.json()["error"]

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=_json({"context": {}, "entry_node_id": "manual_b"}),
        content_type="application/json",
    )
    assert response.status_code == 202
    assert response.json()["entry_node_id"] == "manual_b"


@pytest.mark.django_db
def test_webhook_trigger_stores_entry_node_id(monkeypatch):
    user = User.objects.create_user(username="webhook-user", password="x")
    _grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)
    monkeypatch.setattr("studio.views._launch_pipeline_run_async", lambda _run: None)

    pipeline = Pipeline.objects.create(
        name="Webhook flow",
        owner=user,
        nodes=[
            {"id": "webhook", "type": "trigger/webhook", "position": {"x": 0, "y": 0}, "data": {"label": "Webhook", "webhook_payload_map": {"ref": "git.ref"}}},
            _report_node("report"),
        ],
        edges=[{"id": "e1", "source": "webhook", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()
    trigger = pipeline.triggers.get(trigger_type="webhook")

    response = client.post(
        f"/api/studio/triggers/{trigger.webhook_token}/receive/",
        data=_json({"git": {"ref": "refs/heads/main"}}),
        content_type="application/json",
    )

    assert response.status_code == 200
    run = PipelineRun.objects.get(pk=response.json()["run_id"])
    assert run.entry_node_id == "webhook"
    assert run.context["ref"] == "refs/heads/main"


@pytest.mark.django_db
def test_schedule_runner_stores_entry_node_id(monkeypatch):
    user = User.objects.create_user(username="schedule-user", password="x")
    pipeline = Pipeline.objects.create(
        name="Schedule flow",
        owner=user,
        nodes=[
            {"id": "schedule", "type": "trigger/schedule", "position": {"x": 0, "y": 0}, "data": {"label": "Schedule", "cron_expression": "*/5 * * * *"}},
            _report_node("report"),
        ],
        edges=[{"id": "e1", "source": "schedule", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()
    trigger = pipeline.triggers.get(trigger_type="schedule")

    monkeypatch.setattr("studio.views._launch_pipeline_run_async", lambda _run: None)
    RunScheduledPipelinesCommand()._fire_trigger(trigger)

    run = PipelineRun.objects.get(trigger=trigger)
    assert run.entry_node_id == "schedule"
    assert run.trigger_data["source"] == "schedule"


@pytest.mark.django_db
def test_old_graph_version_is_rejected_by_run_api(monkeypatch):
    user = User.objects.create_user(username="old-graph-user", password="x")
    _grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)
    monkeypatch.setattr("studio.views._launch_pipeline_run_async", lambda _run: None)

    pipeline = Pipeline.objects.create(
        name="Legacy flow",
        owner=user,
        graph_version=1,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
            _report_node("report"),
        ],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=_json({"context": {}}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "graph_version=1" in response.json()["error"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("graph_name", "build_nodes", "build_edges"),
    [
        ("keycloak_provisioning", lambda mcp_id: build_keycloak_nodes(mcp_id), build_keycloak_edges),
        (
            "keycloak_ops_test",
            lambda mcp_id: build_keycloak_ops_nodes(mcp_id, fixed_profile="test", environment_label="TEST"),
            build_keycloak_ops_edges,
        ),
        ("mcp_showcase", lambda mcp_id: build_showcase_nodes(mcp_id), build_showcase_edges),
        ("webhook_smoke", lambda _mcp_id: build_webhook_smoke_nodes(), build_webhook_smoke_edges),
    ],
)
def test_generated_v2_graphs_validate_cleanly(graph_name, build_nodes, build_edges):
    user = User.objects.create_user(username=f"{graph_name}-owner", password="x", is_staff=True)
    mcp_server = MCPServerPool.objects.create(
        owner=user,
        name=f"{graph_name}-mcp",
        transport=MCPServerPool.TRANSPORT_SSE,
        url="http://127.0.0.1:9999/mcp",
    )

    errors = validate_pipeline_definition(
        nodes=build_nodes(mcp_server.id),
        edges=build_edges(),
        owner=user,
        graph_version=2,
    )

    assert errors == []


@pytest.mark.django_db(transaction=True)
def test_webhook_smoke_pipeline_executes_critical_and_normal_branches(monkeypatch):
    user = User.objects.create_user(username="webhook-smoke-owner", password="x")
    pipeline = ensure_webhook_smoke_pipeline(user)
    trigger = pipeline.triggers.get(trigger_type="webhook")
    client = Client()

    def _run_now(run):
        async_to_sync(PipelineExecutor(run).execute)(context=run.context)

    monkeypatch.setattr("studio.views._launch_pipeline_run_async", _run_now)

    critical_response = client.post(
        f"/api/studio/triggers/{trigger.webhook_token}/receive/",
        data=_json(WEBHOOK_SMOKE_CRITICAL_PAYLOAD),
        content_type="application/json",
    )
    assert critical_response.status_code == 200
    critical_run = PipelineRun.objects.get(pk=critical_response.json()["run_id"])
    assert critical_run.status == PipelineRun.STATUS_COMPLETED
    assert "Branch selected: `critical`" in critical_run.summary

    normal_response = client.post(
        f"/api/studio/triggers/{trigger.webhook_token}/receive/",
        data=_json(WEBHOOK_SMOKE_NORMAL_PAYLOAD),
        content_type="application/json",
    )
    assert normal_response.status_code == 200
    normal_run = PipelineRun.objects.get(pk=normal_response.json()["run_id"])
    assert normal_run.status == PipelineRun.STATUS_COMPLETED
    assert "Branch selected: `normal`" in normal_run.summary
