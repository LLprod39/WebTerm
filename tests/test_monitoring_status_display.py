from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from servers.models import ServerHealthCheck
from servers.views.server_monitoring import _resolve_display_status

pytestmark = pytest.mark.django_db


class _FakeHC:
    def __init__(self, *, id: int, status: str, checked_at, raw_output=None):
        self.id = id
        self.status = status
        self.checked_at = checked_at
        self.raw_output = raw_output or {}


def test_lite_unreachable_defers_to_fresh_metrics_status():
    now = timezone.now()
    hc = _FakeHC(
        id=2,
        status=ServerHealthCheck.STATUS_UNREACHABLE,
        checked_at=now,
        raw_output={"lite": True, "probe": "tcp"},
    )
    metrics = _FakeHC(
        id=1,
        status=ServerHealthCheck.STATUS_WARNING,
        checked_at=now - timedelta(seconds=30),
    )
    assert (
        _resolve_display_status(hc, metrics, stale_seconds=300, now=now)
        == ServerHealthCheck.STATUS_WARNING
    )


def test_full_unreachable_with_very_fresh_metrics_still_prefers_metrics():
    now = timezone.now()
    hc = _FakeHC(
        id=2,
        status=ServerHealthCheck.STATUS_UNREACHABLE,
        checked_at=now,
        raw_output={"error": "ssh timeout"},
    )
    metrics = _FakeHC(
        id=1,
        status=ServerHealthCheck.STATUS_HEALTHY,
        checked_at=now - timedelta(seconds=20),
    )
    assert (
        _resolve_display_status(hc, metrics, stale_seconds=300, now=now)
        == ServerHealthCheck.STATUS_HEALTHY
    )


def test_full_unreachable_with_old_metrics_stays_unreachable():
    now = timezone.now()
    hc = _FakeHC(
        id=2,
        status=ServerHealthCheck.STATUS_UNREACHABLE,
        checked_at=now,
        raw_output={"error": "ssh timeout"},
    )
    metrics = _FakeHC(
        id=1,
        status=ServerHealthCheck.STATUS_HEALTHY,
        checked_at=now - timedelta(seconds=200),
    )
    assert (
        _resolve_display_status(hc, metrics, stale_seconds=300, now=now)
        == ServerHealthCheck.STATUS_UNREACHABLE
    )


def test_no_checks_is_unknown():
    assert _resolve_display_status(None, None, stale_seconds=300, now=timezone.now()) == "unknown"
