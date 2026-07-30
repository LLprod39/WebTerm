"""Persistence for collector v2 metric samples (servers.monitoring.metrics_parsing output).

Split from servers.monitoring.monitor to keep that module under the size limit.
"""

from __future__ import annotations

from typing import Any

from servers.models import Server, ServerMetricSample

# Metric-dict keys copied verbatim onto ServerMetricSample fields.
SAMPLE_FIELDS: tuple[str, ...] = (
    "cpu_percent",
    "cpu_iowait_percent",
    "cpu_steal_percent",
    "cpu_count",
    "load_1m",
    "load_5m",
    "load_15m",
    "memory_total_mb",
    "memory_available_mb",
    "memory_percent",
    "swap_total_mb",
    "swap_used_mb",
    "swap_percent",
    "disk_mounts",
    "net_rx_bps",
    "net_tx_bps",
    "net_errors_per_sec",
    "tcp_retrans_per_sec",
    "tcp_established",
    "fd_used",
    "fd_max",
    "process_count",
    "zombie_count",
    "top_processes",
    "journal_err_10m",
    "journal_warn_10m",
    "reboot_required",
    "ntp_synchronized",
    "uptime_seconds",
)


def build_sample_kwargs(metrics: dict[str, Any]) -> dict[str, Any]:
    return {field: metrics[field] for field in SAMPLE_FIELDS if field in metrics}


def create_metric_sample(server: Server, metrics: dict[str, Any], *, source: str) -> ServerMetricSample:
    return ServerMetricSample.objects.create(
        server=server,
        source=source,
        **build_sample_kwargs(metrics),
    )


def mirror_metric_sample(sample: ServerMetricSample, targets: list[Server]) -> list[ServerMetricSample]:
    """Copy a sample onto sibling inventory rows sharing the same host:port."""
    rows = [
        ServerMetricSample(
            server=target,
            source=sample.source,
            extra={"mirrored_from_server_id": sample.server_id},
            **{field: getattr(sample, field) for field in SAMPLE_FIELDS},
        )
        for target in targets
        if target.id != sample.server_id
    ]
    if not rows:
        return []
    return ServerMetricSample.objects.bulk_create(rows)
