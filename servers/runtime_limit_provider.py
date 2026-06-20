from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from app.runtime_limits import ACTIVE_AGENT_RUN_STATUSES, ACTIVE_TERMINAL_CONNECTION_STATUSES
from servers.models import AgentRun, ServerConnection


class DjangoAgentRunLimitProvider:
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
