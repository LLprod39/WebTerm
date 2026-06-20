from __future__ import annotations

from app.server_alert_provider import ServerAlertSnapshot
from servers.services.alert_query import get_alert_snapshot, get_open_alert_snapshot


class DjangoServerAlertProvider:
    def get_alert_snapshot(self, alert_id: int) -> ServerAlertSnapshot | None:
        return get_alert_snapshot(alert_id)

    def get_open_alert_snapshot(self, alert_id: int) -> ServerAlertSnapshot | None:
        return get_open_alert_snapshot(alert_id)
