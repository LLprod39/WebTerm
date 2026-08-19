"""
Linux UI workload endpoints: services, processes, and Docker.
"""

import json

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
    get_linux_ui_docker,
    get_linux_ui_docker_logs,
    get_linux_ui_processes,
    get_linux_ui_service_logs,
    get_linux_ui_services,
    run_linux_ui_docker_action,
    run_linux_ui_process_action,
    run_linux_ui_service_action,
)
from servers.views.server_helpers import (
    _accessible_servers_queryset,
    _require_ssh_server,
    _resolve_server_secret,
    _server_has_capability,
)
from servers.views.server_linux_ui import (
    _linux_ui_error_response,
    _linux_ui_server_payload,
    _missing_linux_ui_capability_response,
    require_linux_ui_admin,
)


@login_required
@require_feature("servers")
@require_linux_ui_admin
@require_http_methods(["GET"])
def server_linux_ui_services(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "connect_terminal"):
        return _missing_linux_ui_capability_response("connect_terminal")
    try:
        _require_ssh_server(server)
        secret = _resolve_server_secret(server, request, request.GET)
        services = async_to_sync(get_linux_ui_services)(
            server,
            secret=secret or "",
            limit=request.GET.get("limit") or 120,
            user_id=request.user.id,
        )
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_linux_ui_services",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Linux UI services for "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
        )
        return JsonResponse(
            {
                "success": True,
                "server": _linux_ui_server_payload(server),
                "services": services["services"],
                "summary": services["summary"],
                "limit": services["limit"],
                "observed_at": timezone.now().isoformat(),
            }
        )
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature("servers")
@require_linux_ui_admin
@require_http_methods(["GET"])
def server_linux_ui_service_logs(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "connect_terminal"):
        return _missing_linux_ui_capability_response("connect_terminal")
    try:
        _require_ssh_server(server)
        secret = _resolve_server_secret(server, request, request.GET)
        logs = async_to_sync(get_linux_ui_service_logs)(
            server,
            secret=secret or "",
            service=str(request.GET.get("service") or ""),
            lines=request.GET.get("lines") or 80,
            user_id=request.user.id,
        )
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_linux_ui_service_logs",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved service logs for "{logs["service"]}" on "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata={"service": logs["service"], "source": logs["source"]},
        )
        return JsonResponse(
            {
                "success": True,
                "server": _linux_ui_server_payload(server),
                "service_logs": logs,
                "observed_at": timezone.now().isoformat(),
            }
        )
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature("servers")
@require_linux_ui_admin
@require_http_methods(["POST"])
def server_linux_ui_service_action(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "execute_command"):
        return _missing_linux_ui_capability_response("execute_command")
    try:
        _require_ssh_server(server)
        data = json.loads(request.body or "{}")
        secret = _resolve_server_secret(server, request, data)
        action_result = async_to_sync(run_linux_ui_service_action)(
            server,
            secret=secret or "",
            service=str(data.get("service") or ""),
            action=str(data.get("action") or ""),
            user_id=request.user.id,
        )
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_linux_ui_service_action",
            status=UserActivityLog.STATUS_SUCCESS if action_result.get("success") else UserActivityLog.STATUS_ERROR,
            description=(
                f'Ran Linux UI action "{action_result["action"]}" on "{action_result["service"]}" for "{server.name}"'
            ),
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata={
                "service": action_result["service"],
                "action": action_result["action"],
                "dangerous": bool(action_result.get("dangerous")),
            },
        )
        return JsonResponse(
            {
                "success": bool(action_result.get("success")),
                "server": _linux_ui_server_payload(server),
                "service_action": action_result,
                "performed_at": timezone.now().isoformat(),
            }
        )
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature("servers")
@require_linux_ui_admin
@require_http_methods(["GET"])
def server_linux_ui_processes(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "connect_terminal"):
        return _missing_linux_ui_capability_response("connect_terminal")
    try:
        _require_ssh_server(server)
        secret = _resolve_server_secret(server, request, request.GET)
        processes = async_to_sync(get_linux_ui_processes)(
            server,
            secret=secret or "",
            limit=request.GET.get("limit") or 80,
            user_id=request.user.id,
        )
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_linux_ui_processes",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Linux UI processes for "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
        )
        return JsonResponse(
            {
                "success": True,
                "server": _linux_ui_server_payload(server),
                "processes": processes,
                "observed_at": timezone.now().isoformat(),
            }
        )
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature("servers")
@require_linux_ui_admin
@require_http_methods(["POST"])
def server_linux_ui_process_action(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "execute_command"):
        return _missing_linux_ui_capability_response("execute_command")
    try:
        _require_ssh_server(server)
        data = json.loads(request.body or "{}")
        secret = _resolve_server_secret(server, request, data)
        action_result = async_to_sync(run_linux_ui_process_action)(
            server,
            secret=secret or "",
            pid=data.get("pid"),
            action=str(data.get("action") or ""),
            user_id=request.user.id,
        )
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_linux_ui_process_action",
            status=UserActivityLog.STATUS_SUCCESS if action_result.get("success") else UserActivityLog.STATUS_ERROR,
            description=f'Ran Linux UI process action "{action_result["action"]}" on PID {action_result["pid"]} for "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata={
                "pid": action_result["pid"],
                "action": action_result["action"],
                "dangerous": bool(action_result.get("dangerous")),
            },
        )
        return JsonResponse(
            {
                "success": bool(action_result.get("success")),
                "server": _linux_ui_server_payload(server),
                "process_action": action_result,
                "performed_at": timezone.now().isoformat(),
            }
        )
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature("servers")
@require_linux_ui_admin
@require_http_methods(["GET"])
def server_linux_ui_docker(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "connect_terminal"):
        return _missing_linux_ui_capability_response("connect_terminal")
    try:
        _require_ssh_server(server)
        secret = _resolve_server_secret(server, request, request.GET)
        docker_data = async_to_sync(get_linux_ui_docker)(
            server,
            secret=secret or "",
            user_id=request.user.id,
        )
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_linux_ui_docker",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Linux UI docker data for "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata=docker_data.get("summary") or {},
        )
        return JsonResponse(
            {
                "success": True,
                "server": _linux_ui_server_payload(server),
                "docker": docker_data,
                "observed_at": timezone.now().isoformat(),
            }
        )
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature("servers")
@require_linux_ui_admin
@require_http_methods(["GET"])
def server_linux_ui_docker_logs(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "connect_terminal"):
        return _missing_linux_ui_capability_response("connect_terminal")
    try:
        _require_ssh_server(server)
        secret = _resolve_server_secret(server, request, request.GET)
        docker_logs = async_to_sync(get_linux_ui_docker_logs)(
            server,
            secret=secret or "",
            container=str(request.GET.get("container") or ""),
            lines=request.GET.get("lines") or 80,
            user_id=request.user.id,
        )
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_linux_ui_docker_logs",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Retrieved Docker logs for "{docker_logs["container"]}" on "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata={"container": docker_logs["container"], "lines": docker_logs["lines"]},
        )
        return JsonResponse(
            {
                "success": True,
                "server": _linux_ui_server_payload(server),
                "docker_logs": docker_logs,
                "observed_at": timezone.now().isoformat(),
            }
        )
    except Exception as exc:
        return _linux_ui_error_response(exc)


@login_required
@require_feature("servers")
@require_linux_ui_admin
@require_http_methods(["POST"])
def server_linux_ui_docker_action(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "execute_command"):
        return _missing_linux_ui_capability_response("execute_command")
    try:
        _require_ssh_server(server)
        data = json.loads(request.body or "{}")
        secret = _resolve_server_secret(server, request, data)
        action_result = async_to_sync(run_linux_ui_docker_action)(
            server,
            secret=secret or "",
            container=str(data.get("container") or ""),
            action=str(data.get("action") or ""),
            user_id=request.user.id,
        )
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_linux_ui_docker_action",
            status=UserActivityLog.STATUS_SUCCESS if action_result.get("success") else UserActivityLog.STATUS_ERROR,
            description=(
                f'Ran Docker action "{action_result["action"]}" on "{action_result["container"]}" for "{server.name}"'
            ),
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata={
                "container": action_result["container"],
                "action": action_result["action"],
                "dangerous": bool(action_result.get("dangerous")),
            },
        )
        return JsonResponse(
            {
                "success": bool(action_result.get("success")),
                "server": _linux_ui_server_payload(server),
                "docker_action": action_result,
                "performed_at": timezone.now().isoformat(),
            }
        )
    except Exception as exc:
        return _linux_ui_error_response(exc)
