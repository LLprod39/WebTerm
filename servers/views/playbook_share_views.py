"""Owner-managed user, group and workspace playbook grants."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from servers.models import PlaybookGrant
from servers.services.playbooks.sharing import (
    PlaybookGrantError,
    revoke_grant,
    save_grant,
    serialize_grant,
)
from servers.views.playbook_workspace_helpers import get_playbook_for_action, json_body, workspace_error


@login_required
@require_feature("servers")
@require_http_methods(["GET", "POST"])
def playbook_shares(request, playbook_id: int):
    try:
        playbook = get_playbook_for_action(request.user, playbook_id, "share")
        if request.method == "GET":
            grants = playbook.grants.select_related("user", "group")
            return JsonResponse({"success": True, "shares": [serialize_grant(item) for item in grants]})
        data = json_body(request)
        principal_type = str(data.get("principal_type") or "").strip().lower()
        user = None
        group = None
        workspace_shared = principal_type == "workspace"
        if principal_type == "user":
            user = get_object_or_404(get_user_model(), id=int(data.get("principal_id") or 0), is_active=True)
        elif principal_type == "group":
            group = get_object_or_404(Group, id=int(data.get("principal_id") or 0))
        elif not workspace_shared:
            raise PlaybookGrantError("principal_type must be user, group or workspace")
        expires_at = parse_datetime(str(data.get("expires_at") or "")) if data.get("expires_at") else None
        grant = save_grant(
            playbook=playbook,
            actor=request.user,
            role=str(data.get("role") or PlaybookGrant.ROLE_VIEWER),
            user=user,
            group=group,
            workspace_shared=workspace_shared,
            expires_at=expires_at,
            capability_overrides=(data.get("capabilities") if isinstance(data.get("capabilities"), dict) else None),
        )
        return JsonResponse({"success": True, "share": serialize_grant(grant)}, status=201)
    except PermissionDenied as exc:
        return workspace_error(code="playbook_forbidden", message=str(exc), status=403, stage="authorization")
    except (PlaybookGrantError, TypeError, ValueError) as exc:
        return workspace_error(code="playbook_share_invalid", message=str(exc), stage="share_save")


@login_required
@require_feature("servers")
@require_http_methods(["DELETE"])
def playbook_share_detail(request, playbook_id: int, share_id: int):
    try:
        playbook = get_playbook_for_action(request.user, playbook_id, "share")
        grant = get_object_or_404(PlaybookGrant, id=share_id, playbook=playbook)
        grant = revoke_grant(grant, actor=request.user)
        return JsonResponse({"success": True, "share": serialize_grant(grant)})
    except PermissionDenied as exc:
        return workspace_error(code="playbook_forbidden", message=str(exc), status=403, stage="authorization")
