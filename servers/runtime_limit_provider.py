from __future__ import annotations

from datetime import timedelta

from django.db import DataError
from django.utils import timezone

from app.runtime_limits import ACTIVE_AGENT_RUN_STATUSES, ACTIVE_TERMINAL_CONNECTION_STATUSES
from servers.models import AgentRun, ServerConnection

LEGACY_INTEGER_MAX_MS = 2_147_483_647


def _save_failed_stale_agent_run(run: AgentRun, *, update_fields: list[str]) -> None:
    try:
        run.save(update_fields=update_fields)
    except DataError as exc:
        if "integer out of range" not in str(exc).lower() or "duration_ms" not in update_fields:
            raise
        run.duration_ms = min(max(0, int(run.duration_ms or 0)), LEGACY_INTEGER_MAX_MS)
        run.save(update_fields=update_fields)


class DjangoAgentRunLimitProvider:
    def cleanup_stale_runs(self, *, stale_seconds: int) -> int:
        if stale_seconds <= 0:
            return 0

        from servers.agent_dispatch import cancel_agent_dispatches_for_run
        from servers.agent_run_report import refresh_agent_run_report_payload
        from servers.run_events import record_run_event

        now = timezone.now()
        cutoff = now - timedelta(seconds=stale_seconds)
        stale_runs = list(
            AgentRun.objects.filter(
                status__in=ACTIVE_AGENT_RUN_STATUSES,
                started_at__lt=cutoff,
                completed_at__isnull=True,
            ).select_related("agent", "server")[:200]
        )
        for run in stale_runs:
            message = f"Agent run exceeded stale runtime threshold ({stale_seconds}s) and was marked failed."
            record_run_event(
                run.id,
                "agent_stale_failed",
                {
                    "stale_seconds": int(stale_seconds),
                    "started_at": run.started_at.isoformat() if run.started_at else None,
                    "message": message,
                    "severity": "critical",
                },
            )
            cancel_agent_dispatches_for_run(run.id, reason="stale_agent_run")
            run.status = AgentRun.STATUS_FAILED
            run.ai_analysis = message
            run.completed_at = now
            if run.started_at:
                run.duration_ms = max(0, int((now - run.started_at).total_seconds() * 1000))
            _save_failed_stale_agent_run(run, update_fields=["status", "ai_analysis", "completed_at", "duration_ms"])
            refresh_agent_run_report_payload(run)
        return len(stale_runs)

    def count_active_runs(self, *, user_id: int | None = None) -> int:
        queryset = AgentRun.objects.filter(status__in=ACTIVE_AGENT_RUN_STATUSES)
        if user_id is not None:
            queryset = queryset.filter(user_id=user_id)
        return queryset.count()


class DjangoTerminalSessionLimitProvider:
    def cleanup_stale_sessions(self, *, stale_seconds: int) -> int:
        if stale_seconds <= 0:
            return 0

        now = timezone.now()
        cutoff = now - timedelta(seconds=stale_seconds)
        return ServerConnection.objects.filter(
            status__in=ACTIVE_TERMINAL_CONNECTION_STATUSES,
            disconnected_at__isnull=True,
            last_seen_at__lt=cutoff,
        ).update(
            status="disconnected",
            disconnected_at=now,
        )

    def active_connections_queryset(self, *, stale_seconds: int):
        queryset = ServerConnection.objects.filter(
            status__in=ACTIVE_TERMINAL_CONNECTION_STATUSES,
            disconnected_at__isnull=True,
        )
        if stale_seconds <= 0:
            return queryset

        cutoff = timezone.now() - timedelta(seconds=stale_seconds)
        return queryset.filter(last_seen_at__gte=cutoff)

    def count_active_connections(self, *, stale_seconds: int, user_id: int | None = None) -> int:
        queryset = self.active_connections_queryset(stale_seconds=stale_seconds)
        if user_id is not None:
            queryset = queryset.filter(user_id=user_id)
        return queryset.count()
