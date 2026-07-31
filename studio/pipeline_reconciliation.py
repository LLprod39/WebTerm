"""Recovery helpers for pipeline runs left active without an execution worker."""

from __future__ import annotations

from datetime import timedelta

from django.apps import apps as django_apps
from django.db.models import Q, QuerySet
from django.utils import timezone

from core_ui.activity import log_user_activity

PipelineRun = django_apps.get_model("studio", "PipelineRun", require_ready=False)


def stale_pipeline_runs(*, stale_seconds: int) -> QuerySet[PipelineRun]:
    if stale_seconds <= 0:
        return PipelineRun.objects.none()
    cutoff = timezone.now() - timedelta(seconds=stale_seconds)
    return PipelineRun.objects.filter(
        Q(status=PipelineRun.STATUS_PENDING, created_at__lt=cutoff)
        | Q(status=PipelineRun.STATUS_RUNNING, started_at__lt=cutoff)
        | Q(status=PipelineRun.STATUS_RUNNING, started_at__isnull=True, created_at__lt=cutoff)
    ).filter(dispatch__isnull=True)


def reconcile_stale_pipeline_runs(*, stale_seconds: int, reason: str = "worker_restart") -> int:
    """Fail stale active runs and append an auditable run-history event."""

    reason_code = str(reason or "worker_restart").strip()[:80] or "worker_restart"
    now = timezone.now()
    candidates = list(
        stale_pipeline_runs(stale_seconds=stale_seconds)
        .select_related("pipeline", "pipeline__owner", "triggered_by")
        .order_by("pk")
    )
    reconciled = 0
    for run in candidates:
        previous_status = run.status
        updated = (
            stale_pipeline_runs(stale_seconds=stale_seconds)
            .filter(pk=run.pk)
            .update(
                status=PipelineRun.STATUS_FAILED,
                error=f"{reason_code}: active pipeline run had no live execution worker.",
                finished_at=now,
            )
        )
        if not updated:
            continue
        reconciled += 1
        actor = run.triggered_by or run.pipeline.owner
        log_user_activity(
            user=actor,
            category="pipeline",
            action="pipeline_run_reconciled",
            status="error",
            description=f"Pipeline run #{run.pk} reconciled after worker restart.",
            entity_type="pipeline_run",
            entity_id=str(run.pk),
            entity_name=run.pipeline.name,
            metadata={
                "reason": reason_code,
                "previous_status": previous_status,
                "status": PipelineRun.STATUS_FAILED,
                "stale_seconds": stale_seconds,
            },
        )
    return reconciled
