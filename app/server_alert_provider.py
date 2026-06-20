from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ServerAlertSnapshot:
    alert_id: int
    alert_type: str
    severity: str
    title: str
    message: str
    is_resolved: bool
    metadata: dict[str, Any]
    server_id: int
    server_name: str
    server_host: str
    server_username: str
    server_owner_id: int


class ServerAlertProvider(Protocol):
    def get_alert_snapshot(self, alert_id: int) -> ServerAlertSnapshot | None: ...

    def get_open_alert_snapshot(self, alert_id: int) -> ServerAlertSnapshot | None: ...


_server_alert_provider: ServerAlertProvider | None = None


def register_server_alert_provider(provider: ServerAlertProvider | None) -> None:
    global _server_alert_provider
    _server_alert_provider = provider


def get_alert_snapshot(alert_id: int) -> ServerAlertSnapshot | None:
    if _server_alert_provider is None:
        return None
    return _server_alert_provider.get_alert_snapshot(alert_id)


def get_open_alert_snapshot(alert_id: int) -> ServerAlertSnapshot | None:
    if _server_alert_provider is None:
        return None
    return _server_alert_provider.get_open_alert_snapshot(alert_id)
