from __future__ import annotations

import json

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.test import Client

from core_ui.models import UserAppPermission
from studio.models import Pipeline, PipelineRun
from studio.pipeline.pipeline_executor import PipelineExecutor
from studio.pipeline.pipeline_runtime_context import (
    get_missing_pipeline_runtime_context_fields,
    get_pipeline_runtime_context_fields,
    validate_pipeline_entry_branch,
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


def _context_pipeline(owner: User, *, trigger_type: str = "trigger/manual") -> Pipeline:
    trigger_id = "manual" if trigger_type == "trigger/manual" else "webhook"
    pipeline = Pipeline.objects.create(
        name=f"Runtime context {trigger_id}",
        owner=owner,
        nodes=[
            {
                "id": trigger_id,
                "type": trigger_type,
                "position": {"x": 0, "y": 0},
                "data": {
                    "label": trigger_id.title(),
                    "webhook_payload_map": {"ticket_id": "ticket.id"} if trigger_type == "trigger/webhook" else {},
                },
            },
            {
                "id": "report",
                "type": "output/report",
                "position": {"x": 200, "y": 0},
                "data": {"template": "Ticket {ticket_id}\nPrevious {manual_output}\nRun {run_id}"},
            },
        ],
        edges=[{"id": "e1", "source": trigger_id, "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()
    return pipeline


def _multi_trigger_context_pipeline(owner: User) -> Pipeline:
    pipeline = Pipeline.objects.create(
        name="Runtime context multi trigger",
        owner=owner,
        nodes=[
            {
                "id": "manual",
                "type": "trigger/manual",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Manual"},
            },
            {
                "id": "webhook",
                "type": "trigger/webhook",
                "position": {"x": 0, "y": 120},
                "data": {"label": "Webhook", "webhook_payload_map": {"webhook_ref": "git.ref"}},
            },
            {
                "id": "manual_report",
                "type": "output/report",
                "position": {"x": 220, "y": 0},
                "data": {"template": "Ticket {ticket_id}"},
            },
            {
                "id": "webhook_report",
                "type": "output/report",
                "position": {"x": 220, "y": 120},
                "data": {"template": "Webhook {webhook_ref}"},
            },
        ],
        edges=[
            {"id": "e1", "source": "manual", "target": "manual_report", "sourceHandle": "out"},
            {"id": "e2", "source": "webhook", "target": "webhook_report", "sourceHandle": "out"},
        ],
    )
    pipeline.sync_triggers_from_nodes()
    return pipeline


def _trigger_only_pipeline(owner: User, *, trigger_type: str = "trigger/manual") -> Pipeline:
    trigger_id = "manual" if trigger_type == "trigger/manual" else "webhook"
    pipeline = Pipeline.objects.create(
        name=f"Trigger-only {trigger_id}",
        owner=owner,
        nodes=[
            {
                "id": trigger_id,
                "type": trigger_type,
                "position": {"x": 0, "y": 0},
                "data": {
                    "label": trigger_id.title(),
                    "webhook_payload_map": {} if trigger_type == "trigger/webhook" else {},
                },
            }
        ],
        edges=[],
    )
    pipeline.sync_triggers_from_nodes()
    return pipeline


@pytest.mark.django_db
def test_runtime_context_helper_ignores_builtin_and_output_placeholders():
    nodes = [
        {
            "id": "manual",
            "type": "trigger/manual",
            "data": {"label": "Manual"},
        },
        {
            "id": "report",
            "type": "output/report",
            "data": {
                "template": "{pipeline_name} {run_id} {manual_output} {prep_error} {ticket_id} {dry_run}",
                "command": "docker inspect --format '{{if .State.Health}}{{else}}{{end}}' {container_name}",
            },
        },
    ]
    fields = get_pipeline_runtime_context_fields(nodes)

    assert fields == ["container_name", "dry_run", "ticket_id"]
    assert (
        get_missing_pipeline_runtime_context_fields(
            nodes,
            {"container_name": "app", "dry_run": False, "ticket_id": "INC-100"},
        )
        == []
    )


@pytest.mark.django_db
def test_runtime_context_helper_includes_implicit_ops_context_keys():
    nodes = [
        {"id": "manual", "type": "trigger/manual", "data": {"label": "Manual"}},
        {
            "id": "snapshot",
            "type": "ops/server_snapshot",
            "data": {"server_id_context_key": "target_server_id"},
        },
        {
            "id": "service",
            "type": "ops/service_action",
            "data": {"server_id_context_key": "target_server_id", "action": "reload"},
        },
        {
            "id": "docker",
            "type": "ops/docker_action",
            "data": {"server_id_context_key": "target_server_id", "action": "restart"},
        },
        {
            "id": "process",
            "type": "ops/process_action",
            "data": {"server_id_context_key": "target_server_id", "action": "terminate"},
        },
        {"id": "alert", "type": "ops/alert_update", "data": {"action": "resolve"}},
    ]
    edges = [
        {"id": "e1", "source": "manual", "target": "snapshot", "sourceHandle": "out"},
        {"id": "e2", "source": "snapshot", "target": "service", "sourceHandle": "success"},
        {"id": "e3", "source": "service", "target": "docker", "sourceHandle": "success"},
        {"id": "e4", "source": "docker", "target": "process", "sourceHandle": "success"},
        {"id": "e5", "source": "process", "target": "alert", "sourceHandle": "success"},
    ]

    assert get_pipeline_runtime_context_fields(nodes, edges=edges, entry_node_id="manual") == [
        "alert_id",
        "container_name",
        "pid",
        "service_name",
        "target_server_id",
    ]
    assert get_missing_pipeline_runtime_context_fields(
        nodes,
        {"target_server_id": 1, "service_name": "nginx"},
        edges=edges,
        entry_node_id="manual",
    ) == ["alert_id", "container_name", "pid"]


@pytest.mark.django_db
def test_entry_branch_helper_requires_downstream_executable_node():
    user = User.objects.create_user(username="entry-branch-helper", password="x")
    pipeline = _trigger_only_pipeline(user)

    assert validate_pipeline_entry_branch(pipeline.nodes, pipeline.edges, "manual") == [
        "Selected trigger 'manual' has no downstream executable nodes."
    ]


@pytest.mark.django_db
def test_runtime_context_helper_scopes_fields_to_entry_branch():
    user = User.objects.create_user(username="runtime-context-scope", password="x")
    pipeline = _multi_trigger_context_pipeline(user)

    assert get_pipeline_runtime_context_fields(
        pipeline.nodes,
        edges=pipeline.edges,
        entry_node_id="manual",
    ) == ["ticket_id"]
    assert get_pipeline_runtime_context_fields(
        pipeline.nodes,
        edges=pipeline.edges,
        entry_node_id="webhook",
    ) == ["webhook_ref"]


@pytest.mark.django_db
def test_manual_pipeline_run_rejects_missing_runtime_context(monkeypatch):
    user = User.objects.create_user(username="runtime-context-manual", password="x")
    _grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    pipeline = _context_pipeline(user)
    client = Client()
    client.force_login(user)
    monkeypatch.setattr("studio.views._launch_pipeline_run_async", lambda _run: None)

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=_json({"context": {}}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "Missing required runtime context fields: ticket_id." in response.json()["error"]
    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 0


@pytest.mark.django_db
def test_manual_pipeline_run_validate_only_reports_missing_runtime_context():
    user = User.objects.create_user(username="runtime-context-validate", password="x")
    _grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    pipeline = _context_pipeline(user)
    client = Client()
    client.force_login(user)

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=_json({"context": {}, "validate_only": True}),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["validation"]["errors"] == ["Missing required runtime context fields: ticket_id."]
    assert "runtime_context" in payload["dry_run"]["checks"]
    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 0


@pytest.mark.django_db
def test_manual_pipeline_run_accepts_runtime_context(monkeypatch):
    user = User.objects.create_user(username="runtime-context-ok", password="x")
    _grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    pipeline = _context_pipeline(user)
    client = Client()
    client.force_login(user)
    monkeypatch.setattr("studio.views._launch_pipeline_run_async", lambda _run: None)

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=_json({"context": {"ticket_id": "INC-200"}}),
        content_type="application/json",
    )

    assert response.status_code == 202
    run = PipelineRun.objects.get(pk=response.json()["id"])
    assert run.context["ticket_id"] == "INC-200"


@pytest.mark.django_db
def test_manual_pipeline_run_rejects_trigger_without_downstream_nodes(monkeypatch):
    user = User.objects.create_user(username="runtime-context-manual-empty", password="x")
    _grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    pipeline = _trigger_only_pipeline(user)
    client = Client()
    client.force_login(user)
    monkeypatch.setattr("studio.views._launch_pipeline_run_async", lambda _run: pytest.fail("empty branch launched"))

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=_json({"context": {}}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "has no downstream executable nodes" in response.json()["error"]
    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 0


@pytest.mark.django_db
def test_manual_pipeline_run_ignores_runtime_context_from_other_trigger_branch(monkeypatch):
    user = User.objects.create_user(username="runtime-context-manual-branch", password="x")
    _grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    pipeline = _multi_trigger_context_pipeline(user)
    client = Client()
    client.force_login(user)
    monkeypatch.setattr("studio.views._launch_pipeline_run_async", lambda _run: None)

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=_json({"context": {"ticket_id": "INC-300"}}),
        content_type="application/json",
    )

    assert response.status_code == 202
    run = PipelineRun.objects.get(pk=response.json()["id"])
    assert run.entry_node_id == "manual"
    assert run.context == {"ticket_id": "INC-300"}


@pytest.mark.django_db
def test_webhook_trigger_rejects_missing_mapped_runtime_context(monkeypatch):
    user = User.objects.create_user(username="runtime-context-webhook", password="x")
    pipeline = _context_pipeline(user, trigger_type="trigger/webhook")
    trigger = pipeline.triggers.get(node_id="webhook")
    monkeypatch.setattr("studio.views._launch_pipeline_run_async", lambda _run: None)

    response = Client().post(
        f"/api/studio/triggers/{trigger.webhook_token}/receive/",
        data=_json({"ticket": {}}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "Missing required runtime context fields: ticket_id." in response.json()["error"]
    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 0


@pytest.mark.django_db
def test_webhook_trigger_rejects_trigger_without_downstream_nodes(monkeypatch):
    user = User.objects.create_user(username="runtime-context-webhook-empty", password="x")
    pipeline = _trigger_only_pipeline(user, trigger_type="trigger/webhook")
    trigger = pipeline.triggers.get(node_id="webhook")
    monkeypatch.setattr(
        "studio.views._launch_pipeline_run_async", lambda _run: pytest.fail("empty webhook branch launched")
    )

    response = Client().post(
        f"/api/studio/triggers/{trigger.webhook_token}/receive/",
        data=_json({"ok": True}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "has no downstream executable nodes" in response.json()["error"]
    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 0


@pytest.mark.django_db
def test_webhook_trigger_ignores_runtime_context_from_manual_branch(monkeypatch):
    user = User.objects.create_user(username="runtime-context-webhook-branch", password="x")
    pipeline = _multi_trigger_context_pipeline(user)
    trigger = pipeline.triggers.get(node_id="webhook")
    monkeypatch.setattr("studio.views._launch_pipeline_run_async", lambda _run: None)

    response = Client().post(
        f"/api/studio/triggers/{trigger.webhook_token}/receive/",
        data=_json({"git": {"ref": "refs/heads/main"}}),
        content_type="application/json",
    )

    assert response.status_code == 200
    run = PipelineRun.objects.get(pk=response.json()["run_id"])
    assert run.entry_node_id == "webhook"
    assert run.context == {"webhook_ref": "refs/heads/main"}


@pytest.mark.django_db(transaction=True)
def test_executor_fails_run_with_missing_runtime_context():
    user = User.objects.create_user(username="runtime-context-executor", password="x")
    pipeline = _context_pipeline(user)
    run = PipelineRun.objects.create(
        pipeline=pipeline,
        status=PipelineRun.STATUS_PENDING,
        nodes_snapshot=pipeline.nodes,
        edges_snapshot=pipeline.edges,
        entry_node_id="manual",
        context={},
    )

    result = async_to_sync(PipelineExecutor(run).execute)(context={})

    assert result.status == PipelineRun.STATUS_FAILED
    assert "Missing required runtime context fields: ticket_id." in result.error
