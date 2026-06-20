from __future__ import annotations

from typing import Protocol


class AdminServerMetricsProvider(Protocol):
    def terminal_summary(self) -> dict: ...

    def server_summary(self) -> dict: ...

    def fleet_summary(self) -> dict: ...

    def active_terminal_count_for_user(self, user_id: int) -> int: ...


_admin_server_metrics_provider: AdminServerMetricsProvider | None = None


def register_admin_server_metrics_provider(provider: AdminServerMetricsProvider | None) -> None:
    """Register server-owned read models for the admin dashboard."""
    global _admin_server_metrics_provider
    _admin_server_metrics_provider = provider


def get_admin_terminal_summary() -> dict:
    if _admin_server_metrics_provider is None:
        return {"active": 0, "connections": []}
    return dict(_admin_server_metrics_provider.terminal_summary())


def get_admin_server_summary() -> dict:
    if _admin_server_metrics_provider is None:
        return {"total": 0, "active": 0}
    return dict(_admin_server_metrics_provider.server_summary())


def get_admin_fleet_summary() -> dict:
    if _admin_server_metrics_provider is None:
        return {
            "fleet_health": {
                "avg_cpu": 0,
                "avg_memory": 0,
                "avg_disk": 0,
                "healthy": 0,
                "warning": 0,
                "critical": 0,
                "unreachable": 0,
            },
            "active_alerts_count": 0,
            "alerts": [],
        }
    return dict(_admin_server_metrics_provider.fleet_summary())


def get_admin_user_active_terminal_count(user_id: int) -> int:
    if _admin_server_metrics_provider is None:
        return 0
    return int(_admin_server_metrics_provider.active_terminal_count_for_user(user_id))
