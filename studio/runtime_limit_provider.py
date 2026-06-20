from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from app.runtime_limits import ACTIVE_PIPELINE_RUN_STATUSES
from studio.models import PipelineRun


class DjangoPipelineRunLimitProvider:
    def cleanup_stale_runs(self, *, stale_seconds: int) -> int:
        if stale_seconds <= 0:
            return 0

        now = timezone.now()
        cutoff = now - timedelta(seconds=stale_seconds)
        stale_runs = PipelineRun.objects.filter(
            status__in=ACTIVE_PIPELINE_RUN_STATUSES,
        ).filter(
            Q(status=PipelineRun.STATUS_PENDING, created_at__lt=cutoff)
            | Q(status=PipelineRun.STATUS_RUNNING, started_at__lt=cutoff)
            | Q(status=PipelineRun.STATUS_RUNNING, started_at__isnull=True, created_at__lt=cutoff)
        )
        return stale_runs.update(
            status=PipelineRun.STATUS_FAILED,
            error=f"Pipeline run exceeded stale runtime threshold ({stale_seconds} seconds).",
            finished_at=now,
        )

    def active_runs_queryset(self, *, stale_seconds: int, cleanup_stale: bool = True):
        if cleanup_stale:
            self.cleanup_stale_runs(stale_seconds=stale_seconds)
        queryset = PipelineRun.objects.filter(status__in=ACTIVE_PIPELINE_RUN_STATUSES)
        if stale_seconds <= 0:
            return queryset

        cutoff = timezone.now() - timedelta(seconds=stale_seconds)
        return queryset.exclude(
            Q(status=PipelineRun.STATUS_PENDING, created_at__lt=cutoff)
            | Q(status=PipelineRun.STATUS_RUNNING, started_at__lt=cutoff)
            | Q(status=PipelineRun.STATUS_RUNNING, started_at__isnull=True, created_at__lt=cutoff)
        )

    def count_active_runs(
        self,
        *,
        stale_seconds: int,
        owner_id: int | None = None,
        cleanup_stale: bool = True,
    ) -> int:
        queryset = self.active_runs_queryset(stale_seconds=stale_seconds, cleanup_stale=cleanup_stale)
        if owner_id is not None:
            queryset = queryset.filter(pipeline__owner_id=owner_id)
        return queryset.count()
