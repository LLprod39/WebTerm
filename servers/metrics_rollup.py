"""Downsampling and retention for extended metric time series.

Raw ServerMetricSample rows (5-10 min cadence) are aggregated into hourly
buckets; daily buckets are aggregated from the hourly ones so they survive
raw-sample cleanup. Both passes are idempotent upserts, safe to re-run over
partially filled buckets.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from typing import Any

from django.conf import settings
from django.utils import timezone

from servers.models import ServerMetricRollup, ServerMetricSample

# metric_key -> ServerMetricSample field, copied as-is.
METRIC_SCALAR_FIELDS: dict[str, str] = {
    "cpu.percent": "cpu_percent",
    "cpu.iowait_percent": "cpu_iowait_percent",
    "cpu.steal_percent": "cpu_steal_percent",
    "load.1m": "load_1m",
    "mem.percent": "memory_percent",
    "mem.available_mb": "memory_available_mb",
    "swap.percent": "swap_percent",
    "net.rx_bps": "net_rx_bps",
    "net.tx_bps": "net_tx_bps",
    "net.errors_per_sec": "net_errors_per_sec",
    "tcp.retrans_per_sec": "tcp_retrans_per_sec",
    "tcp.established": "tcp_established",
    "procs.count": "process_count",
    "procs.zombie": "zombie_count",
    "journal.err_10m": "journal_err_10m",
    "journal.warn_10m": "journal_warn_10m",
}

_ROLLUP_UPDATE_FIELDS = ["value_min", "value_avg", "value_max", "value_last", "sample_count", "updated_at"]
_UPSERT_BATCH = 500


def iter_sample_metrics(sample: ServerMetricSample) -> Iterator[tuple[str, float]]:
    """Yield (metric_key, value) pairs for every chartable series in a sample."""
    for metric_key, field in METRIC_SCALAR_FIELDS.items():
        value = getattr(sample, field, None)
        if value is not None:
            yield metric_key, float(value)

    if sample.fd_used is not None and sample.fd_max:
        yield "fd.used_percent", round(sample.fd_used / sample.fd_max * 100.0, 2)

    for mount in sample.disk_mounts or []:
        if not isinstance(mount, dict):
            continue
        name = str(mount.get("mount") or "").strip()
        if not name:
            continue
        for suffix, source_key in (("percent", "percent"), ("used_gb", "used_gb"), ("inode_percent", "inode_percent")):
            value = mount.get(source_key)
            if isinstance(value, (int, float)):
                yield f"disk.{name}.{suffix}", float(value)


def bucket_start_for(moment: datetime, granularity: str) -> datetime:
    moment = moment.astimezone(dt_timezone.utc) if timezone.is_aware(moment) else moment
    if granularity == ServerMetricRollup.GRANULARITY_DAY:
        return moment.replace(hour=0, minute=0, second=0, microsecond=0)
    return moment.replace(minute=0, second=0, microsecond=0)


class _Accumulator:
    __slots__ = ("minimum", "maximum", "total", "count", "last")

    def __init__(self) -> None:
        self.minimum = float("inf")
        self.maximum = float("-inf")
        self.total = 0.0
        self.count = 0
        self.last = 0.0

    def add(self, value: float, weight: int = 1) -> None:
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)
        self.total += value * weight
        self.count += weight
        self.last = value

    def add_aggregate(self, minimum: float, maximum: float, avg: float, count: int, last: float) -> None:
        self.minimum = min(self.minimum, minimum)
        self.maximum = max(self.maximum, maximum)
        self.total += avg * max(1, count)
        self.count += max(1, count)
        self.last = last


def _flush(groups: dict[tuple[int, str, datetime], _Accumulator], granularity: str) -> int:
    rows = [
        ServerMetricRollup(
            server_id=server_id,
            metric_key=metric_key,
            granularity=granularity,
            bucket_start=bucket,
            value_min=acc.minimum,
            value_avg=round(acc.total / acc.count, 4),
            value_max=acc.maximum,
            value_last=acc.last,
            sample_count=acc.count,
        )
        for (server_id, metric_key, bucket), acc in groups.items()
        if acc.count > 0
    ]
    for offset in range(0, len(rows), _UPSERT_BATCH):
        ServerMetricRollup.objects.bulk_create(
            rows[offset : offset + _UPSERT_BATCH],
            update_conflicts=True,
            unique_fields=["server", "metric_key", "granularity", "bucket_start"],
            update_fields=_ROLLUP_UPDATE_FIELDS,
        )
    return len(rows)


def compute_hour_rollups(now: datetime | None = None, *, lookback_hours: int = 3) -> int:
    """Aggregate raw samples into hourly buckets covering the lookback window."""
    now = now or timezone.now()
    window_start = bucket_start_for(now, ServerMetricRollup.GRANULARITY_HOUR) - timedelta(hours=lookback_hours - 1)

    groups: dict[tuple[int, str, datetime], _Accumulator] = {}
    samples = (
        ServerMetricSample.objects.filter(collected_at__gte=window_start)
        .order_by("collected_at")
        .iterator(chunk_size=1000)
    )
    for sample in samples:
        bucket = bucket_start_for(sample.collected_at, ServerMetricRollup.GRANULARITY_HOUR)
        for metric_key, value in iter_sample_metrics(sample):
            groups.setdefault((sample.server_id, metric_key, bucket), _Accumulator()).add(value)

    return _flush(groups, ServerMetricRollup.GRANULARITY_HOUR)


def compute_day_rollups(now: datetime | None = None, *, lookback_days: int = 2) -> int:
    """Aggregate hourly rollups into daily buckets (survives raw-sample cleanup)."""
    now = now or timezone.now()
    window_start = bucket_start_for(now, ServerMetricRollup.GRANULARITY_DAY) - timedelta(days=lookback_days - 1)

    groups: dict[tuple[int, str, datetime], _Accumulator] = {}
    hours = (
        ServerMetricRollup.objects.filter(
            granularity=ServerMetricRollup.GRANULARITY_HOUR,
            bucket_start__gte=window_start,
        )
        .order_by("bucket_start")
        .iterator(chunk_size=1000)
    )
    for row in hours:
        bucket = bucket_start_for(row.bucket_start, ServerMetricRollup.GRANULARITY_DAY)
        groups.setdefault((row.server_id, row.metric_key, bucket), _Accumulator()).add_aggregate(
            row.value_min, row.value_max, row.value_avg, row.sample_count, row.value_last
        )

    return _flush(groups, ServerMetricRollup.GRANULARITY_DAY)


def run_metric_rollups(now: datetime | None = None) -> dict[str, int]:
    """One rollup pass (hour + day). Returns row counts for worker summaries."""
    hour_rows = compute_hour_rollups(now)
    day_rows = compute_day_rollups(now)
    return {"hour_rows": hour_rows, "day_rows": day_rows}


def cleanup_metric_data(now: datetime | None = None) -> dict[str, int]:
    """Retention pass for raw samples and rollups (settings-overridable)."""
    now = now or timezone.now()
    sample_days = int(getattr(settings, "METRICS_SAMPLE_RETENTION_DAYS", 14) or 14)
    hour_days = int(getattr(settings, "METRICS_HOUR_ROLLUP_RETENTION_DAYS", 400) or 400)
    day_days = int(getattr(settings, "METRICS_DAY_ROLLUP_RETENTION_DAYS", 1100) or 1100)

    deleted_samples, _ = ServerMetricSample.objects.filter(
        collected_at__lt=now - timedelta(days=sample_days)
    ).delete()
    deleted_hours, _ = ServerMetricRollup.objects.filter(
        granularity=ServerMetricRollup.GRANULARITY_HOUR,
        bucket_start__lt=now - timedelta(days=hour_days),
    ).delete()
    deleted_days, _ = ServerMetricRollup.objects.filter(
        granularity=ServerMetricRollup.GRANULARITY_DAY,
        bucket_start__lt=now - timedelta(days=day_days),
    ).delete()
    return {"samples": deleted_samples, "hour_rollups": deleted_hours, "day_rollups": deleted_days}


def fetch_metric_series(
    server_id: int,
    metric_key: str,
    *,
    granularity: str = ServerMetricRollup.GRANULARITY_HOUR,
    since: datetime | None = None,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    """Series points for charts/forecasting, oldest first."""
    qs = ServerMetricRollup.objects.filter(
        server_id=server_id, metric_key=metric_key, granularity=granularity
    )
    if since is not None:
        qs = qs.filter(bucket_start__gte=since)
    rows = list(qs.order_by("-bucket_start")[: max(1, limit)])
    rows.reverse()
    return [
        {
            "bucket_start": row.bucket_start,
            "min": row.value_min,
            "avg": row.value_avg,
            "max": row.value_max,
            "last": row.value_last,
            "count": row.sample_count,
        }
        for row in rows
    ]
