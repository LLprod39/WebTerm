from __future__ import annotations

from app.server_alert_provider import ServerAlertSnapshot
from servers.models import ServerAlert


def get_alert_snapshot(alert_id: int) -> ServerAlertSnapshot | None:
    alert = ServerAlert.objects.select_related("server", "server__user").filter(pk=alert_id).first()
    if alert is None:
        return None
    metadata = alert.metadata if isinstance(alert.metadata, dict) else {}
    return ServerAlertSnapshot(
        alert_id=alert.pk,
        alert_type=str(alert.alert_type or ""),
        severity=str(alert.severity or ""),
        title=str(alert.title or ""),
        message=str(alert.message or ""),
        is_resolved=bool(alert.is_resolved),
        metadata=dict(metadata),
        server_id=alert.server_id,
        server_name=str(alert.server.name or ""),
        server_host=str(alert.server.host or ""),
        server_username=str(alert.server.username or ""),
        server_owner_id=alert.server.user_id,
    )


def get_open_alert_snapshot(alert_id: int) -> ServerAlertSnapshot | None:
    snapshot = get_alert_snapshot(alert_id)
    if snapshot is None or snapshot.is_resolved:
        return None
    return snapshot
