from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from servers.models import ServerHealthCheck
from servers.views.server_monitoring import (
    _resolve_display_status,
    _serialize_monitoring_status_item,
)
from tests.servers_api_smoke_harness import create_server, grant_feature

pytestmark = pytest.mark.django_db


class _FakeHC:
    def __init__(
        self,
        *,
        id: int,
        status: str,
        checked_at,
        raw_output=None,
        response_time_ms=None,
        cpu_percent=None,
    ):
        self.id = id
        self.status = status
        self.checked_at = checked_at
        self.raw_output = raw_output or {}
        self.response_time_ms = response_time_ms
        self.cpu_percent = cpu_percent
        self.memory_percent = None
        self.disk_percent = None
        self.load_1m = None


def _status(hc, metrics, *, stale_seconds=300, now=None, full_fail_trust_seconds=90):
    now = now or timezone.now()
    status, _row = _resolve_display_status(
        hc,
        metrics,
        stale_seconds=stale_seconds,
        now=now,
        full_fail_trust_seconds=full_fail_trust_seconds,
    )
    return status


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
    status, row = _resolve_display_status(hc, metrics, stale_seconds=300, now=now, full_fail_trust_seconds=90)
    assert status == ServerHealthCheck.STATUS_WARNING
    assert row is metrics


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
        _status(hc, metrics, now=now)
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
        _status(hc, metrics, now=now)
        == ServerHealthCheck.STATUS_UNREACHABLE
    )


def test_no_checks_is_unknown():
    status, row = _resolve_display_status(None, None, stale_seconds=300, now=timezone.now())
    assert status == "unknown"
    assert row is None


def test_non_unreachable_passthrough_keeps_latest_row():
    now = timezone.now()
    hc = _FakeHC(
        id=5,
        status=ServerHealthCheck.STATUS_CRITICAL,
        checked_at=now,
        raw_output={"lite": True},
        response_time_ms=8,
    )
    metrics = _FakeHC(
        id=4,
        status=ServerHealthCheck.STATUS_HEALTHY,
        checked_at=now - timedelta(seconds=10),
        cpu_percent=10.0,
    )
    status, row = _resolve_display_status(hc, metrics, stale_seconds=300, now=now)
    assert status == ServerHealthCheck.STATUS_CRITICAL
    assert row is hc


def test_same_id_unreachable_does_not_self_override():
    now = timezone.now()
    hc = _FakeHC(
        id=9,
        status=ServerHealthCheck.STATUS_UNREACHABLE,
        checked_at=now,
        raw_output={"error": "ssh"},
        cpu_percent=1.0,
    )
    status, row = _resolve_display_status(hc, hc, stale_seconds=300, now=now)
    assert status == ServerHealthCheck.STATUS_UNREACHABLE
    assert row is hc


def test_metrics_without_checked_at_does_not_override():
    now = timezone.now()
    hc = _FakeHC(
        id=2,
        status=ServerHealthCheck.STATUS_UNREACHABLE,
        checked_at=now,
        raw_output={"lite": True},
    )
    metrics = _FakeHC(
        id=1,
        status=ServerHealthCheck.STATUS_HEALTHY,
        checked_at=None,
    )
    assert _status(hc, metrics, now=now) == ServerHealthCheck.STATUS_UNREACHABLE


def test_serialize_override_aligns_status_fields_with_metrics_row():
    now = timezone.now()
    metrics_at = now - timedelta(seconds=25)
    probe_at = now
    metrics = _FakeHC(
        id=1,
        status=ServerHealthCheck.STATUS_WARNING,
        checked_at=metrics_at,
        response_time_ms=120,
        cpu_percent=77.0,
    )
    probe = _FakeHC(
        id=2,
        status=ServerHealthCheck.STATUS_UNREACHABLE,
        checked_at=probe_at,
        raw_output={"lite": True, "probe": "tcp"},
        response_time_ms=5000,
    )
    server = type("S", (), {"id": 10, "name": "web", "host": "10.0.0.1", "server_type": "ssh"})()
    item = _serialize_monitoring_status_item(server, probe, metrics, now)
    assert item["status"] == ServerHealthCheck.STATUS_WARNING
    assert item["checked_at"] == metrics_at.isoformat()
    assert item["response_time_ms"] == 120
    assert item["is_lite"] is False
    assert item["probe_is_lite"] is True
    assert item["status_from_metrics"] is True
    assert item["cpu_percent"] == 77.0
    assert item["probe_checked_at"] == probe_at.isoformat()


def test_dashboard_and_status_agree_on_lite_unreachable_override():
    user = User.objects.create_user(username="mon-parity", password="x")
    grant_feature(user, "servers")
    server = create_server(user, name="parity-srv", host="10.0.0.9")
    now = timezone.now()
    metrics = ServerHealthCheck.objects.create(
        server=server,
        status=ServerHealthCheck.STATUS_WARNING,
        cpu_percent=65.0,
        memory_percent=40.0,
        disk_percent=50.0,
        response_time_ms=90,
    )
    # auto_now_add: pin timestamps via update so metrics stay "fresh".
    ServerHealthCheck.objects.filter(pk=metrics.pk).update(checked_at=now - timedelta(seconds=20))
    probe = ServerHealthCheck.objects.create(
        server=server,
        status=ServerHealthCheck.STATUS_UNREACHABLE,
        response_time_ms=3000,
        raw_output={"lite": True, "probe": "tcp"},
    )
    ServerHealthCheck.objects.filter(pk=probe.pk).update(checked_at=now)

    client = Client()
    client.force_login(user)
    status_body = client.get("/servers/api/monitoring/status/").json()
    dash_body = client.get("/servers/api/monitoring/dashboard/").json()

    status_item = status_body["servers"][0]
    dash_item = dash_body["servers"][0]
    assert status_item["status"] == ServerHealthCheck.STATUS_WARNING
    assert dash_item["status"] == ServerHealthCheck.STATUS_WARNING
    assert status_body["summary"]["warning"] == 1
    assert dash_body["summary"]["warning"] == 1
    assert status_item["is_lite"] is False
    assert dash_item["is_lite"] is False
    assert status_item["cpu_percent"] == 65.0
    assert dash_item["cpu_percent"] == 65.0
    assert status_body["meta"]["full_fail_metrics_trust_seconds"] == 90
