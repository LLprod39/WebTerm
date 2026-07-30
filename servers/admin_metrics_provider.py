from __future__ import annotations

import logging
from datetime import timedelta

from django.db.models import Avg, Count, F, Max, Min, Q
from django.utils import timezone

from servers.models import (
    AgentRunDispatch,
    BackgroundWorkerState,
    PlaybookRunDispatch,
    Server,
    ServerAlert,
    ServerConnection,
    ServerHealthCheck,
)

logger = logging.getLogger(__name__)


def _queue_snapshot(model, *, queue_id: str, label: str, now, exhausted_filter: Q | None = None) -> dict:
    active_statuses = [model.STATUS_QUEUED, model.STATUS_CLAIMED]
    since = now - timedelta(hours=24)
    aggregates = model.objects.aggregate(
        depth=Count("id", filter=Q(status=model.STATUS_QUEUED)),
        in_flight=Count("id", filter=Q(status=model.STATUS_CLAIMED)),
        lease_expired=Count(
            "id",
            filter=Q(status=model.STATUS_CLAIMED) & (Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now)),
        ),
        retrying=Count("id", filter=Q(status__in=active_statuses, attempt_count__gt=1)),
        retried_24h=Count(
            "id",
            filter=Q(attempt_count__gt=1) & (Q(status__in=active_statuses) | Q(completed_at__gte=since)),
        ),
        oldest_queued_at=Min("queued_at", filter=Q(status=model.STATUS_QUEUED)),
        attempts_exhausted_24h=Count(
            "id",
            filter=(exhausted_filter or Q(pk__in=[])) & Q(completed_at__gte=since),
        ),
    )
    oldest = aggregates.pop("oldest_queued_at")
    return {
        "id": queue_id,
        "label": label,
        **{key: int(value or 0) for key, value in aggregates.items()},
        "oldest_queued_seconds": max(0, int((now - oldest).total_seconds())) if oldest else 0,
    }


class DjangoAdminServerMetricsProvider:
    """Server-domain read models for the core admin dashboard."""

    def terminal_summary(self) -> dict:
        active_connections = ServerConnection.objects.filter(status="connected").select_related("server", "user")
        connections = [
            {
                "server": conn.server.name,
                "user": conn.user.username if conn.user_id else "unknown",
                "connected_at": conn.connected_at.isoformat(),
            }
            for conn in active_connections
        ]
        return {"active": active_connections.count(), "connections": connections}

    def server_summary(self) -> dict:
        return {"total": Server.objects.count(), "active": Server.objects.filter(is_active=True).count()}

    def fleet_summary(self) -> dict:
        fleet_health = {
            "avg_cpu": 0,
            "avg_memory": 0,
            "avg_disk": 0,
            "healthy": 0,
            "warning": 0,
            "critical": 0,
            "unreachable": 0,
        }
        try:
            latest_per_server = ServerHealthCheck.objects.values("server_id").annotate(last_id=Max("id"))
            latest_ids = [row["last_id"] for row in latest_per_server]
            if latest_ids:
                agg = ServerHealthCheck.objects.filter(id__in=latest_ids).aggregate(
                    avg_cpu=Avg("cpu_percent"),
                    avg_mem=Avg("memory_percent"),
                    avg_disk=Avg("disk_percent"),
                )
                fleet_health["avg_cpu"] = round(agg["avg_cpu"] or 0, 1)
                fleet_health["avg_memory"] = round(agg["avg_mem"] or 0, 1)
                fleet_health["avg_disk"] = round(agg["avg_disk"] or 0, 1)
                for status in ServerHealthCheck.objects.filter(id__in=latest_ids).values_list("status", flat=True):
                    fleet_health[status] = fleet_health.get(status, 0) + 1
        except Exception:
            logger.debug("fleet health aggregation unavailable", exc_info=True)

        recent_alerts = list(
            ServerAlert.objects.filter(is_resolved=False).select_related("server").order_by("-created_at")[:10]
        )
        alerts = [
            {
                "server": alert.server.name,
                "type": alert.alert_type,
                "severity": alert.severity,
                "title": alert.title,
                "time": alert.created_at.isoformat(),
            }
            for alert in recent_alerts
        ]
        return {
            "fleet_health": fleet_health,
            "active_alerts_count": ServerAlert.objects.filter(is_resolved=False).count(),
            "alerts": alerts,
        }

    def execution_queue_summary(self) -> dict:
        now = timezone.now()
        queues = [
            _queue_snapshot(
                AgentRunDispatch,
                queue_id="agents",
                label="Agent runs",
                now=now,
                exhausted_filter=Q(
                    status=AgentRunDispatch.STATUS_FAILED,
                    attempt_count__gte=F("max_attempts"),
                ),
            ),
            _queue_snapshot(
                PlaybookRunDispatch,
                queue_id="playbooks",
                label="Playbook runs",
                now=now,
            ),
        ]
        stale_workers = BackgroundWorkerState.objects.filter(status=BackgroundWorkerState.STATUS_RUNNING).filter(
            Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now)
        )
        return {
            "observed_at": now.isoformat(),
            **{
                key: sum(queue[key] for queue in queues)
                for key in (
                    "depth",
                    "in_flight",
                    "lease_expired",
                    "retrying",
                    "retried_24h",
                    "attempts_exhausted_24h",
                )
            },
            "stale_workers": stale_workers.count(),
            "oldest_queued_seconds": max((queue["oldest_queued_seconds"] for queue in queues), default=0),
            "queues": queues,
        }

    def active_terminal_count_for_user(self, user_id: int) -> int:
        return ServerConnection.objects.filter(user_id=user_id, status="connected").count()
