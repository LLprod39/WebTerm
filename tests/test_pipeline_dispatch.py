from __future__ import annotations

import inspect
from datetime import timedelta

import pytest
from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone

from studio.dispatch import (
    claim_next_pipeline_dispatch,
    complete_pipeline_dispatch,
    heartbeat_pipeline_dispatch,
    retry_or_fail_pipeline_dispatch,
)
from studio.trigger_dispatch import create_pipeline_run, launch_pipeline_run_async

Pipeline = django_apps.get_model("studio", "Pipeline", require_ready=False)
PipelineRun = django_apps.get_model("studio", "PipelineRun", require_ready=False)
PipelineRunDispatch = django_apps.get_model("studio", "PipelineRunDispatch", require_ready=False)

pytestmark = pytest.mark.django_db(transaction=True)


def _pipeline(owner: User, name: str = "Durable pipeline") -> Pipeline:
    pipeline = Pipeline.objects.create(
        owner=owner,
        name=name,
        nodes=[
            {
                "id": "manual",
                "type": "trigger/manual",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Manual"},
            },
            {
                "id": "report",
                "type": "output/report",
                "position": {"x": 200, "y": 0},
                "data": {"template": "Recovered run {run_id}"},
            },
        ],
        edges=[{"id": "edge", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()
    return pipeline


def _run(pipeline: Pipeline) -> PipelineRun:
    return create_pipeline_run(
        pipeline=pipeline,
        triggered_by=pipeline.owner,
        context={},
        entry_node_id="manual",
    )


def test_pipeline_creation_atomically_enqueues_and_launch_facade_is_idempotent():
    owner = User.objects.create_user(username="pipeline-queue-owner", password="x")
    run = _run(_pipeline(owner))

    dispatch = PipelineRunDispatch.objects.get(run=run)
    assert dispatch.status == PipelineRunDispatch.STATUS_QUEUED
    launch_pipeline_run_async(run)
    assert PipelineRunDispatch.objects.filter(run=run).count() == 1

    source = inspect.getsource(__import__("studio.trigger_dispatch", fromlist=["trigger_dispatch"]))
    assert "threading.Thread" not in source
    assert "daemon=True" not in source


def test_expired_lease_is_reclaimed_and_old_attempt_is_fenced():
    owner = User.objects.create_user(username="pipeline-fence-owner", password="x")
    run = _run(_pipeline(owner))
    first = claim_next_pipeline_dispatch(worker_name="worker-a", lease_seconds=30)
    assert first is not None
    assert first.attempt_count == 1

    PipelineRunDispatch.objects.filter(pk=first.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
    second = claim_next_pipeline_dispatch(worker_name="worker-b", lease_seconds=30)
    assert second is not None
    assert second.pk == first.pk
    assert second.attempt_count == 2
    assert (
        heartbeat_pipeline_dispatch(
            first.pk,
            worker_name="worker-a",
            attempt_count=1,
            lease_seconds=30,
        )
        is False
    )
    assert complete_pipeline_dispatch(first.pk, worker_name="worker-a", attempt_count=1) is None
    assert complete_pipeline_dispatch(second.pk, worker_name="worker-b", attempt_count=2) is not None
    run.refresh_from_db()
    assert run.status == PipelineRun.STATUS_PENDING


def test_failed_attempt_is_requeued_until_max_attempts():
    owner = User.objects.create_user(username="pipeline-retry-owner", password="x")
    run = _run(_pipeline(owner))
    dispatch = claim_next_pipeline_dispatch(worker_name="retry-worker", lease_seconds=30)
    assert dispatch is not None

    retried = retry_or_fail_pipeline_dispatch(
        dispatch.pk,
        worker_name="retry-worker",
        attempt_count=dispatch.attempt_count,
        error="transient worker failure",
    )
    assert retried is not None
    assert retried.status == PipelineRunDispatch.STATUS_QUEUED
    run.refresh_from_db()
    assert run.status == PipelineRun.STATUS_PENDING

    claimed_again = claim_next_pipeline_dispatch(worker_name="retry-worker-2", lease_seconds=30)
    assert claimed_again is not None
    assert claimed_again.attempt_count == 2


def test_per_user_and_global_claim_limits_are_database_enforced():
    first_owner = User.objects.create_user(username="pipeline-limit-owner-a", password="x")
    second_owner = User.objects.create_user(username="pipeline-limit-owner-b", password="x")
    first_pipeline = _pipeline(first_owner, "Owner A")
    _run(first_pipeline)
    _run(first_pipeline)
    _run(_pipeline(second_owner, "Owner B"))

    first = claim_next_pipeline_dispatch(
        worker_name="limit-a",
        lease_seconds=30,
        global_concurrency=2,
        per_user_concurrency=1,
    )
    second = claim_next_pipeline_dispatch(
        worker_name="limit-b",
        lease_seconds=30,
        global_concurrency=2,
        per_user_concurrency=1,
    )
    blocked = claim_next_pipeline_dispatch(
        worker_name="limit-c",
        lease_seconds=30,
        global_concurrency=2,
        per_user_concurrency=1,
    )

    assert first is not None and second is not None
    assert first.run.pipeline.owner_id != second.run.pipeline.owner_id
    assert blocked is None


def test_ten_active_runs_survive_backend_restart_and_finish_in_worker():
    owner = User.objects.create_user(username="pipeline-restart-owner", password="x")
    pipeline = _pipeline(owner, "Restart recovery")
    runs = [_run(pipeline) for _index in range(10)]
    stale_time = timezone.now() - timedelta(minutes=5)
    PipelineRun.objects.filter(pk__in=[run.pk for run in runs]).update(
        status=PipelineRun.STATUS_RUNNING,
        started_at=stale_time,
    )
    PipelineRunDispatch.objects.filter(run__in=runs).update(
        status=PipelineRunDispatch.STATUS_CLAIMED,
        claimed_by="dead-backend",
        claimed_at=stale_time,
        heartbeat_at=stale_time,
        lease_expires_at=stale_time,
        attempt_count=1,
    )

    call_command(
        "run_pipeline_execution_plane",
        once=True,
        limit=10,
        lease_seconds=60,
        global_concurrency=10,
        per_user_concurrency=10,
        worker_key="restart-worker",
    )

    assert (
        PipelineRun.objects.filter(pk__in=[run.pk for run in runs], status=PipelineRun.STATUS_COMPLETED).count() == 10
    )
    assert (
        PipelineRunDispatch.objects.filter(
            run__in=runs,
            status=PipelineRunDispatch.STATUS_COMPLETED,
            claimed_by="restart-worker",
            attempt_count=2,
        ).count()
        == 10
    )
