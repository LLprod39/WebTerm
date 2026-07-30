"""Serialization helpers for server monitoring views.

F-08a.10: extracted from ``server_monitoring`` so view handlers stay thin.
"""

import contextlib
from datetime import UTC

from django.conf import settings
from django.core.cache import cache
from django.db.models import Max
from django.utils import timezone

from servers.models import Server, ServerHealthCheck
from servers.views.server_helpers import _accessible_servers_queryset


def _monitoring_stale_seconds() -> int:
    return max(60, int(getattr(settings, "MONITORING_STATUS_STALE_SECONDS", 300) or 300))


def _monitoring_full_fail_trust_seconds() -> int:
    """How long full SSH unreachable may still yield to fresher metrics."""
    return max(
        15,
        # Prefer last good CPU/RAM longer so dashboards don't flash "нет связи"
        # between monitor cycles / before live WS reconnects.
        int(getattr(settings, "MONITORING_FULL_FAIL_METRICS_TRUST_SECONDS", 300) or 300),
    )


def _maybe_kick_stale_fleet_refresh(server_health: list[dict]) -> None:
    """If the fleet snapshot is mostly stale, schedule a background SSH metrics pass.

    Fire-and-forget: the HTTP response already returns last-known rows. The
    ``run_monitor`` worker is the main collector; this covers local/dev when the
    worker is down or just after servers were added.
    """
    if not server_health:
        return
    stale_ids = [
        int(row["server_id"])
        for row in server_health
        if row.get("server_id")
        and (
            row.get("is_stale")
            or row.get("status") in (None, "unknown", "unreachable")
            or row.get("cpu_percent") is None
        )
    ]
    # Only act when a meaningful share of the fleet needs attention.
    if not stale_ids:
        return
    ratio = len(stale_ids) / max(1, len(server_health))
    if ratio < 0.25 and len(stale_ids) < 2:
        return

    cooldown = max(
        45,
        int(getattr(settings, "MONITORING_METRICS_REFRESH_COOLDOWN_SECONDS", 90) or 90),
    )
    lock_key = "monitoring:auto-stale-refresh:global"
    if not cache.add(lock_key, "1", timeout=cooldown):
        return

    try:
        from servers.monitoring.monitor import schedule_health_check_for_server_ids

        schedule_health_check_for_server_ids(stale_ids, deep=False)
    except Exception:
        cache.delete(lock_key)
        raise


def _latest_health_checks_by_server_id(
    server_ids: list[int], *, with_metrics: bool = False
) -> dict[int, ServerHealthCheck]:
    if not server_ids:
        return {}
    qs = ServerHealthCheck.objects.filter(server_id__in=server_ids)
    if with_metrics:
        qs = qs.filter(cpu_percent__isnull=False)
    latest_rows = qs.values("server_id").annotate(last_id=Max("id"))
    latest_ids = [row["last_id"] for row in latest_rows if row.get("last_id")]
    if not latest_ids:
        return {}
    checks = ServerHealthCheck.objects.filter(id__in=latest_ids)
    return {hc.server_id: hc for hc in checks}


def _is_lite_probe(hc: ServerHealthCheck | None) -> bool:
    if not hc:
        return False
    raw_output = hc.raw_output if isinstance(hc.raw_output, dict) else {}
    return bool(raw_output.get("lite"))


def _resolve_display_status(
    hc: ServerHealthCheck | None,
    metrics_hc: ServerHealthCheck | None,
    *,
    stale_seconds: int,
    now,
    full_fail_trust_seconds: int | None = None,
) -> tuple[str, ServerHealthCheck | None]:
    """Pick status + the health-check row that produced it.

    A flaky lite TCP probe can write ``unreachable`` while a slightly older full
    check (or live SSH stream) still has valid CPU/RAM. Prefer the metrics-based
    health when that probe is still fresh so the list does not flash "Недоступен".

    Returns ``(status, status_row)`` where ``status_row`` is the check whose
    status/timestamps should be shown to the operator (or ``None`` for unknown).
    """
    if full_fail_trust_seconds is None:
        full_fail_trust_seconds = _monitoring_full_fail_trust_seconds()

    if not hc:
        if metrics_hc and metrics_hc.status:
            metrics_age = int((now - metrics_hc.checked_at).total_seconds()) if metrics_hc.checked_at else None
            if metrics_age is not None and metrics_age <= stale_seconds:
                return metrics_hc.status, metrics_hc
        return "unknown", None

    status = hc.status or "unknown"
    is_lite = _is_lite_probe(hc)

    if status != ServerHealthCheck.STATUS_UNREACHABLE:
        return status, hc

    # Latest says unreachable. If we still have a fresh non-unreachable metrics
    # snapshot (and the failure was only a lite probe, or metrics are very fresh),
    # keep showing the metrics-derived health.
    if not metrics_hc or not metrics_hc.status or metrics_hc.status == ServerHealthCheck.STATUS_UNREACHABLE:
        return status, hc
    if metrics_hc.id == hc.id:
        return status, hc

    metrics_age = int((now - metrics_hc.checked_at).total_seconds()) if metrics_hc.checked_at else None
    if metrics_age is None:
        return status, hc

    # Lite probe failures are noisy; trust metrics for the full stale window.
    # Full SSH failures only yield if metrics are very recent (likely still up).
    trust_window = stale_seconds if is_lite else min(int(full_fail_trust_seconds), stale_seconds)
    if metrics_age <= trust_window:
        return metrics_hc.status, metrics_hc
    return status, hc


def _metrics_source(
    hc: ServerHealthCheck | None,
    metrics_hc: ServerHealthCheck | None,
) -> ServerHealthCheck | None:
    """Prefer latest row when it carries metrics; else last metrics snapshot."""
    if hc and hc.cpu_percent is not None:
        return hc
    return metrics_hc


def _apply_cached_live_metrics(item: dict, live: dict | None, now) -> dict:
    """Overlay a fresh live cache sample onto a status item (for reload first paint).

    Background monitor writes DB metrics about every 60s. Live samples are ~2s but
    were only on the WebSocket — after F5 the list looked "old" until WS reconnected.
    """
    if not live or not isinstance(live, dict):
        return item
    try:
        live_ts = float(live.get("ts") or 0)
    except (TypeError, ValueError):
        return item
    if live_ts <= 0:
        return item

    from datetime import datetime

    live_dt = datetime.fromtimestamp(live_ts, tz=UTC)
    live_age = int((now - live_dt).total_seconds())
    # Ignore expired/stale cache entries even if TTL has not purged them.
    live_max_age = max(
        60,
        int(getattr(settings, "MONITORING_LIVE_CACHE_SECONDS", 300) or 300),
    )
    if live_age < 0 or live_age > live_max_age:
        return item

    metrics_checked_at = item.get("metrics_checked_at")
    if metrics_checked_at:
        with contextlib.suppress(TypeError, ValueError):
            db_dt = datetime.fromisoformat(str(metrics_checked_at).replace("Z", "+00:00"))
            if db_dt.tzinfo is None:
                db_dt = db_dt.replace(tzinfo=UTC)
            if live_dt <= db_dt:
                return item

    def _pick(key: str):
        val = live.get(key)
        return val if val is not None else item.get(key)

    item["cpu_percent"] = _pick("cpu_percent")
    item["memory_percent"] = _pick("memory_percent")
    item["disk_percent"] = _pick("disk_percent")
    item["load_1m"] = _pick("load_1m")
    item["metrics_checked_at"] = live_dt.isoformat()
    item["metrics_age_seconds"] = live_age
    item["is_lite"] = False
    # Live sample means the host was recently reachable.
    if item.get("status") in (None, "unknown", "unreachable") and any(
        item.get(k) is not None for k in ("cpu_percent", "memory_percent", "disk_percent")
    ):
        item["status"] = "healthy"
        item["is_stale"] = False
        item["age_seconds"] = live_age
        item["checked_at"] = live_dt.isoformat()
    return item


def _serialize_monitoring_status_item(
    server: Server,
    hc: ServerHealthCheck | None,
    metrics_hc: ServerHealthCheck | None,
    now,
    live_sample: dict | None = None,
) -> dict:
    stale_seconds = _monitoring_stale_seconds()
    full_fail_trust = _monitoring_full_fail_trust_seconds()
    status, status_row = _resolve_display_status(
        hc,
        metrics_hc,
        stale_seconds=stale_seconds,
        now=now,
        full_fail_trust_seconds=full_fail_trust,
    )
    # Latest check may be a lite TCP probe without metrics; fall back to the
    # newest check that actually carries CPU/RAM/disk numbers.
    source = _metrics_source(hc, metrics_hc)
    status_checked_at = status_row.checked_at if status_row and status_row.checked_at else None
    metrics_checked_at = source.checked_at if source and source.checked_at else None
    # Age/staleness: prefer status-defining timestamp, else metrics we display.
    display_checked_at = status_checked_at or metrics_checked_at
    display_age = int((now - display_checked_at).total_seconds()) if display_checked_at else None
    metrics_age_seconds = int((now - metrics_checked_at).total_seconds()) if metrics_checked_at else None
    probe_checked_at = hc.checked_at if hc and hc.checked_at else None
    is_stale = display_age is None or display_age > stale_seconds
    # Recent metrics beat a transient unreachable probe for list first-paint.
    if (
        status == ServerHealthCheck.STATUS_UNREACHABLE
        and metrics_age_seconds is not None
        and metrics_age_seconds <= stale_seconds
        and source
        and source.cpu_percent is not None
    ):
        status = source.status if source.status and source.status != ServerHealthCheck.STATUS_UNREACHABLE else "healthy"
        is_stale = False
        status_checked_at = metrics_checked_at or status_checked_at
        display_age = metrics_age_seconds
    # Stale unreachable without a fresh live overlay looks like a false outage on first paint.
    if status == ServerHealthCheck.STATUS_UNREACHABLE and is_stale:
        status = "unknown"
    item = {
        "server_id": server.id,
        "server_name": server.name,
        "host": server.host,
        "server_type": server.server_type or "ssh",
        "status": status,
        # Timestamps/RTT/lite flag follow the row that produced *status*.
        "checked_at": status_checked_at.isoformat() if status_checked_at else None,
        "age_seconds": display_age,
        "is_stale": is_stale,
        "response_time_ms": status_row.response_time_ms if status_row else None,
        "cpu_percent": source.cpu_percent if source else None,
        "memory_percent": source.memory_percent if source else None,
        "disk_percent": source.disk_percent if source else None,
        "load_1m": source.load_1m if source else None,
        "metrics_checked_at": metrics_checked_at.isoformat() if metrics_checked_at else None,
        "metrics_age_seconds": metrics_age_seconds,
        "is_lite": _is_lite_probe(status_row),
        # Raw latest probe (may differ when status was overridden by metrics).
        "probe_checked_at": probe_checked_at.isoformat() if probe_checked_at else None,
        "probe_is_lite": _is_lite_probe(hc),
        "status_from_metrics": bool(
            status_row is not None
            and metrics_hc is not None
            and status_row.id == metrics_hc.id
            and hc is not None
            and status_row.id != hc.id
        ),
    }
    return _apply_cached_live_metrics(item, live_sample, now)


def _serialize_health_check(hc: ServerHealthCheck) -> dict:
    return {
        "id": getattr(hc, "id", None),
        "status": getattr(hc, "status", None),
        "cpu_percent": getattr(hc, "cpu_percent", None),
        "memory_percent": getattr(hc, "memory_percent", None),
        "disk_percent": getattr(hc, "disk_percent", None),
        "load_1m": getattr(hc, "load_1m", None),
        "load_5m": getattr(hc, "load_5m", None),
        "load_15m": getattr(hc, "load_15m", None),
        "memory_used_mb": getattr(hc, "memory_used_mb", None),
        "memory_total_mb": getattr(hc, "memory_total_mb", None),
        "disk_used_gb": getattr(hc, "disk_used_gb", None),
        "disk_total_gb": getattr(hc, "disk_total_gb", None),
        "uptime_seconds": getattr(hc, "uptime_seconds", None),
        "process_count": getattr(hc, "process_count", None),
        "response_time_ms": getattr(hc, "response_time_ms", None),
        "is_deep": getattr(hc, "is_deep", None),
        "checked_at": hc.checked_at.isoformat() if getattr(hc, "checked_at", None) else None,
    }


def _parse_net_traffic(raw_output):
    if not isinstance(raw_output, dict):
        return None, None
    quick = raw_output.get("quick")
    if not isinstance(quick, str):
        return None, None

    rx_bytes = None
    tx_bytes = None
    for line in quick.splitlines():
        stripped = line.strip()
        if stripped.startswith("NET_RX_BYTES="):
            with contextlib.suppress(TypeError, ValueError):
                rx_bytes = int(stripped.split("=", 1)[1].strip())
        elif stripped.startswith("NET_TX_BYTES="):
            with contextlib.suppress(TypeError, ValueError):
                tx_bytes = int(stripped.split("=", 1)[1].strip())
    return rx_bytes, tx_bytes


def _build_monitoring_status_payload(user) -> dict:
    now = timezone.now()
    servers = list(_accessible_servers_queryset(user))
    server_ids = [server.id for server in servers]
    latest_by_id = _latest_health_checks_by_server_id(server_ids)
    metrics_by_id = _latest_health_checks_by_server_id(server_ids, with_metrics=True)
    # Last live WebSocket samples (cached ~2m) — fresher than 60s DB monitor after reload.
    live_by_id: dict[int, dict] = {}
    with contextlib.suppress(Exception):
        from servers.monitoring.monitoring_live import fetch_live_samples

        live_by_id = fetch_live_samples(server_ids)

    items = [
        _serialize_monitoring_status_item(
            server,
            latest_by_id.get(server.id),
            metrics_by_id.get(server.id),
            now,
            live_sample=live_by_id.get(server.id),
        )
        for server in servers
    ]
    checked_items = [item for item in items if item["checked_at"]]
    latest_checked_at = max((item["checked_at"] for item in checked_items), default=None)
    stale_count = sum(1 for item in items if item["is_stale"])

    status_counts: dict[str, int] = {}
    for item in items:
        if item["status"] != "unknown":
            status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1

    return {
        "success": True,
        "servers": items,
        "summary": {
            "total_servers": len(server_ids),
            "healthy": status_counts.get("healthy", 0),
            "warning": status_counts.get("warning", 0),
            "critical": status_counts.get("critical", 0),
            "unreachable": status_counts.get("unreachable", 0),
            "unknown": sum(1 for item in items if item["status"] == "unknown"),
            "stale": stale_count,
        },
        "meta": {
            "stale_after_seconds": _monitoring_stale_seconds(),
            "full_fail_metrics_trust_seconds": _monitoring_full_fail_trust_seconds(),
            "latest_checked_at": latest_checked_at,
            "has_stale": stale_count > 0,
        },
    }


def _serialize_dashboard_server_item(
    server: Server,
    hc: ServerHealthCheck | None,
    metrics_hc: ServerHealthCheck | None,
    now,
    live_sample: dict | None = None,
) -> dict:
    """Dashboard row: same status resolution as fleet status API + richer metrics."""
    stale_seconds = _monitoring_stale_seconds()
    status, status_row = _resolve_display_status(
        hc,
        metrics_hc,
        stale_seconds=stale_seconds,
        now=now,
    )
    source = _metrics_source(hc, metrics_hc)
    net_source = source or status_row or hc
    net_rx_bytes, net_tx_bytes = _parse_net_traffic(net_source.raw_output if net_source else None)
    checked_at = status_row.checked_at if status_row and status_row.checked_at else None
    display_age = int((now - checked_at).total_seconds()) if checked_at else None
    is_stale = display_age is None or display_age > stale_seconds
    # Prefer last metrics snapshot age for staleness when status row is a lite fail.
    if source and source.checked_at and (is_stale or status == ServerHealthCheck.STATUS_UNREACHABLE):
        metrics_age = int((now - source.checked_at).total_seconds())
        if metrics_age <= stale_seconds and source.cpu_percent is not None:
            # Still have recent metrics — do not paint a hard outage.
            if status == ServerHealthCheck.STATUS_UNREACHABLE:
                status = (
                    source.status
                    if source.status and source.status != ServerHealthCheck.STATUS_UNREACHABLE
                    else "healthy"
                )
            is_stale = False
            checked_at = source.checked_at
    # Stale "unreachable" is usually a failed probe window, not a confirmed outage —
    # paint as unknown so dashboards don't flash red before metrics/live catch up.
    if status == ServerHealthCheck.STATUS_UNREACHABLE and is_stale:
        status = "unknown"
    item = {
        "server_id": server.id,
        "server_name": server.name,
        "host": server.host,
        "status": status,
        "cpu_percent": source.cpu_percent if source else None,
        "memory_percent": source.memory_percent if source else None,
        "disk_percent": source.disk_percent if source else None,
        "memory_used_mb": source.memory_used_mb if source else None,
        "memory_total_mb": source.memory_total_mb if source else None,
        "disk_used_gb": source.disk_used_gb if source else None,
        "disk_total_gb": source.disk_total_gb if source else None,
        "net_rx_bytes": net_rx_bytes,
        "net_tx_bytes": net_tx_bytes,
        "load_1m": source.load_1m if source else None,
        "uptime_seconds": source.uptime_seconds if source else None,
        "response_time_ms": status_row.response_time_ms if status_row else None,
        "checked_at": checked_at.isoformat() if checked_at else None,
        "is_stale": is_stale,
        "is_lite": _is_lite_probe(status_row),
    }
    # Same live-cache overlay as /monitoring/status so dashboard matches the servers list.
    item = _apply_cached_live_metrics(item, live_sample, now)
    return item
