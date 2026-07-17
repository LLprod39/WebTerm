"""Tests for forecast persistence, forecast alerts, and alert dedup fixes."""

from __future__ import annotations

from datetime import timedelta

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.utils import timezone

from servers.forecast_persistence import (
    alert_title_for,
    persist_predictions_for_server,
    run_forecast_persistence,
    sync_forecast_alerts,
)
from servers.models import (
    Server,
    ServerAlert,
    ServerMetricRollup,
    ServerMetricSample,
    ServerPrediction,
)
from servers.monitor_alerts import _create_alerts
from servers.watcher_service import WatcherService

pytestmark = pytest.mark.django_db


def _make_server(username: str, host: str = "10.0.7.1") -> Server:
    owner = User.objects.create_user(username=username, password="x")
    return Server.objects.create(
        user=owner, name=f"srv-{username}", host=host, username="root", server_type="ssh", is_active=True
    )


def _disk_prediction(eta: float = 1.5, severity: str = "critical") -> dict:
    return {
        "kind": "disk_full",
        "target": "disk:/var",
        "severity": severity,
        "eta_days": eta,
        "predicted_for": (timezone.now() + timedelta(days=eta)).isoformat(),
        "current_value": 84.0,
        "threshold": 90.0,
        "unit": "%",
        "slope_per_day": 4.0,
        "confidence": 0.95,
        "evidence": {"mount": "/var"},
    }


def test_persist_upsert_resolve_and_reactivate():
    server = _make_server("persist")
    now = timezone.now()

    summary = persist_predictions_for_server(server, [_disk_prediction()], now=now)
    assert summary == {"created": 1, "updated": 0, "resolved": 0}
    row = ServerPrediction.objects.get(server=server)
    assert row.status == ServerPrediction.STATUS_ACTIVE
    assert row.severity == "critical"

    # Same forecast again -> update in place, still one row.
    summary = persist_predictions_for_server(server, [_disk_prediction(eta=1.2)], now=now)
    assert summary == {"created": 0, "updated": 1, "resolved": 0}
    assert ServerPrediction.objects.filter(server=server).count() == 1

    # Forecast disappears -> resolved.
    summary = persist_predictions_for_server(server, [], now=now)
    assert summary == {"created": 0, "updated": 0, "resolved": 1}
    row.refresh_from_db()
    assert row.status == ServerPrediction.STATUS_RESOLVED
    assert row.resolved_at is not None

    # Comes back -> the same row re-activates.
    persist_predictions_for_server(server, [_disk_prediction()], now=now)
    row.refresh_from_db()
    assert row.status == ServerPrediction.STATUS_ACTIVE
    assert row.resolved_at is None
    assert ServerPrediction.objects.filter(server=server).count() == 1


def test_forecast_alerts_lifecycle_no_duplicates():
    server = _make_server("fc-alerts")
    now = timezone.now()

    sync_forecast_alerts(server, [_disk_prediction()], now=now)
    assert ServerAlert.objects.filter(server=server, alert_type="forecast").count() == 1
    alert = ServerAlert.objects.get(server=server)
    assert "диск /var" in alert.title
    assert alert.severity == "critical"

    # Re-sync: update in place, no new rows even much later.
    sync_forecast_alerts(server, [_disk_prediction(eta=1.0, severity="warning")], now=now + timedelta(hours=2))
    assert ServerAlert.objects.filter(server=server, alert_type="forecast").count() == 1
    alert.refresh_from_db()
    assert alert.severity == "warning"
    assert "~1.0 дн" in alert.title

    # Forecast gone -> alert auto-resolves.
    sync_forecast_alerts(server, [], now=now + timedelta(hours=3))
    alert.refresh_from_db()
    assert alert.is_resolved is True

    # Info-severity forecasts never alert.
    sync_forecast_alerts(server, [_disk_prediction(severity="info")], now=now)
    assert ServerAlert.objects.filter(server=server, is_resolved=False).count() == 0


def test_alert_titles_cover_kinds():
    assert "inode" in alert_title_for({"kind": "inode_full", "target": "inode:/", "evidence": {"mount": "/"}})
    assert "истёк" in alert_title_for(
        {"kind": "cert_expiry", "target": "cert:443", "evidence": {"port": 443, "expired": True}}
    )
    assert "память" in alert_title_for({"kind": "memory_pressure", "target": "memory", "eta_days": 3.0}).lower()


@pytest.mark.django_db(transaction=True)
def test_monitor_alerts_update_in_place_instead_of_duplicating():
    """The old 15-minute window recreated unresolved alerts forever."""
    server = _make_server("dedup")
    metrics = {"cpu_percent": 10.0, "memory_percent": 10.0, "disk_percent": 10.0}
    deep = {"failed_services": [], "log_errors": ["ERROR boom"], "kernel_errors": []}

    async_to_sync(_create_alerts)(server, metrics, deep)
    assert ServerAlert.objects.filter(server=server, alert_type="log_error").count() == 1
    first = ServerAlert.objects.get(server=server, alert_type="log_error")

    # Simulate the next deep cycle 20+ minutes later: same problem, more lines.
    ServerAlert.objects.filter(id=first.id).update(created_at=timezone.now() - timedelta(minutes=25))
    deep2 = {"failed_services": [], "log_errors": ["ERROR boom", "ERROR again"], "kernel_errors": []}
    async_to_sync(_create_alerts)(server, metrics, deep2)

    rows = ServerAlert.objects.filter(server=server, alert_type="log_error")
    assert rows.count() == 1  # updated, not duplicated
    assert "2" in rows.first().title

    # Once resolved, a recurring problem creates a fresh alert.
    rows.update(is_resolved=True)
    async_to_sync(_create_alerts)(server, metrics, deep2)
    assert ServerAlert.objects.filter(server=server, alert_type="log_error").count() == 2


def test_run_forecast_persistence_end_to_end():
    server = _make_server("fc-run")
    now = timezone.now()
    ServerMetricSample.objects.create(server=server, disk_mounts=[{"mount": "/", "percent": 73.5}])
    rows = []
    floor = now.replace(minute=0, second=0, microsecond=0)
    for index, value in enumerate([50.0 + i * 0.5 for i in range(48)]):
        rows.append(
            ServerMetricRollup(
                server=server, metric_key="disk./.percent", granularity="hour",
                bucket_start=floor - timedelta(hours=48 - index),
                value_min=value, value_avg=value, value_max=value, value_last=value, sample_count=6,
            )
        )
    ServerMetricRollup.objects.bulk_create(rows)

    totals = run_forecast_persistence(now=now)
    assert totals["servers"] >= 1
    assert ServerPrediction.objects.filter(server=server, status="active", kind="disk_full").exists()
    assert ServerAlert.objects.filter(server=server, alert_type="forecast", is_resolved=False).exists()


def test_watcher_includes_active_predictions():
    server = _make_server("fc-watch")
    ServerPrediction.objects.create(
        server=server,
        kind="disk_full",
        target="disk:/var",
        severity="critical",
        status=ServerPrediction.STATUS_ACTIVE,
        eta_days=1.4,
        last_seen_at=timezone.now(),
    )

    payload = WatcherService().scan_queryset(Server.objects.filter(id=server.id))
    assert payload["summary"]["drafts"] == 1
    draft = payload["drafts"][0]
    assert draft["severity"] == "critical"
    assert any("Прогноз" in reason for reason in draft["reasons"])
    assert "диск" in draft["objective"].lower()
    assert draft["recommended_role"] == "infra_scout"
