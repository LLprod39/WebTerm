"""Owner-managed user, group and workspace playbook grants."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db.models import Count, F, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from core_ui.models.projects import ProjectMembership
from servers.models import PlaybookGrant
from servers.services.playbooks.bundle_archive import BundleValidationError
from servers.services.playbooks.sharing import (
    PlaybookGrantError,
    revoke_grant,
    save_grant,
    serialize_grant,
)
from servers.views.playbook_workspace_helpers import get_playbook_for_action, json_body, workspace_error


@login_required
@require_feature("automation")
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
        if principal_type == "user":
            user = get_object_or_404(
                get_user_model(),
                id=int(data.get("principal_id") or 0),
                is_active=True,
                project_memberships__project_id=playbook.project_id,
            )
        elif principal_type == "group":
            group = get_object_or_404(_eligible_group_query(playbook), id=int(data.get("principal_id") or 0))
        else:
            raise PlaybookGrantError("principal_type must be user or group")
        expires_at = parse_datetime(str(data.get("expires_at") or "")) if data.get("expires_at") else None
        grant = save_grant(
            playbook=playbook,
            actor=request.user,
            role=str(data.get("role") or PlaybookGrant.ROLE_VIEWER),
            user=user,
            group=group,
            workspace_shared=False,
            expires_at=expires_at,
            capability_overrides=(data.get("capabilities") if isinstance(data.get("capabilities"), dict) else None),
        )
        return JsonResponse({"success": True, "share": serialize_grant(grant)}, status=201)
    except PermissionDenied as exc:
        return workspace_error(code="playbook_forbidden", message=str(exc), status=403, stage="authorization")
    except BundleValidationError as exc:
        return workspace_error(
            code=exc.code,
            message=str(exc),
            status=exc.status_code,
            stage="share_save",
            details=exc.details,
        )
    except (PlaybookGrantError, TypeError, ValueError) as exc:
        return workspace_error(code="playbook_share_invalid", message=str(exc), stage="share_save")


@login_required
@require_feature("automation")
@require_http_methods(["DELETE"])
def playbook_share_detail(request, playbook_id: int, share_id: int):
    try:
        playbook = get_playbook_for_action(request.user, playbook_id, "share")
        grant = get_object_or_404(PlaybookGrant, id=share_id, playbook=playbook)
        grant = revoke_grant(grant, actor=request.user)
        return JsonResponse({"success": True, "share": serialize_grant(grant)})
    except PermissionDenied as exc:
        return workspace_error(code="playbook_forbidden", message=str(exc), status=403, stage="authorization")


@login_required
@require_feature("automation")
@require_http_methods(["GET"])
def playbook_share_candidates(request, playbook_id: int):
    """Return a bounded directory listing only to principals allowed to share."""

    try:
        playbook = get_playbook_for_action(request.user, playbook_id, "share")
        query = str(request.GET.get("q") or "").strip()[:100]
        try:
            limit = max(1, min(int(request.GET.get("limit") or 20), 50))
        except (TypeError, ValueError) as exc:
            raise PlaybookGrantError("limit must be an integer from 1 to 50") from exc

        member_ids = ProjectMembership.objects.filter(project_id=playbook.project_id).values("user_id")
        user_query = (
            get_user_model().objects.filter(is_active=True, id__in=member_ids).exclude(pk=playbook.user_id).distinct()
        )
        group_query = _eligible_group_query(playbook)
        if query:
            user_query = user_query.filter(
                Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query)
            )
            group_query = group_query.filter(name__icontains=query)
        shared_user_ids = set(
            playbook.grants.filter(user_id__isnull=False, revoked_at__isnull=True).values_list("user_id", flat=True)
        )
        shared_group_ids = set(
            playbook.grants.filter(group_id__isnull=False, revoked_at__isnull=True).values_list("group_id", flat=True)
        )
        users = [
            {
                "id": item.id,
                "username": item.get_username(),
                "label": item.get_full_name().strip() or item.get_username(),
                "email": item.email or "",
                "already_shared": item.id in shared_user_ids,
            }
            for item in user_query.order_by("username", "id")[:limit]
        ]
        groups = [
            {
                "id": item.id,
                "name": item.name,
                "label": item.name,
                "already_shared": item.id in shared_group_ids,
            }
            for item in group_query.order_by("name", "id")[:limit]
        ]
        return JsonResponse({"success": True, "candidates": {"users": users, "groups": groups}})
    except PermissionDenied as exc:
        return workspace_error(code="playbook_forbidden", message=str(exc), status=403, stage="authorization")
    except PlaybookGrantError as exc:
        return workspace_error(code="playbook_share_invalid", message=str(exc), stage="share_candidates")


def _eligible_group_query(playbook):
    """Groups are shareable only when every active user is already in the project."""

    return (
        Group.objects.annotate(
            active_user_count=Count("user", filter=Q(user__is_active=True), distinct=True),
            project_member_count=Count(
                "user",
                filter=Q(
                    user__is_active=True,
                    user__project_memberships__project_id=playbook.project_id,
                ),
                distinct=True,
            ),
        )
        .filter(active_user_count__gt=0, active_user_count=F("project_member_count"))
        .distinct()
    )
