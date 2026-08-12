"""
Server SSR page and SPA bootstrap views.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from core_ui.models import UserActivityLog
from servers.models import GlobalServerRules, Server, ServerConnection, ServerGroup, ServerGroupMember, ServerShare
from servers.secret_utils import has_saved_server_sudo_secret
from servers.ssh_host_keys import has_trusted_host_keys
from servers.views.server_helpers import _accessible_servers_queryset, _serialize_detected_os_fields


def _frontend_app_url(path: str) -> str:
    base = str(getattr(settings, "FRONTEND_APP_URL", "") or "").rstrip("/")
    if not base:
        return path
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{base}{normalized}"


def _active_terminal_connections_queryset():
    queryset = ServerConnection.objects.filter(status="connected", disconnected_at__isnull=True)
    stale_seconds = max(int(getattr(settings, "SSH_TERMINAL_SESSION_STALE_SECONDS", 0) or 0), 0)
    if stale_seconds <= 0:
        return queryset
    cutoff = timezone.now() - timedelta(seconds=stale_seconds)
    return queryset.filter(last_seen_at__gte=cutoff)


@login_required
@require_feature("servers", redirect_on_forbidden=True)
def server_list(request):
    now = timezone.now()
    servers_qs = _accessible_servers_queryset(request.user)
    servers = list(servers_qs.order_by("group__name", "name"))
    server_ids = [server.id for server in servers]

    active_shares = (
        ServerShare.objects.select_related("shared_by")
        .filter(user=request.user, is_revoked=False, server_id__in=server_ids)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    )
    shares_by_server = {share.server_id: share for share in active_shares}

    connected_server_ids = set(
        _active_terminal_connections_queryset().filter(server_id__in=server_ids).values_list("server_id", flat=True)
    )
    groups = list(ServerGroup.objects.filter(user=request.user).order_by("name"))
    all_users = list(User.objects.exclude(id=request.user.id).values("id", "username"))

    servers_data = []
    for server in servers:
        share = shares_by_server.get(server.id)
        is_shared = bool(share) and server.user_id != request.user.id
        status = _frontend_status_for_server(server, connected_server_ids, now)
        servers_data.append(
            {
                "obj": server,
                "status": status,
                "is_shared": is_shared,
                "can_edit": server.user_id == request.user.id,
                "shared_by": share.shared_by.username if share and share.shared_by else None,
            }
        )

    global_rules = GlobalServerRules.objects.filter(user=request.user).first()
    has_master_password = bool(request.session.get("_mp"))

    return render(
        request,
        "servers/list.html",
        {
            "servers_data": servers_data,
            "groups": groups,
            "all_users": all_users,
            "global_rules": global_rules,
            "has_master_password": has_master_password,
        },
    )


def _frontend_status_for_server(server: Server, connected_server_ids: set[int], now):
    if server.id in connected_server_ids:
        return "online"
    if server.last_connected:
        if now - server.last_connected <= timedelta(minutes=15):
            return "online"
        return "offline"
    return "unknown"


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def frontend_bootstrap(request):
    """JSON bootstrap payload for external SPA frontend."""
    now = timezone.now()
    servers = list(_accessible_servers_queryset(request.user))
    server_ids = [server.id for server in servers]
    accessible_groups = list(
        ServerGroup.objects.filter(Q(user=request.user) | Q(memberships__user=request.user)).distinct().order_by("name")
    )
    group_ids = {group.id for group in accessible_groups}
    group_ids.update(server.group_id for server in servers if server.group_id)
    memberships_by_group = {
        membership.group_id: membership.role
        for membership in ServerGroupMember.objects.filter(group_id__in=group_ids, user=request.user)
    }

    active_shares = (
        ServerShare.objects.select_related("shared_by")
        .filter(user=request.user, is_revoked=False, server_id__in=server_ids)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    )
    shares_by_server = {share.server_id: share for share in active_shares}

    connected_server_ids = set(
        _active_terminal_connections_queryset().filter(server_id__in=server_ids).values_list("server_id", flat=True)
    )

    servers_payload = []

    def serialize_group(group: ServerGroup | None) -> dict:
        if not group:
            return {
                "id": None,
                "name": "Ungrouped",
                "description": "",
                "color": "#6b7280",
                "server_count": 0,
                "role": "",
                "can_edit": False,
            }

        role = "owner" if group.user_id == request.user.id else memberships_by_group.get(group.id, "")
        return {
            "id": group.id,
            "name": group.name,
            "description": group.description or "",
            "color": group.color or "#3b82f6",
            "server_count": 0,
            "role": role,
            "can_edit": role in {"owner", "admin"},
        }

    groups_index: dict[str, dict] = {str(group.id): serialize_group(group) for group in accessible_groups}
    owned_count = 0
    shared_count = 0

    for server in sorted(
        servers, key=lambda item: (item.group.name.lower() if item.group else "zzzz", item.name.lower())
    ):
        share = shares_by_server.get(server.id)
        is_shared = bool(share) and server.user_id != request.user.id
        if is_shared:
            shared_count += 1
        else:
            owned_count += 1

        group_name = server.group.name if server.group else "Ungrouped"
        status = _frontend_status_for_server(server, connected_server_ids, now)
        item = {
            "id": server.id,
            "name": server.name,
            "host": server.host,
            "port": int(server.port or 0),
            "username": server.username,
            "server_type": server.server_type or "ssh",
            "status": status,
            "group_id": server.group_id,
            "group_name": group_name,
            "is_shared": is_shared,
            "can_edit": bool(server.user_id == request.user.id),
            "share_context_enabled": bool(share.share_context) if share else True,
            "shared_by_username": share.shared_by.username if share and share.shared_by else "",
            "terminal_path": f"/servers/{server.id}/terminal/",
            "minimal_terminal_path": f"/servers/{server.id}/terminal/minimal/",
            "last_connected": server.last_connected.isoformat() if server.last_connected else None,
            "ai_read_only": bool(getattr(server, "ai_read_only", True)),
            "sudo_auth_mode": getattr(server, "sudo_auth_mode", "none") or "none",
            "has_saved_sudo_password": bool(server.user_id == request.user.id and has_saved_server_sudo_secret(server)),
            "has_trusted_host_keys": has_trusted_host_keys(server),
            **_serialize_detected_os_fields(server),
        }
        servers_payload.append(item)

        key = str(server.group_id or "ungrouped")
        if key not in groups_index:
            groups_index[key] = serialize_group(server.group if server.group_id else None)
        groups_index[key]["server_count"] += 1

    recent_activity = list(
        UserActivityLog.objects.filter(user=request.user, category="servers")
        .order_by("-created_at")
        .values("id", "action", "status", "description", "entity_name", "created_at")[:12]
    )
    for row in recent_activity:
        row["created_at"] = row["created_at"].isoformat() if row.get("created_at") else None

    from servers.os_detect_service import schedule_os_detect_after_bootstrap

    schedule_os_detect_after_bootstrap(servers)

    return JsonResponse(
        {
            "success": True,
            "servers": servers_payload,
            "groups": sorted(groups_index.values(), key=lambda group: group["name"].lower()),
            "stats": {
                "owned": owned_count,
                "shared": shared_count,
                "total": len(servers_payload),
            },
            "recent_activity": recent_activity,
        }
    )


@login_required
@require_feature("servers", redirect_on_forbidden=True)
def server_terminal_page(request, server_id: int):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    all_servers = list(_accessible_servers_queryset(request.user).order_by("name"))
    has_master_password = bool(request.session.get("_mp"))
    return render(
        request,
        "servers/terminal.html",
        {
            "server": server,
            "all_servers": all_servers,
            "has_master_password": has_master_password,
        },
    )


@login_required
@require_feature("servers", redirect_on_forbidden=True)
def multi_terminal(request):
    all_servers = list(_accessible_servers_queryset(request.user).order_by("name"))
    return render(
        request,
        "servers/multi_terminal.html",
        {
            "all_servers": all_servers,
            "has_master_password": bool(request.session.get("_mp")),
        },
    )


@login_required
@require_feature("servers", redirect_on_forbidden=True)
def terminal_minimal(request, server_id: int):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    all_servers = list(_accessible_servers_queryset(request.user).order_by("name"))
    return render(
        request,
        "servers/terminal_minimal.html",
        {
            "server": server,
            "all_servers": all_servers,
            "has_master_password": bool(request.session.get("_mp")),
        },
    )
