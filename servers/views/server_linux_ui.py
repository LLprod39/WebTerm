"""
Linux UI read-only snapshot endpoints.
"""

from asgiref.sync import async_to_sync
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core_ui.activity import log_user_activity
from core_ui.decorators import require_feature
from core_ui.models import UserActivityLog
from servers.linux_ui import (
    get_linux_ui_capabilities,
    get_linux_ui_disk,
    get_linux_ui_logs,
    get_linux_ui_network,
    get_linux_ui_overview,
    get_linux_ui_packages,
    get_linux_ui_settings,
)
from servers.views.server_helpers import (
    _accessible_servers_queryset,
    _require_ssh_server,
    _resolve_server_secret,
    _server_has_capability,
)


def _linux_ui_error_response(exc: Exception) -> JsonResponse:
    if isinstance(exc, ValueError):
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    if isinstance(exc, PermissionError):
        return JsonResponse({"success": False, "error": "Недостаточно прав для выполнения операции"}, status=403)
    return JsonResponse({"success": False, "error": str(exc) or "Linux UI request failed"}, status=500)


def _linux_ui_server_payload(server) -> dict:
    return {
        "id": server.id,
        "name": server.name,
        "host": server.host,
        "username": server.username,
    }


def _missing_linux_ui_capability_response(capability: str) -> JsonResponse:
    return JsonResponse({"success": False, "error": f"Missing server capability: {capability}"}, status=403)


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def server_linux_ui_capabilities(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "connect_terminal"):
        return _missing_linux_ui_capability_response("connect_terminal")
    try:
        _require_ssh_server(server)
        secret = _resolve_server_secret(server, request, {})
        capabilities = async_to_sync(get_linux_ui_capabilities)(server, secret=secret or "")
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_linux_ui_capabilities",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Linux UI capabilities for "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
        )
        return JsonResponse(
            {
                "success": True,
                "server": _linux_ui_server_payload(server),
                "capabilities": capabilities,
                "observed_at": timezone.now().isoformat(),
            }
        )
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def server_linux_ui_settings(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "connect_terminal"):
        return _missing_linux_ui_capability_response("connect_terminal")
    try:
        _require_ssh_server(server)
        secret = _resolve_server_secret(server, request, {})
        settings_snapshot = async_to_sync(get_linux_ui_settings)(server, secret=secret or "")
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_linux_ui_settings",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Linux UI settings snapshot for "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
        )
        return JsonResponse(
            {
                "success": True,
                "server": _linux_ui_server_payload(server),
                "settings": settings_snapshot,
                "observed_at": timezone.now().isoformat(),
            }
        )
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def server_linux_ui_overview(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "connect_terminal"):
        return _missing_linux_ui_capability_response("connect_terminal")
    try:
        _require_ssh_server(server)
        secret = _resolve_server_secret(server, request, {})
        overview = async_to_sync(get_linux_ui_overview)(server, secret=secret or "")
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_linux_ui_overview",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Linux UI overview for "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
        )
        return JsonResponse(
            {
                "success": True,
                "server": _linux_ui_server_payload(server),
                "overview": overview,
                "observed_at": timezone.now().isoformat(),
            }
        )
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def server_linux_ui_logs(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "connect_terminal"):
        return _missing_linux_ui_capability_response("connect_terminal")
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
            category="servers",
            action="server_linux_ui_logs",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Linux UI logs ({logs["source"]}) for "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata={"source": logs["source"], "service": logs.get("service") or ""},
        )
        return JsonResponse(
            {
                "success": True,
                "server": _linux_ui_server_payload(server),
                "logs": logs,
                "observed_at": timezone.now().isoformat(),
            }
        )
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def server_linux_ui_disk(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "connect_terminal"):
        return _missing_linux_ui_capability_response("connect_terminal")
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
            category="servers",
            action="server_linux_ui_disk",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Linux UI disk data for "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata=disk.get("summary") or {},
        )
        return JsonResponse(
            {
                "success": True,
                "server": _linux_ui_server_payload(server),
                "disk": disk,
                "observed_at": timezone.now().isoformat(),
            }
        )
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def server_linux_ui_network(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "connect_terminal"):
        return _missing_linux_ui_capability_response("connect_terminal")
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
            category="servers",
            action="server_linux_ui_network",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Linux UI network data for "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata=network.get("summary") or {},
        )
        return JsonResponse(
            {
                "success": True,
                "server": _linux_ui_server_payload(server),
                "network": network,
                "observed_at": timezone.now().isoformat(),
            }
        )
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def server_linux_ui_packages(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "connect_terminal"):
        return _missing_linux_ui_capability_response("connect_terminal")
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
            category="servers",
            action="server_linux_ui_packages",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Linux UI package data for "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata={
                "package_manager": packages.get("package_manager") or "",
                **(packages.get("summary") or {}),
            },
        )
        return JsonResponse(
            {
                "success": True,
                "server": _linux_ui_server_payload(server),
                "packages": packages,
                "observed_at": timezone.now().isoformat(),
            }
        )
    except Exception as exc:
        return _linux_ui_error_response(exc)
