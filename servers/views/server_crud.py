"""
Server CRUD, detail, and saved-secret endpoints.
"""

import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from core_ui.activity import log_user_activity
from core_ui.decorators import require_feature
from core_ui.models import UserActivityLog
from app.agent_kernel.sudo_policy import SUDO_AUTH_MODE_STORED_PASSWORD, normalize_sudo_auth_mode
from servers.models import Server, ServerGroup
from servers.secret_utils import (
    clear_server_sudo_secret,
    get_server_auth_secret,
    has_saved_server_secret,
    has_saved_server_sudo_secret,
    store_server_auth_secret,
    store_server_sudo_secret,
)
from servers.ssh_private_keys import delete_managed_private_key, store_uploaded_private_key
from servers.ssh_host_keys import clear_server_trusted_host_keys, get_server_trusted_host_keys
from servers.views.server_helpers import (
    _accessible_servers_queryset,
    _active_server_share,
    _effective_master_password,
    _get_group_role,
    _server_capabilities,
    _shared_server_context_allowed,
)


def _normalize_group_for_user(raw_group_id, user):
    group_id = raw_group_id.strip() if isinstance(raw_group_id, str) else raw_group_id
    if group_id in ("", "null", "None"):
        return None, None
    if group_id is None:
        return None, None
    try:
        group_id = int(group_id)
    except (TypeError, ValueError):
        return None, JsonResponse({"error": "Invalid group_id"}, status=400)
    try:
        group = ServerGroup.objects.get(id=group_id)
        if _get_group_role(group, user) == "":
            return None, JsonResponse({"error": "Permission denied for group"}, status=403)
    except ServerGroup.DoesNotExist:
        return None, JsonResponse({"error": "Invalid group"}, status=400)
    return group, None


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_create(request):
    """Create a new server."""
    try:
        data = json.loads(request.body)

        raw_port = data.get("port", 22)
        try:
            port = int(raw_port)
        except (TypeError, ValueError):
            return JsonResponse({"error": "Invalid port"}, status=400)
        if port < 1 or port > 65535:
            return JsonResponse({"error": "Port must be in range 1..65535"}, status=400)

        server_type = str(data.get("server_type", "ssh") or "ssh").strip().lower()
        if server_type != "ssh":
            return JsonResponse({"error": "Invalid server_type"}, status=400)

        auth_method = str(data.get("auth_method", "password") or "password").strip().lower()
        if auth_method not in ("password", "key", "key_password"):
            return JsonResponse({"error": "Invalid auth_method"}, status=400)

        group, error_response = _normalize_group_for_user(data.get("group_id"), request.user)
        if error_response:
            return error_response

        password = str(data.get("password", "") or "").strip()
        sudo_auth_mode = normalize_sudo_auth_mode(data.get("sudo_auth_mode"))
        sudo_password = str(data.get("sudo_password", "") or "").strip()
        if sudo_auth_mode == SUDO_AUTH_MODE_STORED_PASSWORD and not sudo_password:
            return JsonResponse({"error": "sudo_password is required when sudo_auth_mode=stored_password"}, status=400)

        master_password = _effective_master_password(request, data)
        private_key = str(data.get("ssh_private_key") or "")
        with transaction.atomic():
            server = Server.objects.create(
                user=request.user,
                name=data.get("name", ""),
                server_type=server_type,
                host=data.get("host", ""),
                port=port,
                username=data.get("username", ""),
                auth_method=auth_method,
                key_path=data.get("key_path", ""),
                sudo_auth_mode=sudo_auth_mode,
                tags=data.get("tags", ""),
                notes=data.get("notes", ""),
                corporate_context=data.get("corporate_context", ""),
                group=group,
            )

            if private_key.strip() and auth_method in ("key", "key_password"):
                server.key_path = store_uploaded_private_key(server, private_key, passphrase=password)
                server.save(update_fields=["key_path"])
            if password:
                store_server_auth_secret(server, secret_value=password, master_password=master_password)
                server.save()
            if sudo_auth_mode == SUDO_AUTH_MODE_STORED_PASSWORD and sudo_password:
                store_server_sudo_secret(server, secret_value=sudo_password, master_password=master_password)
                server.save()

        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_create",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Created server "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata={
                "host": server.host,
                "port": server.port,
                "server_type": server.server_type,
                "group_id": server.group_id,
            },
        )

        from servers.os_detect_service import schedule_os_detect_for_server_ids

        schedule_os_detect_for_server_ids([server.id], force=True)

        return JsonResponse({"success": True, "server_id": server.id, "message": "Server created successfully"})

    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_create",
            status=UserActivityLog.STATUS_ERROR,
            description=f"Server create failed: {e}",
            entity_type="server",
        )
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_update(request, server_id):
    """Update server configuration including network_config."""
    try:
        server = get_object_or_404(Server, id=server_id, user=request.user)
        data = json.loads(request.body)
        host_changed = False

        if "name" in data:
            server.name = data["name"]
        if "host" in data:
            next_host = str(data["host"] or "")
            host_changed = host_changed or next_host != server.host
            server.host = next_host
        if "port" in data:
            try:
                port = int(data["port"])
            except (TypeError, ValueError):
                return JsonResponse({"error": "Invalid port"}, status=400)
            if port < 1 or port > 65535:
                return JsonResponse({"error": "Port must be in range 1..65535"}, status=400)
            host_changed = host_changed or port != int(server.port or 22)
            server.port = port
        if "username" in data:
            server.username = data["username"]
        if "server_type" in data:
            server_type = str(data.get("server_type") or "").strip().lower()
            if server_type != "ssh":
                return JsonResponse({"error": "Invalid server_type"}, status=400)
            server.server_type = server_type
        if "auth_method" in data:
            auth_method = str(data.get("auth_method") or "").strip().lower()
            if auth_method not in ("password", "key", "key_password"):
                return JsonResponse({"error": "Invalid auth_method"}, status=400)
            server.auth_method = auth_method
        if "key_path" in data:
            server.key_path = data["key_path"]
        if "tags" in data:
            server.tags = data["tags"]
        if "notes" in data:
            server.notes = data["notes"]
        if "corporate_context" in data:
            server.corporate_context = data["corporate_context"]
        if "is_active" in data:
            server.is_active = data["is_active"]
        if "ai_read_only" in data:
            server.ai_read_only = bool(data["ai_read_only"])
        if "sudo_auth_mode" in data:
            server.sudo_auth_mode = normalize_sudo_auth_mode(data.get("sudo_auth_mode"))

        if "group_id" in data:
            group, error_response = _normalize_group_for_user(data.get("group_id"), request.user)
            if error_response:
                return error_response
            server.group = group

        if "network_config" in data:
            network_config = data["network_config"]
            if isinstance(network_config, dict):
                server.network_config = network_config
                server.update_network_flags()

        if "password" in data:
            password = str(data.get("password") or "").strip()
            master_password = _effective_master_password(request, data)
            if password:
                store_server_auth_secret(server, secret_value=password, master_password=master_password)

        if "sudo_auth_mode" in data or "sudo_password" in data:
            sudo_password = str(data.get("sudo_password") or "").strip()
            master_password = _effective_master_password(request, data)
            if server.sudo_auth_mode == SUDO_AUTH_MODE_STORED_PASSWORD:
                if sudo_password:
                    store_server_sudo_secret(server, secret_value=sudo_password, master_password=master_password)
                elif not has_saved_server_sudo_secret(server):
                    return JsonResponse(
                        {"error": "sudo_password is required when sudo_auth_mode=stored_password"},
                        status=400,
                    )
            else:
                clear_server_sudo_secret(server)

        if str(data.get("ssh_private_key") or "").strip() and server.auth_method in ("key", "key_password"):
            old_key_path = server.key_path
            password = str(data.get("password") or "").strip()
            server.key_path = store_uploaded_private_key(server, data["ssh_private_key"], passphrase=password)
            delete_managed_private_key(old_key_path)

        if host_changed:
            clear_server_trusted_host_keys(server)

        changed_fields = sorted(data.keys())
        server.save()
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_update",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Updated server "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata={"changed_fields": changed_fields},
        )

        return JsonResponse(
            {
                "success": True,
                "message": "Server updated successfully",
                "server": {
                    "id": server.id,
                    "name": server.name,
                    "host": server.host,
                    "port": server.port,
                    "network_context": server.get_network_context_summary(),
                },
            }
        )

    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_update",
            status=UserActivityLog.STATUS_ERROR,
            description=f"Server update failed: {e}",
            entity_type="server",
            entity_id=server_id,
        )
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_delete(request, server_id):
    """Delete a server."""
    try:
        server = get_object_or_404(Server, id=server_id, user=request.user)
        server_name = server.name
        server.delete()
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_delete",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Deleted server "{server_name}"',
            entity_type="server",
            entity_id=server_id,
            entity_name=server_name,
        )
        return JsonResponse({"success": True, "message": "Server deleted"})
    except Exception as e:
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_delete",
            status=UserActivityLog.STATUS_ERROR,
            description=f"Server delete failed: {e}",
            entity_type="server",
            entity_id=server_id,
        )
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def server_get(request, server_id):
    """Get server details for viewing/editing."""
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    share = _active_server_share(server, request.user)
    is_owner = server.user_id == request.user.id
    can_access_context = _shared_server_context_allowed(server, request.user, share)
    trusted_host_keys = get_server_trusted_host_keys(server) if is_owner else []
    return JsonResponse(
        {
            "id": server.id,
            "name": server.name,
            "server_type": server.server_type,
            "host": server.host,
            "port": server.port,
            "username": server.username,
            "auth_method": server.auth_method,
            "key_path": server.key_path,
            "tags": server.tags,
            "notes": server.notes if can_access_context else "",
            "corporate_context": server.corporate_context if can_access_context else "",
            "group_id": server.group_id,
            "is_active": server.is_active,
            "ai_read_only": bool(getattr(server, "ai_read_only", False)),
            "sudo_auth_mode": getattr(server, "sudo_auth_mode", "none") or "none",
            "network_config": server.network_config if can_access_context else {},
            "has_saved_password": bool(is_owner and has_saved_server_secret(server)),
            "has_saved_sudo_password": bool(is_owner and has_saved_server_sudo_secret(server)),
            "can_view_password": bool(
                is_owner and server.auth_method in ["password", "key_password"] and has_saved_server_secret(server)
            ),
            "can_edit": bool(is_owner),
            "capabilities": _server_capabilities(server, request.user, share),
            "is_shared_server": bool(share),
            "share_context_enabled": bool(share.share_context) if share else True,
            "shared_by_username": share.shared_by.username if share and share.shared_by else "",
            "has_trusted_host_keys": bool(trusted_host_keys),
            "trusted_host_key_fingerprints": [
                item.get("fingerprint_sha256", "") for item in trusted_host_keys if item.get("fingerprint_sha256")
            ],
        }
    )


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_reveal_password(request, server_id):
    """Reveal decrypted server password for the server owner only."""
    try:
        server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
        if server.user_id != request.user.id:
            return JsonResponse(
                {"success": False, "error": "Only the server owner can reveal the saved password"}, status=403
            )
        if server.auth_method not in ["password", "key_password"]:
            return JsonResponse({"success": False, "error": "Password is not used for this auth method"}, status=400)
        if not has_saved_server_secret(server):
            return JsonResponse({"success": False, "error": "Saved password is not available"}, status=400)

        data = json.loads(request.body or "{}")
        master_password = str(data.get("master_password") or "").strip()
        if not master_password:
            master_password = str(request.session.get("_mp") or "").strip()
        if not master_password:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Master password is required to reveal the saved password",
                },
                status=400,
            )
        try:
            password = get_server_auth_secret(
                server,
                master_password=master_password,
            )
        except ValueError:
            return JsonResponse(
                {"success": False, "error": "Failed to decrypt password. Check MASTER_PASSWORD"}, status=400
            )

        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_password_reveal",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Revealed password for server "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata={
                "is_owner": True,
                "is_shared_server": False,
                "shared_by": "",
            },
        )
        return JsonResponse({"success": True, "password": password})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)
