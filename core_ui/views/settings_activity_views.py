"""
Settings activity log API and export endpoints.
"""

import csv
import json
from datetime import UTC, datetime, timedelta
from io import StringIO

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from loguru import logger

from core_ui.decorators import require_feature
from core_ui.models import UserActivityLog


def _parse_int_query(request, name: str, default: int) -> int:
    try:
        return int(request.GET.get(name, default))
    except (TypeError, ValueError):
        return default


def _activity_username(row: UserActivityLog) -> str:
    if row.user_id and row.user:
        return row.user.username
    if row.username_snapshot:
        return row.username_snapshot
    return "unknown"


def _activity_event_payload(row: UserActivityLog) -> dict:
    return {
        "id": row.id,
        "created_at": row.created_at.isoformat(),
        "user_id": row.user_id,
        "username": _activity_username(row),
        "category": row.category,
        "action": row.action,
        "status": row.status,
        "description": row.description,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "entity_name": row.entity_name,
        "ip_address": row.ip_address or "",
        "user_agent": row.user_agent or "",
        "metadata": row.metadata or {},
    }


def _activity_csv_response(rows: list[UserActivityLog], days: int) -> HttpResponse:
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "created_at",
            "user_id",
            "username",
            "category",
            "action",
            "status",
            "description",
            "entity_type",
            "entity_id",
            "entity_name",
            "ip_address",
            "user_agent",
            "metadata",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.created_at.isoformat(),
                row.user_id or "",
                _activity_username(row),
                row.category,
                row.action,
                row.status,
                row.description,
                row.entity_type,
                row.entity_id,
                row.entity_name,
                row.ip_address or "",
                row.user_agent or "",
                json.dumps(row.metadata or {}, ensure_ascii=False),
            ]
        )
    response = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="activity-logs-{days}d.csv"'
    return response


def _activity_syslog_response(rows: list[UserActivityLog], days: int) -> HttpResponse:
    lines = []
    for row in rows:
        lines.append(
            f"{row.created_at.isoformat()} weu-audit username={_activity_username(row)} category={row.category} "
            f"action={row.action} status={row.status} entity={row.entity_type}:{row.entity_id} "
            f"description={json.dumps(row.description or '', ensure_ascii=False)} "
            f"metadata={json.dumps(row.metadata or {}, ensure_ascii=False)}"
        )
    response = HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="activity-logs-{days}d.syslog"'
    return response


@login_required
@require_feature("settings")
@require_GET
def api_settings_activity_logs(request):
    """Activity log stream and aggregated stats for settings page."""
    try:
        if not request.user.is_staff:
            return JsonResponse({"success": False, "error": "Forbidden"}, status=403)
        limit = max(1, min(_parse_int_query(request, "limit", 50), 200))
        offset = max(0, _parse_int_query(request, "offset", 0))
        days = max(1, min(_parse_int_query(request, "days", 14), 365))

        user_id_raw = (request.GET.get("user_id") or "").strip()
        category = (request.GET.get("category") or "").strip().lower()
        action = (request.GET.get("action") or "").strip().lower()
        status = (request.GET.get("status") or "").strip().lower()
        search = (request.GET.get("search") or "").strip()
        export_format = (request.GET.get("format") or "").strip().lower() or None

        filtered = UserActivityLog.objects.select_related("user").filter(
            created_at__gte=datetime.now(UTC) - timedelta(days=days)
        )

        if user_id_raw:
            try:
                filtered = filtered.filter(user_id=int(user_id_raw))
            except (TypeError, ValueError):
                return JsonResponse({"success": False, "error": "Invalid user_id"}, status=400)
        if category and category != "all":
            filtered = filtered.filter(category=category)
        if action and action != "all":
            filtered = filtered.filter(action=action)
        if status and status != "all":
            filtered = filtered.filter(status=status)
        if search:
            filtered = filtered.filter(
                Q(username_snapshot__icontains=search)
                | Q(action__icontains=search)
                | Q(category__icontains=search)
                | Q(description__icontains=search)
                | Q(entity_name__icontains=search)
            )

        total = filtered.count()
        ordered_qs = filtered.order_by("-created_at")
        if export_format in {"csv", "syslog"}:
            export_rows = list(ordered_qs[:5000])
            if export_format == "csv":
                return _activity_csv_response(export_rows, days)
            return _activity_syslog_response(export_rows, days)

        events = [_activity_event_payload(row) for row in ordered_qs[offset : offset + limit]]

        summary = {
            "total_events": total,
            "total_users": filtered.exclude(user_id__isnull=True).values("user_id").distinct().count(),
            "login_count": filtered.filter(action="login").count(),
            "assistant_requests": filtered.filter(
                action__in=["chat_request", "terminal_ai_request", "llm_request"]
            ).count(),
            "server_connections": filtered.filter(action="terminal_connect").count(),
            "server_changes": filtered.filter(
                action__in=["server_create", "server_update", "server_delete", "servers_bulk_update"]
            ).count(),
        }

        user_stats_rows = (
            filtered.values("user_id", "user__username", "username_snapshot")
            .annotate(
                events_total=Count("id"),
                logins=Count("id", filter=Q(action="login")),
                ai_requests=Count("id", filter=Q(action__in=["chat_request", "terminal_ai_request", "llm_request"])),
                server_connections=Count("id", filter=Q(action="terminal_connect")),
                server_changes=Count(
                    "id",
                    filter=Q(action__in=["server_create", "server_update", "server_delete", "servers_bulk_update"]),
                ),
            )
            .order_by("-events_total")[:50]
        )

        user_stats = [
            {
                "user_id": row.get("user_id"),
                "username": row.get("user__username") or row.get("username_snapshot") or "unknown",
                "events_total": row.get("events_total", 0),
                "logins": row.get("logins", 0),
                "ai_requests": row.get("ai_requests", 0),
                "server_connections": row.get("server_connections", 0),
                "server_changes": row.get("server_changes", 0),
            }
            for row in user_stats_rows
        ]

        users = list(
            UserActivityLog.objects.exclude(user_id__isnull=True)
            .values("user_id", "user__username")
            .distinct()
            .order_by("user__username")[:500]
        )
        user_options = [
            {
                "id": row.get("user_id"),
                "username": row.get("user__username") or "unknown",
            }
            for row in users
        ]

        return JsonResponse(
            {
                "success": True,
                "events": events,
                "summary": summary,
                "user_stats": user_stats,
                "users": user_options,
                "paging": {
                    "limit": limit,
                    "offset": offset,
                    "total": total,
                    "has_more": (offset + limit) < total,
                },
            }
        )
    except Exception as exc:
        logger.exception("api_settings_activity_logs error: %s", exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)
