"""Server monitoring HTTP views.

F-08a.10: serialization helpers live in ``server_monitoring_helpers``.
This module keeps the HTTP endpoints and re-exports helper symbols used
by other modules for a stable import path.
"""

import contextlib
import json
from datetime import timedelta as td

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Avg
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core_ui.activity import log_user_activity
from core_ui.decorators import require_feature
from core_ui.models import UserActivityLog
from servers.models import Server, ServerAlert, ServerHealthCheck
from servers.views.server_helpers import _accessible_servers_queryset
from servers.views.server_monitoring_helpers import (
    _apply_cached_live_metrics,
    _build_monitoring_status_payload,
    _is_lite_probe,
    _latest_health_checks_by_server_id,
    _maybe_kick_stale_fleet_refresh,
    _metrics_source,
    _monitoring_full_fail_trust_seconds,
    _monitoring_stale_seconds,
    _parse_net_traffic,
    _resolve_display_status,
    _serialize_dashboard_server_item,
    _serialize_health_check,
    _serialize_monitoring_status_item,
)

__all__ = [
    "_apply_cached_live_metrics",
    "_build_monitoring_status_payload",
    "_is_lite_probe",
    "_latest_health_checks_by_server_id",
    "_maybe_kick_stale_fleet_refresh",
    "_metrics_source",
    "_monitoring_full_fail_trust_seconds",
    "_monitoring_stale_seconds",
    "_parse_net_traffic",
    "_resolve_display_status",
    "_serialize_dashboard_server_item",
    "_serialize_health_check",
    "_serialize_monitoring_status_item",
    "monitoring_dashboard",
    "monitoring_status",
    "monitoring_refresh",
    "server_health_history",
    "server_health_check_now",
]


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def monitoring_dashboard(request):
    """Aggregated monitoring data for user dashboard."""
    user = request.user
    now = timezone.now()
    servers = list(_accessible_servers_queryset(user))
    server_ids = [server.id for server in servers]
    latest_by_id = _latest_health_checks_by_server_id(server_ids)
    metrics_by_id = _latest_health_checks_by_server_id(server_ids, with_metrics=True)
    live_by_id: dict[int, dict] = {}
    with contextlib.suppress(Exception):
        from servers.monitoring_live import fetch_live_samples

        live_by_id = fetch_live_samples(server_ids)

    server_health = [
        _serialize_dashboard_server_item(
            server,
            latest_by_id.get(server.id),
            metrics_by_id.get(server.id),
            now,
            live_sample=live_by_id.get(server.id),
        )
        for server in servers
    ]

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

    # Averages from last metrics snapshots (not lite TCP-only rows).
    metrics_ids = [hc.id for hc in metrics_by_id.values() if getattr(hc, "id", None)]
    agg = (
        ServerHealthCheck.objects.filter(id__in=metrics_ids).aggregate(
            avg_cpu=Avg("cpu_percent"),
            avg_mem=Avg("memory_percent"),
            avg_disk=Avg("disk_percent"),
        )
        if metrics_ids
        else {"avg_cpu": None, "avg_mem": None, "avg_disk": None}
    )

    status_counts: dict[str, int] = {}
    for item in server_health:
        if item["status"] != "unknown":
            status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1

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

    # Keep collecting even when no browser is watching: if the snapshot is stale,
    # kick a background metrics pass (debounced). Does not block this response.
    with contextlib.suppress(Exception):
        _maybe_kick_stale_fleet_refresh(server_health)

    return JsonResponse(
        {
            "success": True,
            "servers": server_health,
            "alerts": alerts_data,
            "meta": {
                "stale_after_seconds": _monitoring_stale_seconds(),
                "full_fail_metrics_trust_seconds": _monitoring_full_fail_trust_seconds(),
            },
            "summary": {
                "total_servers": len(server_ids),
                "healthy": status_counts.get("healthy", 0),
                "warning": status_counts.get("warning", 0),
                "critical": status_counts.get("critical", 0),
                "unreachable": status_counts.get("unreachable", 0),
                "unknown": sum(1 for item in server_health if item["status"] == "unknown"),
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
    """Debounced fleet check.

    Default (lite): TCP reachability only — does not refresh CPU/RAM/disk.
    With body ``{"metrics": true}``: full SSH quick metrics (CPU/RAM/disk) so the
    servers list can update when live WebSocket is unavailable.
    """
    from servers.monitor import check_all_servers

    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
        body = {}
    want_metrics = bool(
        body.get("metrics") or body.get("full") or str(request.GET.get("metrics") or "").lower() in ("1", "true", "yes")
    )

    if want_metrics:
        cooldown_seconds = max(
            45,
            int(getattr(settings, "MONITORING_METRICS_REFRESH_COOLDOWN_SECONDS", 90) or 90),
        )
        mode_key = "metrics"
    else:
        cooldown_seconds = max(
            30,
            int(getattr(settings, "MONITORING_FLEET_REFRESH_COOLDOWN_SECONDS", 120) or 120),
        )
        mode_key = "lite"

    lock_timeout_seconds = max(30, cooldown_seconds)
    lock_key = f"monitoring:fleet-refresh:{mode_key}:lock:{request.user.id}"
    recent_key = f"monitoring:fleet-refresh:{mode_key}:recent:{request.user.id}"

    payload = _build_monitoring_status_payload(request.user)

    if cache.get(recent_key):
        payload["cached"] = True
        payload["mode"] = mode_key
        return JsonResponse(payload)

    if not cache.add(lock_key, "1", timeout=lock_timeout_seconds):
        payload["queued"] = True
        payload["mode"] = mode_key
        return JsonResponse(payload, status=202)

    server_ids = list(_accessible_servers_queryset(request.user).values_list("id", flat=True))
    try:
        # lite=False runs SSH quick metrics (not deep diagnostics).
        async_to_sync(check_all_servers)(
            lite=not want_metrics,
            deep=False,
            server_ids=server_ids,
        )
    finally:
        cache.delete(lock_key)

    cache.set(recent_key, "1", timeout=cooldown_seconds)
    payload = _build_monitoring_status_payload(request.user)
    payload["refreshed"] = True
    payload["mode"] = mode_key
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
    from servers.monitor import check_all_servers

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
    # Lock by physical endpoint so concurrent users of the same host share one probe.
    host_key = f"{(server.host or '').strip().lower()}:{int(server.port or 22)}"
    lock_key = f"monitoring:healthcheck:lock:{host_key}:deep:{int(deep)}"
    recent_key = f"monitoring:healthcheck:recent:{host_key}:deep:{int(deep)}"

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
        # Probe the shared host:port once and mirror status onto sibling inventory rows.
        sibling_ids = list(
            Server.objects.filter(
                is_active=True,
                server_type="ssh",
                host__iexact=(server.host or "").strip(),
                port=int(server.port or 22),
            ).values_list("id", flat=True)
        )
        results = async_to_sync(check_all_servers)(deep=deep, server_ids=sibling_ids or [server.id], concurrency=1)
        health_check = next((hc for hc in results if hc.server_id == server.id), None)
        if health_check is None and results:
            health_check = results[0]
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
