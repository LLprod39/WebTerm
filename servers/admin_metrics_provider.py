from __future__ import annotations

from django.db.models import Avg, Max

from servers.models import Server, ServerAlert, ServerConnection, ServerHealthCheck


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
            pass

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

    def active_terminal_count_for_user(self, user_id: int) -> int:
        return ServerConnection.objects.filter(user_id=user_id, status="connected").count()
