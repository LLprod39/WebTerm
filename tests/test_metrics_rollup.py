"""Tests for metric rollups, retention, and sample mirroring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from servers.models import Server, ServerMetricRollup, ServerMetricSample
from servers.monitoring.metrics_rollup import (
    bucket_start_for,
    cleanup_metric_data,
    compute_day_rollups,
    compute_hour_rollups,
    fetch_metric_series,
    run_metric_rollups,
)
from servers.monitoring.monitor_metrics import create_metric_sample, mirror_metric_sample

pytestmark = pytest.mark.django_db


def _make_server(username: str, host: str = "10.0.0.10") -> Server:
    owner = User.objects.create_user(username=username, password="x")
    return Server.objects.create(
        user=owner,
        name=f"srv-{username}",
        host=host,
        username="root",
        server_type="ssh",
        is_active=True,
    )


def _make_sample(server: Server, collected_at: datetime, **fields) -> ServerMetricSample:
    sample = ServerMetricSample.objects.create(server=server, **fields)
    ServerMetricSample.objects.filter(id=sample.id).update(collected_at=collected_at)
    sample.refresh_from_db()
    return sample


def test_hour_rollups_aggregate_scalars_and_mounts():
    server = _make_server("rollup-hour")
    base = datetime(2026, 7, 16, 10, 0, tzinfo=UTC)
    _make_sample(
        server,
        base + timedelta(minutes=5),
        cpu_percent=20.0,
        disk_mounts=[{"mount": "/", "percent": 50.0, "used_gb": 10.0, "inode_percent": 5.0}],
    )
    _make_sample(
        server,
        base + timedelta(minutes=25),
        cpu_percent=40.0,
        disk_mounts=[{"mount": "/", "percent": 60.0, "used_gb": 12.0, "inode_percent": 6.0}],
    )

    written = compute_hour_rollups(now=base + timedelta(minutes=59))
    assert written > 0

    cpu = ServerMetricRollup.objects.get(server=server, metric_key="cpu.percent", granularity="hour", bucket_start=base)
    assert cpu.value_min == 20.0
    assert cpu.value_max == 40.0
    assert cpu.value_avg == 30.0
    assert cpu.value_last == 40.0
    assert cpu.sample_count == 2

    disk = ServerMetricRollup.objects.get(
        server=server, metric_key="disk./.percent", granularity="hour", bucket_start=base
    )
    assert disk.value_avg == 55.0
    used = ServerMetricRollup.objects.get(
        server=server, metric_key="disk./.used_gb", granularity="hour", bucket_start=base
    )
    assert used.value_last == 12.0


def test_hour_rollups_are_idempotent():
    server = _make_server("rollup-idem")
    base = datetime(2026, 7, 16, 10, 0, tzinfo=UTC)
    _make_sample(server, base + timedelta(minutes=5), cpu_percent=30.0)

    now = base + timedelta(minutes=30)
    compute_hour_rollups(now=now)
    first_count = ServerMetricRollup.objects.filter(server=server).count()
    compute_hour_rollups(now=now)
    assert ServerMetricRollup.objects.filter(server=server).count() == first_count

    row = ServerMetricRollup.objects.get(server=server, metric_key="cpu.percent", granularity="hour")
    assert row.value_avg == 30.0
    assert row.sample_count == 1


def test_day_rollups_weight_by_sample_count():
    server = _make_server("rollup-day")
    day = datetime(2026, 7, 16, 0, 0, tzinfo=UTC)
    ServerMetricRollup.objects.create(
        server=server,
        metric_key="cpu.percent",
        granularity="hour",
        bucket_start=day + timedelta(hours=10),
        value_min=20.0,
        value_avg=30.0,
        value_max=40.0,
        value_last=40.0,
        sample_count=2,
    )
    ServerMetricRollup.objects.create(
        server=server,
        metric_key="cpu.percent",
        granularity="hour",
        bucket_start=day + timedelta(hours=11),
        value_min=50.0,
        value_avg=60.0,
        value_max=70.0,
        value_last=65.0,
        sample_count=4,
    )

    compute_day_rollups(now=day + timedelta(hours=12))
    row = ServerMetricRollup.objects.get(server=server, metric_key="cpu.percent", granularity="day", bucket_start=day)
    assert row.value_min == 20.0
    assert row.value_max == 70.0
    assert row.value_avg == 50.0  # (30*2 + 60*4) / 6
    assert row.value_last == 65.0
    assert row.sample_count == 6


def test_run_metric_rollups_returns_counts():
    server = _make_server("rollup-run")
    now = timezone.now()
    _make_sample(server, now - timedelta(minutes=10), cpu_percent=10.0)
    summary = run_metric_rollups(now=now)
    assert summary["hour_rows"] >= 1
    assert summary["day_rows"] >= 1


def test_cleanup_metric_data_respects_retention():
    server = _make_server("rollup-clean")
    now = timezone.now()
    _make_sample(server, now - timedelta(days=20), cpu_percent=10.0)
    _make_sample(server, now - timedelta(days=1), cpu_percent=20.0)
    ServerMetricRollup.objects.create(
        server=server,
        metric_key="cpu.percent",
        granularity="hour",
        bucket_start=now - timedelta(days=401),
        value_min=1,
        value_avg=1,
        value_max=1,
        value_last=1,
        sample_count=1,
    )

    summary = cleanup_metric_data(now=now)
    assert summary["samples"] == 1
    assert summary["hour_rollups"] == 1
    assert ServerMetricSample.objects.filter(server=server).count() == 1


def test_fetch_metric_series_returns_oldest_first():
    server = _make_server("rollup-series")
    base = datetime(2026, 7, 16, 0, 0, tzinfo=UTC)
    for hour, value in ((0, 10.0), (1, 20.0), (2, 30.0)):
        ServerMetricRollup.objects.create(
            server=server,
            metric_key="cpu.percent",
            granularity="hour",
            bucket_start=base + timedelta(hours=hour),
            value_min=value,
            value_avg=value,
            value_max=value,
            value_last=value,
            sample_count=1,
        )

    series = fetch_metric_series(server.id, "cpu.percent", granularity="hour")
    assert [point["avg"] for point in series] == [10.0, 20.0, 30.0]
    limited = fetch_metric_series(server.id, "cpu.percent", granularity="hour", limit=2)
    assert [point["avg"] for point in limited] == [20.0, 30.0]


def test_bucket_start_for_truncates_hour_and_day():
    moment = datetime(2026, 7, 16, 13, 45, 12, tzinfo=UTC)
    assert bucket_start_for(moment, "hour") == datetime(2026, 7, 16, 13, 0, tzinfo=UTC)
    assert bucket_start_for(moment, "day") == datetime(2026, 7, 16, 0, 0, tzinfo=UTC)


def test_create_and_mirror_metric_sample():
    server_a = _make_server("mirror-a", host="10.0.0.50")
    server_b = _make_server("mirror-b", host="10.0.0.50")

    metrics = {
        "collector_version": 2,
        "cpu_percent": 33.3,
        "cpu_count": 4,
        "memory_percent": 44.4,
        "disk_mounts": [{"mount": "/", "percent": 55.0}],
        "journal_err_10m": 3,
    }
    sample = create_metric_sample(server_a, metrics, source="quick")
    assert sample.cpu_percent == 33.3
    assert sample.journal_err_10m == 3

    mirrored = mirror_metric_sample(sample, [server_a, server_b])
    assert len(mirrored) == 1
    copy = ServerMetricSample.objects.get(server=server_b)
    assert copy.cpu_percent == 33.3
    assert copy.disk_mounts == [{"mount": "/", "percent": 55.0}]
    assert copy.extra["mirrored_from_server_id"] == server_a.id
