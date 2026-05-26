"""
Server monitoring HTTP endpoints.

This module owns fleet health dashboards, health checks, alerts, watcher drafts,
monitoring config, and AI health analysis. Server OS detection stays with legacy
server CRUD until that endpoint group is split separately.
"""

import contextlib
import json
from datetime import timedelta as td

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Avg, Max
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core_ui.activity import log_user_activity
from core_ui.decorators import require_feature
from core_ui.models import UserActivityLog
from servers.models import Server, ServerAlert, ServerHealthCheck
from servers.views.server_helpers import _accessible_servers_queryset


def _monitoring_stale_seconds() -> int:
    return max(60, int(getattr(settings, "MONITORING_STATUS_STALE_SECONDS", 300) or 300))


def _latest_health_checks_by_server_id(server_ids: list[int]) -> dict[int, ServerHealthCheck]:
    if not server_ids:
        return {}
    latest_rows = (
        ServerHealthCheck.objects.filter(server_id__in=server_ids).values("server_id").annotate(last_id=Max("id"))
    )
    latest_ids = [row["last_id"] for row in latest_rows if row.get("last_id")]
    if not latest_ids:
        return {}
    checks = ServerHealthCheck.objects.filter(id__in=latest_ids)
    return {hc.server_id: hc for hc in checks}


def _serialize_monitoring_status_item(server: Server, hc: ServerHealthCheck | None, now) -> dict:
    stale_seconds = _monitoring_stale_seconds()
    checked_at = hc.checked_at if hc and hc.checked_at else None
    age_seconds = int((now - checked_at).total_seconds()) if checked_at else None
    raw_output = hc.raw_output if hc and isinstance(hc.raw_output, dict) else {}
    return {
        "server_id": server.id,
        "server_name": server.name,
        "host": server.host,
        "server_type": server.server_type or "ssh",
        "status": hc.status if hc else "unknown",
        "checked_at": checked_at.isoformat() if checked_at else None,
        "age_seconds": age_seconds,
        "is_stale": age_seconds is None or age_seconds > stale_seconds,
        "response_time_ms": hc.response_time_ms if hc else None,
        "cpu_percent": hc.cpu_percent if hc else None,
        "memory_percent": hc.memory_percent if hc else None,
        "disk_percent": hc.disk_percent if hc else None,
        "is_lite": bool(raw_output.get("lite")),
    }


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

    items = [_serialize_monitoring_status_item(server, latest_by_id.get(server.id), now) for server in servers]
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
            "latest_checked_at": latest_checked_at,
            "has_stale": stale_count > 0,
        },
    }


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def monitoring_dashboard(request):
    """Aggregated monitoring data for user dashboard."""
    user = request.user
    servers = _accessible_servers_queryset(user)
    server_ids = list(servers.values_list("id", flat=True))

    latest_checks_raw = (
        ServerHealthCheck.objects.filter(server_id__in=server_ids).values("server_id").annotate(last_id=Max("id"))
    )
    latest_ids = [row["last_id"] for row in latest_checks_raw]
    latest_checks = list(
        ServerHealthCheck.objects.filter(id__in=latest_ids).select_related("server").order_by("-checked_at")
    )

    server_health = []
    for hc in latest_checks:
        net_rx_bytes, net_tx_bytes = _parse_net_traffic(hc.raw_output)
        server_health.append(
            {
                "server_id": hc.server_id,
                "server_name": hc.server.name,
                "host": hc.server.host,
                "status": hc.status,
                "cpu_percent": hc.cpu_percent,
                "memory_percent": hc.memory_percent,
                "disk_percent": hc.disk_percent,
                "memory_used_mb": hc.memory_used_mb,
                "memory_total_mb": hc.memory_total_mb,
                "disk_used_gb": hc.disk_used_gb,
                "disk_total_gb": hc.disk_total_gb,
                "net_rx_bytes": net_rx_bytes,
                "net_tx_bytes": net_tx_bytes,
                "load_1m": hc.load_1m,
                "uptime_seconds": hc.uptime_seconds,
                "response_time_ms": hc.response_time_ms,
                "checked_at": hc.checked_at.isoformat() if hc.checked_at else None,
            }
        )

    checked_ids = {hc.server_id for hc in latest_checks}
    for srv in servers:
        if srv.id not in checked_ids:
            server_health.append(
                {
                    "server_id": srv.id,
                    "server_name": srv.name,
                    "host": srv.host,
                    "status": "unknown",
                    "cpu_percent": None,
                    "memory_percent": None,
                    "disk_percent": None,
                    "memory_used_mb": None,
                    "memory_total_mb": None,
                    "disk_used_gb": None,
                    "disk_total_gb": None,
                    "net_rx_bytes": None,
                    "net_tx_bytes": None,
                    "load_1m": None,
                    "uptime_seconds": None,
                    "response_time_ms": None,
                    "checked_at": None,
                }
            )

    active_alerts = list(
        ServerAlert.objects.filter(server_id__in=server_ids, is_resolved=False)
        .select_related("server")
        .order_by("-created_at")[:50]
    )
    alerts_data = [
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
        for alert in active_alerts
    ]

    agg = ServerHealthCheck.objects.filter(id__in=latest_ids).aggregate(
        avg_cpu=Avg("cpu_percent"),
        avg_mem=Avg("memory_percent"),
        avg_disk=Avg("disk_percent"),
    )

    status_counts = {}
    for hc in latest_checks:
        status_counts[hc.status] = status_counts.get(hc.status, 0) + 1

    recent_activity = list(UserActivityLog.objects.filter(user=user).order_by("-created_at")[:20])
    activity_data = [
        {
            "id": activity.id,
            "action": activity.action,
            "category": activity.category,
            "description": activity.description[:200],
            "entity_name": activity.entity_name,
            "created_at": activity.created_at.isoformat(),
        }
        for activity in recent_activity
    ]

    return JsonResponse(
        {
            "success": True,
            "servers": server_health,
            "alerts": alerts_data,
            "meta": {
                "stale_after_seconds": _monitoring_stale_seconds(),
            },
            "summary": {
                "total_servers": len(server_ids),
                "healthy": status_counts.get("healthy", 0),
                "warning": status_counts.get("warning", 0),
                "critical": status_counts.get("critical", 0),
                "unreachable": status_counts.get("unreachable", 0),
                "unknown": len(server_ids) - len(latest_checks),
                "active_alerts": len(active_alerts),
                "avg_cpu": round(agg["avg_cpu"] or 0, 1),
                "avg_memory": round(agg["avg_mem"] or 0, 1),
                "avg_disk": round(agg["avg_disk"] or 0, 1),
            },
            "recent_activity": activity_data,
        }
    )


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def monitoring_status(request):
    """Cached fleet health statuses (read-only, no SSH)."""
    return JsonResponse(_build_monitoring_status_payload(request.user))


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def monitoring_refresh(request):
    """Debounced lite fleet reachability check (TCP only)."""
    from servers.monitor import check_all_servers

    cooldown_seconds = max(
        30,
        int(getattr(settings, "MONITORING_FLEET_REFRESH_COOLDOWN_SECONDS", 120) or 120),
    )
    lock_timeout_seconds = max(30, cooldown_seconds)
    lock_key = f"monitoring:fleet-refresh:lock:{request.user.id}"
    recent_key = f"monitoring:fleet-refresh:recent:{request.user.id}"

    payload = _build_monitoring_status_payload(request.user)

    if cache.get(recent_key):
        payload["cached"] = True
        return JsonResponse(payload)

    if not cache.add(lock_key, "1", timeout=lock_timeout_seconds):
        payload["queued"] = True
        return JsonResponse(payload, status=202)

    server_ids = list(_accessible_servers_queryset(request.user).values_list("id", flat=True))
    try:
        async_to_sync(check_all_servers)(lite=True, deep=False, server_ids=server_ids)
    finally:
        cache.delete(lock_key)

    cache.set(recent_key, "1", timeout=cooldown_seconds)
    payload = _build_monitoring_status_payload(request.user)
    payload["refreshed"] = True
    return JsonResponse(payload)


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def server_health_history(request, server_id):
    """Health check history for a server (last 24h by default)."""
    hours = int(request.GET.get("hours", 24))
    since = timezone.now() - td(hours=hours)

    server = _accessible_servers_queryset(request.user).filter(id=server_id).first()
    if not server:
        return JsonResponse({"success": False, "error": "Server not found"}, status=404)

    checks = list(ServerHealthCheck.objects.filter(server=server, checked_at__gte=since).order_by("checked_at"))

    return JsonResponse(
        {
            "success": True,
            "server_id": server_id,
            "server_name": server.name,
            "checks": [_serialize_health_check(check) for check in checks],
        }
    )


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_health_check_now(request, server_id):
    """Trigger an immediate health check for a server."""
    from servers.monitor import check_server

    server = _accessible_servers_queryset(request.user).filter(id=server_id).first()
    if not server:
        return JsonResponse({"success": False, "error": "Server not found"}, status=404)

    if server.server_type != "ssh":
        return JsonResponse({"success": False, "error": "Only SSH servers support health checks"}, status=400)

    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = {}
    deep = bool(data.get("deep", False))

    cooldown_seconds = max(5, int(getattr(settings, "MONITORING_HEALTHCHECK_COOLDOWN_SECONDS", 60) or 60))
    lock_timeout_seconds = max(10, int(getattr(settings, "MONITORING_HEALTHCHECK_LOCK_SECONDS", 45) or 45))
    lock_key = f"monitoring:healthcheck:lock:{server.id}:deep:{int(deep)}"
    recent_key = f"monitoring:healthcheck:recent:{server.id}:deep:{int(deep)}"

    latest = ServerHealthCheck.objects.filter(server=server).order_by("-checked_at").first()
    if cache.get(recent_key):
        if latest:
            return JsonResponse(
                {
                    "success": True,
                    "cached": True,
                    "server_id": server.id,
                    "server_name": server.name,
                    "check": _serialize_health_check(latest),
                }
            )
        return JsonResponse({"success": True, "cached": True, "server_id": server.id, "server_name": server.name})

    if not cache.add(lock_key, "1", timeout=lock_timeout_seconds):
        if latest:
            return JsonResponse(
                {
                    "success": True,
                    "queued": True,
                    "server_id": server.id,
                    "server_name": server.name,
                    "check": _serialize_health_check(latest),
                }
            )
        return JsonResponse(
            {"success": True, "queued": True, "server_id": server.id, "server_name": server.name},
            status=202,
        )

    try:
        health_check = async_to_sync(check_server)(server, deep=deep)
    except Exception as exc:
        cache.delete(lock_key)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)
    finally:
        cache.delete(lock_key)

    if not health_check:
        return JsonResponse({"success": False, "error": "Check returned no result"}, status=500)

    cache.set(recent_key, health_check.id, timeout=cooldown_seconds)

    log_user_activity(
        user=request.user,
        request=request,
        category="monitoring",
        action="manual_health_check",
        entity_type="server",
        entity_id=str(server_id),
        entity_name=server.name,
    )

    return JsonResponse(
        {
            "success": True,
            "check": _serialize_health_check(health_check),
        }
    )
