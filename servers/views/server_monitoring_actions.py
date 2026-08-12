"""
Monitoring action endpoints: alerts, watcher drafts, config, and AI analysis.
"""

import contextlib
import json

from asgiref.sync import async_to_sync
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from app.core.llm import LLMProvider
from core_ui.activity import log_user_activity
from core_ui.api_failure import internal_error_response
from core_ui.decorators import require_feature
from servers.agents.agent_service import launch_watcher_draft_for_user
from servers.models_inventory import Server
from servers.models_monitoring import ServerAlert, ServerHealthCheck
from servers.monitoring.watcher_service import WatcherService
from servers.views.server_helpers import _accessible_servers_queryset


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def server_alerts_list(request):
    """List alerts, optionally filtered by server/severity/resolved status."""
    user = request.user
    server_ids = list(_accessible_servers_queryset(user).values_list("id", flat=True))

    queryset = ServerAlert.objects.filter(server_id__in=server_ids).select_related("server")

    server_id = request.GET.get("server_id")
    if server_id:
        queryset = queryset.filter(server_id=int(server_id))

    severity = request.GET.get("severity")
    if severity:
        queryset = queryset.filter(severity=severity)

    resolved = request.GET.get("resolved")
    if resolved is not None:
        queryset = queryset.filter(is_resolved=resolved.lower() in ("true", "1", "yes"))

    limit = min(int(request.GET.get("limit", 100)), 500)
    alerts = list(queryset.order_by("-created_at")[:limit])

    return JsonResponse(
        {
            "success": True,
            "alerts": [
                {
                    "id": alert.id,
                    "server_id": alert.server_id,
                    "server_name": alert.server.name,
                    "alert_type": alert.alert_type,
                    "severity": alert.severity,
                    "title": alert.title,
                    "message": alert.message,
                    "is_resolved": alert.is_resolved,
                    "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
                    "created_at": alert.created_at.isoformat(),
                    "metadata": alert.metadata,
                }
                for alert in alerts
            ],
        }
    )


@login_required
@require_feature("servers")
@require_http_methods(["GET", "POST"])
def server_watcher_scan(request):
    """Build watcher drafts for the user's accessible servers."""
    payload = {}
    if request.method == "POST":
        try:
            payload = json.loads(request.body) if request.body else {}
        except Exception:
            payload = {}

    raw_server_ids = payload.get("server_ids")
    if raw_server_ids is None:
        raw_server_ids = request.GET.getlist("server_ids") or request.GET.get("server_ids")

    requested_server_ids: list[int] = []
    if isinstance(raw_server_ids, str):
        raw_server_ids = [part.strip() for part in raw_server_ids.split(",")]
    for value in raw_server_ids or []:
        with contextlib.suppress(TypeError, ValueError):
            requested_server_ids.append(int(value))

    limit_raw = payload.get("limit", request.GET.get("limit", 25))
    try:
        limit = max(1, min(int(limit_raw), 100))
    except (TypeError, ValueError):
        limit = 25

    queryset = _accessible_servers_queryset(request.user).order_by("name")
    if requested_server_ids:
        queryset = queryset.filter(id__in=requested_server_ids)

    persist_raw = payload.get("persist", request.GET.get("persist", "false"))
    persist = str(persist_raw).lower() in {"1", "true", "yes", "on"}
    watcher_service = WatcherService()
    watcher_payload = (
        watcher_service.persist_queryset(queryset, limit=limit)
        if persist
        else watcher_service.scan_queryset(queryset, limit=limit)
    )
    watcher_payload["requested_server_ids"] = requested_server_ids
    watcher_payload["persisted_scan"] = persist

    log_user_activity(
        user=request.user,
        request=request,
        category="monitoring",
        action="watcher_scan",
        entity_type="fleet",
        entity_id="watchers",
        entity_name="Watcher scan",
    )

    return JsonResponse(
        {
            "success": True,
            **watcher_payload,
        }
    )


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def server_watcher_drafts(request):
    """List persisted watcher drafts for accessible servers."""
    queryset = _accessible_servers_queryset(request.user).order_by("name")

    server_id = request.GET.get("server_id")
    if server_id:
        with contextlib.suppress(TypeError, ValueError):
            queryset = queryset.filter(id=int(server_id))

    status_values = request.GET.getlist("status") or request.GET.get("status", "")
    if isinstance(status_values, str):
        statuses = [item.strip() for item in status_values.split(",") if item.strip()]
    else:
        statuses = [str(item).strip() for item in status_values if str(item).strip()]

    try:
        limit = max(1, min(int(request.GET.get("limit", 100)), 200))
    except (TypeError, ValueError):
        limit = 100

    watcher_payload = WatcherService().list_persisted_queryset(queryset, statuses=statuses or None, limit=limit)
    return JsonResponse({"success": True, **watcher_payload})


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_watcher_draft_ack(request, draft_id):
    """Acknowledge a persisted watcher draft."""
    queryset = _accessible_servers_queryset(request.user).order_by("name")
    draft = WatcherService().acknowledge_draft(draft_id, user=request.user, servers_qs=queryset)
    if draft is None:
        return JsonResponse({"success": False, "error": "Watcher draft not found"}, status=404)

    log_user_activity(
        user=request.user,
        request=request,
        category="monitoring",
        action="watcher_acknowledge",
        entity_type="watcher_draft",
        entity_id=str(draft_id),
        entity_name=draft["objective"][:120],
    )
    return JsonResponse({"success": True, "draft": draft})


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_watcher_draft_launch(request, draft_id):
    """Launch a suggested agent run from a persisted watcher draft."""
    result = launch_watcher_draft_for_user(
        draft_id=draft_id,
        user=request.user,
        accessible_servers_queryset=_accessible_servers_queryset(request.user).order_by("name"),
    )
    if not result["ok"]:
        return JsonResponse(result["payload"], status=int(result["status"]))

    payload = dict(result["payload"] or {})
    draft_payload = payload.get("draft") or {}

    log_user_activity(
        user=request.user,
        request=request,
        category="monitoring",
        action="watcher_launch",
        entity_type="watcher_draft",
        entity_id=str(draft_id),
        entity_name=str(draft_payload.get("objective") or "")[:120],
    )
    return JsonResponse(payload)


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_alert_resolve(request, alert_id):
    """Mark an alert as resolved."""
    user = request.user
    server_ids = list(_accessible_servers_queryset(user).values_list("id", flat=True))

    alert = ServerAlert.objects.filter(id=alert_id, server_id__in=server_ids).first()
    if not alert:
        return JsonResponse({"success": False, "error": "Alert not found"}, status=404)

    alert.is_resolved = True
    alert.resolved_at = timezone.now()
    alert.resolved_by = user
    alert.save(update_fields=["is_resolved", "resolved_at", "resolved_by"])

    log_user_activity(
        user=user,
        request=request,
        category="monitoring",
        action="resolve_alert",
        entity_type="alert",
        entity_id=str(alert_id),
        entity_name=alert.title,
    )

    return JsonResponse({"success": True})


@login_required
@require_http_methods(["GET", "POST"])
def monitoring_config(request):
    """GET/POST monitoring thresholds and intervals. Staff only."""
    if not request.user.is_staff:
        return JsonResponse({"error": "Forbidden"}, status=403)

    import servers.monitoring.monitor as mon

    if request.method == "GET":
        total_checks = ServerHealthCheck.objects.count()
        total_alerts = ServerAlert.objects.filter(is_resolved=False).count()
        last_check = ServerHealthCheck.objects.order_by("-checked_at").first()

        return JsonResponse(
            {
                "success": True,
                "thresholds": {
                    "cpu_warn": mon.CPU_WARN,
                    "cpu_crit": mon.CPU_CRIT,
                    "mem_warn": mon.MEM_WARN,
                    "mem_crit": mon.MEM_CRIT,
                    "disk_warn": mon.DISK_WARN,
                    "disk_crit": mon.DISK_CRIT,
                },
                "stats": {
                    "total_checks": total_checks,
                    "active_alerts": total_alerts,
                    "last_check_at": last_check.checked_at.isoformat() if last_check else None,
                    "monitored_servers": Server.objects.filter(is_active=True, server_type="ssh").count(),
                },
            }
        )

    try:
        data = json.loads(request.body)
        thresholds = data.get("thresholds", {})

        if "cpu_warn" in thresholds:
            mon.CPU_WARN = float(thresholds["cpu_warn"])
        if "cpu_crit" in thresholds:
            mon.CPU_CRIT = float(thresholds["cpu_crit"])
        if "mem_warn" in thresholds:
            mon.MEM_WARN = float(thresholds["mem_warn"])
        if "mem_crit" in thresholds:
            mon.MEM_CRIT = float(thresholds["mem_crit"])
        if "disk_warn" in thresholds:
            mon.DISK_WARN = float(thresholds["disk_warn"])
        if "disk_crit" in thresholds:
            mon.DISK_CRIT = float(thresholds["disk_crit"])

        log_user_activity(
            user=request.user,
            request=request,
            category="settings",
            action="update_monitoring_config",
            description=f"Updated monitoring thresholds: {thresholds}",
        )

        return JsonResponse({"success": True})
    except Exception as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def ai_analyze_server(request, server_id):
    """AI analysis of server health data and logs."""
    try:
        data = json.loads(request.body) if request.body else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    server = _accessible_servers_queryset(request.user).filter(id=server_id).first()
    if not server:
        return JsonResponse({"success": False, "error": "Server not found"}, status=404)

    last_check = ServerHealthCheck.objects.filter(server=server).order_by("-checked_at").first()
    active_alerts = list(ServerAlert.objects.filter(server=server, is_resolved=False).order_by("-created_at")[:10])
    recent_checks = list(ServerHealthCheck.objects.filter(server=server).order_by("-checked_at")[:6])

    prompt_parts = [
        f"Проанализируй сервер **{server.name}** ({server.host}:{server.port}).",
        "",
    ]

    if last_check:
        prompt_parts.append("## Latest Health Check")
        prompt_parts.append(f"- Status: **{last_check.status}**")
        if last_check.cpu_percent is not None:
            prompt_parts.append(f"- CPU: {last_check.cpu_percent}%")
        if last_check.memory_percent is not None:
            prompt_parts.append(
                f"- RAM: {last_check.memory_percent}% ({last_check.memory_used_mb or '?'}MB / {last_check.memory_total_mb or '?'}MB)"
            )
        if last_check.disk_percent is not None:
            prompt_parts.append(
                f"- Disk: {last_check.disk_percent}% ({last_check.disk_used_gb or '?'}GB / {last_check.disk_total_gb or '?'}GB)"
            )
        if last_check.load_1m is not None:
            prompt_parts.append(f"- Load: {last_check.load_1m}/{last_check.load_5m}/{last_check.load_15m}")
        if last_check.uptime_seconds:
            days = last_check.uptime_seconds // 86400
            prompt_parts.append(f"- Uptime: {days} days")
        if last_check.process_count:
            prompt_parts.append(f"- Processes: {last_check.process_count}")
        if last_check.response_time_ms:
            prompt_parts.append(f"- Response time: {last_check.response_time_ms}ms")

        raw = last_check.raw_output or {}
        if raw.get("deep"):
            deep = raw["deep"]
            if deep.get("failed_services"):
                prompt_parts.append(f"\n### Failed Services\n```\n{chr(10).join(deep['failed_services'][:10])}\n```")
            if deep.get("log_errors"):
                prompt_parts.append(f"\n### System Log Errors\n```\n{chr(10).join(deep['log_errors'][:15])}\n```")
            if deep.get("kernel_errors"):
                prompt_parts.append(f"\n### Kernel Errors\n```\n{chr(10).join(deep['kernel_errors'][:10])}\n```")
    else:
        prompt_parts.append("No health check data available yet.")

    if active_alerts:
        prompt_parts.append("\n## Active Alerts")
        for alert in active_alerts:
            prompt_parts.append(f"- [{alert.severity.upper()}] {alert.title}: {alert.message[:200]}")

    if len(recent_checks) > 1:
        prompt_parts.append("\n## Trend (last checks)")
        for health_check in recent_checks[:6]:
            prompt_parts.append(
                f"- {health_check.checked_at.strftime('%H:%M')}: CPU={health_check.cpu_percent or '?'}% RAM={health_check.memory_percent or '?'}% Disk={health_check.disk_percent or '?'}% [{health_check.status}]"
            )

    prompt_parts.extend(
        [
            "",
            "---",
            "Предоставь краткий анализ в формате markdown на русском языке:",
            "1. **Резюме** — общее состояние здоровья в 1-2 предложениях",
            "2. **Проблемы** — обнаруженные проблемы, ранжированные по серьёзности",
            "3. **Рекомендации** — конкретные практические шаги для исправления",
            "4. **Уровень риска** — Низкий / Средний / Высокий / Критический",
            "",
            "Будь конкретным. Если всё в порядке, скажи это кратко. Отвечай на русском языке.",
        ]
    )

    full_prompt = "\n".join(prompt_parts)
    provider = LLMProvider()
    from core_ui.services.ai_execution_context import build_execution_context

    execution_context = build_execution_context(
        actor_user_id=request.user.pk,
        project_id=server.project_id,
        purpose="opssummary",
        source_kind="server_monitoring_analysis",
        source_id=server.pk,
        stored_binding=data.get("provider_binding"),
        idempotency_key=f"server-monitoring:{server.pk}:{getattr(last_check, 'pk', 'none')}",
    )

    async def _collect():
        chunks = []
        async for chunk in provider.stream_chat(
            full_prompt,
            model="auto",
            execution_context=execution_context,
        ):
            chunks.append(chunk)
        return "".join(chunks)

    try:
        result = async_to_sync(_collect)()
    except Exception as exc:
        return internal_error_response(request, exc)

    log_user_activity(
        user=request.user,
        request=request,
        category="monitoring",
        action="ai_analyze_server",
        entity_type="server",
        entity_id=str(server_id),
        entity_name=server.name,
    )

    return JsonResponse({"success": True, "analysis": result, "server_name": server.name})
