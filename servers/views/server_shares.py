"""
Server sharing endpoints.
"""

import json

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from core_ui.activity import log_user_activity
from core_ui.decorators import require_feature
from core_ui.models import UserActivityLog
from servers.models import Server, ServerShare


def _parse_expires_at(raw_value):
    if raw_value in (None, "", "null", "None"):
        return None
    dt = parse_datetime(str(raw_value))
    if not dt:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _parse_bool(raw_value, default: bool = False) -> bool:
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        return raw_value
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def _share_payload(share: ServerShare, *, active: bool | None = None) -> dict:
    if active is None:
        active = share.is_active()
    return {
        "id": share.id,
        "user_id": share.user_id,
        "username": share.user.username,
        "email": share.user.email or "",
        "share_context": bool(share.share_context),
        "can_connect_terminal": bool(share.can_connect_terminal),
        "can_execute_command": bool(share.can_execute_command),
        "can_read_files": bool(share.can_read_files),
        "can_write_files": bool(share.can_write_files),
        "expires_at": share.expires_at.isoformat() if share.expires_at else None,
        "created_at": share.created_at.isoformat() if share.created_at else None,
        "is_active": active and not share.is_revoked,
    }


@login_required
@require_feature("servers")
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
        payload.append(_share_payload(share, active=active))
    return JsonResponse({"success": True, "shares": payload})


@login_required
@require_feature("servers")
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
            target_user = (
                User.objects.filter(username=identifier).first() or User.objects.filter(email=identifier).first()
            )
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

        share_context = _parse_bool(data.get("share_context"), True)
        can_connect_terminal = _parse_bool(data.get("can_connect_terminal"))
        can_execute_command = _parse_bool(data.get("can_execute_command"))
        can_read_files = _parse_bool(data.get("can_read_files"))
        can_write_files = _parse_bool(data.get("can_write_files"))

        share, _ = ServerShare.objects.update_or_create(
            server=server,
            user=target_user,
            defaults={
                "shared_by": request.user,
                "share_context": share_context,
                "can_connect_terminal": can_connect_terminal,
                "can_execute_command": can_execute_command,
                "can_read_files": can_read_files,
                "can_write_files": can_write_files,
                "expires_at": expires_at,
                "is_revoked": False,
                "revoked_at": None,
            },
        )

        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_share_create",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Shared server "{server.name}" with user "{target_user.username}"',
            entity_type="server_share",
            entity_id=share.id,
            entity_name=server.name,
            metadata={
                "server_id": server.id,
                "shared_with_user_id": target_user.id,
                "shared_with_username": target_user.username,
                "share_context": bool(share_context),
                "capabilities": {
                    "connect_terminal": bool(can_connect_terminal),
                    "execute_command": bool(can_execute_command),
                    "read_files": bool(can_read_files),
                    "write_files": bool(can_write_files),
                },
                "expires_at": share.expires_at.isoformat() if share.expires_at else None,
            },
        )

        return JsonResponse(
            {
                "success": True,
                "share": _share_payload(share),
            }
        )
    except Http404:
        raise
    except Exception as e:
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_share_create",
            status=UserActivityLog.STATUS_ERROR,
            description=f"Server share create failed: {e}",
            entity_type="server",
            entity_id=server_id,
        )
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_feature("servers")
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
        category="servers",
        action="server_share_revoke",
        status=UserActivityLog.STATUS_SUCCESS,
        description=f'Revoked server share for "{server.name}"',
        entity_type="server_share",
        entity_id=share.id,
        entity_name=server.name,
        metadata={
            "server_id": server.id,
            "shared_user_id": share.user_id,
            "shared_username": share.user.username,
        },
    )
    return JsonResponse({"success": True})
