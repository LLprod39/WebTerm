from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from studio.management.commands.run_scheduled_pipelines import Command as RunScheduledPipelinesCommand
from studio.models import Pipeline, PipelineRun
from studio.pipeline_validation import validate_pipeline_definition
from tests.studio_pipeline_v2_harness import disable_activity_logging, report_node


@pytest.fixture(autouse=True)
def _disable_activity_logging(monkeypatch):
    disable_activity_logging(monkeypatch)


@pytest.mark.django_db
def test_schedule_runner_stores_entry_node_id(monkeypatch):
    user = User.objects.create_user(username="schedule-user", password="x")
    pipeline = Pipeline.objects.create(
        name="Schedule flow",
        owner=user,
        nodes=[
            {
                "id": "schedule",
                "type": "trigger/schedule",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Schedule", "cron_expression": "*/5 * * * *"},
            },
            report_node("report"),
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
def test_schedule_runner_fires_with_fallback_cron_without_croniter(monkeypatch):
    user = User.objects.create_user(username="schedule-fallback-user", password="x")
    pipeline = Pipeline.objects.create(
        name="Fallback schedule flow",
        owner=user,
        nodes=[
            {
                "id": "schedule",
                "type": "trigger/schedule",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Schedule", "cron_expression": "* * * * *"},
            },
            report_node("report"),
        ],
        edges=[{"id": "e1", "source": "schedule", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()
    trigger = pipeline.triggers.get(trigger_type="schedule")
    now = timezone.now().replace(second=30, microsecond=0)

    monkeypatch.setattr("studio.cron_schedule.croniter", None)
    monkeypatch.setattr("studio.management.commands.run_scheduled_pipelines.timezone.now", lambda: now)
    monkeypatch.setattr("studio.trigger_dispatch.launch_pipeline_run_async", lambda _run: None)

    RunScheduledPipelinesCommand()._tick(interval_seconds=60)

    run = PipelineRun.objects.get(trigger=trigger)
    trigger.refresh_from_db()
    assert run.entry_node_id == "schedule"
    assert run.trigger_data == {"source": "schedule", "cron": "* * * * *"}
    assert trigger.last_triggered_at is not None


@pytest.mark.django_db
def test_schedule_validation_rejects_invalid_fallback_cron_without_croniter(monkeypatch):
    user = User.objects.create_user(username="schedule-validation-fallback-user", password="x")
    monkeypatch.setattr("studio.cron_schedule.croniter", None)

    errors = validate_pipeline_definition(
        nodes=[
            {
                "id": "schedule",
                "type": "trigger/schedule",
                "position": {"x": 0, "y": 0},
                "data": {"cron_expression": "*/0 * * * *"},
            },
            report_node("report"),
        ],
        edges=[{"id": "e1", "source": "schedule", "target": "report", "sourceHandle": "out"}],
        owner=user,
        graph_version=2,
    )

    assert any("invalid cron expression" in error for error in errors)
