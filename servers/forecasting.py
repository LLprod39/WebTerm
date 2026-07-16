"""Deterministic trend forecasting over metric rollups (Phase 1 core).

Pure-Python Theil-Sen (median of pairwise slopes) — robust to spikes, no
numpy. Series come from hourly rollups with a raw-sample fallback for young
installs, so a fleet-wide pass stays cheap. Predictions are computed on
request; persistence + alert/watcher integration is a later phase.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Any

from django.utils import timezone

from servers.metrics_rollup import iter_sample_metrics
from servers.models import Server, ServerCertificate, ServerMetricRollup, ServerMetricSample

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"
_SEVERITY_RANK = {SEVERITY_CRITICAL: 0, SEVERITY_WARNING: 1, SEVERITY_INFO: 2}

# ETA (days) → severity for resource-exhaustion forecasts.
_ETA_CRITICAL_DAYS = 2.0
_ETA_WARNING_DAYS = 7.0
_ETA_HORIZON_DAYS = 30.0
# Certificate lead times (days).
_CERT_CRITICAL_DAYS = 7
_CERT_WARNING_DAYS = 30
_CERT_INFO_DAYS = 60

_SERIES_WINDOW_DAYS = 7
_MIN_POINTS = 6
_MIN_POINTS_MEMORY = 12
# Memory has strong daily usage cycles: a weak downward drift is not a leak.
_MIN_CONSISTENCY_MEMORY = 0.75
_MAX_FIT_POINTS = 60
_MAX_MOUNTS = 8


def theil_sen(points: list[tuple[float, float]]) -> dict[str, float] | None:
    """Median-of-pairwise-slopes fit for [(x, y)] with x in days.

    Returns slope/intercept plus `consistency` — the share of pairwise slopes
    matching the median's sign, a cheap robustness signal used as confidence.
    """
    if len(points) < 3:
        return None
    if len(points) > _MAX_FIT_POINTS:
        step = len(points) / _MAX_FIT_POINTS
        points = [points[int(index * step)] for index in range(_MAX_FIT_POINTS)]

    slopes: list[float] = []
    for i in range(len(points) - 1):
        x0, y0 = points[i]
        for j in range(i + 1, len(points)):
            x1, y1 = points[j]
            if x1 != x0:
                slopes.append((y1 - y0) / (x1 - x0))
    if not slopes:
        return None

    slope = median(slopes)
    intercept = median(y - slope * x for x, y in points)
    if slope == 0:
        consistency = sum(1 for s in slopes if s == 0) / len(slopes)
    else:
        consistency = sum(1 for s in slopes if s * slope > 0) / len(slopes)
    return {
        "slope": slope,
        "intercept": intercept,
        "consistency": round(consistency, 3),
        "points": len(points),
    }


def eta_days_to(current: float, threshold: float, slope_per_day: float) -> float | None:
    """Days until a growing metric crosses threshold; None if not approaching."""
    if slope_per_day <= 1e-9 or current >= threshold:
        return None
    return (threshold - current) / slope_per_day


def _eta_severity(eta: float) -> str:
    if eta <= _ETA_CRITICAL_DAYS:
        return SEVERITY_CRITICAL
    if eta <= _ETA_WARNING_DAYS:
        return SEVERITY_WARNING
    return SEVERITY_INFO


def fetch_series(
    server_id: int,
    metric_key: str,
    *,
    now: datetime,
    window_days: int = _SERIES_WINDOW_DAYS,
) -> list[tuple[float, float]]:
    """[(x_days, value)] from hourly rollups; raw samples cover young installs."""
    since = now - timedelta(days=window_days)
    rows = list(
        ServerMetricRollup.objects.filter(
            server_id=server_id,
            metric_key=metric_key,
            granularity=ServerMetricRollup.GRANULARITY_HOUR,
            bucket_start__gte=since,
        )
        .order_by("bucket_start")
        .values_list("bucket_start", "value_avg")
    )
    points = [(bucket.timestamp() / 86400.0, float(value)) for bucket, value in rows]
    if len(points) >= _MIN_POINTS:
        return points

    samples = ServerMetricSample.objects.filter(
        server_id=server_id, collected_at__gte=now - timedelta(days=2)
    ).order_by("-collected_at")[:300]
    sample_points: list[tuple[float, float]] = []
    for sample in reversed(list(samples)):
        for key, value in iter_sample_metrics(sample):
            if key == metric_key:
                sample_points.append((sample.collected_at.timestamp() / 86400.0, value))
                break
    return sample_points if len(sample_points) > len(points) else points


def _prediction(
    *,
    kind: str,
    target: str,
    severity: str,
    now: datetime,
    eta_days: float | None,
    current_value: float | None,
    threshold: float | None,
    unit: str,
    slope_per_day: float | None,
    confidence: float,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    predicted_for = now + timedelta(days=eta_days) if eta_days is not None else None
    return {
        "kind": kind,
        "target": target,
        "severity": severity,
        "eta_days": round(eta_days, 2) if eta_days is not None else None,
        "predicted_for": predicted_for.isoformat() if predicted_for else None,
        "current_value": round(current_value, 2) if current_value is not None else None,
        "threshold": threshold,
        "unit": unit,
        "slope_per_day": round(slope_per_day, 4) if slope_per_day is not None else None,
        "confidence": round(confidence, 2),
        "evidence": evidence,
    }


def _exhaustion_prediction(
    server_id: int,
    *,
    now: datetime,
    metric_key: str,
    kind: str,
    target: str,
    unit: str = "%",
    warn_threshold: float = 90.0,
    hard_threshold: float = 100.0,
    min_slope: float = 0.05,
    min_points: int = _MIN_POINTS,
    confidence_factor: float = 1.0,
    extra_evidence: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Generic 'metric grows toward a ceiling' forecast (disk, inodes, swap)."""
    series = fetch_series(server_id, metric_key, now=now)
    if len(series) < min_points:
        return None
    fit = theil_sen(series)
    if not fit or fit["slope"] < min_slope:
        return None

    current = series[-1][1]
    threshold = warn_threshold if current < warn_threshold else hard_threshold
    eta = eta_days_to(current, threshold, fit["slope"])
    if eta is None or eta > _ETA_HORIZON_DAYS:
        return None

    evidence = {
        "window_days": _SERIES_WINDOW_DAYS,
        "points": fit["points"],
        "metric_key": metric_key,
    }
    if extra_evidence:
        evidence.update(extra_evidence)
    return _prediction(
        kind=kind,
        target=target,
        severity=_eta_severity(eta),
        now=now,
        eta_days=eta,
        current_value=current,
        threshold=threshold,
        unit=unit,
        slope_per_day=fit["slope"],
        confidence=max(0.1, fit["consistency"] * confidence_factor),
        evidence=evidence,
    )


def _memory_prediction(server_id: int, *, now: datetime, total_mb: int | None) -> dict[str, Any] | None:
    """MemAvailable trending toward ~5% of RAM (leak / pressure)."""
    if not total_mb:
        return None
    series = fetch_series(server_id, "mem.available_mb", now=now)
    if len(series) < _MIN_POINTS_MEMORY:
        return None
    fit = theil_sen(series)
    if not fit or fit["slope"] >= -1.0 or fit["consistency"] < _MIN_CONSISTENCY_MEMORY:
        return None

    current = series[-1][1]
    floor_mb = max(total_mb * 0.05, 64.0)
    if current <= floor_mb:
        return None
    eta = (current - floor_mb) / -fit["slope"]
    if eta > _ETA_HORIZON_DAYS:
        return None

    return _prediction(
        kind="memory_pressure",
        target="memory",
        severity=_eta_severity(eta),
        now=now,
        eta_days=eta,
        current_value=current,
        threshold=round(floor_mb),
        unit="MB",
        slope_per_day=fit["slope"],
        # Daily usage cycles make memory noisier than disk — damp confidence.
        confidence=max(0.1, fit["consistency"] * 0.8),
        evidence={"window_days": _SERIES_WINDOW_DAYS, "points": fit["points"], "total_mb": total_mb},
    )


def _log_surge_prediction(server_id: int, *, now: datetime) -> dict[str, Any] | None:
    """Error-rate acceleration: last 24h vs the 6 days before it."""
    series = fetch_series(server_id, "journal.err_10m", now=now)
    if len(series) < _MIN_POINTS * 2:
        return None
    split_x = (now - timedelta(days=1)).timestamp() / 86400.0
    recent = [value for x, value in series if x >= split_x]
    baseline = [value for x, value in series if x < split_x]
    if len(recent) < 3 or len(baseline) < 6:
        return None

    recent_avg = sum(recent) / len(recent)
    baseline_avg = sum(baseline) / len(baseline)
    if recent_avg < 6 or recent_avg < max(baseline_avg, 0.5) * 3:
        return None

    ratio = recent_avg / max(baseline_avg, 0.5)
    return _prediction(
        kind="log_error_surge",
        target="journal",
        severity=SEVERITY_WARNING if ratio < 10 else SEVERITY_CRITICAL,
        now=now,
        eta_days=None,
        current_value=recent_avg,
        threshold=None,
        unit="errors/10m",
        slope_per_day=None,
        confidence=0.7,
        evidence={"recent_avg": round(recent_avg, 1), "baseline_avg": round(baseline_avg, 1), "ratio": round(ratio, 1)},
    )


def _certificate_predictions(server: Server, *, now: datetime) -> list[dict[str, Any]]:
    predictions: list[dict[str, Any]] = []
    certs = ServerCertificate.objects.filter(server=server, is_active=True)
    for cert in certs:
        target = f"cert:{cert.port}"
        if cert.not_after is not None:
            days_left = (cert.not_after - now).total_seconds() / 86400.0
            if days_left <= _CERT_INFO_DAYS:
                if days_left <= _CERT_CRITICAL_DAYS:
                    severity = SEVERITY_CRITICAL
                elif days_left <= _CERT_WARNING_DAYS:
                    severity = SEVERITY_WARNING
                else:
                    severity = SEVERITY_INFO
                predictions.append(
                    _prediction(
                        kind="cert_expiry",
                        target=target,
                        severity=severity,
                        now=now,
                        eta_days=max(days_left, 0.0),
                        current_value=days_left,
                        threshold=None,
                        unit="days",
                        slope_per_day=None,
                        confidence=1.0,
                        evidence={
                            "port": cert.port,
                            "endpoint": cert.endpoint,
                            "subject": cert.subject[:120],
                            "issuer": cert.issuer[:120],
                            "not_after": cert.not_after.isoformat(),
                            "expired": days_left <= 0,
                        },
                    )
                )
        if cert.fingerprint_changed_at and (now - cert.fingerprint_changed_at) <= timedelta(days=7):
            predictions.append(
                _prediction(
                    kind="cert_changed",
                    target=target,
                    severity=SEVERITY_INFO,
                    now=now,
                    eta_days=None,
                    current_value=None,
                    threshold=None,
                    unit="",
                    slope_per_day=None,
                    confidence=1.0,
                    evidence={
                        "port": cert.port,
                        "endpoint": cert.endpoint,
                        "changed_at": cert.fingerprint_changed_at.isoformat(),
                        "previous_fingerprint": cert.previous_fingerprint[:32],
                    },
                )
            )
    return predictions


def build_server_predictions(server: Server, *, now: datetime | None = None) -> list[dict[str, Any]]:
    """All deterministic forecasts for one server, most urgent first."""
    now = now or timezone.now()
    predictions: list[dict[str, Any]] = []

    latest = ServerMetricSample.objects.filter(server=server).order_by("-collected_at").first()
    mounts: list[str] = []
    if latest:
        mounts = [
            str(item.get("mount"))
            for item in (latest.disk_mounts or [])
            if isinstance(item, dict) and item.get("mount")
        ][:_MAX_MOUNTS]

    for mount in mounts:
        disk = _exhaustion_prediction(
            server.id,
            now=now,
            metric_key=f"disk.{mount}.percent",
            kind="disk_full",
            target=f"disk:{mount}",
            extra_evidence={"mount": mount},
        )
        if disk:
            gb_fit = theil_sen(fetch_series(server.id, f"disk.{mount}.used_gb", now=now))
            if gb_fit and gb_fit["slope"] > 0:
                disk["evidence"]["gb_per_day"] = round(gb_fit["slope"], 2)
            predictions.append(disk)

        inode = _exhaustion_prediction(
            server.id,
            now=now,
            metric_key=f"disk.{mount}.inode_percent",
            kind="inode_full",
            target=f"inode:{mount}",
            extra_evidence={"mount": mount},
        )
        if inode:
            predictions.append(inode)

    memory = _memory_prediction(server.id, now=now, total_mb=latest.memory_total_mb if latest else None)
    if memory:
        predictions.append(memory)

    swap = _exhaustion_prediction(
        server.id,
        now=now,
        metric_key="swap.percent",
        kind="swap_growth",
        target="swap",
        min_slope=0.2,
        confidence_factor=0.9,
    )
    if swap:
        predictions.append(swap)

    surge = _log_surge_prediction(server.id, now=now)
    if surge:
        predictions.append(surge)

    predictions.extend(_certificate_predictions(server, now=now))

    predictions.sort(
        key=lambda item: (
            _SEVERITY_RANK.get(item["severity"], 3),
            item["eta_days"] if item["eta_days"] is not None else 9999.0,
        )
    )
    return predictions
