from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.test.utils import override_settings
from django.utils import timezone

from core_ui.models import UserAppPermission
from studio.management.commands.run_scheduled_pipelines import Command as RunScheduledPipelinesCommand
from studio.models import Pipeline, PipelineRun


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


def _pipeline(owner: User, *, trigger_type: str = "trigger/manual") -> Pipeline:
    if trigger_type == "trigger/manual":
        trigger_id = "manual"
    elif trigger_type == "trigger/webhook":
        trigger_id = "webhook"
    elif trigger_type == "trigger/schedule":
        trigger_id = "schedule"
    else:
        trigger_id = "trigger"
    trigger_data = {"label": trigger_id.title()}
    if trigger_type == "trigger/webhook":
        trigger_data["webhook_payload_map"] = {}
    if trigger_type == "trigger/schedule":
        trigger_data["cron_expression"] = "*/5 * * * *"
    pipeline = Pipeline.objects.create(
        name=f"Run creation race {trigger_id}",
        owner=owner,
        nodes=[
            {
                "id": trigger_id,
                "type": trigger_type,
                "position": {"x": 0, "y": 0},
                "data": trigger_data,
            },
            {
                "id": "report",
                "type": "output/report",
                "position": {"x": 200, "y": 0},
                "data": {"template": "ok"},
            },
        ],
        edges=[{"id": "e1", "source": trigger_id, "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()
    return pipeline


@pytest.mark.django_db
def test_manual_run_returns_validation_error_when_creation_preflight_races(monkeypatch):
    user = User.objects.create_user(username="manual-race-user", password="x")
    _grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    pipeline = _pipeline(user)
    client = Client()
    client.force_login(user)

    def fail_create(**_kwargs):
        raise ValueError("Pipeline is not runnable: Selected trigger 'manual' has no downstream executable nodes.")

    monkeypatch.setattr("studio.views.pipeline_views._create_pipeline_run", fail_create)

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=_json({"context": {}}),
        content_type="application/json",
    )

    assert response.status_code == 400
    payload = response.json()
    assert "has no downstream executable nodes" in payload["error"]
    assert payload["issues"][0]["code"] == "trigger_without_downstream"
    assert "Connect this trigger" in payload["issues"][0]["next_action"]
    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 0


@pytest.mark.django_db
def test_webhook_run_returns_validation_error_when_creation_preflight_races(monkeypatch):
    owner = User.objects.create_user(username="webhook-race-user", password="x")
    pipeline = _pipeline(owner, trigger_type="trigger/webhook")
    trigger = pipeline.triggers.get(node_id="webhook")

    def fail_create(**_kwargs):
        raise ValueError("Pipeline is not runnable: Missing required runtime context fields: ticket_id.")

    monkeypatch.setattr("studio.views.trigger_views._create_pipeline_run", fail_create)

    response = Client().post(
        f"/api/studio/triggers/{trigger.webhook_token}/receive/",
        data=_json({"ok": True}),
        content_type="application/json",
    )

    assert response.status_code == 400
    payload = response.json()
    assert "ticket_id" in payload["error"]
    assert payload["issues"][0]["code"] == "runtime_context_required"
    assert payload["issues"][0]["fields"] == ["ticket_id"]
    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 0


@pytest.mark.django_db
@override_settings(PIPELINE_ACTIVE_RUNS_PER_USER_LIMIT=1, PIPELINE_ACTIVE_RUNS_GLOBAL_LIMIT=0)
def test_webhook_run_limit_returns_actionable_issue(monkeypatch):
    owner = User.objects.create_user(username="webhook-limit-user", password="x")
    pipeline = _pipeline(owner, trigger_type="trigger/webhook")
    trigger = pipeline.triggers.get(node_id="webhook")
    PipelineRun.objects.create(pipeline=pipeline, status=PipelineRun.STATUS_RUNNING, context={})
    monkeypatch.setattr(
        "studio.views.trigger_views._launch_pipeline_run",
        lambda _run: pytest.fail("run should not launch when limit is hit"),
    )

    response = Client().post(
        f"/api/studio/triggers/{trigger.webhook_token}/receive/",
        data=_json({"ok": True}),
        content_type="application/json",
    )

    assert response.status_code == 429
    payload = response.json()
    assert payload["code"] == "pipeline_user_limit_reached"
    assert payload["issues"][0]["source"] == "runtime_limit"
    assert payload["issues"][0]["next_action"].startswith("Wait for active runs")
    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 1


@pytest.mark.django_db
def test_manual_run_validate_only_returns_actionable_issues():
    user = User.objects.create_user(username="manual-validate-only-issues", password="x")
    _grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    pipeline = Pipeline.objects.create(
        name="Validate only context",
        owner=user,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
            {
                "id": "report",
                "type": "output/report",
                "position": {"x": 200, "y": 0},
                "data": {"template": "Ticket {ticket_id}"},
            },
        ],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()
    client = Client()
    client.force_login(user)

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=_json({"validate_only": True, "context": {}}),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["would_create_run"] is False
    assert payload["validation"]["issues"][0]["code"] == "runtime_context_required"
    assert payload["validation"]["issues"][0]["fields"] == ["ticket_id"]
    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 0


@pytest.mark.django_db
def test_manual_run_validate_only_blocks_missing_integrations(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    user = User.objects.create_user(username="manual-validate-integration", password="x")
    _grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    pipeline = Pipeline.objects.create(
        name="Validate missing LLM",
        owner=user,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
            {
                "id": "llm",
                "type": "agent/llm_query",
                "position": {"x": 200, "y": 0},
                "data": {"provider": "gemini", "prompt": "Summarize"},
            },
        ],
        edges=[{"id": "e1", "source": "manual", "target": "llm", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()
    client = Client()
    client.force_login(user)

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=_json({"validate_only": True, "context": {}}),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["validation"]["issues"][0]["code"] == "llm_credentials_missing"
    assert payload["integration_requirements"][0]["severity"] == "error"
    assert "integrations" in payload["dry_run"]["checks"]
    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 0


@pytest.mark.django_db
def test_manual_run_validate_only_ignores_other_trigger_branch_integrations(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    user = User.objects.create_user(username="manual-validate-branch-scope", password="x")
    _grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    pipeline = Pipeline.objects.create(
        name="Validate selected branch only",
        owner=user,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
            {"id": "webhook", "type": "trigger/webhook", "position": {"x": 0, "y": 120}, "data": {"webhook_payload_map": {}}},
            {"id": "report", "type": "output/report", "position": {"x": 200, "y": 0}, "data": {"template": "ok"}},
            {
                "id": "webhook_llm",
                "type": "agent/llm_query",
                "position": {"x": 200, "y": 120},
                "data": {"provider": "gemini", "prompt": "Summarize"},
            },
        ],
        edges=[
            {"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"},
            {"id": "e2", "source": "webhook", "target": "webhook_llm", "sourceHandle": "out"},
        ],
    )
    pipeline.sync_triggers_from_nodes()
    client = Client()
    client.force_login(user)

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=_json({"validate_only": True, "context": {}, "entry_node_id": "manual"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["validation"]["issues"] == []
    assert payload["integration_requirements"] == []


@pytest.mark.django_db
@override_settings(PIPELINE_ACTIVE_RUNS_PER_USER_LIMIT=1, PIPELINE_ACTIVE_RUNS_GLOBAL_LIMIT=0)
def test_manual_run_validate_only_reports_active_run_limit():
    user = User.objects.create_user(username="manual-validate-limit", password="x")
    _grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    pipeline = Pipeline.objects.create(
        name="Validate limit",
        owner=user,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
            {"id": "report", "type": "output/report", "position": {"x": 200, "y": 0}, "data": {"template": "ok"}},
        ],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()
    PipelineRun.objects.create(pipeline=pipeline, status=PipelineRun.STATUS_RUNNING, context={})
    client = Client()
    client.force_login(user)

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=_json({"validate_only": True, "context": {}}),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["dry_run"]["ok"] is False
    assert "runtime_limits" in payload["dry_run"]["checks"]
    assert payload["validation"]["issues"][0]["source"] == "runtime_limit"
    assert payload["validation"]["issues"][0]["code"] == "pipeline_user_limit_reached"
    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 1


@pytest.mark.django_db
@override_settings(
    PIPELINE_ACTIVE_RUNS_PER_USER_LIMIT=1,
    PIPELINE_ACTIVE_RUNS_GLOBAL_LIMIT=0,
    PIPELINE_RUN_STALE_SECONDS=1,
)
def test_manual_run_validate_only_does_not_cleanup_stale_runs():
    user = User.objects.create_user(username="manual-validate-stale-limit", password="x")
    _grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    pipeline = _pipeline(user)
    stale = PipelineRun.objects.create(
        pipeline=pipeline,
        status=PipelineRun.STATUS_RUNNING,
        context={},
    )
    old = timezone.now() - timedelta(seconds=60)
    PipelineRun.objects.filter(pk=stale.pk).update(created_at=old, started_at=old)
    client = Client()
    client.force_login(user)

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=_json({"validate_only": True, "context": {}}),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["validation"]["issues"] == []
    stale.refresh_from_db()
    assert stale.status == PipelineRun.STATUS_RUNNING
    assert stale.finished_at is None
    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 1


@pytest.mark.django_db
def test_schedule_runner_skips_when_creation_preflight_races(monkeypatch):
    owner = User.objects.create_user(username="schedule-race-user", password="x")
    pipeline = _pipeline(owner, trigger_type="trigger/schedule")
    trigger = pipeline.triggers.get(node_id="schedule")
    stderr = StringIO()

    def fail_create(**_kwargs):
        raise ValueError("Pipeline is not runnable: Selected trigger 'schedule' has no downstream executable nodes.")

    monkeypatch.setattr("studio.trigger_dispatch.create_pipeline_run", fail_create)

    RunScheduledPipelinesCommand(stderr=stderr)._fire_trigger(trigger)

    trigger.refresh_from_db()
    assert trigger.last_triggered_at is None
    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 0
    assert "has no downstream executable nodes" in stderr.getvalue()
