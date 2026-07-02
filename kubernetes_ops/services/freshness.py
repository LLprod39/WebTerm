from __future__ import annotations

from datetime import datetime
from typing import Any

from django.conf import settings
from django.utils import timezone


def kubernetes_stale_after_seconds() -> int:
    value = int(getattr(settings, "KUBERNETES_OPS_STALE_AFTER_SECONDS", 900) or 900)
    return max(60, value)


def sync_freshness(
    last_sync_at: datetime | None,
    *,
    last_error: str = "",
    enabled: bool = True,
) -> dict[str, Any]:
    stale_after = kubernetes_stale_after_seconds()
    if not enabled:
        return {
            "sync_status": "disabled",
            "is_stale": False,
            "sync_age_seconds": None,
            "sync_stale_after_seconds": stale_after,
        }
    if not last_sync_at:
        return {
            "sync_status": "missing",
            "is_stale": True,
            "sync_age_seconds": None,
            "sync_stale_after_seconds": stale_after,
        }

    synced_at = last_sync_at
    if timezone.is_naive(synced_at):
        synced_at = timezone.make_aware(synced_at, timezone.get_current_timezone())
    age = max(0, int((timezone.now() - synced_at).total_seconds()))
    status = "error" if last_error else ("stale" if age > stale_after else "fresh")
    return {
        "sync_status": status,
        "is_stale": status in {"error", "stale"},
        "sync_age_seconds": age,
        "sync_stale_after_seconds": stale_after,
    }

