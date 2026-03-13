from __future__ import annotations

import asyncio
import json
from functools import wraps

from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core_ui.context_processors import user_can_feature
from core_ui.desktop_auth import (
    ACCESS_TOKEN_TTL_SECONDS,
    DesktopAuthError,
    authenticate_access_token,
    authenticate_credentials,
    create_refresh_token,
    issue_access_token,
    issue_ws_token,
    revoke_refresh_token,
    rotate_refresh_token,
)
from core_ui.desktop_api.serializers import (
    accessible_share_for_server,
    connected_ids_for_servers,
    serialize_global_context,
    serialize_group,
    serialize_group_context,
    serialize_knowledge_item,
    serialize_mcp_summary,
    serialize_server_detail,
    serialize_server_summary,
    serialize_user,
)
from core_ui.managed_secrets import set_mcp_secret_env
from servers.models import GlobalServerRules, Server, ServerGroup, ServerKnowledge
from servers.secret_utils import clear_server_auth_secret, store_server_auth_secret
from servers.views import _accessible_servers_queryset, _active_server_share, _get_group_role, _shared_server_context_allowed
from studio.mcp_client import MCPClientError, inspect_mcp_server
from studio.models import MCPServerPool
from studio.views import _normalize_sse_url, _test_mcp_connection


def _json_body(request) -> dict:
    try:
        return json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _error(message: str, *, code: str = "bad_request", status: int = 400, details=None) -> JsonResponse:
    payload = {"error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return JsonResponse(payload, status=status)


def _ok(data: dict, *, status: int = 200) -> JsonResponse:
    return JsonResponse(data, status=status)


def _require_admin(request, *, message: str = "Admin access required") -> JsonResponse | None:
    user = getattr(request, "desktop_user", None)
    if user and getattr(user, "is_staff", False):
        return None
    return _error(message, code="forbidden", status=403)


def _bearer_token(request) -> str:
    raw = request.headers.get("Authorization", "")
    if not raw.startswith("Bearer "):
        return ""
    return raw[7:].strip()


def desktop_auth_required(feature: str | None = None):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            token = _bearer_token(request)
            if not token:
                return _error("Missing bearer token", code="missing_bearer_token", status=401)
            try:
                user = authenticate_access_token(token)
            except DesktopAuthError as exc:
                return _error(str(exc), code=exc.code, status=401)
            if feature and not user_can_feature(user, feature):
                return _error("Forbidden", code="forbidden", status=403)
            request.desktop_user = user
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def _group_for_write(group_id, user):
    group = ServerGroup.objects.filter(id=group_id).first()
    if not group:
        raise ValueError("Group not found")
    if _get_group_role(group, user) == "":
        raise ValueError("Permission denied for group")
    return group


def _coerce_port(raw_value) -> int:
    try:
        port = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid port") from exc
    if port < 1 or port > 65535:
        raise ValueError("Port must be in range 1..65535")
    return port


def _apply_server_payload(server: Server, payload: dict, *, user, partial: bool = False) -> None:
    if not partial or "name" in payload:
        server.name = str(payload.get("name") or server.name).strip()
    if not server.name:
        raise ValueError("name is required")

    if not partial or "server_type" in payload:
        server_type = str(payload.get("server_type") or server.server_type or "ssh").strip().lower()
        if server_type not in ("ssh", "rdp"):
            raise ValueError("Invalid server_type")
        server.server_type = server_type

    if not partial or "host" in payload:
        server.host = str(payload.get("host") or server.host).strip()
    if not server.host:
        raise ValueError("host is required")

    if not partial or "port" in payload:
        server.port = _coerce_port(payload.get("port", server.port))

    if not partial or "username" in payload:
        server.username = str(payload.get("username") or server.username).strip()
    if not server.username:
        raise ValueError("username is required")

    if not partial or "auth_method" in payload:
        auth_method = str(payload.get("auth_method") or server.auth_method or "password").strip().lower()
        if auth_method not in ("password", "key", "key_password"):
            raise ValueError("Invalid auth_method")
        server.auth_method = auth_method

    if "key_path" in payload or not partial:
        server.key_path = str(payload.get("key_path") or server.key_path or "").strip()
    if "tags" in payload or not partial:
        server.tags = str(payload.get("tags") or server.tags or "")
    if "notes" in payload or not partial:
        server.notes = str(payload.get("notes") or server.notes or "")
    if "corporate_context" in payload or not partial:
        server.corporate_context = str(payload.get("corporate_context") or server.corporate_context or "")
    if "network_config" in payload or not partial:
        network_config = payload.get("network_config", server.network_config or {})
        if not isinstance(network_config, dict):
            raise ValueError("network_config must be an object")
        server.network_config = network_config
        server.update_network_flags()
    if "is_active" in payload or not partial:
        server.is_active = bool(payload.get("is_active", server.is_active))

    if "group_id" in payload or not partial:
        raw_group_id = payload.get("group_id", server.group_id)
        if raw_group_id in ("", None, "null", "None"):
            server.group = None
        else:
            try:
                group_id = int(raw_group_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("Invalid group_id") from exc
            server.group = _group_for_write(group_id, user)


@csrf_exempt
@require_http_methods(["POST"])
def auth_login(request):
    data = _json_body(request)
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    if not username or not password:
        return _error("username and password are required", code="invalid_credentials", status=400)

    try:
        user = authenticate_credentials(username, password)
    except DesktopAuthError as exc:
        return _error(str(exc), code=exc.code, status=401)

    refresh_token, _ = create_refresh_token(
        user,
        label=str(data.get("device_name") or "WinUI Desktop").strip()[:120],
        user_agent=request.headers.get("User-Agent", ""),
    )
    return _ok(
        {
            "user": serialize_user(user),
            "session": {
                "access_token": issue_access_token(user),
                "refresh_token": refresh_token,
                "expires_in": ACCESS_TOKEN_TTL_SECONDS,
            },
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def auth_refresh(request):
    data = _json_body(request)
    refresh_token = str(data.get("refresh_token") or "").strip()
    if not refresh_token:
        return _error("refresh_token is required", code="refresh_token_required", status=400)
    try:
        user, new_refresh_token, _ = rotate_refresh_token(
            refresh_token,
            user_agent=request.headers.get("User-Agent", ""),
        )
    except DesktopAuthError as exc:
        return _error(str(exc), code=exc.code, status=401)

    return _ok(
        {
            "user": serialize_user(user),
            "session": {
                "access_token": issue_access_token(user),
                "refresh_token": new_refresh_token,
                "expires_in": ACCESS_TOKEN_TTL_SECONDS,
            },
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
@desktop_auth_required()
def auth_logout(request):
    data = _json_body(request)
    refresh_token = str(data.get("refresh_token") or "").strip()
    revoke_refresh_token(refresh_token)
    return _ok({"ok": True})


@require_http_methods(["GET"])
@desktop_auth_required()
def auth_me(request):
    return _ok({"user": serialize_user(request.desktop_user)})


@require_http_methods(["GET"])
@desktop_auth_required()
def bootstrap(request):
    user = request.desktop_user
    servers = list(_accessible_servers_queryset(user))
    groups = list(
        ServerGroup.objects.filter(user=user)
        .annotate(server_count=Count("servers"))
        .order_by("name")
    )
    accessible_server_ids = {server.id for server in servers}
    shared_count = sum(1 for server in servers if server.user_id != user.id)
    return _ok(
        {
            "user": serialize_user(user),
            "api": {"version": "v1"},
            "counts": {
                "servers_total": len(servers),
                "servers_owned": sum(1 for server in servers if server.user_id == user.id),
                "servers_shared": shared_count,
                "groups": len(groups),
                "mcp": MCPServerPool.objects.filter(owner=user).count() if user_can_feature(user, "studio") else 0,
            },
            "groups": [serialize_group(group) for group in groups],
            "terminal": {
                "path_template": "/ws/servers/{serverId}/terminal/",
                "auth_mode": "ws_ticket",
            },
            "feature_flags": {
                "native_shell": True,
                "webview_terminal": True,
                "desktop_token_auth": True,
                "managed_secrets": True,
            },
            "capabilities": {
                "servers": bool(user_can_feature(user, "servers")),
                "mcp": bool(user_can_feature(user, "studio")),
            },
            "accessible_server_ids": sorted(accessible_server_ids),
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
@desktop_auth_required("servers")
def terminal_ws_ticket(request):
    user = request.desktop_user
    data = _json_body(request)
    raw_server_id = data.get("server_id")
    server_id = None
    if raw_server_id not in (None, "", "null"):
        try:
            server_id = int(raw_server_id)
        except (TypeError, ValueError):
            return _error("server_id must be an integer", code="invalid_server_id", status=400)
        if not _accessible_servers_queryset(user).filter(id=server_id).exists():
            return _error("Server not found", code="server_not_found", status=404)

    ws_token = issue_ws_token(user)
    host = request.get_host()
    scheme = "wss" if request.is_secure() else "ws"
    path = f"/ws/servers/{server_id}/terminal/" if server_id else "/ws/servers/{serverId}/terminal/"
    ws_url = f"{scheme}://{host}{path}?ws_token={ws_token}"
    return _ok(
        {
            "terminal": {
                "server_id": server_id,
                "ws_token": ws_token,
                "path": path,
                "ws_url": ws_url,
            }
        }
    )


@require_http_methods(["GET", "POST"])
@csrf_exempt
@desktop_auth_required("servers")
def servers_collection(request):
    user = request.desktop_user
    if request.method == "GET":
        servers = list(_accessible_servers_queryset(user).order_by("group__name", "name"))
        connected_ids = connected_ids_for_servers(servers)
        return _ok(
            {
                "items": [
                    serialize_server_summary(
                        server,
                        connected_server_ids=connected_ids,
                        share=accessible_share_for_server(server, user),
                    )
                    for server in servers
                ]
            }
        )

    data = _json_body(request)
    server = Server(user=user)
    try:
        _apply_server_payload(server, data, user=user, partial=False)
    except ValueError as exc:
        return _error(str(exc), code="invalid_server_payload", status=400)

    password = str(data.get("password") or "").strip()
    master_password = str(data.get("master_password") or "").strip()
    with transaction.atomic():
        server.save()
        if password:
            store_server_auth_secret(server, secret_value=password, master_password=master_password)
            server.save(update_fields=["encrypted_password", "salt"])

    return _ok({"item": serialize_server_detail(server, current_user=user)}, status=201)


@require_http_methods(["GET"])
@desktop_auth_required("servers")
def server_groups(request):
    user = request.desktop_user
    groups = list(
        ServerGroup.objects.filter(user=user)
        .annotate(server_count=Count("servers"))
        .order_by("name")
    )
    return _ok({"items": [serialize_group(group) for group in groups]})


@require_http_methods(["GET", "PUT"])
@csrf_exempt
@desktop_auth_required("servers")
def global_context(request):
    user = request.desktop_user
    rules, _ = GlobalServerRules.objects.get_or_create(user=user)
    if request.method == "GET":
        return _ok({"item": serialize_global_context(rules)})

    data = _json_body(request)
    if "rules" in data:
        rules.rules = str(data.get("rules") or "")
    if "forbidden_commands" in data:
        fc = data.get("forbidden_commands") or []
        if isinstance(fc, str):
            fc = [line.strip() for line in fc.splitlines() if line.strip()]
        rules.forbidden_commands = list(fc)
    if "required_checks" in data:
        rc = data.get("required_checks") or []
        if isinstance(rc, str):
            rc = [line.strip() for line in rc.splitlines() if line.strip()]
        rules.required_checks = list(rc)
    if "environment_vars" in data:
        env = data.get("environment_vars") or {}
        if not isinstance(env, dict):
            return _error("environment_vars must be an object", code="invalid_environment_vars", status=400)
        rules.environment_vars = env
    rules.save()
    return _ok({"item": serialize_global_context(rules)})


@require_http_methods(["GET", "PUT"])
@csrf_exempt
@desktop_auth_required("servers")
def group_context(request, group_id: int):
    user = request.desktop_user
    group = ServerGroup.objects.filter(id=group_id).first()
    if not group:
        return _error("Group not found", code="group_not_found", status=404)
    role = _get_group_role(group, user)
    if not role:
        return _error("Forbidden", code="forbidden", status=403)
    if request.method == "GET":
        return _ok({"item": serialize_group_context(group, include_environment_vars=role in ("owner", "admin"))})

    if role not in ("owner", "admin"):
        return _error("Forbidden", code="forbidden", status=403)
    data = _json_body(request)
    if "rules" in data:
        group.rules = str(data.get("rules") or "")
    if "forbidden_commands" in data:
        fc = data.get("forbidden_commands") or []
        if isinstance(fc, str):
            fc = [line.strip() for line in fc.splitlines() if line.strip()]
        group.forbidden_commands = list(fc)
    if "environment_vars" in data:
        env = data.get("environment_vars") or {}
        if not isinstance(env, dict):
            return _error("environment_vars must be an object", code="invalid_environment_vars", status=400)
        group.environment_vars = env
    group.save()
    return _ok({"item": serialize_group_context(group)})


@require_http_methods(["GET", "PUT", "DELETE"])
@csrf_exempt
@desktop_auth_required("servers")
def server_detail(request, server_id: int):
    user = request.desktop_user
    server = _accessible_servers_queryset(user).filter(id=server_id).first()
    if not server:
        return _error("Server not found", code="server_not_found", status=404)

    if request.method == "GET":
        share = _active_server_share(server, user)
        return _ok(
            {
                "item": serialize_server_detail(
                    server,
                    current_user=user,
                    share=share,
                    can_access_context=_shared_server_context_allowed(server, user, share=share),
                )
            }
        )

    if server.user_id != user.id:
        return _error("Only owner can modify server", code="forbidden", status=403)

    if request.method == "DELETE":
        server.delete()
        return _ok({"ok": True})

    data = _json_body(request)
    try:
        _apply_server_payload(server, data, user=user, partial=True)
    except ValueError as exc:
        return _error(str(exc), code="invalid_server_payload", status=400)

    password = data.get("password")
    clear_saved_secret = bool(data.get("clear_saved_secret"))
    master_password = str(data.get("master_password") or "").strip()
    with transaction.atomic():
        if clear_saved_secret:
            clear_server_auth_secret(server)
        elif password is not None:
            store_server_auth_secret(server, secret_value=str(password), master_password=master_password)
        server.save()
    return _ok({"item": serialize_server_detail(server, current_user=user)})


@require_http_methods(["GET", "POST"])
@csrf_exempt
@desktop_auth_required("servers")
def server_knowledge_collection(request, server_id: int):
    user = request.desktop_user
    server = Server.objects.filter(id=server_id, user=user).first()
    if not server:
        return _error("Server not found", code="server_not_found", status=404)

    if request.method == "GET":
        items = list(ServerKnowledge.objects.filter(server=server).order_by("-updated_at")[:100])
        return _ok({"items": [serialize_knowledge_item(item) for item in items]})

    data = _json_body(request)
    title = str(data.get("title") or "").strip()
    content = str(data.get("content") or "").strip()
    if not title or not content:
        return _error("title and content are required", code="invalid_knowledge_payload", status=400)
    item = ServerKnowledge.objects.create(
        server=server,
        title=title,
        content=content,
        category=str(data.get("category") or "other"),
        is_active=bool(data.get("is_active", True)),
        created_by=user,
    )
    return _ok({"item": serialize_knowledge_item(item)}, status=201)


@require_http_methods(["PUT", "DELETE"])
@csrf_exempt
@desktop_auth_required("servers")
def server_knowledge_detail(request, server_id: int, knowledge_id: int):
    user = request.desktop_user
    item = ServerKnowledge.objects.filter(id=knowledge_id, server_id=server_id, server__user=user).first()
    if not item:
        return _error("Knowledge item not found", code="knowledge_not_found", status=404)

    if request.method == "DELETE":
        item.delete()
        return _ok({"ok": True})

    data = _json_body(request)
    for field in ("title", "content", "category"):
        if field in data:
            setattr(item, field, data[field])
    if "is_active" in data:
        item.is_active = bool(data.get("is_active"))
    item.save()
    return _ok({"item": serialize_knowledge_item(item)})


@require_http_methods(["GET", "POST"])
@csrf_exempt
@desktop_auth_required("studio")
def mcp_collection(request):
    admin_error = _require_admin(request)
    if admin_error:
        return admin_error
    user = request.desktop_user
    if request.method == "GET":
        items = list(MCPServerPool.objects.filter(owner=user).order_by("name"))
        return _ok({"items": [serialize_mcp_summary(item) for item in items]})

    data = _json_body(request)
    name = str(data.get("name") or "").strip()
    if not name:
        return _error("name is required", code="invalid_mcp_payload", status=400)
    transport = str(data.get("transport") or MCPServerPool.TRANSPORT_STDIO)
    url = str(data.get("url") or "").strip()
    if transport == MCPServerPool.TRANSPORT_SSE and url:
        url = _normalize_sse_url(url)
    item = MCPServerPool.objects.create(
        name=name,
        description=str(data.get("description") or ""),
        transport=transport,
        command=str(data.get("command") or ""),
        args=data.get("args") or [],
        env=data.get("env") or {},
        url=url,
        owner=user,
        is_shared=bool(data.get("is_shared", False)),
    )
    set_mcp_secret_env(item.id, data.get("secret_env") if isinstance(data.get("secret_env"), dict) else {})
    return _ok({"item": serialize_mcp_summary(item)}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
@csrf_exempt
@desktop_auth_required("studio")
def mcp_detail(request, mcp_id: int):
    admin_error = _require_admin(request)
    if admin_error:
        return admin_error
    user = request.desktop_user
    item = MCPServerPool.objects.filter(id=mcp_id, owner=user).first()
    if not item:
        return _error("MCP server not found", code="mcp_not_found", status=404)

    if request.method == "GET":
        return _ok({"item": serialize_mcp_summary(item)})

    if request.method == "DELETE":
        item.delete()
        set_mcp_secret_env(mcp_id, {})
        return _ok({"ok": True})

    data = _json_body(request)
    for field in ("name", "description", "transport", "command", "args", "env", "url", "is_shared"):
        if field in data:
            value = data[field]
            if field == "url" and (data.get("transport") or item.transport) == MCPServerPool.TRANSPORT_SSE and value:
                value = _normalize_sse_url(str(value))
            setattr(item, field, value)
    item.save()
    if "secret_env" in data:
        if data.get("secret_env") is not None and not isinstance(data.get("secret_env"), dict):
            return _error("secret_env must be an object", code="invalid_mcp_payload", status=400)
        set_mcp_secret_env(item.id, data.get("secret_env") or {})
    return _ok({"item": serialize_mcp_summary(item)})


@require_http_methods(["POST"])
@csrf_exempt
@desktop_auth_required("studio")
def mcp_test(request, mcp_id: int):
    admin_error = _require_admin(request)
    if admin_error:
        return admin_error
    user = request.desktop_user
    item = MCPServerPool.objects.filter(id=mcp_id, owner=user).first()
    if not item:
        return _error("MCP server not found", code="mcp_not_found", status=404)
    ok, error = _test_mcp_connection(item)
    item.last_test_ok = ok
    item.last_test_error = error or ""
    item.last_test_at = timezone.now()
    item.save(update_fields=["last_test_ok", "last_test_error", "last_test_at"])
    return _ok({"ok": ok, "error": error})


@require_http_methods(["GET"])
@desktop_auth_required("studio")
def mcp_tools(request, mcp_id: int):
    admin_error = _require_admin(request)
    if admin_error:
        return admin_error
    user = request.desktop_user
    item = MCPServerPool.objects.filter(id=mcp_id, owner=user).first()
    if not item:
        return _error("MCP server not found", code="mcp_not_found", status=404)
    try:
        result = asyncio.run(inspect_mcp_server(item))
    except MCPClientError as exc:
        return _error(str(exc), code="mcp_inspection_failed", status=400)
    except Exception as exc:
        return _error(f"Failed to inspect MCP server: {exc}", code="mcp_inspection_failed", status=500)
    return _ok(result)
