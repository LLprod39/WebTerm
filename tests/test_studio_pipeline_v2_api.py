from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client

from studio.models import Pipeline, PipelineRun
from tests.studio_pipeline_v2_harness import (
    build_run,
    disable_activity_logging,
    grant_feature,
    json_payload,
    report_node,
)


@pytest.fixture(autouse=True)
def _disable_activity_logging(monkeypatch):
    disable_activity_logging(monkeypatch)


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
    run = build_run(pipeline, entry_node_id="manual")
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
    grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)
    monkeypatch.setattr("studio.trigger_dispatch.launch_pipeline_run_async", lambda _run: None)

    pipeline = Pipeline.objects.create(
        name="Manual API flow",
        owner=user,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
            report_node("report"),
        ],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=json_payload({"context": {"ticket": "INC-1"}}),
        content_type="application/json",
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["entry_node_id"] == "manual"
    assert payload["trigger_type"] == "manual"
    assert payload["trigger_id"] is not None


@pytest.mark.django_db
def test_manual_run_validate_only_does_not_create_or_launch_run(monkeypatch):
    user = User.objects.create_user(username="manual-validate-user", password="x")
    grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)
    launch_calls: list[int] = []
    monkeypatch.setattr("studio.views._launch_pipeline_run_async", lambda run: launch_calls.append(run.id))

    pipeline = Pipeline.objects.create(
        name="Manual validate flow",
        owner=user,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
            report_node("report"),
        ],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=json_payload({"context": {"ticket": "INC-1"}, "validate_only": True}),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["validation"] == {"ok": True, "errors": [], "issues": []}
    assert payload["dry_run"]["executed"] is False
    assert payload["dry_run"]["mode"] == "validate_only"
    assert payload["entry_node_id"] == "manual"
    assert payload["would_create_run"] is False
    assert launch_calls == []
    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 0


@pytest.mark.django_db
def test_manual_run_validate_only_reports_graph_errors_without_launch(monkeypatch):
    user = User.objects.create_user(username="manual-validate-errors-user", password="x")
    grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)
    monkeypatch.setattr(
        "studio.views._launch_pipeline_run_async", lambda _run: pytest.fail("validate_only must not launch")
    )

    pipeline = Pipeline.objects.create(
        name="Legacy validate flow",
        owner=user,
        graph_version=1,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
            report_node("report"),
        ],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=json_payload({"context": {}, "dry_run": True}),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["validation"]["ok"] is False
    assert any("graph_version=1" in error for error in payload["validation"]["errors"])
    assert payload["dry_run"]["executed"] is False
    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 0


@pytest.mark.django_db
def test_create_pipeline_without_nodes_seeds_manual_draft():
    user = User.objects.create_user(username="draft-create-user", password="x")
    grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)

    response = client.post(
        "/api/studio/pipelines/",
        data=json_payload({"name": "Draft Pipeline", "nodes": [], "edges": []}),
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
    grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)
    monkeypatch.setattr("studio.views._launch_pipeline_run_async", lambda _run: None)

    pipeline = Pipeline.objects.create(
        name="Multiple manual triggers",
        owner=user,
        nodes=[
            {"id": "manual_a", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual A"}},
            {"id": "manual_b", "type": "trigger/manual", "position": {"x": 0, "y": 120}, "data": {"label": "Manual B"}},
            report_node("report_a"),
            report_node("report_b"),
        ],
        edges=[
            {"id": "e1", "source": "manual_a", "target": "report_a", "sourceHandle": "out"},
            {"id": "e2", "source": "manual_b", "target": "report_b", "sourceHandle": "out"},
        ],
    )
    pipeline.sync_triggers_from_nodes()

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=json_payload({"context": {}}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "entry_node_id" in response.json()["error"]

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=json_payload({"context": {}, "entry_node_id": "manual_b"}),
        content_type="application/json",
    )
    assert response.status_code == 202
    assert response.json()["entry_node_id"] == "manual_b"


@pytest.mark.django_db
def test_webhook_trigger_stores_entry_node_id(monkeypatch):
    user = User.objects.create_user(username="webhook-user", password="x")
    grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)
    monkeypatch.setattr("studio.views._launch_pipeline_run_async", lambda _run: None)

    pipeline = Pipeline.objects.create(
        name="Webhook flow",
        owner=user,
        nodes=[
            {
                "id": "webhook",
                "type": "trigger/webhook",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Webhook", "webhook_payload_map": {"ref": "git.ref"}},
            },
            report_node("report"),
        ],
        edges=[{"id": "e1", "source": "webhook", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()
    trigger = pipeline.triggers.get(trigger_type="webhook")

    response = client.post(
        f"/api/studio/triggers/{trigger.webhook_token}/receive/",
        data=json_payload({"git": {"ref": "refs/heads/main"}}),
        content_type="application/json",
    )

    assert response.status_code == 200
    run = PipelineRun.objects.get(pk=response.json()["run_id"])
    assert run.entry_node_id == "webhook"
    assert run.context["ref"] == "refs/heads/main"


@pytest.mark.django_db
def test_old_graph_version_is_rejected_by_run_api(monkeypatch):
    user = User.objects.create_user(username="old-graph-user", password="x")
    grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)
    monkeypatch.setattr("studio.views._launch_pipeline_run_async", lambda _run: None)

    pipeline = Pipeline.objects.create(
        name="Legacy flow",
        owner=user,
        graph_version=1,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
            report_node("report"),
        ],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=json_payload({"context": {}}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "graph_version=1" in response.json()["error"]
