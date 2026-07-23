from __future__ import annotations

from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from app.background_workers import STUDIO_SCHEDULED_PIPELINES_WORKER
from servers.models import BackgroundWorkerState
from studio.management.commands.run_scheduled_pipelines import Command as RunScheduledPipelinesCommand
from studio.models import Pipeline, PipelineRun


def _report_node(node_id: str) -> dict:
    return {
        "id": node_id,
        "type": "output/report",
        "position": {"x": 200, "y": 0},
        "data": {"template": "ok"},
    }


@pytest.mark.django_db
def test_schedule_runner_skips_invalid_pipeline_before_creating_run(monkeypatch):
    user = User.objects.create_user(username="schedule-invalid-user", password="x")
    pipeline = Pipeline.objects.create(
        name="Invalid schedule flow",
        owner=user,
        graph_version=1,
        nodes=[
            {
                "id": "schedule",
                "type": "trigger/schedule",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Schedule", "cron_expression": "*/5 * * * *"},
            },
            _report_node("report"),
        ],
        edges=[{"id": "e1", "source": "schedule", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()
    trigger = pipeline.triggers.get(trigger_type="schedule")
    monkeypatch.setattr(
        "studio.trigger_dispatch.launch_pipeline_run_async", lambda _run: pytest.fail("invalid schedule launched")
    )
    stderr = StringIO()

    RunScheduledPipelinesCommand(stderr=stderr)._fire_trigger(trigger)

    trigger.refresh_from_db()
    assert PipelineRun.objects.filter(trigger=trigger).count() == 0
    assert trigger.last_triggered_at is None
    assert "graph_version=1" in stderr.getvalue()


@pytest.mark.django_db
def test_schedule_runner_skips_trigger_without_downstream_nodes(monkeypatch):
    user = User.objects.create_user(username="schedule-empty-user", password="x")
    pipeline = Pipeline.objects.create(
        name="Empty schedule flow",
        owner=user,
        nodes=[
            {
                "id": "schedule",
                "type": "trigger/schedule",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Schedule", "cron_expression": "*/5 * * * *"},
            }
        ],
        edges=[],
    )
    pipeline.sync_triggers_from_nodes()
    trigger = pipeline.triggers.get(trigger_type="schedule")
    monkeypatch.setattr(
        "studio.trigger_dispatch.launch_pipeline_run_async", lambda _run: pytest.fail("empty schedule launched")
    )
    stderr = StringIO()

    RunScheduledPipelinesCommand(stderr=stderr)._fire_trigger(trigger)

    trigger.refresh_from_db()
    assert PipelineRun.objects.filter(trigger=trigger).count() == 0
    assert trigger.last_triggered_at is None
    assert "has no downstream executable nodes" in stderr.getvalue()


@pytest.mark.django_db(transaction=True)
def test_schedule_runner_once_updates_worker_state():
    call_command("run_scheduled_pipelines", once=True, worker_key="pytest-scheduler")

    state = BackgroundWorkerState.objects.get(
        worker_kind=STUDIO_SCHEDULED_PIPELINES_WORKER,
        worker_key="pytest-scheduler",
    )
    assert state.status == BackgroundWorkerState.STATUS_IDLE
    assert state.last_started_at is not None
    assert state.last_stopped_at is not None
    assert state.last_summary["evaluated"] == 0
