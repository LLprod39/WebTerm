"""
Admin dashboard page and JSON APIs.
"""

import json
from datetime import date, timedelta, timezone

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncHour
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone as django_timezone
from django.views.decorators.http import require_http_methods

from app.core.model_config import model_manager
from core_ui.context_processors import user_can_feature
from core_ui.models import UserActivityLog
from core_ui.views.admin_billing import _get_provider_billing_snapshot


@login_required
def dashboard_view(request):
    """Dashboard entry for mini build: staff monitoring page."""
    if not user_can_feature(request.user, "dashboard") or not request.user.is_staff:
        return redirect("servers:server_list")

    return _admin_dashboard_view(request)


@login_required
def api_dashboard_stats(request):
    """Backward-compat alias to admin dashboard API in mini build."""
    if not user_can_feature(request.user, "dashboard") or not request.user.is_staff:
        return JsonResponse({"error": "Forbidden"}, status=403)

    return api_admin_dashboard(request)


def _model_or_none(app_label: str, model_name: str):
    from django.apps import apps as django_apps

    try:
        return django_apps.get_model(app_label, model_name)
    except LookupError:
        return None


def _collect_admin_dashboard_data(include_version: bool = False) -> dict:
    from django.contrib.auth.models import User

    from core_ui.models import LLMUsageLog
    from servers.models import Server, ServerConnection

    Task = _model_or_none("tasks", "Task")
    AgentRun = _model_or_none("agent_hub", "AgentRun")

    now = django_timezone.now()
    today = date.today()
    last_24h = now - timedelta(hours=24)
    last_5min = now - timedelta(minutes=5)
    last_7d = now - timedelta(days=7)

    online_user_ids = list(
        UserActivityLog.objects.filter(created_at__gte=last_5min, user_id__isnull=False)
        .values_list("user_id", flat=True)
        .distinct()
    )
    online_users = []
    for user in User.objects.filter(id__in=online_user_ids):
        last_log = UserActivityLog.objects.filter(user=user).order_by("-created_at").first()
        online_users.append(
            {
                "username": user.username,
                "action": last_log.action if last_log else "",
                "time": last_log.created_at.isoformat() if last_log else "",
            }
        )

    ai_requests_today = UserActivityLog.objects.filter(
        action__in=["chat_request", "terminal_ai_request", "chat_message", "llm_request"],
        created_at__date=today,
    ).count()

    active_connections = ServerConnection.objects.filter(status="connected").select_related("server", "user")
    terminals = [
        {
            "server": conn.server.name,
            "user": conn.user.username if conn.user_id else "unknown",
            "connected_at": conn.connected_at.isoformat(),
        }
        for conn in active_connections
    ]

    if AgentRun is not None:
        agents_running = AgentRun.objects.filter(status="running").count()
        agents_today = AgentRun.objects.filter(created_at__date=today).count()
        succeeded_24h = AgentRun.objects.filter(status="completed", created_at__gte=last_24h).count()
        failed_24h = AgentRun.objects.filter(status="failed", created_at__gte=last_24h).count()
    else:
        agents_running = 0
        agents_today = 0
        succeeded_24h = 0
        failed_24h = 0

    total_finished_24h = succeeded_24h + failed_24h
    success_rate = round(succeeded_24h / total_finished_24h * 100) if total_finished_24h > 0 else 100

    cost_per_1k = {"gemini": 0.0005, "grok": 0.005, "claude": 0.003, "openai": 0.002, "ollama": 0.0}
    api_usage = {}
    for provider in ("gemini", "grok", "claude", "openai", "ollama"):
        qs = LLMUsageLog.objects.filter(provider=provider, created_at__date=today)
        agg = qs.aggregate(inp=Sum("input_tokens"), out=Sum("output_tokens"))
        inp, out = agg["inp"] or 0, agg["out"] or 0
        estimated_cost = round((inp + out) / 1000 * cost_per_1k.get(provider, 0.001), 4)
        api_usage[provider] = {
            "calls": qs.count(),
            "input_tokens": inp,
            "output_tokens": out,
            "errors": qs.filter(status__in=["error", "timeout"]).count(),
            "estimated_cost_usd": estimated_cost,
            "actual_spend_usd": None,
            "balance_usd": None,
            "billing_source": "estimated_logs",
            "billing_note": "Estimated from local token counters.",
            "cost_usd": estimated_cost,
        }

    providers = {}
    for provider in ("gemini", "grok", "claude", "openai", "ollama"):
        enabled = getattr(model_manager.config, f"{provider}_enabled", False)
        providers[provider] = {
            "enabled": enabled,
            "model": model_manager.get_chat_model(provider) if enabled else "",
        }

    billing_data = _get_provider_billing_snapshot(now.astimezone(timezone.utc), providers)
    for provider, usage in api_usage.items():
        billing = billing_data.get(provider, {})
        actual_spend = billing.get("actual_spend_usd")
        usage["actual_spend_usd"] = actual_spend
        usage["balance_usd"] = billing.get("balance_usd")
        usage["billing_source"] = billing.get("billing_source", "estimated_logs")
        usage["billing_note"] = billing.get("billing_note", "")
        if actual_spend is not None:
            usage["cost_usd"] = round(actual_spend, 4)

    hourly = list(
        UserActivityLog.objects.filter(created_at__gte=last_24h)
        .annotate(hour=TruncHour("created_at"))
        .values("hour")
        .annotate(count=Count("id"))
        .order_by("hour")
    )
    hourly_activity = [{"hour": h["hour"].isoformat(), "count": h["count"]} for h in hourly]

    top_users = list(
        UserActivityLog.objects.filter(created_at__gte=last_7d, user__isnull=False)
        .values("user__username")
        .annotate(
            total=Count("id"),
            ai_requests=Count(
                "id", filter=Q(action__in=["chat_request", "terminal_ai_request", "chat_message", "llm_request"])
            ),
            terminal_sessions=Count("id", filter=Q(category="terminal")),
        )
        .order_by("-total")[:10]
    )
    top_users = [
        {
            "username": row["user__username"],
            "total": row["total"],
            "ai_requests": row["ai_requests"],
            "terminal_sessions": row["terminal_sessions"],
        }
        for row in top_users
    ]

    recent_activity = list(UserActivityLog.objects.select_related("user").order_by("-created_at")[:20])
    recent_activity = [
        {
            "user": row.username_snapshot or (row.user.username if row.user_id else "system"),
            "category": row.category,
            "action": row.action,
            "time": row.created_at.isoformat(),
        }
        for row in recent_activity
    ]

    tasks_total = Task.objects.count() if Task is not None else 0
    tasks_in_progress = Task.objects.filter(status="IN_PROGRESS").count() if Task is not None else 0

    from servers.models import ServerAlert, ServerHealthCheck

    fleet_health = {
        "avg_cpu": 0,
        "avg_memory": 0,
        "avg_disk": 0,
        "healthy": 0,
        "warning": 0,
        "critical": 0,
        "unreachable": 0,
    }
    try:
        from django.db.models import Avg as AvgF
        from django.db.models import Max

        latest_per_server = ServerHealthCheck.objects.values("server_id").annotate(last_id=Max("id"))
        latest_ids = [r["last_id"] for r in latest_per_server]
        if latest_ids:
            agg = ServerHealthCheck.objects.filter(id__in=latest_ids).aggregate(
                avg_cpu=AvgF("cpu_percent"),
                avg_mem=AvgF("memory_percent"),
                avg_disk=AvgF("disk_percent"),
            )
            fleet_health["avg_cpu"] = round(agg["avg_cpu"] or 0, 1)
            fleet_health["avg_memory"] = round(agg["avg_mem"] or 0, 1)
            fleet_health["avg_disk"] = round(agg["avg_disk"] or 0, 1)
            for hc in ServerHealthCheck.objects.filter(id__in=latest_ids).values_list("status", flat=True):
                fleet_health[hc] = fleet_health.get(hc, 0) + 1
    except Exception:
        pass

    active_alerts_count = ServerAlert.objects.filter(is_resolved=False).count()
    recent_alerts = list(
        ServerAlert.objects.filter(is_resolved=False).select_related("server").order_by("-created_at")[:10]
    )
    alerts_list = [
        {
            "server": a.server.name,
            "type": a.alert_type,
            "severity": a.severity,
            "title": a.title,
            "time": a.created_at.isoformat(),
        }
        for a in recent_alerts
    ]

    data = {
        "online_users": {
            "count": len(online_users),
            "total_registered": User.objects.count(),
            "users": online_users,
        },
        "ai": {"requests_today": ai_requests_today},
        "terminals": {"active": active_connections.count(), "connections": terminals},
        "agents": {
            "running": agents_running,
            "today": agents_today,
            "succeeded_24h": succeeded_24h,
            "failed_24h": failed_24h,
            "success_rate": success_rate,
        },
        "api_usage": api_usage,
        "api_calls_today": sum(v["calls"] for v in api_usage.values()),
        "providers": providers,
        "servers": {"total": Server.objects.count(), "active": Server.objects.filter(is_active=True).count()},
        "tasks": {"total": tasks_total, "in_progress": tasks_in_progress},
        "hourly_activity": hourly_activity,
        "top_users": top_users,
        "recent_activity": recent_activity,
        "fleet_health": fleet_health,
        "active_alerts_count": active_alerts_count,
        "alerts": alerts_list,
    }
    if include_version:
        data["app_version"] = getattr(settings, "WEU_VERSION", "2.0.0")
    return data


def _admin_dashboard_view(request):
    """Render admin monitoring dashboard."""
    if not user_can_feature(request.user, "dashboard") or not request.user.is_staff:
        return redirect("servers:server_list")

    context = _collect_admin_dashboard_data(include_version=True)
    context["hourly_activity"] = json.dumps(context["hourly_activity"])
    return render(request, "admin_dashboard.html", context)


@login_required
@require_http_methods(["GET"])
def api_admin_dashboard(request):
    """JSON API for admin dashboard auto-refresh."""
    if not user_can_feature(request.user, "dashboard") or not request.user.is_staff:
        return JsonResponse({"error": "Forbidden"}, status=403)

    data = _collect_admin_dashboard_data(include_version=True)
    return JsonResponse({"success": True, "data": data})


@login_required
@require_http_methods(["GET"])
def api_admin_users_activity(request):
    """Detailed user activity logs for admin dashboard with filtering."""
    if not user_can_feature(request.user, "dashboard") or not request.user.is_staff:
        return JsonResponse({"error": "Forbidden"}, status=403)

    try:
        limit = min(int(request.GET.get("limit", 50)), 200)
        offset = max(0, int(request.GET.get("offset", 0)))
        days = min(int(request.GET.get("days", 7)), 90)
    except (TypeError, ValueError):
        limit, offset, days = 50, 0, 7

    since = django_timezone.now() - timedelta(days=days)
    qs = UserActivityLog.objects.select_related("user").filter(created_at__gte=since)

    user_id = request.GET.get("user_id")
    if user_id:
        qs = qs.filter(user_id=int(user_id))

    category = request.GET.get("category", "").strip()
    if category:
        qs = qs.filter(category=category)

    search = request.GET.get("search", "").strip()
    if search:
        qs = qs.filter(
            Q(username_snapshot__icontains=search)
            | Q(action__icontains=search)
            | Q(description__icontains=search)
            | Q(entity_name__icontains=search)
        )

    total = qs.count()
    rows = list(qs.order_by("-created_at")[offset : offset + limit])

    events = [
        {
            "id": r.id,
            "user_id": r.user_id,
            "username": r.username_snapshot or (r.user.username if r.user_id else "system"),
            "category": r.category,
            "action": r.action,
            "status": r.status,
            "description": r.description[:300],
            "entity_type": r.entity_type,
            "entity_name": r.entity_name,
            "ip_address": r.ip_address or "",
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]

    return JsonResponse({"success": True, "total": total, "events": events})


@login_required
@require_http_methods(["GET"])
def api_admin_users_sessions(request):
    """Active user sessions - who's online now and what they're doing."""
    if not user_can_feature(request.user, "dashboard") or not request.user.is_staff:
        return JsonResponse({"error": "Forbidden"}, status=403)

    from django.contrib.auth.models import User as AuthUser

    from servers.models import ServerConnection

    last_5min = django_timezone.now() - timedelta(minutes=5)
    active_user_ids = list(
        UserActivityLog.objects.filter(created_at__gte=last_5min, user_id__isnull=False)
        .values_list("user_id", flat=True)
        .distinct()
    )

    sessions = []
    for user in AuthUser.objects.filter(id__in=active_user_ids).order_by("username"):
        last_log = UserActivityLog.objects.filter(user=user).order_by("-created_at").first()
        active_terminals = ServerConnection.objects.filter(user=user, status="connected").count()
        today_actions = UserActivityLog.objects.filter(user=user, created_at__date=django_timezone.now().date()).count()
        sessions.append(
            {
                "user_id": user.id,
                "username": user.username,
                "email": user.email,
                "is_staff": user.is_staff,
                "last_action": last_log.action if last_log else "",
                "last_category": last_log.category if last_log else "",
                "last_activity": last_log.created_at.isoformat() if last_log else "",
                "active_terminals": active_terminals,
                "today_actions": today_actions,
            }
        )

    total_registered = AuthUser.objects.count()
    total_active_today = (
        UserActivityLog.objects.filter(created_at__date=django_timezone.now().date(), user_id__isnull=False)
        .values("user_id")
        .distinct()
        .count()
    )

    return JsonResponse(
        {
            "success": True,
            "online_count": len(sessions),
            "total_registered": total_registered,
            "active_today": total_active_today,
            "sessions": sessions,
        }
    )
