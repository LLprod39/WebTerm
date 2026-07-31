"""Durable lease-based queue for Studio pipeline execution."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import timedelta
from typing import Any

from asgiref.sync import sync_to_async
from django.apps import apps as django_apps
from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from core_ui.activity import log_user_activity
from studio.dispatch_models import PipelineDispatchControl, PipelineRunDispatch

PipelineRun = django_apps.get_model("studio", "PipelineRun", require_ready=False)

logger = logging.getLogger(__name__)


class PipelineDispatchLeaseLost(RuntimeError):
    """The worker no longer owns the claimed dispatch attempt."""


def _active_run_statuses() -> tuple[str, ...]:
    return (
        PipelineRun.STATUS_PENDING,
        PipelineRun.STATUS_RUNNING,
        PipelineRun.STATUS_HIBERNATING,
    )


def _record_dispatch_event(dispatch: PipelineRunDispatch, action: str, **metadata: Any) -> None:
    run = dispatch.run
    actor = run.triggered_by or run.pipeline.owner
    log_user_activity(
        user=actor,
        category="pipeline",
        action=action,
        status="error" if action.endswith(("failed", "exhausted")) else "success",
        description=f"Pipeline dispatch #{dispatch.pk} {action.removeprefix('pipeline_dispatch_').replace('_', ' ')}.",
        entity_type="pipeline_run_dispatch",
        entity_id=str(dispatch.pk),
        entity_name=run.pipeline.name,
        metadata={
            "run_id": run.pk,
            "attempt_count": int(dispatch.attempt_count),
            "max_attempts": int(dispatch.max_attempts),
            **metadata,
        },
    )


def enqueue_pipeline_run_dispatch(
    run: PipelineRun,
    *,
    max_attempts: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> PipelineRunDispatch:
    attempts = max(1, int(max_attempts or getattr(settings, "PIPELINE_EXECUTION_MAX_ATTEMPTS", 3)))
    dispatch, created = PipelineRunDispatch.objects.get_or_create(
        run=run,
        defaults={"max_attempts": attempts, "metadata": dict(metadata or {})},
    )
    if created:
        _record_dispatch_event(dispatch, "pipeline_dispatch_enqueued")
    return dispatch


@transaction.atomic
def requeue_pipeline_run_dispatch(
    run: PipelineRun,
    *,
    max_attempts: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> PipelineRunDispatch:
    """Reset an existing terminal dispatch for an explicitly resumed run."""

    attempts = max(1, int(max_attempts or getattr(settings, "PIPELINE_EXECUTION_MAX_ATTEMPTS", 3)))
    dispatch = PipelineRunDispatch.objects.select_for_update().filter(run=run).first()
    if dispatch is None:
        dispatch = PipelineRunDispatch.objects.create(
            run=run,
            max_attempts=attempts,
            metadata=dict(metadata or {}),
        )
    else:
        dispatch.status = PipelineRunDispatch.STATUS_QUEUED
        dispatch.metadata = dict(metadata or {})
        dispatch.queued_at = timezone.now()
        dispatch.claimed_at = None
        dispatch.heartbeat_at = None
        dispatch.lease_expires_at = None
        dispatch.completed_at = None
        dispatch.claimed_by = ""
        dispatch.attempt_count = 0
        dispatch.max_attempts = attempts
        dispatch.error = ""
        dispatch.save(
            update_fields=[
                "status",
                "metadata",
                "queued_at",
                "claimed_at",
                "heartbeat_at",
                "lease_expires_at",
                "completed_at",
                "claimed_by",
                "attempt_count",
                "max_attempts",
                "error",
            ]
        )
    _record_dispatch_event(dispatch, "pipeline_dispatch_resume_queued")
    return dispatch


def _fail_exhausted_dispatches(now) -> int:
    exhausted = list(
        # of=("self",) is required: run__triggered_by is nullable, so select_related
        # emits a LEFT OUTER JOIN and PostgreSQL refuses a bare FOR UPDATE over it
        # ("FOR UPDATE cannot be applied to the nullable side of an outer join").
        # Locking only the dispatch row is also the correct semantics here.
        PipelineRunDispatch.objects.select_for_update(skip_locked=True, of=("self",))
        .select_related("run", "run__pipeline", "run__pipeline__owner", "run__triggered_by")
        .filter(
            Q(status=PipelineRunDispatch.STATUS_QUEUED)
            | Q(status=PipelineRunDispatch.STATUS_CLAIMED, lease_expires_at__lte=now),
            attempt_count__gte=F("max_attempts"),
            run__status__in=_active_run_statuses(),
        )
        .order_by("queued_at", "id")[:100]
    )
    for dispatch in exhausted:
        error = f"Pipeline dispatch exhausted its {dispatch.max_attempts} permitted attempts"
        dispatch.status = PipelineRunDispatch.STATUS_FAILED
        dispatch.completed_at = now
        dispatch.lease_expires_at = now
        dispatch.error = error
        dispatch.save(update_fields=["status", "completed_at", "lease_expires_at", "error"])
        PipelineRun.objects.filter(pk=dispatch.run_id, status__in=_active_run_statuses()).update(
            status=PipelineRun.STATUS_FAILED,
            error=error,
            finished_at=now,
        )
        _record_dispatch_event(dispatch, "pipeline_dispatch_exhausted", error=error)
    return len(exhausted)


def claim_next_pipeline_dispatch(
    *,
    worker_name: str,
    lease_seconds: int = 180,
    global_concurrency: int = 4,
    per_user_concurrency: int = 2,
) -> PipelineRunDispatch | None:
    now = timezone.now()
    lease_delta = timedelta(seconds=max(30, int(lease_seconds)))
    global_limit = max(1, int(global_concurrency))
    user_limit = max(1, int(per_user_concurrency))
    with transaction.atomic():
        control, _created = PipelineDispatchControl.objects.get_or_create(name="global")
        PipelineDispatchControl.objects.select_for_update().get(pk=control.pk)
        _fail_exhausted_dispatches(now)
        active_claims = list(
            PipelineRunDispatch.objects.filter(
                status=PipelineRunDispatch.STATUS_CLAIMED,
                lease_expires_at__gt=now,
            ).values_list("run__pipeline__owner_id", flat=True)
        )
        if len(active_claims) >= global_limit:
            return None
        claims_by_user = Counter(active_claims)
        candidates = list(
            PipelineRunDispatch.objects.select_for_update(skip_locked=True, of=("self",))
            .select_related("run", "run__pipeline", "run__pipeline__owner", "run__triggered_by")
            .filter(
                Q(status=PipelineRunDispatch.STATUS_QUEUED)
                | Q(status=PipelineRunDispatch.STATUS_CLAIMED, lease_expires_at__lte=now),
                attempt_count__lt=F("max_attempts"),
                run__status__in=_active_run_statuses(),
            )
            .order_by("queued_at", "id")[:100]
        )
        dispatch = next(
            (candidate for candidate in candidates if claims_by_user[candidate.run.pipeline.owner_id] < user_limit),
            None,
        )
        if dispatch is None:
            return None

        dispatch.status = PipelineRunDispatch.STATUS_CLAIMED
        dispatch.claimed_at = now
        dispatch.heartbeat_at = now
        dispatch.lease_expires_at = now + lease_delta
        dispatch.claimed_by = str(worker_name or "default")[:120]
        dispatch.attempt_count = int(dispatch.attempt_count) + 1
        dispatch.error = ""
        dispatch.save(
            update_fields=[
                "status",
                "claimed_at",
                "heartbeat_at",
                "lease_expires_at",
                "claimed_by",
                "attempt_count",
                "error",
            ]
        )
        _record_dispatch_event(dispatch, "pipeline_dispatch_claimed", worker_key=dispatch.claimed_by)
        return dispatch


def heartbeat_pipeline_dispatch(
    dispatch_id: int,
    *,
    worker_name: str,
    attempt_count: int,
    lease_seconds: int = 180,
) -> bool:
    now = timezone.now()
    updated = PipelineRunDispatch.objects.filter(
        pk=dispatch_id,
        status=PipelineRunDispatch.STATUS_CLAIMED,
        claimed_by=str(worker_name or "default")[:120],
        attempt_count=int(attempt_count),
        lease_expires_at__gt=now,
    ).update(
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=max(30, int(lease_seconds))),
    )
    return bool(updated)


@transaction.atomic
def complete_pipeline_dispatch(
    dispatch_id: int,
    *,
    worker_name: str,
    attempt_count: int,
) -> PipelineRunDispatch | None:
    now = timezone.now()
    dispatch = (
        PipelineRunDispatch.objects.select_for_update(of=("self",))
        .select_related("run", "run__pipeline", "run__pipeline__owner", "run__triggered_by")
        .filter(
            pk=dispatch_id,
            status=PipelineRunDispatch.STATUS_CLAIMED,
            claimed_by=str(worker_name or "default")[:120],
            attempt_count=int(attempt_count),
            lease_expires_at__gt=now,
        )
        .first()
    )
    if dispatch is None:
        return None
    dispatch.status = PipelineRunDispatch.STATUS_COMPLETED
    dispatch.completed_at = now
    dispatch.save(update_fields=["status", "completed_at"])
    _record_dispatch_event(dispatch, "pipeline_dispatch_completed", run_status=dispatch.run.status)
    return dispatch


@transaction.atomic
def retry_or_fail_pipeline_dispatch(
    dispatch_id: int,
    *,
    worker_name: str,
    attempt_count: int,
    error: str,
) -> PipelineRunDispatch | None:
    now = timezone.now()
    dispatch = (
        PipelineRunDispatch.objects.select_for_update(of=("self",))
        .select_related("run", "run__pipeline", "run__pipeline__owner", "run__triggered_by")
        .filter(
            pk=dispatch_id,
            status=PipelineRunDispatch.STATUS_CLAIMED,
            claimed_by=str(worker_name or "default")[:120],
            attempt_count=int(attempt_count),
            lease_expires_at__gt=now,
        )
        .first()
    )
    if dispatch is None:
        return None
    dispatch.error = str(error)[:4000]
    dispatch.claimed_by = ""
    dispatch.heartbeat_at = None
    dispatch.lease_expires_at = None
    if dispatch.attempt_count < dispatch.max_attempts:
        dispatch.status = PipelineRunDispatch.STATUS_QUEUED
        dispatch.claimed_at = None
        dispatch.save(update_fields=["status", "claimed_at", "heartbeat_at", "lease_expires_at", "claimed_by", "error"])
        _record_dispatch_event(dispatch, "pipeline_dispatch_retry_queued", error=dispatch.error)
        return dispatch

    dispatch.status = PipelineRunDispatch.STATUS_FAILED
    dispatch.completed_at = now
    dispatch.save(update_fields=["status", "completed_at", "heartbeat_at", "lease_expires_at", "claimed_by", "error"])
    PipelineRun.objects.filter(pk=dispatch.run_id, status__in=_active_run_statuses()).update(
        status=PipelineRun.STATUS_FAILED,
        error=dispatch.error,
        finished_at=now,
    )
    _record_dispatch_event(dispatch, "pipeline_dispatch_failed", error=dispatch.error)
    return dispatch


async def execute_pipeline_dispatch(dispatch_id: int, *, worker_name: str, lease_seconds: int = 180) -> PipelineRun:
    dispatch = await sync_to_async(
        lambda: PipelineRunDispatch.objects.select_related(
            "run", "run__pipeline", "run__pipeline__owner", "run__triggered_by", "run__trigger"
        ).get(pk=dispatch_id),
        thread_sensitive=True,
    )()
    attempt_count = int(dispatch.attempt_count)
    if dispatch.status != PipelineRunDispatch.STATUS_CLAIMED or dispatch.claimed_by != worker_name[:120]:
        raise PipelineDispatchLeaseLost("Pipeline dispatch is not owned by this worker")

    from studio.pipeline.pipeline_executor import PipelineExecutor

    executor = PipelineExecutor(dispatch.run)
    stop_heartbeat = asyncio.Event()
    lease_lost = asyncio.Event()

    async def heartbeat_loop() -> None:
        interval = max(5, int(lease_seconds) // 3)
        while not stop_heartbeat.is_set():
            try:
                await asyncio.wait_for(stop_heartbeat.wait(), timeout=interval)
                break
            except TimeoutError:
                alive = await sync_to_async(heartbeat_pipeline_dispatch, thread_sensitive=True)(
                    dispatch_id,
                    worker_name=worker_name,
                    attempt_count=attempt_count,
                    lease_seconds=lease_seconds,
                )
                if not alive:
                    lease_lost.set()
                    executor.request_stop()
                    break

    heartbeat_task = asyncio.create_task(heartbeat_loop())
    try:
        metadata = dispatch.metadata if isinstance(dispatch.metadata, dict) else {}
        routing_state = dispatch.run.routing_state if isinstance(dispatch.run.routing_state, dict) else {}
        has_checkpoint = bool(dispatch.run.node_states) or bool(routing_state.get("completed_nodes"))
        run = await executor.execute(
            context=dispatch.run.context,
            resume=bool(metadata.get("resume")) or (attempt_count > 1 and has_checkpoint),
            non_idempotent_confirmed=bool(metadata.get("non_idempotent_confirmed")),
        )
        if lease_lost.is_set():
            raise PipelineDispatchLeaseLost("Pipeline dispatch lease was lost during execution")
        completed = await sync_to_async(complete_pipeline_dispatch, thread_sensitive=True)(
            dispatch_id,
            worker_name=worker_name,
            attempt_count=attempt_count,
        )
        if completed is None:
            raise PipelineDispatchLeaseLost("Pipeline dispatch completion was fenced")
        return run
    except PipelineDispatchLeaseLost:
        raise
    except Exception as exc:
        await sync_to_async(retry_or_fail_pipeline_dispatch, thread_sensitive=True)(
            dispatch_id,
            worker_name=worker_name,
            attempt_count=attempt_count,
            error=f"{exc.__class__.__name__}: {exc}",
        )
        raise
    finally:
        stop_heartbeat.set()
        await heartbeat_task


def cancel_pipeline_dispatch_for_run(run_id: int, *, reason: str = "run_stopped") -> int:
    now = timezone.now()
    return PipelineRunDispatch.objects.filter(
        run_id=run_id,
        status__in=[PipelineRunDispatch.STATUS_QUEUED, PipelineRunDispatch.STATUS_CLAIMED],
    ).update(
        status=PipelineRunDispatch.STATUS_CANCELED,
        completed_at=now,
        error=str(reason)[:4000],
    )
