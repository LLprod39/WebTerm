from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.apps import apps as django_apps
from django.core.management import call_command
from django.utils import timezone

from core_ui.models.audit import UserActivityLog

Pipeline = django_apps.get_model("studio", "Pipeline", require_ready=False)
PipelineRun = django_apps.get_model("studio", "PipelineRun", require_ready=False)


@pytest.mark.django_db
def test_reconcile_pipeline_runs_fails_only_stale_active_runs(django_user_model):
    owner = django_user_model.objects.create_user(username="pipeline-reconcile-owner", password="x")
    pipeline = Pipeline.objects.create(name="Reconcile pipeline", owner=owner, nodes=[], edges=[])
    stale_pending = PipelineRun.objects.create(pipeline=pipeline, status=PipelineRun.STATUS_PENDING)
    stale_running = PipelineRun.objects.create(
        pipeline=pipeline,
        status=PipelineRun.STATUS_RUNNING,
        started_at=timezone.now(),
    )
    recent = PipelineRun.objects.create(pipeline=pipeline, status=PipelineRun.STATUS_PENDING)
    old = timezone.now() - timedelta(minutes=10)
    PipelineRun.objects.filter(pk=stale_pending.pk).update(created_at=old)
    PipelineRun.objects.filter(pk=stale_running.pk).update(created_at=old, started_at=old)

    output = StringIO()
    call_command("reconcile_pipeline_runs", stale_seconds=60, stdout=output)

    stale_pending.refresh_from_db()
    stale_running.refresh_from_db()
    recent.refresh_from_db()
    assert stale_pending.status == PipelineRun.STATUS_FAILED
    assert stale_running.status == PipelineRun.STATUS_FAILED
    assert stale_pending.finished_at is not None
    assert "worker_restart" in stale_pending.error
    assert recent.status == PipelineRun.STATUS_PENDING
    events = UserActivityLog.objects.filter(
        action="pipeline_run_reconciled",
        entity_type="pipeline_run",
    ).order_by("entity_id")
    assert events.count() == 2
    assert {event.metadata["reason"] for event in events} == {"worker_restart"}
    assert "failed=2" in output.getvalue()
