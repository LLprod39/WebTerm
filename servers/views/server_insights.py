"""Admin-only fleet insights API: extended metrics, forecasts, certificates.

One payload feeds the "Метрики и прогнозы" page: fleet summary, per-server
latest collector-v2 sample with 24h sparklines, deterministic predictions
(servers.forecasting), certificate inventory, and active alerts.
"""

from __future__ import annotations

import json
import threading
from datetime import timedelta
from typing import Any

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Max
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from loguru import logger

from servers.ai_insights import (
    ai_insights_enabled,
    latest_fleet_insight,
    latest_insights_by_endpoint,
    run_ai_insights_for_servers,
    serialize_insight,
)
from servers.forecasting import build_server_predictions
from servers.models import (
    Server,
    ServerAlert,
    ServerCertificate,
    ServerMetricRollup,
    ServerMetricSample,
)
from servers.views.server_monitoring import _latest_health_checks_by_server_id

__all__ = ["admin_insights", "admin_insights_ai_run"]

_AI_RUN_LOCK_KEY = "servers_admin_ai_insights_running"
_AI_RUN_LOCK_SECONDS = 600

_CACHE_KEY = "servers_admin_insights_v1"
_CACHE_SECONDS = 60
_SPARK_HOURS = 24
_SPARK_KEYS = {"cpu.percent": "cpu", "mem.percent": "mem", "disk./.percent": "disk"}
_MAX_ALERTS = 50


def _latest_samples_by_server_id(server_ids: list[int]) -> dict[int, ServerMetricSample]:
    if not server_ids:
        return {}
    latest_rows = (
        ServerMetricSample.objects.filter(server_id__in=server_ids).values("server_id").annotate(last_id=Max("id"))
    )
    latest_ids = [row["last_id"] for row in latest_rows if row.get("last_id")]
    if not latest_ids:
        return {}
    return {row.server_id: row for row in ServerMetricSample.objects.filter(id__in=latest_ids)}


def _sparklines_by_server_id(server_ids: list[int], now) -> dict[int, dict[str, list[float]]]:
    """{server_id: {"cpu": [...], "mem": [...], "disk": [...]}} — 24 hourly points."""
    since = now - timedelta(hours=_SPARK_HOURS)
    rows = (
        ServerMetricRollup.objects.filter(
            server_id__in=server_ids,
            metric_key__in=list(_SPARK_KEYS),
            granularity=ServerMetricRollup.GRANULARITY_HOUR,
            bucket_start__gte=since,
        )
        .order_by("bucket_start")
        .values_list("server_id", "metric_key", "value_avg")
    )
    result: dict[int, dict[str, list[float]]] = {}
    for server_id, metric_key, value in rows:
        series = result.setdefault(server_id, {name: [] for name in _SPARK_KEYS.values()})
        series[_SPARK_KEYS[metric_key]].append(round(float(value), 1))
    return result


def _worst_disk(sample: ServerMetricSample | None) -> dict[str, Any] | None:
    if not sample:
        return None
    worst: dict[str, Any] | None = None
    for item in sample.disk_mounts or []:
        if not isinstance(item, dict) or not isinstance(item.get("percent"), (int, float)):
            continue
        if worst is None or item["percent"] > worst["percent"]:
            worst = item
    return worst


def _fd_percent(sample: ServerMetricSample | None) -> float | None:
    if not sample or sample.fd_used is None or not sample.fd_max:
        return None
    return round(sample.fd_used / sample.fd_max * 100.0, 2)


def _health_score(
    *,
    status: str,
    predictions: list[dict[str, Any]],
    alerts: list[ServerAlert],
    certs: list[ServerCertificate],
    sample: ServerMetricSample | None,
    now,
) -> int:
    """Deterministic 0-100 wellbeing index: status + forecasts + alerts + hygiene."""
    score = 100.0
    if status == "warning":
        score -= 15
    elif status in ("critical", "unreachable"):
        score -= 40
    elif status == "unknown":
        score -= 10

    prediction_penalty = sum(
        15 if item["severity"] == "critical" else 7 if item["severity"] == "warning" else 0 for item in predictions
    )
    score -= min(prediction_penalty, 30)

    alert_penalty = sum(10 if alert.severity == "critical" else 3 for alert in alerts)
    score -= min(alert_penalty, 25)

    cert_penalty = 0
    for cert in certs:
        if cert.not_after is None:
            continue
        days = (cert.not_after - now).days
        if days < 0:
            cert_penalty += 15
        elif days <= 7:
            cert_penalty += 10
        elif days <= 30:
            cert_penalty += 4
    score -= min(cert_penalty, 20)

    if sample:
        if (sample.journal_err_10m or 0) > 5:
            score -= 4
        if sample.reboot_required:
            score -= 2
        if sample.ntp_synchronized is False:
            score -= 2
        if sample.zombie_count:
            score -= 1

    return int(max(5, min(100, round(score))))


def _serialize_server(
    server: Server,
    *,
    health,
    sample: ServerMetricSample | None,
    spark: dict[str, list[float]],
    predictions: list[dict[str, Any]],
    endpoint_key: str,
) -> dict[str, Any]:
    worst_disk = _worst_disk(sample)
    return {
        "id": server.id,
        "name": server.name,
        "host": server.host,
        "endpoint_key": endpoint_key,
        "owner": server.user.username,
        "status": health.status if health else "unknown",
        "checked_at": health.checked_at.isoformat() if health and health.checked_at else None,
        "sample_at": sample.collected_at.isoformat() if sample else None,
        "has_extended_metrics": sample is not None,
        "cpu_percent": sample.cpu_percent if sample else (health.cpu_percent if health else None),
        "cpu_iowait_percent": sample.cpu_iowait_percent if sample else None,
        "cpu_steal_percent": sample.cpu_steal_percent if sample else None,
        "cpu_count": sample.cpu_count if sample else None,
        "load_1m": sample.load_1m if sample else (health.load_1m if health else None),
        "memory_percent": sample.memory_percent if sample else (health.memory_percent if health else None),
        "memory_available_mb": sample.memory_available_mb if sample else None,
        "swap_percent": sample.swap_percent if sample else None,
        "worst_disk": worst_disk,
        "disk_mounts": list(sample.disk_mounts or []) if sample else [],
        "net_rx_bps": sample.net_rx_bps if sample else None,
        "net_tx_bps": sample.net_tx_bps if sample else None,
        "tcp_retrans_per_sec": sample.tcp_retrans_per_sec if sample else None,
        "tcp_established": sample.tcp_established if sample else None,
        "fd_percent": _fd_percent(sample),
        "process_count": sample.process_count if sample else (health.process_count if health else None),
        "zombie_count": sample.zombie_count if sample else None,
        "top_processes": dict(sample.top_processes or {}) if sample else {},
        "journal_err_10m": sample.journal_err_10m if sample else None,
        "journal_warn_10m": sample.journal_warn_10m if sample else None,
        "reboot_required": sample.reboot_required if sample else None,
        "ntp_synchronized": sample.ntp_synchronized if sample else None,
        "uptime_seconds": sample.uptime_seconds if sample else (health.uptime_seconds if health else None),
        "spark": spark,
        "predictions": predictions,
    }


def _serialize_certificate(cert: ServerCertificate, now) -> dict[str, Any]:
    days_left: float | None = None
    if cert.not_after is not None:
        days_left = round((cert.not_after - now).total_seconds() / 86400.0, 1)
    return {
        "id": cert.id,
        "server_id": cert.server_id,
        "server_name": cert.server.name,
        "port": cert.port,
        "endpoint": cert.endpoint,
        "subject": cert.subject,
        "issuer": cert.issuer,
        "not_after": cert.not_after.isoformat() if cert.not_after else None,
        "days_left": days_left,
        "sans": list(cert.sans or [])[:10],
        "is_active": cert.is_active,
        "changed_at": cert.fingerprint_changed_at.isoformat() if cert.fingerprint_changed_at else None,
        "last_checked_at": cert.last_checked_at.isoformat() if cert.last_checked_at else None,
    }


def _build_insights_payload() -> dict[str, Any]:
    now = timezone.now()
    servers = list(Server.objects.filter(is_active=True).select_related("user").order_by("name"))
    server_ids = [server.id for server in servers]

    health_by_id = _latest_health_checks_by_server_id(server_ids)
    samples_by_id = _latest_samples_by_server_id(server_ids)
    sparks_by_id = _sparklines_by_server_id(server_ids, now)

    alert_rows = list(
        ServerAlert.objects.filter(server_id__in=server_ids, is_resolved=False)
        .select_related("server")
        .order_by("-created_at")[:300]
    )
    alerts_by_server: dict[int, list[ServerAlert]] = {}
    for alert in alert_rows:
        alerts_by_server.setdefault(alert.server_id, []).append(alert)

    cert_rows = list(
        ServerCertificate.objects.filter(server_id__in=server_ids, is_active=True)
        .select_related("server")
        .order_by("not_after")
    )
    certs_by_server: dict[int, list[ServerCertificate]] = {}
    for cert in cert_rows:
        certs_by_server.setdefault(cert.server_id, []).append(cert)

    status_counts = {"healthy": 0, "warning": 0, "critical": 0, "unreachable": 0, "unknown": 0}
    all_predictions: list[dict[str, Any]] = []
    # Inventory rows sharing one host:port carry mirrored samples; the flat
    # forecast list keeps one entry per physical endpoint, not per row.
    seen_endpoint_predictions: set[tuple[str, str, str]] = set()
    server_entries: list[dict[str, Any]] = []
    for server in servers:
        health = health_by_id.get(server.id)
        status = health.status if health else "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1

        predictions = build_server_predictions(server, now=now)
        endpoint_key = f"{(server.host or '').strip().lower()}:{server.port or 22}"
        for item in predictions:
            dedupe_key = (endpoint_key, item["kind"], item["target"])
            if dedupe_key in seen_endpoint_predictions:
                continue
            seen_endpoint_predictions.add(dedupe_key)
            all_predictions.append({**item, "server_id": server.id, "server_name": server.name})

        entry = _serialize_server(
            server,
            health=health,
            sample=samples_by_id.get(server.id),
            spark=sparks_by_id.get(server.id, {"cpu": [], "mem": [], "disk": []}),
            predictions=predictions,
            endpoint_key=endpoint_key,
        )
        entry["health_score"] = _health_score(
            status=status,
            predictions=predictions,
            alerts=alerts_by_server.get(server.id, []),
            certs=certs_by_server.get(server.id, []),
            sample=samples_by_id.get(server.id),
            now=now,
        )
        server_entries.append(entry)

    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    all_predictions.sort(
        key=lambda item: (
            severity_rank.get(item["severity"], 3),
            item["eta_days"] if item["eta_days"] is not None else 9999.0,
        )
    )

    certificates = [_serialize_certificate(cert, now) for cert in cert_rows]

    alerts = [
        {
            "id": alert.id,
            "server_id": alert.server_id,
            "server_name": alert.server.name,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "title": alert.title,
            "message": alert.message[:300],
            "created_at": alert.created_at.isoformat(),
        }
        for alert in alert_rows[:_MAX_ALERTS]
    ]

    scores = [entry["health_score"] for entry in server_entries]
    fleet_health_score = int(round(sum(scores) / len(scores))) if scores else 100
    fleet_health_worst = min(scores) if scores else 100

    expiring_30d = sum(1 for cert in certificates if cert["days_left"] is not None and cert["days_left"] <= 30)
    changed_7d = sum(
        1
        for cert in cert_rows
        if cert.fingerprint_changed_at and (now - cert.fingerprint_changed_at) <= timedelta(days=7)
    )

    endpoint_keys = sorted({entry["endpoint_key"] for entry in server_entries})
    insights_by_endpoint = latest_insights_by_endpoint(endpoint_keys)
    ai_block = {
        "enabled": ai_insights_enabled(),
        "running": bool(cache.get(_AI_RUN_LOCK_KEY)),
        "fleet": serialize_insight(latest_fleet_insight()),
        "by_endpoint": {key: serialize_insight(row) for key, row in insights_by_endpoint.items()},
    }

    return {
        "success": True,
        "generated_at": now.isoformat(),
        "ai": ai_block,
        "summary": {
            "servers_total": len(servers),
            **status_counts,
            "fleet_health_score": fleet_health_score,
            "fleet_health_worst": fleet_health_worst,
            "active_alerts": len(alerts),
            "predictions_total": len(all_predictions),
            "predictions_critical": sum(1 for item in all_predictions if item["severity"] == "critical"),
            "predictions_warning": sum(1 for item in all_predictions if item["severity"] == "warning"),
            "certificates_total": len(certificates),
            "certificates_expiring_30d": expiring_30d,
            "certificates_changed_7d": changed_7d,
        },
        "servers": server_entries,
        "predictions": all_predictions,
        "certificates": certificates,
        "alerts": alerts,
    }


@login_required
@require_http_methods(["GET"])
def admin_insights(request):
    """Fleet insights payload (staff only, 60s cache, ?refresh=1 bypasses)."""
    if not request.user.is_staff:
        return JsonResponse({"success": False, "error": "Admin access required"}, status=403)

    refresh = str(request.GET.get("refresh") or "").strip() in {"1", "true", "yes"}
    if not refresh:
        cached = cache.get(_CACHE_KEY)
        if cached is not None:
            return JsonResponse({**cached, "cached": True})

    payload = _build_insights_payload()
    cache.set(_CACHE_KEY, payload, _CACHE_SECONDS)
    return JsonResponse(payload)


@login_required
@require_http_methods(["POST"])
def admin_insights_ai_run(request):
    """Queue an AI analysis pass (whole fleet or one server) in the background."""
    if not request.user.is_staff:
        return JsonResponse({"success": False, "error": "Admin access required"}, status=403)
    if not ai_insights_enabled():
        return JsonResponse({"success": False, "error": "AI insights disabled"}, status=400)

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        body = {}
    server_id = body.get("server_id")
    force = bool(body.get("force", True))
    server_ids = [int(server_id)] if server_id else None

    if not cache.add(_AI_RUN_LOCK_KEY, "1", _AI_RUN_LOCK_SECONDS):
        return JsonResponse({"success": True, "queued": False, "running": True})

    def _worker() -> None:
        try:
            summary = run_ai_insights_for_servers(server_ids, force=force)
            logger.info("AI insights run finished: {}", summary)
        except Exception as exc:
            logger.error("AI insights run failed: {}", exc)
        finally:
            cache.delete(_AI_RUN_LOCK_KEY)
            cache.delete(_CACHE_KEY)

    threading.Thread(target=_worker, daemon=True, name="admin-ai-insights").start()
    return JsonResponse({"success": True, "queued": True})
