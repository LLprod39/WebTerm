"""
Server operational endpoints: connection test, command execution, and OS detection.
"""

import json

from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from app.tools.ssh_tools import SSHExecuteTool, ssh_manager
from core_ui.activity import log_user_activity
from core_ui.api_failure import internal_error_response
from core_ui.decorators import require_feature
from core_ui.models import UserActivityLog
from servers.models import ServerCommandHistory
from servers.ssh_host_keys import (
    SSHHostKeyEnrollmentRequired,
    SSHHostKeyFingerprintMismatch,
    SSHHostKeyRotationRequired,
    enroll_server_host_key,
    get_server_trusted_host_keys,
    probe_server_host_key,
)
from servers.views.server_helpers import (
    _accessible_servers_queryset,
    _resolve_server_secret,
    _resolve_server_sudo_secret,
    _serialize_detected_os_fields,
    _server_has_capability,
)


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_test_connection(request, server_id):
    """Test connection to server."""
    try:
        server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
        if not _server_has_capability(server, request.user, "connect_terminal"):
            return JsonResponse({"success": False, "error": "Missing server capability: connect_terminal"}, status=403)
        data = json.loads(request.body)
        refresh_host_key = data.get("refresh_host_key") is True
        enroll_host_key = data.get("enroll_host_key") is True
        is_owner = server.user_id == request.user.id
        trusted_host_keys = get_server_trusted_host_keys(server)
        trusted_fingerprints = [
            str(item.get("fingerprint_sha256") or "") for item in trusted_host_keys if item.get("fingerprint_sha256")
        ]

        if (refresh_host_key or enroll_host_key) and not is_owner:
            return JsonResponse({"success": False, "error": "Only owner can enroll trusted SSH host key"}, status=403)

        if enroll_host_key:
            expected_fingerprint = str(data.get("expected_host_key_fingerprint") or "").strip()
            try:
                enrolled_record = async_to_sync(enroll_server_host_key)(
                    server,
                    expected_fingerprint=expected_fingerprint,
                    allow_replace=data.get("replace_host_key") is True,
                )
            except SSHHostKeyFingerprintMismatch as exc:
                return JsonResponse(
                    {
                        "success": False,
                        "code": "host_key_fingerprint_mismatch",
                        "error": str(exc),
                        "host_key": {
                            "fingerprint_sha256": exc.observed,
                        },
                        "trusted_fingerprints": trusted_fingerprints,
                        "is_rotation": bool(trusted_host_keys),
                    }
                )
            except (SSHHostKeyEnrollmentRequired, SSHHostKeyRotationRequired) as exc:
                return JsonResponse(
                    {"success": False, "code": "host_key_enrollment_rejected", "error": str(exc)}, status=409
                )

            log_user_activity(
                user=request.user,
                request=request,
                category="servers",
                action="server_host_key_rotated" if trusted_host_keys else "server_host_key_enrolled",
                status=UserActivityLog.STATUS_SUCCESS,
                description=f'SSH host key trusted for "{server.name}"',
                entity_type="server",
                entity_id=server.id,
                entity_name=server.name,
                metadata={
                    "algorithm": enrolled_record.get("algorithm", ""),
                    "fingerprint_sha256": enrolled_record.get("fingerprint_sha256", ""),
                    "previous_fingerprints": trusted_fingerprints,
                },
            )
            trusted_host_keys = [enrolled_record]
        elif is_owner:
            candidate = async_to_sync(probe_server_host_key)(server)
            candidate_is_trusted = any(
                item.get("public_key") == candidate.get("public_key") for item in trusted_host_keys
            )
            if refresh_host_key or not candidate_is_trusted:
                is_rotation = bool(trusted_host_keys)
                return JsonResponse(
                    {
                        "success": False,
                        "code": (
                            "host_key_rotation_confirmation_required"
                            if is_rotation
                            else "host_key_confirmation_required"
                        ),
                        "error": (
                            "SSH host key changed. Verify the new fingerprint before replacing trust."
                            if is_rotation
                            else "Verify the SSH host key fingerprint before the first connection."
                        ),
                        "host_key": {
                            "algorithm": candidate.get("algorithm", ""),
                            "fingerprint_sha256": candidate.get("fingerprint_sha256", ""),
                        },
                        "trusted_fingerprints": trusted_fingerprints,
                        "is_rotation": is_rotation,
                    }
                )
        elif not trusted_host_keys:
            return JsonResponse(
                {
                    "success": False,
                    "code": "host_key_owner_enrollment_required",
                    "error": "Server owner must verify and enroll the SSH host key before shared connections.",
                },
                status=409,
            )
        try:
            password = _resolve_server_secret(server, request, data)
        except ValueError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)

        async def test_conn():
            try:
                conn_id = await ssh_manager.connect(
                    host=server.host,
                    username=server.username,
                    password=password,
                    key_path=server.key_path if server.auth_method in ["key", "key_password"] else None,
                    port=server.port,
                    network_config=server.network_config or {},
                    server=server,
                )
                await ssh_manager.disconnect(conn_id)
                return {"success": True, "message": "Connection successful"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        result = async_to_sync(test_conn)()

        if result["success"]:
            server.last_connected = timezone.now()
            server.save(update_fields=["last_connected"])
            from servers.os_detect_service import schedule_os_detect_for_server_ids

            schedule_os_detect_for_server_ids([server.id])
            log_user_activity(
                user=request.user,
                request=request,
                category="servers",
                action="server_test_connection",
                status=UserActivityLog.STATUS_SUCCESS,
                description=f'Server connection test succeeded for "{server.name}"',
                entity_type="server",
                entity_id=server.id,
                entity_name=server.name,
                metadata={"host": server.host, "port": server.port},
            )
        else:
            log_user_activity(
                user=request.user,
                request=request,
                category="servers",
                action="server_test_connection",
                status=UserActivityLog.STATUS_ERROR,
                description=f'Server connection test failed for "{server.name}": {result.get("error", "unknown error")}',
                entity_type="server",
                entity_id=server.id,
                entity_name=server.name,
                metadata={"host": server.host, "port": server.port},
            )

        return JsonResponse(result)

    except Exception as e:
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_test_connection",
            status=UserActivityLog.STATUS_ERROR,
            description="Server connection test failed (internal_error)",
            entity_type="server",
            entity_id=server_id,
        )
        return internal_error_response(request, e)


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_execute_command(request, server_id):
    """Execute command on server."""
    try:
        server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
        if not _server_has_capability(server, request.user, "execute_command"):
            return JsonResponse({"success": False, "error": "Missing server capability: execute_command"}, status=403)
        data = json.loads(request.body)
        command = data.get("command", "")

        if not command:
            return JsonResponse({"error": "Command required"}, status=400)

        try:
            password = _resolve_server_secret(server, request, data)
            sudo_password = _resolve_server_sudo_secret(server, request, data)
        except ValueError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)

        async def exec_cmd():
            try:
                conn_id = await ssh_manager.connect(
                    host=server.host,
                    username=server.username,
                    password=password,
                    key_path=server.key_path if server.auth_method in ["key", "key_password"] else None,
                    port=server.port,
                    network_config=server.network_config or {},
                    server=server,
                )

                execute_tool = SSHExecuteTool()
                result = await execute_tool.execute(
                    conn_id=conn_id,
                    command=command,
                    sudo_auth_mode=getattr(server, "sudo_auth_mode", "none"),
                    sudo_password=sudo_password,
                )

                out_str = result.get("stdout", "") + (result.get("stderr") or "")
                await sync_to_async(ServerCommandHistory.objects.create, thread_sensitive=True)(
                    server=server,
                    user=request.user,
                    actor_kind=ServerCommandHistory.ACTOR_HUMAN,
                    source_kind=ServerCommandHistory.SOURCE_API,
                    command=command,
                    output=out_str or str(result),
                    exit_code=result.get("exit_code", 0),
                )

                await ssh_manager.disconnect(conn_id)
                return {"success": True, "output": result}
            except Exception as e:
                return {"success": False, "error": str(e)}

        result = async_to_sync(exec_cmd)()
        if result.get("success"):
            output = result.get("output") or {}
            command_preview = command if len(command) <= 400 else command[:397] + "..."
            log_user_activity(
                user=request.user,
                request=request,
                category="servers",
                action="server_command_execute",
                status=UserActivityLog.STATUS_SUCCESS,
                description=f'Executed command on "{server.name}": {command_preview}',
                entity_type="server",
                entity_id=server.id,
                entity_name=server.name,
                metadata={
                    "command": command_preview,
                    "exit_code": output.get("exit_code"),
                },
            )
        else:
            log_user_activity(
                user=request.user,
                request=request,
                category="servers",
                action="server_command_execute",
                status=UserActivityLog.STATUS_ERROR,
                description=f'Command execution failed on "{server.name}": {result.get("error", "unknown error")}',
                entity_type="server",
                entity_id=server.id,
                entity_name=server.name,
                metadata={"command": command[:400]},
            )
        return JsonResponse(result)

    except Exception as e:
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_command_execute",
            status=UserActivityLog.STATUS_ERROR,
            description="Command execution failed (internal_error)",
            entity_type="server",
            entity_id=server_id,
        )
        return internal_error_response(request, e)


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_detect_os(request, server_id):
    """SSH OS detection for a single server.

    Manual UI action always forces a fresh probe (ignores auto-detect cooldown).
    """
    from servers.os_detect_service import detect_os_for_server

    server = _accessible_servers_queryset(request.user).filter(id=server_id).first()
    if not server:
        return JsonResponse({"success": False, "error": "Server not found"}, status=404)

    try:
        body = json.loads(request.body) if request.body else {}
    except Exception:
        body = {}
    # Explicit user action defaults to force=true; allow opt-out with force=false.
    force = True if "force" not in body else bool(body.get("force"))

    try:
        result = detect_os_for_server(server.id, force=force)
    except Exception as exc:
        return internal_error_response(request, exc)

    server.refresh_from_db(fields=["detected_os", "detected_os_meta", "detected_os_attempted_at"])
    if result.get("success") and not result.get("cached") and not result.get("needs_retry"):
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_detect_os",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'OS detected for "{server.name}": {result.get("detected_os", "unknown")}',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
        )
    elif not result.get("cached"):
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_detect_os",
            status=UserActivityLog.STATUS_ERROR,
            description=f'OS detection failed for "{server.name}": {result.get("error", "unknown")}',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
        )

    fields = _serialize_detected_os_fields(server)
    # Cached/queued probes stay 200; unresolved known-failure probes also 200 with needs_retry.
    status_code = (
        200
        if result.get("success") or result.get("cached") or result.get("queued") or result.get("needs_retry")
        else 500
    )
    return JsonResponse(
        {
            **result,
            **fields,
        },
        status=status_code,
    )


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_detect_os_batch(request):
    """Batch OS detection for accessible servers."""
    from servers.os_detect import detect_os_batch
    from servers.os_detect_service import server_needs_os_detect

    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = {}

    only_stale = bool(data.get("only_stale", False))
    server_ids = data.get("server_ids")
    concurrency = max(1, min(int(data.get("concurrency", 4) or 4), 5))

    servers = list(_accessible_servers_queryset(request.user).filter(is_active=True))
    if server_ids:
        wanted = {int(x) for x in server_ids}
        servers = [server for server in servers if server.id in wanted]
    if only_stale:
        # Includes empty + unknown + time-stale known distros.
        servers = [server for server in servers if server_needs_os_detect(server)]

    if not servers:
        return JsonResponse({"success": True, "results": [], "count": 0})

    batch_lock = "servers:os-detect:batch:lock"
    if not cache.add(batch_lock, "1", timeout=max(60, concurrency * 20)):
        return JsonResponse({"success": False, "error": "Batch detection already running"}, status=429)

    try:
        results = async_to_sync(detect_os_batch)(servers, concurrency=concurrency)
    except Exception as exc:
        return internal_error_response(request, exc)
    finally:
        cache.delete(batch_lock)

    ok_count = sum(1 for item in results if item.get("success"))
    log_user_activity(
        user=request.user,
        request=request,
        category="servers",
        action="server_detect_os_batch",
        status=UserActivityLog.STATUS_SUCCESS if ok_count else UserActivityLog.STATUS_ERROR,
        description=f"Batch OS detection: {ok_count}/{len(results)} succeeded",
        entity_type="server",
        metadata={"count": len(results), "ok": ok_count},
    )

    return JsonResponse(
        {
            "success": ok_count > 0,
            "count": len(results),
            "ok": ok_count,
            "results": results,
        }
    )
