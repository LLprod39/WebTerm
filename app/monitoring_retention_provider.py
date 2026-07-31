"""Dependency-inversion hook for monitoring retention owned by ``servers``."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

MonitoringRetentionProvider = Callable[..., dict[str, int]]

_provider: MonitoringRetentionProvider | None = None


def register_monitoring_retention_provider(provider: MonitoringRetentionProvider | None) -> None:
    global _provider
    _provider = provider


def cleanup_monitoring_metric_data(*, now: datetime, dry_run: bool) -> dict[str, int]:
    if _provider is None:
        return {"samples": 0, "hour_rollups": 0, "day_rollups": 0, "ai_insights": 0}
    return _provider(now=now, dry_run=dry_run)
