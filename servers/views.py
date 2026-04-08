"""
Server Management Views
"""
import contextlib
import json
import os
import tempfile
from datetime import timedelta
from asgiref.sync import async_to_sync
from django.shortcuts import get_object_or_404, redirect, render
from django.http import FileResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.contrib.auth.models import User
from django.db import transaction
from django.conf import settings
from django.core.cache import cache
from .models import (
    Server,
    ServerShare,
    ServerGroup,
    ServerCommandHistory,
    ServerKnowledge,
    ServerGroupMember,
    ServerGroupTag,
    ServerGroupSubscription,
    GlobalServerRules,
    ServerHealthCheck,
    ServerAlert,
    ServerAgent,
    AgentRun,
    AgentRunEvent,
    ServerWatcherDraft,
)
from app.runtime_limits import get_active_terminal_connections_queryset, get_agent_run_limit_error
from app.tools.ssh_tools import ssh_manager
from core_ui.activity import log_user_activity
from core_ui.access import feature_allowed_for_user
from core_ui.models import UserActivityLog
from core_ui.decorators import require_feature
from passwords.encryption import PasswordEncryption
from .agent_background import launch_plan_execution_background
from .agent_launch import launch_full_agent_run
from .agent_service import (
    approve_agent_plan_for_user,
    dispatch_scheduled_agents_for_user,
    launch_watcher_draft_for_user,
    list_agents_for_user,
    list_scheduled_agents_for_user,
    reply_to_agent_run_for_user,
    start_agent_run_for_user,
    stop_agent_run_for_user,
)
from .agent_runtime import get_engine_for_agent, get_engine_for_run, update_runtime_control
from .linux_ui import (
    get_linux_ui_capabilities,
    get_linux_ui_settings,
    get_linux_ui_disk,
    get_linux_ui_docker,
    get_linux_ui_docker_logs,
    get_linux_ui_logs,
    get_linux_ui_network,
    get_linux_ui_overview,
    get_linux_ui_packages,
    get_linux_ui_processes,
    get_linux_ui_service_logs,
    get_linux_ui_services,
    run_linux_ui_docker_action,
    run_linux_ui_process_action,
    run_linux_ui_service_action,
)
from .sftp import (
    change_owner,
    change_permissions,
    create_directory,
    delete_path,
    download_file,
    get_directory_listing,
    read_text_file,
    rename_path,
    upload_local_file,
    write_text_file,
)
from .secret_utils import clear_server_auth_secret, get_server_auth_secret, has_saved_server_secret, store_server_auth_secret
from .ssh_host_keys import clear_server_trusted_host_keys, get_server_trusted_host_keys
from .run_events import record_run_event, serialize_run_event
from .agent_dispatch import serialize_agent_dispatch
from .watcher_service import WatcherService
from .watcher_actions import ensure_watcher_agent, mark_watcher_draft_launched

PASSWORD_ENCRYPTION_COMPAT = PasswordEncryption


def _frontend_app_url(path: str) -> str:
    base = str(getattr(settings, "FRONTEND_APP_URL", "") or "").rstrip("/")
    if not base:
        return path
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{base}{normalized}"


@login_required
@require_feature('servers', redirect_on_forbidden=True)
def server_list(request):
    now = timezone.now()
    servers_qs = _accessible_servers_queryset(request.user)
    servers = list(servers_qs.order_by('group__name', 'name'))
    server_ids = [s.id for s in servers]

    active_shares = (
        ServerShare.objects.select_related("shared_by")
        .filter(user=request.user, is_revoked=False, server_id__in=server_ids)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    )
    shares_by_server = {s.server_id: s for s in active_shares}

    connected_server_ids = set(
        get_active_terminal_connections_queryset().filter(server_id__in=server_ids).values_list("server_id", flat=True)
    )

    groups = list(ServerGroup.objects.filter(user=request.user).order_by('name'))
    all_users = list(User.objects.exclude(id=request.user.id).values('id', 'username'))

    servers_data = []
    for server in servers:
        share = shares_by_server.get(server.id)
        is_shared = bool(share) and server.user_id != request.user.id
        status = _frontend_status_for_server(server, connected_server_ids, now)
        servers_data.append({
            'obj': server,
            'status': status,
            'is_shared': is_shared,
            'can_edit': server.user_id == request.user.id,
            'shared_by': share.shared_by.username if share and share.shared_by else None,
        })

    global_rules = GlobalServerRules.objects.filter(user=request.user).first()
    has_master_password = bool(request.session.get('_mp'))

    return render(request, 'servers/list.html', {
        'servers_data': servers_data,
        'groups': groups,
        'all_users': all_users,
        'global_rules': global_rules,
        'has_master_password': has_master_password,
    })


def _frontend_status_for_server(server: Server, connected_server_ids: set[int], now):
    if server.id in connected_server_ids:
        return "online"
    if server.last_connected:
        if now - server.last_connected <= timedelta(minutes=15):
            return "online"
        return "offline"
    return "unknown"


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def frontend_bootstrap(request):
    """JSON bootstrap payload for external SPA frontend."""
    now = timezone.now()
    servers = list(_accessible_servers_queryset(request.user))
    server_ids = [s.id for s in servers]
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
    shares_by_server = {s.server_id: s for s in active_shares}

    connected_server_ids = set(
        get_active_terminal_connections_queryset().filter(server_id__in=server_ids).values_list("server_id", flat=True)
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

    groups_index: dict[str, dict] = {
        str(group.id): serialize_group(group)
        for group in accessible_groups
    }
    owned_count = 0
    shared_count = 0

    for server in sorted(servers, key=lambda item: (item.group.name.lower() if item.group else "zzzz", item.name.lower())):
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
            "rdp": bool(server.is_rdp()),
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

    return JsonResponse(
        {
            "success": True,
            "servers": servers_payload,
            "groups": sorted(groups_index.values(), key=lambda g: g["name"].lower()),
            "stats": {
                "owned": owned_count,
                "shared": shared_count,
                "total": len(servers_payload),
            },
            "recent_activity": recent_activity,
        }
    )


@login_required
@require_feature('servers', redirect_on_forbidden=True)
def server_terminal_page(request, server_id: int):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if server.is_rdp():
        return render(request, 'servers/rdp_terminal.html', {
            'server': server,
            'has_master_password': bool(request.session.get('_mp')),
        })
    all_servers = list(_accessible_servers_queryset(request.user).order_by('name'))
    has_master_password = bool(request.session.get('_mp'))
    return render(request, 'servers/terminal.html', {
        'server': server,
        'all_servers': all_servers,
        'has_master_password': has_master_password,
    })


@login_required
@require_feature('servers', redirect_on_forbidden=True)
def multi_terminal(request):
    all_servers = list(_accessible_servers_queryset(request.user).order_by('name'))
    return render(request, 'servers/multi_terminal.html', {
        'all_servers': all_servers,
        'has_master_password': bool(request.session.get('_mp')),
    })


@login_required
@require_feature('servers', redirect_on_forbidden=True)
def terminal_minimal(request, server_id: int):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if server.is_rdp():
        return render(request, 'servers/rdp_terminal_minimal.html', {
            'server': server,
            'has_master_password': bool(request.session.get('_mp')),
        })
    all_servers = list(_accessible_servers_queryset(request.user).order_by('name'))
    return render(request, 'servers/terminal_minimal.html', {
        'server': server,
        'all_servers': all_servers,
        'has_master_password': bool(request.session.get('_mp')),
    })


def _get_group_role(group: ServerGroup, user: User) -> str:
    if group.user_id == user.id:
        return "owner"
    membership = ServerGroupMember.objects.filter(group=group, user=user).first()
    return membership.role if membership else ""


def _active_share_q(user: User) -> Q:
    now = timezone.now()
    return (
        Q(shares__user=user, shares__is_revoked=False)
        & (Q(shares__expires_at__isnull=True) | Q(shares__expires_at__gt=now))
    )


def _accessible_servers_queryset(user: User):
    return (
        Server.objects.select_related("group", "user")
        .filter(is_active=True)
        .filter(Q(user=user) | _active_share_q(user))
        .distinct()
    )


def _active_server_share(server: Server, user: User) -> ServerShare | None:
    if not server or server.user_id == user.id:
        return None
    now = timezone.now()
    return (
        ServerShare.objects.filter(server=server, user=user, is_revoked=False)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .first()
    )


def _shared_server_context_allowed(server: Server, user: User, share: ServerShare | None = None) -> bool:
    if not server:
        return False
    if server.user_id == user.id:
        return True
    active_share = share if share is not None else _active_server_share(server, user)
    return bool(active_share and active_share.share_context)


def _effective_master_password(request, data: dict | None = None) -> str:
    """Resolve master password from payload, session, or env."""
    data = data or {}
    from_payload = str(data.get("master_password") or "").strip()
    if from_payload:
        return from_payload

    try:
        from_session = str(request.session.get("_mp") or "").strip()
    except Exception:
        from_session = ""
    if from_session:
        return from_session

    return str(os.environ.get("MASTER_PASSWORD") or "").strip()


def _resolve_server_secret(server: Server, request, data: dict) -> str | None:
    """
    Resolve server password/passphrase from encrypted secret or direct payload.
    """
    if server.auth_method not in ["password", "key_password"]:
        return None

    direct_secret = str(data.get("password") or "").strip()
    master_password = _effective_master_password(request, data)
    try:
        secret = get_server_auth_secret(
            server,
            master_password=master_password,
            fallback_plain=direct_secret,
        )
    except ValueError as exc:
        raise ValueError("Не удалось расшифровать пароль сервера. Проверь MASTER_PASSWORD в .env.") from exc
    return secret or None


def _parse_expires_at(raw_value):
    if raw_value in (None, "", "null", "None"):
        return None
    dt = parse_datetime(str(raw_value))
    if not dt:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _parse_bool(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _require_ssh_server(server: Server) -> None:
    if server.is_rdp():
        raise ValueError("SFTP доступен только для SSH-серверов")


def _materialize_uploaded_file(uploaded_file) -> tuple[str, bool]:
    try:
        return uploaded_file.temporary_file_path(), False
    except Exception:
        pass

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        for chunk in uploaded_file.chunks():
            tmp.write(chunk)
        return tmp.name, True


def _sftp_error_response(exc: Exception) -> JsonResponse:
    if isinstance(exc, FileNotFoundError):
        return JsonResponse({"success": False, "error": "Файл или папка не найдены"}, status=404)
    if isinstance(exc, FileExistsError):
        return JsonResponse({"success": False, "error": "Файл уже существует"}, status=409)
    if isinstance(exc, NotADirectoryError):
        return JsonResponse({"success": False, "error": "Указанный путь не является папкой"}, status=400)
    if isinstance(exc, IsADirectoryError):
        return JsonResponse({"success": False, "error": "Операция требует файл, а не папку"}, status=400)
    if isinstance(exc, PermissionError):
        return JsonResponse({"success": False, "error": "Недостаточно прав для выполнения операции"}, status=403)
    if isinstance(exc, ValueError):
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    return JsonResponse({"success": False, "error": str(exc) or "SFTP operation failed"}, status=500)


def _linux_ui_error_response(exc: Exception) -> JsonResponse:
    if isinstance(exc, ValueError):
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    if isinstance(exc, PermissionError):
        return JsonResponse({"success": False, "error": "Недостаточно прав для выполнения операции"}, status=403)
    return JsonResponse({"success": False, "error": str(exc) or "Linux UI request failed"}, status=500)


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def group_create(request):
    data = json.loads(request.body)
    name = data.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "Group name required"}, status=400)

    group = ServerGroup.objects.create(
        user=request.user,
        name=name,
        description=data.get("description", ""),
        color=data.get("color", "#3b82f6"),
    )
    ServerGroupMember.objects.create(group=group, user=request.user, role="owner")

    tag_ids = data.get("tag_ids", [])
    if tag_ids:
        group.tags.set(ServerGroupTag.objects.filter(id__in=tag_ids, user=request.user))

    log_user_activity(
        user=request.user,
        request=request,
        category='servers',
        action='group_create',
        status=UserActivityLog.STATUS_SUCCESS,
        description=f'Created server group "{group.name}"',
        entity_type='server_group',
        entity_id=group.id,
        entity_name=group.name,
    )

    return JsonResponse({"success": True, "group_id": group.id})


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def group_update(request, group_id):
    group = get_object_or_404(ServerGroup, id=group_id)
    role = _get_group_role(group, request.user)
    if role not in ["owner", "admin"]:
        return JsonResponse({"error": "Permission denied"}, status=403)

    data = json.loads(request.body)
    group.name = data.get("name", group.name)
    group.description = data.get("description", group.description)
    group.color = data.get("color", group.color)
    group.save()

    if "tag_ids" in data:
        group.tags.set(ServerGroupTag.objects.filter(id__in=data.get("tag_ids", []), user=request.user))

    log_user_activity(
        user=request.user,
        request=request,
        category='servers',
        action='group_update',
        status=UserActivityLog.STATUS_SUCCESS,
        description=f'Updated server group "{group.name}"',
        entity_type='server_group',
        entity_id=group.id,
        entity_name=group.name,
    )

    return JsonResponse({"success": True})


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def group_delete(request, group_id):
    group = get_object_or_404(ServerGroup, id=group_id)
    if _get_group_role(group, request.user) != "owner":
        return JsonResponse({"error": "Only owner can delete group"}, status=403)
    group_name = group.name
    group.delete()
    log_user_activity(
        user=request.user,
        request=request,
        category='servers',
        action='group_delete',
        status=UserActivityLog.STATUS_SUCCESS,
        description=f'Deleted server group "{group_name}"',
        entity_type='server_group',
        entity_id=group_id,
        entity_name=group_name,
    )
    return JsonResponse({"success": True})


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def group_add_member(request, group_id):
    group = get_object_or_404(ServerGroup, id=group_id)
    role = _get_group_role(group, request.user)
    if role not in ["owner", "admin"]:
        return JsonResponse({"error": "Permission denied"}, status=403)

    data = json.loads(request.body)
    identifier = data.get("user")
    member_role = data.get("role", "member")
    if not identifier:
        return JsonResponse({"error": "User required"}, status=400)

    user = User.objects.filter(username=identifier).first() or User.objects.filter(email=identifier).first()
    if not user:
        return JsonResponse({"error": "User not found"}, status=404)

    ServerGroupMember.objects.update_or_create(group=group, user=user, defaults={"role": member_role})
    return JsonResponse({"success": True})


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def group_remove_member(request, group_id):
    group = get_object_or_404(ServerGroup, id=group_id)
    role = _get_group_role(group, request.user)
    if role not in ["owner", "admin"]:
        return JsonResponse({"error": "Permission denied"}, status=403)

    data = json.loads(request.body)
    user_id = data.get("user_id")
    if not user_id:
        return JsonResponse({"error": "User required"}, status=400)
    ServerGroupMember.objects.filter(group=group, user_id=user_id).delete()
    return JsonResponse({"success": True})


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def group_subscribe(request, group_id):
    group = get_object_or_404(ServerGroup, id=group_id)
    data = json.loads(request.body)
    kind = data.get("kind", "follow")
    if kind not in ["follow", "favorite"]:
        return JsonResponse({"error": "Invalid kind"}, status=400)
    ServerGroupSubscription.objects.update_or_create(group=group, user=request.user, kind=kind)
    return JsonResponse({"success": True})


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def bulk_update_servers(request):
    data = json.loads(request.body)
    server_ids = data.get("server_ids", [])
    if not server_ids:
        return JsonResponse({"error": "server_ids required"}, status=400)

    updates = {}
    if "group_id" in data:
        group_id = data.get("group_id")
        if group_id:
            group = get_object_or_404(ServerGroup, id=group_id)
            if _get_group_role(group, request.user) == "":
                return JsonResponse({"error": "Permission denied"}, status=403)
        updates["group_id"] = group_id

    if "tags" in data:
        updates["tags"] = data.get("tags", "")

    if "is_active" in data:
        updates["is_active"] = bool(data.get("is_active"))

    updated_count = Server.objects.filter(user=request.user, id__in=server_ids).update(**updates)
    if updated_count:
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='servers_bulk_update',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Bulk updated {updated_count} servers',
            entity_type='server',
            entity_name='bulk',
            metadata={
                'server_ids': server_ids[:200],
                'updated_fields': sorted(list(updates.keys())),
                'updated_count': updated_count,
            },
        )
    return JsonResponse({"success": True})


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_create(request):
    """Create a new server"""
    try:
        data = json.loads(request.body)

        # Validate and normalize core fields
        raw_port = data.get("port", 22)
        try:
            port = int(raw_port)
        except (TypeError, ValueError):
            return JsonResponse({"error": "Invalid port"}, status=400)
        if port < 1 or port > 65535:
            return JsonResponse({"error": "Port must be in range 1..65535"}, status=400)

        server_type = str(data.get("server_type", "ssh") or "ssh").strip().lower()
        if server_type not in ("ssh", "rdp"):
            return JsonResponse({"error": "Invalid server_type"}, status=400)

        group = None
        group_id = data.get("group_id")
        if isinstance(group_id, str):
            group_id = group_id.strip()
        if group_id in ("", "null", "None"):
            group_id = None
        if group_id is not None:
            try:
                group_id = int(group_id)
            except (TypeError, ValueError):
                return JsonResponse({"error": "Invalid group_id"}, status=400)
            try:
                group = ServerGroup.objects.get(id=group_id)
                if _get_group_role(group, request.user) == "":
                    return JsonResponse({'error': 'Permission denied for group'}, status=403)
            except ServerGroup.DoesNotExist:
                return JsonResponse({'error': 'Invalid group'}, status=400)
        
        # Create server
        server = Server.objects.create(
            user=request.user,
            name=data.get('name', ''),
            server_type=server_type,
            host=data.get('host', ''),
            port=port,
            username=data.get('username', ''),
            auth_method=data.get('auth_method', 'password'),
            key_path=data.get('key_path', ''),
            tags=data.get('tags', ''),
            notes=data.get('notes', ''),
            corporate_context=data.get('corporate_context', ''),
            group=group,
        )
        
        # Store password/passphrase in managed secrets; legacy encryption remains optional.
        password = str(data.get('password', '') or '').strip()
        master_password = _effective_master_password(request, data)
        if password:
            store_server_auth_secret(server, secret_value=password, master_password=master_password)
            server.save()
        
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_create',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Created server "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata={
                'host': server.host,
                'port': server.port,
                'server_type': server.server_type,
                'group_id': server.group_id,
            },
        )

        return JsonResponse({
            'success': True,
            'server_id': server.id,
            'message': 'Server created successfully'
        })
        
    except Exception as e:
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_create',
            status=UserActivityLog.STATUS_ERROR,
            description=f'Server create failed: {e}',
            entity_type='server',
        )
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_update(request, server_id):
    """Update server configuration including network_config"""
    try:
        server = get_object_or_404(Server, id=server_id, user=request.user)
        data = json.loads(request.body)
        host_changed = False
        
        # Update basic fields
        if 'name' in data:
            server.name = data['name']
        if 'host' in data:
            next_host = str(data['host'] or '')
            host_changed = host_changed or next_host != server.host
            server.host = next_host
        if 'port' in data:
            try:
                port = int(data['port'])
            except (TypeError, ValueError):
                return JsonResponse({'error': 'Invalid port'}, status=400)
            if port < 1 or port > 65535:
                return JsonResponse({'error': 'Port must be in range 1..65535'}, status=400)
            host_changed = host_changed or port != int(server.port or 22)
            server.port = port
        if 'username' in data:
            server.username = data['username']
        if 'server_type' in data:
            server_type = str(data.get('server_type') or '').strip().lower()
            if server_type not in ('ssh', 'rdp'):
                return JsonResponse({'error': 'Invalid server_type'}, status=400)
            server.server_type = server_type
        if 'auth_method' in data:
            server.auth_method = data['auth_method']
        if 'key_path' in data:
            server.key_path = data['key_path']
        if 'tags' in data:
            server.tags = data['tags']
        if 'notes' in data:
            server.notes = data['notes']
        if 'corporate_context' in data:
            server.corporate_context = data['corporate_context']
        if 'is_active' in data:
            server.is_active = data['is_active']
        
        # Update group
        if 'group_id' in data:
            group_id = data.get('group_id')
            if isinstance(group_id, str):
                group_id = group_id.strip()
            if group_id in ("", "null", "None"):
                group_id = None

            if group_id is not None:
                try:
                    group_id = int(group_id)
                except (TypeError, ValueError):
                    return JsonResponse({'error': 'Invalid group_id'}, status=400)
                try:
                    group = ServerGroup.objects.get(id=group_id)
                    if _get_group_role(group, request.user) == "":
                        return JsonResponse({'error': 'Permission denied for group'}, status=403)
                    server.group = group
                except ServerGroup.DoesNotExist:
                    return JsonResponse({'error': 'Invalid group'}, status=400)
            else:
                server.group = None
        
        # Update network_config
        if 'network_config' in data:
            network_config = data['network_config']
            if isinstance(network_config, dict):
                server.network_config = network_config
                # Обновляем helper flags
                server.update_network_flags()
        
        # Update password/passphrase in managed secrets; legacy encryption remains optional.
        if 'password' in data:
            password = str(data.get('password') or '').strip()
            master_password = _effective_master_password(request, data)
            if password:
                store_server_auth_secret(server, secret_value=password, master_password=master_password)

        if host_changed:
            clear_server_trusted_host_keys(server)
        
        changed_fields = sorted(list(data.keys()))
        server.save()
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_update',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Updated server "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata={'changed_fields': changed_fields},
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Server updated successfully',
            'server': {
                'id': server.id,
                'name': server.name,
                'host': server.host,
                'port': server.port,
                'network_context': server.get_network_context_summary()
            }
        })
        
    except Exception as e:
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_update',
            status=UserActivityLog.STATUS_ERROR,
            description=f'Server update failed: {e}',
            entity_type='server',
            entity_id=server_id,
        )
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_test_connection(request, server_id):
    """Test connection to server"""
    try:
        server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
        data = json.loads(request.body)
        refresh_host_key = bool(data.get("refresh_host_key"))
        if refresh_host_key and server.user_id != request.user.id:
            return JsonResponse({'success': False, 'error': 'Only owner can refresh trusted SSH host key'}, status=403)
        try:
            password = _resolve_server_secret(server, request, data)
        except ValueError as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
        
        # Test connection using SSH tools
        from asgiref.sync import async_to_sync
        
        async def test_conn():
            try:
                conn_id = await ssh_manager.connect(
                    host=server.host,
                    username=server.username,
                    password=password,
                    key_path=server.key_path if server.auth_method in ['key', 'key_password'] else None,
                    port=server.port,
                    network_config=server.network_config or {},
                    server=server,
                    refresh_host_key=refresh_host_key,
                )
                # Disconnect immediately after test
                await ssh_manager.disconnect(conn_id)
                return {'success': True, 'message': 'Connection successful'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        
        result = async_to_sync(test_conn)()
        
        if result['success']:
            server.last_connected = timezone.now()
            server.save(update_fields=['last_connected'])
            log_user_activity(
                user=request.user,
                request=request,
                category='servers',
                action='server_test_connection',
                status=UserActivityLog.STATUS_SUCCESS,
                description=f'Server connection test succeeded for "{server.name}"',
                entity_type='server',
                entity_id=server.id,
                entity_name=server.name,
                metadata={'host': server.host, 'port': server.port},
            )
        else:
            log_user_activity(
                user=request.user,
                request=request,
                category='servers',
                action='server_test_connection',
                status=UserActivityLog.STATUS_ERROR,
                description=f'Server connection test failed for "{server.name}": {result.get("error", "unknown error")}',
                entity_type='server',
                entity_id=server.id,
                entity_name=server.name,
                metadata={'host': server.host, 'port': server.port},
            )
        
        return JsonResponse(result)
        
    except Exception as e:
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_test_connection',
            status=UserActivityLog.STATUS_ERROR,
            description=f'Server connection test failed: {e}',
            entity_type='server',
            entity_id=server_id,
        )
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_execute_command(request, server_id):
    """Execute command on server"""
    try:
        server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
        data = json.loads(request.body)
        command = data.get('command', '')
        
        if not command:
            return JsonResponse({'error': 'Command required'}, status=400)
        
        try:
            password = _resolve_server_secret(server, request, data)
        except ValueError as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
        
        # Execute command
        from asgiref.sync import async_to_sync
        from app.tools.ssh_tools import SSHExecuteTool
        
        async def exec_cmd():
            try:
                # Connect
                conn_id = await ssh_manager.connect(
                    host=server.host,
                    username=server.username,
                    password=password,
                    key_path=server.key_path if server.auth_method in ['key', 'key_password'] else None,
                    port=server.port,
                    network_config=server.network_config or {},
                    server=server,
                )
                
                # Execute
                execute_tool = SSHExecuteTool()
                result = await execute_tool.execute(conn_id=conn_id, command=command)
                
                # Save to history
                out_str = result.get('stdout', '') + (result.get('stderr') or '')
                ServerCommandHistory.objects.create(
                    server=server,
                    user=request.user,
                    actor_kind=ServerCommandHistory.ACTOR_HUMAN,
                    source_kind=ServerCommandHistory.SOURCE_API,
                    command=command,
                    output=out_str or str(result),
                    exit_code=result.get('exit_code', 0),
                )
                
                # Disconnect
                await ssh_manager.disconnect(conn_id)
                
                return {'success': True, 'output': result}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        
        result = async_to_sync(exec_cmd)()
        if result.get('success'):
            output = result.get('output') or {}
            command_preview = command if len(command) <= 400 else command[:397] + '...'
            log_user_activity(
                user=request.user,
                request=request,
                category='servers',
                action='server_command_execute',
                status=UserActivityLog.STATUS_SUCCESS,
                description=f'Executed command on "{server.name}": {command_preview}',
                entity_type='server',
                entity_id=server.id,
                entity_name=server.name,
                metadata={
                    'command': command_preview,
                    'exit_code': output.get('exit_code'),
                },
            )
        else:
            log_user_activity(
                user=request.user,
                request=request,
                category='servers',
                action='server_command_execute',
                status=UserActivityLog.STATUS_ERROR,
                description=f'Command execution failed on "{server.name}": {result.get("error", "unknown error")}',
                entity_type='server',
                entity_id=server.id,
                entity_name=server.name,
                metadata={'command': command[:400]},
            )
        return JsonResponse(result)

    except Exception as e:
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_command_execute',
            status=UserActivityLog.STATUS_ERROR,
            description=f'Command execution failed: {e}',
            entity_type='server',
            entity_id=server_id,
        )
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_linux_ui_capabilities(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        secret = _resolve_server_secret(server, request, {})
        capabilities = async_to_sync(get_linux_ui_capabilities)(server, secret=secret or "")
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_linux_ui_capabilities',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Linux UI capabilities for "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
        )
        return JsonResponse({
            "success": True,
            "server": {
                "id": server.id,
                "name": server.name,
                "host": server.host,
                "username": server.username,
            },
            "capabilities": capabilities,
            "observed_at": timezone.now().isoformat(),
        })
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_linux_ui_settings(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        secret = _resolve_server_secret(server, request, {})
        settings_snapshot = async_to_sync(get_linux_ui_settings)(server, secret=secret or "")
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_linux_ui_settings',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Linux UI settings snapshot for "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
        )
        return JsonResponse({
            "success": True,
            "server": {
                "id": server.id,
                "name": server.name,
                "host": server.host,
                "username": server.username,
            },
            "settings": settings_snapshot,
            "observed_at": timezone.now().isoformat(),
        })
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_linux_ui_overview(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        secret = _resolve_server_secret(server, request, {})
        overview = async_to_sync(get_linux_ui_overview)(server, secret=secret or "")
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_linux_ui_overview',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Linux UI overview for "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
        )
        return JsonResponse({
            "success": True,
            "server": {
                "id": server.id,
                "name": server.name,
                "host": server.host,
                "username": server.username,
            },
            "overview": overview,
            "observed_at": timezone.now().isoformat(),
        })
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_linux_ui_services(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        secret = _resolve_server_secret(server, request, request.GET)
        services = async_to_sync(get_linux_ui_services)(
            server,
            secret=secret or "",
            limit=request.GET.get("limit") or 120,
        )
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_linux_ui_services',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Linux UI services for "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
        )
        return JsonResponse({
            "success": True,
            "server": {
                "id": server.id,
                "name": server.name,
                "host": server.host,
                "username": server.username,
            },
            "services": services["services"],
            "summary": services["summary"],
            "limit": services["limit"],
            "observed_at": timezone.now().isoformat(),
        })
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_linux_ui_service_logs(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        secret = _resolve_server_secret(server, request, request.GET)
        logs = async_to_sync(get_linux_ui_service_logs)(
            server,
            secret=secret or "",
            service=str(request.GET.get("service") or ""),
            lines=request.GET.get("lines") or 80,
        )
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_linux_ui_service_logs',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved service logs for "{logs["service"]}" on "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata={'service': logs["service"], 'source': logs["source"]},
        )
        return JsonResponse({
            "success": True,
            "server": {
                "id": server.id,
                "name": server.name,
                "host": server.host,
                "username": server.username,
            },
            "service_logs": logs,
            "observed_at": timezone.now().isoformat(),
        })
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_linux_ui_service_action(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        data = json.loads(request.body or "{}")
        secret = _resolve_server_secret(server, request, data)
        action_result = async_to_sync(run_linux_ui_service_action)(
            server,
            secret=secret or "",
            service=str(data.get("service") or ""),
            action=str(data.get("action") or ""),
        )
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_linux_ui_service_action',
            status=UserActivityLog.STATUS_SUCCESS if action_result.get("success") else UserActivityLog.STATUS_ERROR,
            description=(
                f'Ran Linux UI action "{action_result["action"]}" on "{action_result["service"]}" '
                f'for "{server.name}"'
            ),
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata={
                'service': action_result["service"],
                'action': action_result["action"],
                'dangerous': bool(action_result.get("dangerous")),
            },
        )
        return JsonResponse({
            "success": bool(action_result.get("success")),
            "server": {
                "id": server.id,
                "name": server.name,
                "host": server.host,
                "username": server.username,
            },
            "service_action": action_result,
            "performed_at": timezone.now().isoformat(),
        })
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_linux_ui_processes(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        secret = _resolve_server_secret(server, request, request.GET)
        processes = async_to_sync(get_linux_ui_processes)(
            server,
            secret=secret or "",
            limit=request.GET.get("limit") or 80,
        )
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_linux_ui_processes',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Linux UI processes for "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
        )
        return JsonResponse({
            "success": True,
            "server": {
                "id": server.id,
                "name": server.name,
                "host": server.host,
                "username": server.username,
            },
            "processes": processes,
            "observed_at": timezone.now().isoformat(),
        })
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_linux_ui_process_action(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        data = json.loads(request.body or "{}")
        secret = _resolve_server_secret(server, request, data)
        action_result = async_to_sync(run_linux_ui_process_action)(
            server,
            secret=secret or "",
            pid=data.get("pid"),
            action=str(data.get("action") or ""),
        )
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_linux_ui_process_action',
            status=UserActivityLog.STATUS_SUCCESS if action_result.get("success") else UserActivityLog.STATUS_ERROR,
            description=f'Ran Linux UI process action "{action_result["action"]}" on PID {action_result["pid"]} for "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata={
                'pid': action_result["pid"],
                'action': action_result["action"],
                'dangerous': bool(action_result.get("dangerous")),
            },
        )
        return JsonResponse({
            "success": bool(action_result.get("success")),
            "server": {
                "id": server.id,
                "name": server.name,
                "host": server.host,
                "username": server.username,
            },
            "process_action": action_result,
            "performed_at": timezone.now().isoformat(),
        })
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_linux_ui_logs(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        secret = _resolve_server_secret(server, request, request.GET)
        logs = async_to_sync(get_linux_ui_logs)(
            server,
            secret=secret or "",
            source=str(request.GET.get("source") or "journal"),
            lines=request.GET.get("lines") or 120,
            service=str(request.GET.get("service") or ""),
        )
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_linux_ui_logs',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Linux UI logs ({logs["source"]}) for "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata={'source': logs["source"], 'service': logs.get("service") or ""},
        )
        return JsonResponse({
            "success": True,
            "server": {
                "id": server.id,
                "name": server.name,
                "host": server.host,
                "username": server.username,
            },
            "logs": logs,
            "observed_at": timezone.now().isoformat(),
        })
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_linux_ui_disk(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        secret = _resolve_server_secret(server, request, request.GET)
        disk = async_to_sync(get_linux_ui_disk)(
            server,
            secret=secret or "",
        )
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_linux_ui_disk',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Linux UI disk data for "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata=disk.get("summary") or {},
        )
        return JsonResponse({
            "success": True,
            "server": {
                "id": server.id,
                "name": server.name,
                "host": server.host,
                "username": server.username,
            },
            "disk": disk,
            "observed_at": timezone.now().isoformat(),
        })
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_linux_ui_network(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        secret = _resolve_server_secret(server, request, request.GET)
        network = async_to_sync(get_linux_ui_network)(
            server,
            secret=secret or "",
        )
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_linux_ui_network',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Linux UI network data for "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata=network.get("summary") or {},
        )
        return JsonResponse({
            "success": True,
            "server": {
                "id": server.id,
                "name": server.name,
                "host": server.host,
                "username": server.username,
            },
            "network": network,
            "observed_at": timezone.now().isoformat(),
        })
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_linux_ui_packages(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        secret = _resolve_server_secret(server, request, request.GET)
        packages = async_to_sync(get_linux_ui_packages)(
            server,
            secret=secret or "",
        )
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_linux_ui_packages',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Linux UI package data for "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata={
                'package_manager': packages.get("package_manager") or "",
                **(packages.get("summary") or {}),
            },
        )
        return JsonResponse({
            "success": True,
            "server": {
                "id": server.id,
                "name": server.name,
                "host": server.host,
                "username": server.username,
            },
            "packages": packages,
            "observed_at": timezone.now().isoformat(),
        })
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_linux_ui_docker(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        secret = _resolve_server_secret(server, request, request.GET)
        docker_data = async_to_sync(get_linux_ui_docker)(
            server,
            secret=secret or "",
        )
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_linux_ui_docker',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Linux UI docker data for "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata=docker_data.get("summary") or {},
        )
        return JsonResponse({
            "success": True,
            "server": {
                "id": server.id,
                "name": server.name,
                "host": server.host,
                "username": server.username,
            },
            "docker": docker_data,
            "observed_at": timezone.now().isoformat(),
        })
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_linux_ui_docker_logs(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        secret = _resolve_server_secret(server, request, request.GET)
        docker_logs = async_to_sync(get_linux_ui_docker_logs)(
            server,
            secret=secret or "",
            container=str(request.GET.get("container") or ""),
            lines=request.GET.get("lines") or 80,
        )
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_linux_ui_docker_logs',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Docker logs for "{docker_logs["container"]}" on "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata={'container': docker_logs["container"], 'lines': docker_logs["lines"]},
        )
        return JsonResponse({
            "success": True,
            "server": {
                "id": server.id,
                "name": server.name,
                "host": server.host,
                "username": server.username,
            },
            "docker_logs": docker_logs,
            "observed_at": timezone.now().isoformat(),
        })
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_linux_ui_docker_action(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        data = json.loads(request.body or "{}")
        secret = _resolve_server_secret(server, request, data)
        action_result = async_to_sync(run_linux_ui_docker_action)(
            server,
            secret=secret or "",
            container=str(data.get("container") or ""),
            action=str(data.get("action") or ""),
        )
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_linux_ui_docker_action',
            status=UserActivityLog.STATUS_SUCCESS if action_result.get("success") else UserActivityLog.STATUS_ERROR,
            description=(
                f'Ran Docker action "{action_result["action"]}" on "{action_result["container"]}" '
                f'for "{server.name}"'
            ),
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata={
                'container': action_result["container"],
                'action': action_result["action"],
                'dangerous': bool(action_result.get("dangerous")),
            },
        )
        return JsonResponse({
            "success": bool(action_result.get("success")),
            "server": {
                "id": server.id,
                "name": server.name,
                "host": server.host,
                "username": server.username,
            },
            "docker_action": action_result,
            "performed_at": timezone.now().isoformat(),
        })
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_file_list(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        password = _resolve_server_secret(server, request, request.GET)
        result = async_to_sync(get_directory_listing)(
            server,
            secret=password or "",
            path=request.GET.get("path") or ".",
        )
        return JsonResponse({"success": True, **result})
    except Exception as exc:
        return _sftp_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_file_read_text(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        password = _resolve_server_secret(server, request, request.GET)
        result = async_to_sync(read_text_file)(
            server,
            secret=password or "",
            path=str(request.GET.get("path") or ""),
        )
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_file_read_text',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Read text file on "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata={'path': result["path"], 'size': result["size"]},
        )
        return JsonResponse({"success": True, "file": result})
    except Exception as exc:
        return _sftp_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_file_write_text(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        data = json.loads(request.body or "{}")
        password = _resolve_server_secret(server, request, data)
        result = async_to_sync(write_text_file)(
            server,
            secret=password or "",
            path=str(data.get("path") or ""),
            content=str(data.get("content") or ""),
        )
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_file_write_text',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Updated text file on "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata={'path': result["path"], 'size': result["size"]},
        )
        return JsonResponse({"success": True, "file": result})
    except Exception as exc:
        return _sftp_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_file_chmod(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        data = json.loads(request.body or "{}")
        password = _resolve_server_secret(server, request, data)
        result = async_to_sync(change_permissions)(
            server,
            secret=password or "",
            path=str(data.get("path") or ""),
            mode=str(data.get("mode") or ""),
        )
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_file_chmod',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Changed file permissions on "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata={'path': result["entry"]["path"], 'mode': data.get("mode")},
        )
        return JsonResponse({"success": True, **result})
    except Exception as exc:
        return _sftp_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_file_chown(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        data = json.loads(request.body or "{}")
        password = _resolve_server_secret(server, request, data)
        owner_spec = str(data.get("owner") or "").strip()
        owner_name = owner_spec
        group_name = ""
        if ":" in owner_spec:
            owner_name, group_name = owner_spec.split(":", 1)

        result = async_to_sync(change_owner)(
            server,
            secret=password or "",
            path=str(data.get("path") or ""),
            owner=owner_name or None,
            group=group_name or None,
            recursive=bool(data.get("recursive")),
        )
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_file_chown',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Changed file owner on "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata={
                'path': result["entry"]["path"],
                'owner': owner_spec,
                'recursive': bool(data.get("recursive")),
            },
        )
        return JsonResponse({"success": True, **result})
    except Exception as exc:
        return _sftp_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_file_upload(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        password = _resolve_server_secret(server, request, request.POST)
        target_path = request.POST.get("path") or "."
        overwrite = _parse_bool(request.POST.get("overwrite"))
        uploaded_files = request.FILES.getlist("files")
        if not uploaded_files:
            return JsonResponse({"success": False, "error": "Нет файлов для загрузки"}, status=400)

        uploaded_entries = []
        current_path = target_path
        for uploaded_file in uploaded_files:
            local_path, should_cleanup = _materialize_uploaded_file(uploaded_file)
            try:
                result = async_to_sync(upload_local_file)(
                    server,
                    secret=password or "",
                    remote_dir=target_path,
                    local_path=local_path,
                    remote_name=uploaded_file.name,
                    overwrite=overwrite,
                )
                current_path = result["path"]
                uploaded_entries.append(result["entry"])
            finally:
                if should_cleanup:
                    with contextlib.suppress(OSError):
                        os.remove(local_path)

        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_file_upload',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Uploaded {len(uploaded_entries)} file(s) to "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata={'path': current_path, 'count': len(uploaded_entries)},
        )
        return JsonResponse({"success": True, "path": current_path, "entries": uploaded_entries})
    except Exception as exc:
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_file_upload',
            status=UserActivityLog.STATUS_ERROR,
            description=f'File upload failed for "{server.name}": {exc}',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
        )
        return _sftp_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_file_download(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        data = json.loads(request.body or "{}")
        password = _resolve_server_secret(server, request, data)
        target_path = str(data.get("path") or "").strip()
        if not target_path:
            return JsonResponse({"success": False, "error": "Не указан путь к файлу"}, status=400)

        result = async_to_sync(download_file)(server, secret=password or "", path=target_path)
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_file_download',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Downloaded file from "{server.name}": {result["filename"]}',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata={'path': result["path"], 'size': result["size"]},
        )
        response = FileResponse(result["file_obj"], as_attachment=True, filename=result["filename"])
        response["Content-Length"] = str(result["size"])
        response["X-Remote-Path"] = result["path"]
        return response
    except Exception as exc:
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_file_download',
            status=UserActivityLog.STATUS_ERROR,
            description=f'File download failed for "{server.name}": {exc}',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
        )
        return _sftp_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_file_rename(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        data = json.loads(request.body or "{}")
        password = _resolve_server_secret(server, request, data)
        source_path = str(data.get("path") or "").strip()
        new_name = str(data.get("new_name") or "").strip()
        if not source_path or not new_name:
            return JsonResponse({"success": False, "error": "Нужны path и new_name"}, status=400)

        result = async_to_sync(rename_path)(server, secret=password or "", path=source_path, new_name=new_name)
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_file_rename',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Renamed remote entry on "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata={'path': source_path, 'new_name': new_name},
        )
        return JsonResponse({"success": True, **result})
    except Exception as exc:
        return _sftp_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_file_delete(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        data = json.loads(request.body or "{}")
        password = _resolve_server_secret(server, request, data)
        target_path = str(data.get("path") or "").strip()
        recursive = _parse_bool(data.get("recursive"))
        if not target_path:
            return JsonResponse({"success": False, "error": "Не указан path"}, status=400)

        result = async_to_sync(delete_path)(
            server,
            secret=password or "",
            path=target_path,
            recursive=recursive,
        )
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_file_delete',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Deleted remote entry on "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata={'path': result['deleted_path'], 'recursive': recursive},
        )
        return JsonResponse({"success": True, **result})
    except Exception as exc:
        return _sftp_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_file_mkdir(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    try:
        _require_ssh_server(server)
        data = json.loads(request.body or "{}")
        password = _resolve_server_secret(server, request, data)
        parent_path = str(data.get("path") or ".").strip() or "."
        folder_name = str(data.get("name") or "").strip()
        if not folder_name:
            return JsonResponse({"success": False, "error": "Не указано имя папки"}, status=400)

        result = async_to_sync(create_directory)(
            server,
            secret=password or "",
            parent_path=parent_path,
            name=folder_name,
        )
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_file_mkdir',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Created remote directory on "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata={'path': result['path'], 'name': folder_name},
        )
        return JsonResponse({"success": True, **result})
    except Exception as exc:
        return _sftp_error_response(exc)


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_delete(request, server_id):
    """Delete a server"""
    try:
        server = get_object_or_404(Server, id=server_id, user=request.user)
        server_name = server.name
        server.delete()
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_delete',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Deleted server "{server_name}"',
            entity_type='server',
            entity_id=server_id,
            entity_name=server_name,
        )
        return JsonResponse({'success': True, 'message': 'Server deleted'})
    except Exception as e:
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_delete',
            status=UserActivityLog.STATUS_ERROR,
            description=f'Server delete failed: {e}',
            entity_type='server',
            entity_id=server_id,
        )
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_share_list(request, server_id):
    """List shares for an owned server."""
    server = get_object_or_404(Server, id=server_id, user=request.user, is_active=True)
    now = timezone.now()
    shares = (
        ServerShare.objects.select_related("user", "shared_by")
        .filter(server=server, is_revoked=False)
        .order_by("-created_at")
    )
    payload = []
    for share in shares:
        active = share.expires_at is None or share.expires_at > now
        payload.append(
            {
                "id": share.id,
                "user_id": share.user_id,
                "username": share.user.username,
                "email": share.user.email or "",
                "share_context": bool(share.share_context),
                "expires_at": share.expires_at.isoformat() if share.expires_at else None,
                "created_at": share.created_at.isoformat() if share.created_at else None,
                "is_active": active and not share.is_revoked,
            }
        )
    return JsonResponse({"success": True, "shares": payload})


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_share_create(request, server_id):
    """Create or update share for an owned server."""
    try:
        server = get_object_or_404(Server, id=server_id, user=request.user, is_active=True)
        data = json.loads(request.body)

        identifier = str(data.get("user") or "").strip()
        if not identifier:
            return JsonResponse({"error": "User (username/email/id) required"}, status=400)

        target_user = None
        if identifier.isdigit():
            target_user = User.objects.filter(id=int(identifier)).first()
        if not target_user:
            target_user = User.objects.filter(username=identifier).first() or User.objects.filter(email=identifier).first()
        if not target_user:
            return JsonResponse({"error": "User not found"}, status=404)
        if target_user.id == request.user.id:
            return JsonResponse({"error": "Cannot share server with yourself"}, status=400)

        raw_expires = data.get("expires_at")
        expires_at = _parse_expires_at(raw_expires)
        if raw_expires not in (None, "", "null", "None") and not expires_at:
            return JsonResponse({"error": "Invalid expires_at format (use ISO datetime)"}, status=400)
        if expires_at and expires_at <= timezone.now():
            return JsonResponse({"error": "expires_at must be in the future"}, status=400)

        share_context = bool(data.get("share_context", True))

        share, _ = ServerShare.objects.update_or_create(
            server=server,
            user=target_user,
            defaults={
                "shared_by": request.user,
                "share_context": share_context,
                "expires_at": expires_at,
                "is_revoked": False,
                "revoked_at": None,
            },
        )

        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_share_create',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Shared server "{server.name}" with user "{target_user.username}"',
            entity_type='server_share',
            entity_id=share.id,
            entity_name=server.name,
            metadata={
                'server_id': server.id,
                'shared_with_user_id': target_user.id,
                'shared_with_username': target_user.username,
                'share_context': bool(share_context),
                'expires_at': share.expires_at.isoformat() if share.expires_at else None,
            },
        )

        return JsonResponse(
            {
                "success": True,
                "share": {
                    "id": share.id,
                    "user_id": share.user_id,
                    "username": share.user.username,
                    "email": share.user.email or "",
                    "share_context": bool(share.share_context),
                    "expires_at": share.expires_at.isoformat() if share.expires_at else None,
                    "created_at": share.created_at.isoformat() if share.created_at else None,
                    "is_active": share.is_active(),
                },
            }
        )
    except Exception as e:
        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_share_create',
            status=UserActivityLog.STATUS_ERROR,
            description=f'Server share create failed: {e}',
            entity_type='server',
            entity_id=server_id,
        )
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_share_revoke(request, server_id, share_id):
    """Revoke previously issued share."""
    server = get_object_or_404(Server, id=server_id, user=request.user, is_active=True)
    share = get_object_or_404(ServerShare, id=share_id, server=server)
    if not share.is_revoked:
        share.is_revoked = True
        share.revoked_at = timezone.now()
        share.save(update_fields=["is_revoked", "revoked_at", "updated_at"])
    log_user_activity(
        user=request.user,
        request=request,
        category='servers',
        action='server_share_revoke',
        status=UserActivityLog.STATUS_SUCCESS,
        description=f'Revoked server share for "{server.name}"',
        entity_type='server_share',
        entity_id=share.id,
        entity_name=server.name,
        metadata={
            'server_id': server.id,
            'shared_user_id': share.user_id,
            'shared_username': share.user.username,
        },
    )
    return JsonResponse({"success": True})


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def set_master_password(request):
    """Store master password in session for auto-connect"""
    try:
        data = json.loads(request.body)
        mp = data.get('master_password', '')
        if mp:
            request.session['_mp'] = mp
            request.session.set_expiry(0)  # Expires when browser closes
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_feature('servers')
def get_master_password(request):
    """Get master password from session (for auto-connect check)"""
    has_mp = bool(request.session.get('_mp'))
    return JsonResponse({'has_master_password': has_mp})


@login_required
@require_feature('servers')
def clear_master_password(request):
    """Clear master password from session"""
    request.session.pop('_mp', None)
    return JsonResponse({'success': True})


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def global_context_get(request):
    """Get global server rules/context for current user"""
    rules, _ = GlobalServerRules.objects.get_or_create(user=request.user)
    return JsonResponse({
        'rules': rules.rules,
        'forbidden_commands': rules.forbidden_commands,
        'required_checks': rules.required_checks,
        'environment_vars': rules.environment_vars,
    })


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def global_context_save(request):
    """Save global server rules/context for current user"""
    try:
        data = json.loads(request.body)
        rules, _ = GlobalServerRules.objects.get_or_create(user=request.user)
        if 'rules' in data:
            rules.rules = data['rules']
        if 'forbidden_commands' in data:
            fc = data['forbidden_commands']
            if isinstance(fc, str):
                fc = [c.strip() for c in fc.splitlines() if c.strip()]
            rules.forbidden_commands = fc
        if 'required_checks' in data:
            rc = data['required_checks']
            if isinstance(rc, str):
                rc = [c.strip() for c in rc.splitlines() if c.strip()]
            rules.required_checks = rc
        if 'environment_vars' in data:
            rules.environment_vars = data['environment_vars']
        rules.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def group_context_get(request, group_id):
    """Get context (rules, forbidden_commands, environment_vars) for a group"""
    group = get_object_or_404(ServerGroup, id=group_id)
    role = _get_group_role(group, request.user)
    if not role:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    include_environment_vars = role in ["owner", "admin"]
    return JsonResponse({
        'id': group.id,
        'name': group.name,
        'rules': group.rules,
        'forbidden_commands': group.forbidden_commands,
        'environment_vars': group.environment_vars if include_environment_vars else {},
    })


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def group_context_save(request, group_id):
    """Save context (rules, forbidden_commands, environment_vars) for a group"""
    group = get_object_or_404(ServerGroup, id=group_id)
    role = _get_group_role(group, request.user)
    if role not in ["owner", "admin"]:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    try:
        data = json.loads(request.body)
        if 'rules' in data:
            group.rules = data['rules']
        if 'forbidden_commands' in data:
            fc = data['forbidden_commands']
            if isinstance(fc, str):
                fc = [c.strip() for c in fc.splitlines() if c.strip()]
            group.forbidden_commands = fc
        if 'environment_vars' in data:
            group.environment_vars = data['environment_vars']
        group.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_get(request, server_id):
    """Get server details for viewing/editing (owner or active shared access)."""
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    share = _active_server_share(server, request.user)
    is_owner = server.user_id == request.user.id
    can_access_context = _shared_server_context_allowed(server, request.user, share)
    trusted_host_keys = get_server_trusted_host_keys(server) if is_owner else []
    return JsonResponse({
        'id': server.id,
        'name': server.name,
        'server_type': server.server_type,
        'host': server.host,
        'port': server.port,
        'username': server.username,
        'auth_method': server.auth_method,
        'key_path': server.key_path,
        'tags': server.tags,
        'notes': server.notes if can_access_context else '',
        'corporate_context': server.corporate_context if can_access_context else '',
        'group_id': server.group_id,
        'is_active': server.is_active,
        'network_config': server.network_config if can_access_context else {},
        'has_saved_password': bool(is_owner and has_saved_server_secret(server)),
        'can_view_password': bool(
            is_owner
            and server.auth_method in ["password", "key_password"]
            and has_saved_server_secret(server)
        ),
        'can_edit': bool(is_owner),
        'is_shared_server': bool(share),
        'share_context_enabled': bool(share.share_context) if share else True,
        'shared_by_username': share.shared_by.username if share and share.shared_by else '',
        'has_trusted_host_keys': bool(trusted_host_keys),
        'trusted_host_key_fingerprints': [
            item.get('fingerprint_sha256', '')
            for item in trusted_host_keys
            if item.get('fingerprint_sha256')
        ],
    })


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_reveal_password(request, server_id):
    """Reveal decrypted server password for the server owner only."""
    try:
        server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
        if server.user_id != request.user.id:
            return JsonResponse({'success': False, 'error': 'Only the server owner can reveal the saved password'}, status=403)
        if server.auth_method not in ["password", "key_password"]:
            return JsonResponse({'success': False, 'error': 'Password is not used for this auth method'}, status=400)
        if not has_saved_server_secret(server):
            return JsonResponse({'success': False, 'error': 'Saved password is not available'}, status=400)

        data = json.loads(request.body or "{}")
        master_password = str(data.get("master_password") or "").strip()
        if not master_password:
            master_password = str(request.session.get("_mp") or "").strip()
        if not master_password:
            return JsonResponse(
                {
                    'success': False,
                    'error': 'Master password is required to reveal the saved password',
                },
                status=400,
            )
        try:
            password = get_server_auth_secret(
                server,
                master_password=master_password,
            )
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Failed to decrypt password. Check MASTER_PASSWORD'}, status=400)

        log_user_activity(
            user=request.user,
            request=request,
            category='servers',
            action='server_password_reveal',
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Revealed password for server "{server.name}"',
            entity_type='server',
            entity_id=server.id,
            entity_name=server.name,
            metadata={
                'is_owner': True,
                'is_shared_server': False,
                'shared_by': '',
            },
        )
        return JsonResponse({'success': True, 'password': password})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_knowledge_list(request, server_id):
    """List AI/manual knowledge items for server edit modal."""
    server = get_object_or_404(Server, id=server_id, user=request.user)
    include_inactive = str(request.GET.get("include_inactive", "") or "").strip().lower() in {"1", "true", "yes"}
    rows_qs = ServerKnowledge.objects.filter(server=server)
    if not include_inactive:
        rows_qs = rows_qs.filter(is_active=True)
    rows = rows_qs.order_by("-updated_at")[:100]
    return JsonResponse(
        {
            "success": True,
            "items": [
                {
                    "id": k.id,
                    "title": k.title,
                    "content": k.content,
                    "category": k.category,
                    "category_label": k.get_category_display(),
                    "source": k.source,
                    "source_label": k.get_source_display(),
                    "confidence": float(k.confidence or 0.0),
                    "is_active": bool(k.is_active),
                    "updated_at": k.updated_at.isoformat() if k.updated_at else None,
                }
                for k in rows
            ],
            "categories": [{"value": c[0], "label": c[1]} for c in ServerKnowledge.CATEGORY_CHOICES],
            "include_inactive": include_inactive,
        }
    )


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_knowledge_create(request, server_id):
    """Create knowledge entry in edit modal."""
    try:
        from app.agent_kernel.memory.store import DjangoServerMemoryStore

        server = get_object_or_404(Server, id=server_id, user=request.user)
        data = json.loads(request.body or "{}")
        title = str(data.get("title") or "").strip()
        content = str(data.get("content") or "").strip()
        category = str(data.get("category") or "other").strip()
        is_active = bool(data.get("is_active", True))

        valid_categories = {x[0] for x in ServerKnowledge.CATEGORY_CHOICES}
        if category not in valid_categories:
            category = "other"
        if not title:
            return JsonResponse({"success": False, "error": "Title is required"}, status=400)
        if not content:
            return JsonResponse({"success": False, "error": "Content is required"}, status=400)

        knowledge = ServerKnowledge.objects.create(
            server=server,
            category=category,
            title=title[:200],
            content=content[:8000],
            source="manual",
            confidence=1.0,
            is_active=is_active,
            created_by=request.user,
        )
        DjangoServerMemoryStore()._sync_manual_knowledge_snapshot_sync(knowledge.id)
        return JsonResponse({"success": True, "id": knowledge.id})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_knowledge_update(request, server_id, knowledge_id):
    """Update title/content/category/flags for knowledge entry."""
    try:
        from app.agent_kernel.memory.store import DjangoServerMemoryStore

        server = get_object_or_404(Server, id=server_id, user=request.user)
        knowledge = get_object_or_404(ServerKnowledge, id=knowledge_id, server=server)
        data = json.loads(request.body or "{}")

        if "title" in data:
            title = str(data.get("title") or "").strip()
            if not title:
                return JsonResponse({"success": False, "error": "Title is required"}, status=400)
            knowledge.title = title[:200]

        if "content" in data:
            content = str(data.get("content") or "").strip()
            if not content:
                return JsonResponse({"success": False, "error": "Content is required"}, status=400)
            knowledge.content = content[:8000]

        if "category" in data:
            category = str(data.get("category") or "").strip()
            valid_categories = {x[0] for x in ServerKnowledge.CATEGORY_CHOICES}
            if category in valid_categories:
                knowledge.category = category

        if "is_active" in data:
            knowledge.is_active = bool(data.get("is_active"))

        if "confidence" in data:
            try:
                c = float(data.get("confidence"))
                knowledge.confidence = max(0.0, min(1.0, c))
            except Exception:
                pass

        knowledge.save()
        DjangoServerMemoryStore()._sync_manual_knowledge_snapshot_sync(knowledge.id)
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_knowledge_delete(request, server_id, knowledge_id):
    """Delete knowledge entry."""
    try:
        from app.agent_kernel.memory.store import DjangoServerMemoryStore

        server = get_object_or_404(Server, id=server_id, user=request.user)
        knowledge = get_object_or_404(ServerKnowledge, id=knowledge_id, server=server)
        DjangoServerMemoryStore()._archive_manual_knowledge_snapshot_sync(knowledge.id)
        knowledge.delete()
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_memory_overview(request, server_id):
    from app.agent_kernel.memory.store import DjangoServerMemoryStore

    if not request.user.is_staff:
        return JsonResponse({"success": False, "error": "Forbidden"}, status=403)

    server = get_object_or_404(Server, id=server_id, user=request.user)
    overview = DjangoServerMemoryStore()._get_memory_overview_sync(server.id)
    return JsonResponse({"success": True, **overview})


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_memory_run_dreams(request, server_id):
    from app.agent_kernel.memory.store import DjangoServerMemoryStore

    if not request.user.is_staff:
        return JsonResponse({"success": False, "error": "Forbidden"}, status=403)

    server = get_object_or_404(Server, id=server_id, user=request.user)
    data = json.loads(request.body or "{}")
    job_kind = str(data.get("job_kind") or "hybrid").strip().lower()
    if job_kind not in {"nearline", "nightly", "weekly", "hybrid"}:
        job_kind = "hybrid"
    result = DjangoServerMemoryStore()._run_dream_cycle_sync(server.id, job_kind=job_kind, force=True)
    overview = DjangoServerMemoryStore()._get_memory_overview_sync(server.id)
    return JsonResponse({"success": True, "job_kind": job_kind, "result": result, "overview": {"success": True, **overview}})


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_memory_policy_update(request, server_id):
    from app.agent_kernel.memory.store import DjangoServerMemoryStore

    if not request.user.is_staff:
        return JsonResponse({"success": False, "error": "Forbidden"}, status=403)

    server = get_object_or_404(Server, id=server_id, user=request.user)
    store = DjangoServerMemoryStore()
    policy = store._get_or_create_policy_sync(user_id=request.user.id)
    data = json.loads(request.body or "{}")

    dream_mode = str(data.get("dream_mode") or policy.dream_mode).strip().lower()
    allowed_modes = {
        policy.DREAM_HEURISTIC,
        policy.DREAM_NIGHTLY_LLM,
        policy.DREAM_HYBRID,
    }
    if dream_mode not in allowed_modes:
        dream_mode = policy.dream_mode

    policy.dream_mode = dream_mode
    policy.nightly_model_alias = str(data.get("nightly_model_alias") or policy.nightly_model_alias or "opssummary").strip() or "opssummary"
    policy.nearline_event_threshold = max(2, min(int(data.get("nearline_event_threshold") or policy.nearline_event_threshold or 6), 50))
    policy.sleep_start_hour = max(0, min(int(data.get("sleep_start_hour") if data.get("sleep_start_hour") is not None else policy.sleep_start_hour), 23))
    policy.sleep_end_hour = max(0, min(int(data.get("sleep_end_hour") if data.get("sleep_end_hour") is not None else policy.sleep_end_hour), 23))
    policy.raw_event_retention_days = max(7, min(int(data.get("raw_event_retention_days") or policy.raw_event_retention_days or 30), 365))
    policy.episode_retention_days = max(14, min(int(data.get("episode_retention_days") or policy.episode_retention_days or 90), 365))
    if "rdp_semantic_capture_enabled" in data:
        policy.rdp_semantic_capture_enabled = bool(data.get("rdp_semantic_capture_enabled"))
    if "human_habits_capture_enabled" in data:
        policy.human_habits_capture_enabled = bool(data.get("human_habits_capture_enabled"))
    if "is_enabled" in data:
        policy.is_enabled = bool(data.get("is_enabled"))
    policy.save()

    overview = store._get_memory_overview_sync(server.id)
    return JsonResponse({"success": True, "overview": {"success": True, **overview}})


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_memory_snapshot_archive(request, server_id, snapshot_id):
    from app.agent_kernel.memory.store import DjangoServerMemoryStore

    if not request.user.is_staff:
        return JsonResponse({"success": False, "error": "Forbidden"}, status=403)

    server = get_object_or_404(Server, id=server_id, user=request.user)
    store = DjangoServerMemoryStore()
    try:
        snapshot = store._archive_snapshot_sync(server.id, snapshot_id, actor_user_id=request.user.id)
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=404)
    overview = store._get_memory_overview_sync(server.id)
    return JsonResponse({"success": True, "snapshot": snapshot, "overview": {"success": True, **overview}})


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_memory_snapshot_promote_note(request, server_id, snapshot_id):
    from app.agent_kernel.memory.store import DjangoServerMemoryStore

    if not request.user.is_staff:
        return JsonResponse({"success": False, "error": "Forbidden"}, status=403)

    server = get_object_or_404(Server, id=server_id, user=request.user)
    store = DjangoServerMemoryStore()
    try:
        result = store._promote_snapshot_to_manual_knowledge_sync(
            server.id,
            snapshot_id,
            actor_user_id=request.user.id,
        )
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    return JsonResponse({"success": True, **result})


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_memory_snapshot_promote_skill(request, server_id, snapshot_id):
    from app.agent_kernel.memory.store import DjangoServerMemoryStore

    if not request.user.is_staff:
        return JsonResponse({"success": False, "error": "Forbidden"}, status=403)

    if not feature_allowed_for_user(request.user, "studio_skills"):
        return JsonResponse({"success": False, "error": "Studio skills feature is required"}, status=403)

    server = get_object_or_404(Server, id=server_id, user=request.user)
    store = DjangoServerMemoryStore()
    try:
        result = store._promote_skill_draft_to_skill_sync(
            server.id,
            snapshot_id,
            actor_user_id=request.user.id,
        )
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    return JsonResponse({"success": True, **result})


# ---------------------------------------------------------------------------
# Monitoring API endpoints
# ---------------------------------------------------------------------------


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


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def monitoring_dashboard(request):
    """Aggregated monitoring data for user dashboard."""
    from django.db.models import Avg, Max

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
                try:
                    rx_bytes = int(stripped.split("=", 1)[1].strip())
                except (TypeError, ValueError):
                    rx_bytes = None
            elif stripped.startswith("NET_TX_BYTES="):
                try:
                    tx_bytes = int(stripped.split("=", 1)[1].strip())
                except (TypeError, ValueError):
                    tx_bytes = None
        return rx_bytes, tx_bytes

    user = request.user
    servers = _accessible_servers_queryset(user)
    server_ids = list(servers.values_list("id", flat=True))

    latest_checks_raw = (
        ServerHealthCheck.objects.filter(server_id__in=server_ids)
        .values("server_id")
        .annotate(last_id=Max("id"))
    )
    latest_ids = [row["last_id"] for row in latest_checks_raw]
    latest_checks = list(
        ServerHealthCheck.objects.filter(id__in=latest_ids)
        .select_related("server")
        .order_by("-checked_at")
    )

    server_health = []
    for hc in latest_checks:
        net_rx_bytes, net_tx_bytes = _parse_net_traffic(hc.raw_output)
        server_health.append({
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
        })

    checked_ids = {hc.server_id for hc in latest_checks}
    for srv in servers:
        if srv.id not in checked_ids:
            server_health.append({
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
            })

    active_alerts = list(
        ServerAlert.objects.filter(server_id__in=server_ids, is_resolved=False)
        .select_related("server")
        .order_by("-created_at")[:50]
    )
    alerts_data = [
        {
            "id": a.id,
            "server_id": a.server_id,
            "server_name": a.server.name,
            "alert_type": a.alert_type,
            "severity": a.severity,
            "title": a.title,
            "message": a.message[:300],
            "created_at": a.created_at.isoformat(),
        }
        for a in active_alerts
    ]

    agg = (
        ServerHealthCheck.objects.filter(id__in=latest_ids)
        .aggregate(
            avg_cpu=Avg("cpu_percent"),
            avg_mem=Avg("memory_percent"),
            avg_disk=Avg("disk_percent"),
        )
    )

    status_counts = {}
    for hc in latest_checks:
        status_counts[hc.status] = status_counts.get(hc.status, 0) + 1

    recent_activity = list(
        UserActivityLog.objects.filter(user=user).order_by("-created_at")[:20]
    )
    activity_data = [
        {
            "id": a.id,
            "action": a.action,
            "category": a.category,
            "description": a.description[:200],
            "entity_name": a.entity_name,
            "created_at": a.created_at.isoformat(),
        }
        for a in recent_activity
    ]

    return JsonResponse({
        "success": True,
        "servers": server_health,
        "alerts": alerts_data,
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
    })


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_health_history(request, server_id):
    """Health check history for a server (last 24h by default)."""
    from datetime import timedelta as td

    hours = int(request.GET.get("hours", 24))
    since = timezone.now() - td(hours=hours)

    server = _accessible_servers_queryset(request.user).filter(id=server_id).first()
    if not server:
        return JsonResponse({"success": False, "error": "Server not found"}, status=404)

    checks = list(
        ServerHealthCheck.objects.filter(server=server, checked_at__gte=since)
        .order_by("checked_at")
    )

    return JsonResponse({
        "success": True,
        "server_id": server_id,
        "server_name": server.name,
        "checks": [_serialize_health_check(c) for c in checks],
    })


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_health_check_now(request, server_id):
    """Trigger an immediate health check for a server."""
    from asgiref.sync import async_to_sync
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
        hc = async_to_sync(check_server)(server, deep=deep)
    except Exception as e:
        cache.delete(lock_key)
        return JsonResponse({"success": False, "error": str(e)}, status=500)
    finally:
        cache.delete(lock_key)

    if not hc:
        return JsonResponse({"success": False, "error": "Check returned no result"}, status=500)

    cache.set(recent_key, hc.id, timeout=cooldown_seconds)

    log_user_activity(
        user=request.user,
        request=request,
        category="monitoring",
        action="manual_health_check",
        entity_type="server",
        entity_id=str(server_id),
        entity_name=server.name,
    )

    return JsonResponse({
        "success": True,
        "check": _serialize_health_check(hc),
    })


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_alerts_list(request):
    """List alerts, optionally filtered by server/severity/resolved status."""
    user = request.user
    server_ids = list(_accessible_servers_queryset(user).values_list("id", flat=True))

    qs = ServerAlert.objects.filter(server_id__in=server_ids).select_related("server")

    server_id = request.GET.get("server_id")
    if server_id:
        qs = qs.filter(server_id=int(server_id))

    severity = request.GET.get("severity")
    if severity:
        qs = qs.filter(severity=severity)

    resolved = request.GET.get("resolved")
    if resolved is not None:
        qs = qs.filter(is_resolved=resolved.lower() in ("true", "1", "yes"))

    limit = min(int(request.GET.get("limit", 100)), 500)
    alerts = list(qs.order_by("-created_at")[:limit])

    return JsonResponse({
        "success": True,
        "alerts": [
            {
                "id": a.id,
                "server_id": a.server_id,
                "server_name": a.server.name,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "title": a.title,
                "message": a.message,
                "is_resolved": a.is_resolved,
                "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
                "created_at": a.created_at.isoformat(),
                "metadata": a.metadata,
            }
            for a in alerts
        ],
    })


@login_required
@require_feature('servers')
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

    qs = _accessible_servers_queryset(request.user).order_by("name")
    if requested_server_ids:
        qs = qs.filter(id__in=requested_server_ids)

    persist_raw = payload.get("persist", request.GET.get("persist", "false"))
    persist = str(persist_raw).lower() in {"1", "true", "yes", "on"}
    watcher_service = WatcherService()
    watcher_payload = (
        watcher_service.persist_queryset(qs, limit=limit)
        if persist
        else watcher_service.scan_queryset(qs, limit=limit)
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

    return JsonResponse({
        "success": True,
        **watcher_payload,
    })


@login_required
@require_feature('servers')
@require_http_methods(["GET"])
def server_watcher_drafts(request):
    """List persisted watcher drafts for accessible servers."""
    qs = _accessible_servers_queryset(request.user).order_by("name")

    server_id = request.GET.get("server_id")
    if server_id:
        with contextlib.suppress(TypeError, ValueError):
            qs = qs.filter(id=int(server_id))

    status_values = request.GET.getlist("status") or request.GET.get("status", "")
    if isinstance(status_values, str):
        statuses = [item.strip() for item in status_values.split(",") if item.strip()]
    else:
        statuses = [str(item).strip() for item in status_values if str(item).strip()]

    try:
        limit = max(1, min(int(request.GET.get("limit", 100)), 200))
    except (TypeError, ValueError):
        limit = 100

    watcher_payload = WatcherService().list_persisted_queryset(qs, statuses=statuses or None, limit=limit)
    return JsonResponse({"success": True, **watcher_payload})


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def server_watcher_draft_ack(request, draft_id):
    """Acknowledge a persisted watcher draft."""
    qs = _accessible_servers_queryset(request.user).order_by("name")
    draft = WatcherService().acknowledge_draft(draft_id, user=request.user, servers_qs=qs)
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
@require_feature('servers')
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
@require_feature('servers')
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

    from servers.monitor import CPU_WARN, CPU_CRIT, MEM_WARN, MEM_CRIT, DISK_WARN, DISK_CRIT
    import servers.monitor as mon

    if request.method == "GET":
        total_checks = ServerHealthCheck.objects.count()
        total_alerts = ServerAlert.objects.filter(is_resolved=False).count()
        last_check = ServerHealthCheck.objects.order_by("-checked_at").first()

        return JsonResponse({
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
        })

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
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_feature('servers')
@require_http_methods(["POST"])
def ai_analyze_server(request, server_id):
    """AI analysis of server health data and logs."""
    from asgiref.sync import async_to_sync
    from app.core.llm import LLMProvider

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
            prompt_parts.append(f"- RAM: {last_check.memory_percent}% ({last_check.memory_used_mb or '?'}MB / {last_check.memory_total_mb or '?'}MB)")
        if last_check.disk_percent is not None:
            prompt_parts.append(f"- Disk: {last_check.disk_percent}% ({last_check.disk_used_gb or '?'}GB / {last_check.disk_total_gb or '?'}GB)")
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
        for a in active_alerts:
            prompt_parts.append(f"- [{a.severity.upper()}] {a.title}: {a.message[:200]}")

    if len(recent_checks) > 1:
        prompt_parts.append("\n## Trend (last checks)")
        for hc in recent_checks[:6]:
            prompt_parts.append(
                f"- {hc.checked_at.strftime('%H:%M')}: CPU={hc.cpu_percent or '?'}% RAM={hc.memory_percent or '?'}% Disk={hc.disk_percent or '?'}% [{hc.status}]"
            )

    prompt_parts.extend([
        "",
        "---",
        "Предоставь краткий анализ в формате markdown на русском языке:",
        "1. **Резюме** — общее состояние здоровья в 1-2 предложениях",
        "2. **Проблемы** — обнаруженные проблемы, ранжированные по серьёзности",
        "3. **Рекомендации** — конкретные практические шаги для исправления",
        "4. **Уровень риска** — Низкий / Средний / Высокий / Критический",
        "",
        "Будь конкретным. Если всё в порядке, скажи это кратко. Отвечай на русском языке.",
    ])

    full_prompt = "\n".join(prompt_parts)
    provider = LLMProvider()

    async def _collect():
        chunks = []
        async for chunk in provider.stream_chat(full_prompt, model="auto"):
            chunks.append(chunk)
        return "".join(chunks)

    try:
        result = async_to_sync(_collect)()
    except Exception as e:
        return JsonResponse({"success": False, "error": f"AI analysis failed: {e}"}, status=500)

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


# ---------------------------------------------------------------------------
# Mini-Agent API
# ---------------------------------------------------------------------------


@login_required
@require_feature('agents')
@require_http_methods(["GET"])
def agent_list(request):
    """List agents for the current user."""
    mode_filter = request.GET.get("mode")
    data = list_agents_for_user(request.user, mode_filter=mode_filter)
    return JsonResponse({"success": True, "agents": data})


@login_required
@require_feature('agents')
@require_http_methods(["GET"])
def agent_schedule_overview(request):
    """List scheduled agents and their due state for the current user."""
    try:
        limit = max(1, min(int(request.GET.get("limit", 50)), 200))
    except (TypeError, ValueError):
        limit = 50

    payload = list_scheduled_agents_for_user(request.user, limit=limit)
    return JsonResponse({"success": True, **payload})


@login_required
@require_feature('agents')
@require_http_methods(["POST"])
def agent_schedule_dispatch(request):
    """Dispatch due scheduled agents for the current user."""
    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = {}

    raw_agent_ids = data.get("agent_ids") or []
    agent_ids = []
    for value in raw_agent_ids:
        with contextlib.suppress(TypeError, ValueError):
            agent_ids.append(int(value))

    try:
        limit = max(1, min(int(data.get("limit", 100)), 500))
    except (TypeError, ValueError):
        limit = 100

    payload = dispatch_scheduled_agents_for_user(
        request.user,
        limit=limit,
        agent_ids=agent_ids or None,
    )
    log_user_activity(
        user=request.user,
        request=request,
        category="agent",
        action="schedule_dispatch",
        entity_type="agent_schedule",
        entity_id=str(request.user.id),
        entity_name=f"user:{request.user.username}",
    )
    return JsonResponse({"success": True, **payload})


@login_required
@require_feature('agents')
@require_http_methods(["GET"])
def agent_templates(request):
    """Return available agent templates."""
    from servers.agents import get_all_templates
    return JsonResponse({"success": True, "templates": get_all_templates()})


@login_required
@require_feature('agents')
@require_http_methods(["POST"])
def agent_create(request):
    """Create a new agent (mini or full) from template or custom."""
    from servers.agents import get_template

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    mode = data.get("mode", "mini")
    agent_type = data.get("agent_type", "custom")
    name = data.get("name", "").strip()
    server_ids = data.get("server_ids", [])
    custom_commands = data.get("commands", [])
    ai_prompt = data.get("ai_prompt", "")
    schedule = int(data.get("schedule_minutes", 0))

    tpl = get_template(agent_type)
    if not name:
        name = tpl["name"] if tpl else "Custom Agent"

    if mode == "mini":
        commands = custom_commands if custom_commands else (tpl["commands"] if tpl else [])
        if not commands:
            return JsonResponse({"success": False, "error": "No commands specified"}, status=400)
        if not ai_prompt and tpl:
            ai_prompt = tpl.get("ai_prompt", "")
    else:
        commands = custom_commands or []
        if not ai_prompt and tpl:
            ai_prompt = tpl.get("ai_prompt", "")

    goal = data.get("goal", "")
    system_prompt = data.get("system_prompt", "")
    max_iterations = min(int(data.get("max_iterations", 20)), 100)
    allow_multi_server = bool(data.get("allow_multi_server", False))
    tools_config = data.get("tools_config", {})
    stop_conditions = data.get("stop_conditions", [])
    session_timeout = int(data.get("session_timeout_seconds", 600))
    max_connections = min(int(data.get("max_connections", 5)), 10)

    if mode == "full" and tpl:
        if not goal:
            goal = tpl.get("goal", "")
        if not system_prompt:
            system_prompt = tpl.get("system_prompt", "")
        if not stop_conditions:
            stop_conditions = tpl.get("stop_conditions", [])

    agent = ServerAgent.objects.create(
        user=request.user,
        name=name,
        mode=mode,
        agent_type=agent_type,
        commands=commands,
        ai_prompt=ai_prompt,
        goal=goal,
        system_prompt=system_prompt,
        max_iterations=max_iterations,
        allow_multi_server=allow_multi_server,
        tools_config=tools_config,
        stop_conditions=stop_conditions,
        session_timeout_seconds=session_timeout,
        max_connections=max_connections,
        schedule_minutes=schedule,
    )

    accessible = _accessible_servers_queryset(request.user).filter(id__in=server_ids)
    agent.servers.set(accessible)

    log_user_activity(
        user=request.user, request=request,
        category="agent", action="agent_create",
        entity_type="agent", entity_id=str(agent.id), entity_name=agent.name,
    )

    return JsonResponse({"success": True, "id": agent.id})


@login_required
@require_feature('agents')
@require_http_methods(["POST"])
def agent_update(request, agent_id):
    """Update agent configuration."""
    agent = ServerAgent.objects.filter(id=agent_id, user=request.user).first()
    if not agent:
        return JsonResponse({"success": False, "error": "Agent not found"}, status=404)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    simple_fields = {
        "name": str, "commands": list, "ai_prompt": str, "is_enabled": bool,
        "goal": str, "system_prompt": str, "allow_multi_server": bool,
        "tools_config": dict, "stop_conditions": list,
    }
    int_fields = {
        "schedule_minutes": (0, 10080),
        "max_iterations": (1, 100),
        "session_timeout_seconds": (30, 3600),
        "max_connections": (1, 10),
    }

    for field, typ in simple_fields.items():
        if field in data:
            setattr(agent, field, typ(data[field]) if typ != list else data[field])

    for field, (lo, hi) in int_fields.items():
        if field in data:
            setattr(agent, field, max(lo, min(hi, int(data[field]))))

    if "server_ids" in data:
        accessible = _accessible_servers_queryset(request.user).filter(id__in=data["server_ids"])
        agent.servers.set(accessible)

    agent.save()
    return JsonResponse({"success": True})


@login_required
@require_feature('agents')
@require_http_methods(["POST"])
def agent_delete(request, agent_id):
    """Delete an agent."""
    agent = ServerAgent.objects.filter(id=agent_id, user=request.user).first()
    if not agent:
        return JsonResponse({"success": False, "error": "Agent not found"}, status=404)
    agent.delete()
    return JsonResponse({"success": True})


@login_required
@require_feature('agents')
@require_http_methods(["POST"])
def agent_run(request, agent_id):
    """Run agent on its configured servers (or a specific one)."""
    agent = ServerAgent.objects.filter(id=agent_id, user=request.user).prefetch_related("servers").first()
    if not agent:
        return JsonResponse({"success": False, "error": "Agent not found"}, status=404)

    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = {}

    launch_result = start_agent_run_for_user(
        agent=agent,
        user=request.user,
        accessible_servers_queryset=_accessible_servers_queryset(request.user),
        server_id=data.get("server_id"),
        source="http",
    )
    return JsonResponse(launch_result["payload"], status=200 if launch_result["ok"] else int(launch_result["status"]))


@login_required
@require_feature('agents')
@require_http_methods(["GET"])
def agent_runs(request, agent_id):
    """History of runs for an agent."""
    agent = ServerAgent.objects.filter(id=agent_id, user=request.user).first()
    if not agent:
        return JsonResponse({"success": False, "error": "Agent not found"}, status=404)

    limit = min(int(request.GET.get("limit", 20)), 100)
    runs = AgentRun.objects.filter(agent=agent).select_related("server").order_by("-started_at")[:limit]

    data = [
        {
            "id": r.id,
            "server_name": r.server.name if r.server_id else "?",
            "server_id": r.server_id,
            "status": r.status,
            "ai_analysis": r.ai_analysis,
            "commands_output": r.commands_output,
            "duration_ms": r.duration_ms,
            "started_at": r.started_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]

    return JsonResponse({"success": True, "runs": data})


@login_required
@require_feature('agents')
@require_http_methods(["GET"])
def agent_run_detail(request, run_id):
    """Single run detail (supports both mini and full agents)."""
    run = AgentRun.objects.filter(id=run_id, user=request.user).select_related("agent", "server").first()
    if not run:
        run = AgentRun.objects.filter(id=run_id, agent__user=request.user).select_related("agent", "server").first()
    if not run:
        return JsonResponse({"success": False, "error": "Run not found"}, status=404)

    data = {
        "id": run.id,
        "agent_id": run.agent_id,
        "agent_name": run.agent.name,
        "agent_type": run.agent.agent_type,
        "agent_mode": run.agent.mode,
        "server_name": run.server.name if run.server_id else "?",
        "status": run.status,
        "ai_analysis": run.ai_analysis,
        "commands_output": run.commands_output,
        "duration_ms": run.duration_ms,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "iterations_log": run.iterations_log or [],
        "tool_calls": run.tool_calls or [],
        "total_iterations": run.total_iterations,
        "connected_servers": run.connected_servers or [],
        "final_report": run.final_report,
        "pending_question": run.pending_question,
        "plan_tasks": run.plan_tasks or [],
        "orchestrator_log": run.orchestrator_log or [],
        "dispatch": serialize_agent_dispatch(run.dispatches.order_by("-queued_at", "-id").first()),
    }

    return JsonResponse({"success": True, "run": data})


@login_required
@require_feature('agents')
@require_http_methods(["POST"])
def agent_stop(request, agent_id):
    """Stop a running full agent."""
    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = {}

    result = stop_agent_run_for_user(
        agent_id=agent_id,
        user=request.user,
        run_id=data.get("run_id"),
        source="http",
    )
    return JsonResponse(result["payload"], status=200 if result["ok"] else int(result["status"]))


@login_required
@require_feature('agents')
@require_http_methods(["POST"])
def agent_run_reply(request, run_id):
    """Reply to a question asked by a running agent."""
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    result = reply_to_agent_run_for_user(
        run_id=run_id,
        user=request.user,
        answer=data.get("answer", ""),
        source="http",
    )
    return JsonResponse(result["payload"], status=200 if result["ok"] else int(result["status"]))


@login_required
@require_feature('agents')
@require_http_methods(["GET"])
def agent_run_log(request, run_id):
    """Get the iterations log for a run."""
    run = AgentRun.objects.filter(id=run_id, agent__user=request.user).first()
    if not run:
        run = AgentRun.objects.filter(id=run_id, user=request.user).first()
    if not run:
        return JsonResponse({"success": False, "error": "Run not found"}, status=404)

    return JsonResponse({
        "success": True,
        "iterations_log": run.iterations_log or [],
        "tool_calls": run.tool_calls or [],
        "total_iterations": run.total_iterations,
        "status": run.status,
        "pending_question": run.pending_question,
        "plan_tasks": run.plan_tasks or [],
    })


@login_required
@require_feature('agents')
@require_http_methods(["GET"])
def agent_run_events(request, run_id):
    """Get the persistent event timeline for a run."""
    run = AgentRun.objects.filter(id=run_id, agent__user=request.user).first()
    if not run:
        run = AgentRun.objects.filter(id=run_id, user=request.user).first()
    if not run:
        return JsonResponse({"success": False, "error": "Run not found"}, status=404)

    try:
        limit = max(1, min(int(request.GET.get("limit", 200)), 500))
    except (TypeError, ValueError):
        limit = 200
    event_types = [item.strip() for item in request.GET.getlist("event_type") if item.strip()]
    if not event_types:
        event_type_raw = str(request.GET.get("event_type", "") or "").strip()
        if event_type_raw:
            event_types = [item.strip() for item in event_type_raw.split(",") if item.strip()]
    qs = AgentRunEvent.objects.filter(run=run).order_by("created_at", "id")
    if event_types:
        qs = qs.filter(event_type__in=event_types)
    total = qs.count()
    events = [serialize_run_event(item) for item in qs[:limit]]
    return JsonResponse({
        "success": True,
        "events": events,
        "total": total,
    })


@login_required
@require_feature('agents')
@require_http_methods(["POST"])
def agent_run_approve_plan(request, run_id):
    """Approve the plan and start executing the multi-agent pipeline.

    The run must be in plan_review status. Creates an engine instance and
    runs execute_existing_plan() which re-opens SSH connections and runs
    Phase 2 + 3 from the saved plan_tasks.
    """
    result = approve_agent_plan_for_user(
        run_id=run_id,
        user=request.user,
        accessible_servers_queryset=_accessible_servers_queryset(request.user),
        source="http",
    )
    return JsonResponse(result["payload"], status=200 if result["ok"] else int(result["status"]))


@login_required
@require_feature('agents')
@require_http_methods(["POST"])
def agent_run_task_update(request, run_id, task_id):
    """Edit or delete a specific task in a pipeline run's plan_tasks.

    POST body:
      action: "update" | "delete"
      name: str (optional, for update)
      description: str (optional, for update)
    """
    run = AgentRun.objects.filter(
        id=run_id, agent__user=request.user,
    ).first()
    if not run:
        run = AgentRun.objects.filter(id=run_id, user=request.user).first()
    if not run:
        return JsonResponse({"success": False, "error": "Run not found"}, status=404)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    action = data.get("action", "update")
    tasks = list(run.plan_tasks or [])

    target = next((t for t in tasks if t.get("id") == task_id), None)
    if target is None:
        return JsonResponse({"success": False, "error": "Task not found"}, status=404)

    if target.get("status") not in ("pending", "failed", "skipped"):
        return JsonResponse({"success": False, "error": "Only pending/failed/skipped tasks can be edited"}, status=400)

    if action == "delete":
        tasks = [t for t in tasks if t.get("id") != task_id]
    else:
        if "name" in data:
            target["name"] = str(data["name"])[:200]
        if "description" in data:
            target["description"] = str(data["description"])[:1000]

    run.plan_tasks = tasks
    run.save(update_fields=["plan_tasks"])
    return JsonResponse({"success": True, "plan_tasks": tasks})


@login_required
@require_feature('agents')
@require_http_methods(["POST"])
def agent_run_task_ai_refine(request, run_id, task_id):
    """Use LLM to rewrite a task based on user instruction.

    POST body:
      instruction: str — what to change (e.g. "добавь проверку памяти")
    """
    run = AgentRun.objects.filter(
        id=run_id, agent__user=request.user,
    ).first()
    if not run:
        run = AgentRun.objects.filter(id=run_id, user=request.user).first()
    if not run:
        return JsonResponse({"success": False, "error": "Run not found"}, status=404)

    tasks = list(run.plan_tasks or [])
    target = next((t for t in tasks if t.get("id") == task_id), None)
    if target is None:
        return JsonResponse({"success": False, "error": "Task not found"}, status=404)

    if target.get("status") not in ("pending", "failed", "skipped"):
        return JsonResponse({"success": False, "error": "Only pending/failed/skipped tasks can be edited"}, status=400)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    instruction = str(data.get("instruction", "")).strip()
    if not instruction:
        return JsonResponse({"success": False, "error": "instruction required"}, status=400)

    # Call LLM synchronously
    from app.core.llm import LLMProvider
    import asyncio

    prompt = f"""Ты — ассистент, помогающий редактировать задачи в плане DevOps-агента.

Текущая задача:
Название: {target.get("name", "")}
Описание: {target.get("description", "")}

Инструкция пользователя: {instruction}

Верни ТОЛЬКО JSON-объект с полями name и description (без markdown, без пояснений):
{{"name": "...", "description": "..."}}"""

    async def _call():
        provider = LLMProvider()
        chunks = []
        async for chunk in provider.stream_chat(prompt, model="auto", purpose="chat"):
            chunks.append(chunk)
        return "".join(chunks)

    try:
        loop = asyncio.new_event_loop()
        result_text = loop.run_until_complete(_call())
        loop.close()
    except Exception as exc:
        return JsonResponse({"success": False, "error": f"LLM error: {exc}"}, status=500)

    # Parse JSON from response
    import re as _re
    text = _re.sub(r"```(?:json)?\s*", "", result_text).strip().rstrip("`").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return JsonResponse({"success": False, "error": "LLM did not return valid JSON", "raw": result_text[:500]}, status=500)

    try:
        refined = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Failed to parse LLM JSON", "raw": result_text[:500]}, status=500)

    if "name" in refined:
        target["name"] = str(refined["name"])[:200]
    if "description" in refined:
        target["description"] = str(refined["description"])[:1000]

    run.plan_tasks = tasks
    run.save(update_fields=["plan_tasks"])

    return JsonResponse({"success": True, "task": target, "plan_tasks": tasks})


@login_required
@require_feature('agents')
@require_http_methods(["GET"])
def agent_dashboard_runs(request):
    """Active + recent runs for the dashboard widget."""
    active_statuses = [
        AgentRun.STATUS_PENDING,
        AgentRun.STATUS_RUNNING,
        AgentRun.STATUS_PAUSED,
        AgentRun.STATUS_WAITING,
        AgentRun.STATUS_PLAN_REVIEW,
    ]
    active_runs = list(
        AgentRun.objects.filter(agent__user=request.user, status__in=active_statuses)
        .select_related("agent", "server")
        .order_by("-started_at")[:10]
    )
    active_ids = {r.id for r in active_runs}
    recent_runs = list(
        AgentRun.objects.filter(agent__user=request.user)
        .exclude(id__in=active_ids)
        .select_related("agent", "server")
        .order_by("-started_at")[:10]
    )

    def _run_to_dict(r):
        return {
            "id": r.id,
            "agent_id": r.agent_id,
            "agent_name": r.agent.name,
            "agent_mode": r.agent.mode,
            "agent_type": r.agent.agent_type,
            "server_name": r.server.name if r.server_id else "?",
            "server_id": r.server_id,
            "status": r.status,
            "total_iterations": r.total_iterations,
            "duration_ms": r.duration_ms,
            "started_at": r.started_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "pending_question": r.pending_question or "",
            "connected_servers": r.connected_servers or [],
            "ai_analysis": (r.ai_analysis or "")[:500],
            "final_report": (r.final_report or "")[:2000],
            "commands_output": r.commands_output[:5] if r.commands_output else [],
        }

    return JsonResponse({
        "success": True,
        "active": [_run_to_dict(r) for r in active_runs],
        "recent": [_run_to_dict(r) for r in recent_runs],
    })
