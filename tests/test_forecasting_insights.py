"""Tests for deterministic forecasting and the admin insights API."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from servers.models import (
    Server,
    ServerAlert,
    ServerCertificate,
    ServerMetricRollup,
    ServerMetricSample,
)
from servers.monitoring.forecasting import build_server_predictions, eta_days_to, theil_sen


def test_theil_sen_recovers_linear_slope():
    points = [(float(x), 2.0 * x + 1.0) for x in range(10)]
    fit = theil_sen(points)
    assert fit is not None
    assert fit["slope"] == pytest.approx(2.0)
    assert fit["intercept"] == pytest.approx(1.0)
    assert fit["consistency"] == 1.0


def test_theil_sen_robust_to_outlier():
    points = [(float(x), float(x)) for x in range(12)]
    points[5] = (5.0, 500.0)
    fit = theil_sen(points)
    assert fit is not None
    assert fit["slope"] == pytest.approx(1.0, abs=0.2)


def test_eta_days_to():
    assert eta_days_to(70.0, 90.0, 10.0) == pytest.approx(2.0)
    assert eta_days_to(70.0, 90.0, 0.0) is None
    assert eta_days_to(95.0, 90.0, 10.0) is None


def _make_server(username: str = "insights-owner", *, staff: bool = False) -> Server:
    owner = User.objects.create_user(username=username, password="x", is_staff=staff)
    return Server.objects.create(
        user=owner,
        name=f"srv-{username}",
        host="10.0.0.42",
        username="root",
        server_type="ssh",
        is_active=True,
    )


def _seed_hourly(server: Server, metric_key: str, values: list[float], now) -> None:
    rows = []
    for index, value in enumerate(values):
        bucket = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=len(values) - index)
        rows.append(
            ServerMetricRollup(
                server=server,
                metric_key=metric_key,
                granularity=ServerMetricRollup.GRANULARITY_HOUR,
                bucket_start=bucket,
                value_min=value,
                value_avg=value,
                value_max=value,
                value_last=value,
                sample_count=6,
            )
        )
    ServerMetricRollup.objects.bulk_create(rows)


@pytest.mark.django_db
def test_disk_full_prediction_from_rising_series():
    server = _make_server("forecast-disk")
    now = timezone.now()
    ServerMetricSample.objects.create(
        server=server,
        disk_mounts=[{"mount": "/data", "percent": 73.5, "used_gb": 700.0, "total_gb": 1000.0}],
        memory_total_mb=8000,
    )
    # +0.5%/hour over 48h → 12%/day; from 73.5% ETA to 90% ≈ 1.4 days → critical.
    _seed_hourly(server, "disk./data.percent", [50.0 + i * 0.5 for i in range(48)], now)

    predictions = build_server_predictions(server, now=now)
    disk = next(item for item in predictions if item["kind"] == "disk_full")
    assert disk["target"] == "disk:/data"
    assert disk["severity"] == "critical"
    assert disk["threshold"] == 90.0
    assert disk["eta_days"] == pytest.approx(1.4, abs=0.3)
    assert disk["slope_per_day"] == pytest.approx(12.0, abs=0.5)
    assert disk["confidence"] >= 0.9


@pytest.mark.django_db
def test_flat_series_produces_no_disk_prediction():
    server = _make_server("forecast-flat")
    now = timezone.now()
    ServerMetricSample.objects.create(
        server=server,
        disk_mounts=[{"mount": "/", "percent": 55.0}],
    )
    _seed_hourly(server, "disk./.percent", [55.0] * 48, now)

    predictions = build_server_predictions(server, now=now)
    assert not [item for item in predictions if item["kind"] == "disk_full"]


@pytest.mark.django_db
def test_certificate_predictions_expiry_and_change():
    server = _make_server("forecast-cert")
    now = timezone.now()
    ServerCertificate.objects.create(
        server=server,
        port=443,
        endpoint="10.0.0.42:443",
        subject="CN = api",
        not_after=now + timedelta(days=5),
        fingerprint_sha256="AA",
        is_active=True,
    )
    ServerCertificate.objects.create(
        server=server,
        port=8443,
        endpoint="10.0.0.42:8443",
        subject="CN = internal",
        not_after=now + timedelta(days=300),
        fingerprint_sha256="BB",
        previous_fingerprint="OLD",
        fingerprint_changed_at=now - timedelta(days=2),
        is_active=True,
    )

    predictions = build_server_predictions(server, now=now)
    expiry = next(item for item in predictions if item["kind"] == "cert_expiry")
    assert expiry["target"] == "cert:443"
    assert expiry["severity"] == "critical"
    assert expiry["eta_days"] == pytest.approx(5.0, abs=0.1)
    # The 300-day cert is outside the 60-day horizon — only the change is reported.
    changed = next(item for item in predictions if item["kind"] == "cert_changed")
    assert changed["target"] == "cert:8443"
    assert changed["severity"] == "info"


@pytest.mark.django_db
def test_memory_prediction_from_monotone_decline():
    server = _make_server("forecast-mem")
    now = timezone.now()
    ServerMetricSample.objects.create(server=server, memory_total_mb=16000, memory_available_mb=3000)
    # Steady -420 MB/day over 3 days — consistency 1.0 passes the gate.
    _seed_hourly(server, "mem.available_mb", [4310 - i * 17.5 for i in range(74)], now)

    predictions = build_server_predictions(server, now=now)
    memory = next(item for item in predictions if item["kind"] == "memory_pressure")
    assert memory["severity"] == "warning"
    assert memory["eta_days"] == pytest.approx(5.4, abs=0.8)
    assert memory["confidence"] >= 0.75


@pytest.mark.django_db
def test_admin_insights_dedupes_predictions_for_mirrored_endpoint(client):
    cache.clear()
    now = timezone.now()
    owner_a = User.objects.create_user(username="mirror-owner-a", password="x")
    owner_b = User.objects.create_user(username="mirror-owner-b", password="x")
    server_a = Server.objects.create(
        user=owner_a, name="mirror-a", host="10.0.0.60", username="root", server_type="ssh", is_active=True
    )
    server_b = Server.objects.create(
        user=owner_b, name="mirror-b", host="10.0.0.60", username="ubuntu", server_type="ssh", is_active=True
    )
    for server in (server_a, server_b):
        ServerMetricSample.objects.create(server=server, disk_mounts=[{"mount": "/", "percent": 73.5}])
        _seed_hourly(server, "disk./.percent", [50.0 + i * 0.5 for i in range(48)], now)

    staff = User.objects.create_user(username="staff-mirror", password="x", is_staff=True)
    client.force_login(staff)
    payload = client.get(reverse("servers:admin_insights") + "?refresh=1").json()

    flat_disk = [item for item in payload["predictions"] if item["kind"] == "disk_full"]
    assert len(flat_disk) == 1
    # Per-server entries keep their own prediction lists for the fleet table.
    by_name = {entry["name"]: entry for entry in payload["servers"]}
    assert any(item["kind"] == "disk_full" for item in by_name["mirror-a"]["predictions"])
    assert any(item["kind"] == "disk_full" for item in by_name["mirror-b"]["predictions"])


@pytest.mark.django_db
def test_admin_insights_requires_staff(client):
    _make_server("insights-plain")
    plain = User.objects.create_user(username="plain-user", password="x")
    client.force_login(plain)
    response = client.get(reverse("servers:admin_insights"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_insights_payload(client):
    cache.clear()
    server = _make_server("insights-data")
    now = timezone.now()
    ServerMetricSample.objects.create(
        server=server,
        cpu_percent=41.5,
        cpu_iowait_percent=3.0,
        cpu_count=4,
        memory_percent=62.0,
        memory_total_mb=8000,
        memory_available_mb=3000,
        swap_percent=10.0,
        disk_mounts=[{"mount": "/", "percent": 73.5, "used_gb": 70.0, "total_gb": 100.0}],
        zombie_count=1,
        journal_err_10m=2,
        reboot_required=True,
    )
    _seed_hourly(server, "cpu.percent", [40.0 + (i % 3) for i in range(24)], now)
    _seed_hourly(server, "disk./.percent", [50.0 + i * 0.5 for i in range(48)], now)
    ServerCertificate.objects.create(
        server=server,
        port=443,
        endpoint="10.0.0.42:443",
        subject="CN = api",
        not_after=now + timedelta(days=20),
        fingerprint_sha256="AA",
        is_active=True,
    )
    ServerAlert.objects.create(
        server=server,
        alert_type=ServerAlert.TYPE_DISK,
        severity=ServerAlert.SEVERITY_WARNING,
        title="Disk 73%",
    )

    staff = User.objects.create_user(username="staff-user", password="x", is_staff=True)
    client.force_login(staff)
    response = client.get(reverse("servers:admin_insights") + "?refresh=1")
    assert response.status_code == 200
    payload = response.json()

    assert payload["success"] is True
    assert payload["summary"]["servers_total"] == 1
    assert payload["summary"]["active_alerts"] == 1
    assert payload["summary"]["certificates_total"] == 1
    assert payload["summary"]["certificates_expiring_30d"] == 1
    assert payload["summary"]["predictions_total"] >= 2  # disk_full + cert_expiry

    assert 5 <= payload["summary"]["fleet_health_score"] <= 100
    assert payload["summary"]["fleet_health_worst"] <= payload["summary"]["fleet_health_score"]

    entry = payload["servers"][0]
    # Unknown status + critical disk forecast + warning alert + expiring cert eat points.
    assert 5 <= entry["health_score"] < 80
    assert entry["cpu_percent"] == 41.5
    assert entry["worst_disk"]["mount"] == "/"
    assert entry["reboot_required"] is True
    assert entry["zombie_count"] == 1
    # Bucket floor vs. `now - 24h` can trim one boundary point.
    assert len(entry["spark"]["cpu"]) >= 20
    assert entry["has_extended_metrics"] is True

    kinds = {item["kind"] for item in payload["predictions"]}
    assert "disk_full" in kinds
    assert "cert_expiry" in kinds
    assert payload["certificates"][0]["days_left"] == pytest.approx(20.0, abs=0.2)
    assert payload["alerts"][0]["title"] == "Disk 73%"
