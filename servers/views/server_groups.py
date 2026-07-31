"""
Server group membership and bulk update endpoints.
"""

import json

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from core_ui.activity import log_user_activity
from core_ui.decorators import require_feature
from core_ui.models import UserActivityLog
from core_ui.projects import active_project_for_user, user_can_write_project
from servers.models import (
    Server,
    ServerBulkOperation,
    ServerGroup,
    ServerGroupMember,
    ServerGroupSubscription,
    ServerGroupTag,
)
from servers.services.server_bulk_operations import (
    ServerBulkOperationError,
    create_bulk_operation,
    serialize_bulk_operation,
)
from servers.views.server_helpers import _get_group_role


@login_required
@require_feature("servers")
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
        category="servers",
        action="group_create",
        status=UserActivityLog.STATUS_SUCCESS,
        description=f'Created server group "{group.name}"',
        entity_type="server_group",
        entity_id=group.id,
        entity_name=group.name,
    )

    return JsonResponse({"success": True, "group_id": group.id})


@login_required
@require_feature("servers")
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
        category="servers",
        action="group_update",
        status=UserActivityLog.STATUS_SUCCESS,
        description=f'Updated server group "{group.name}"',
        entity_type="server_group",
        entity_id=group.id,
        entity_name=group.name,
    )

    return JsonResponse({"success": True})


@login_required
@require_feature("servers")
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
        category="servers",
        action="group_delete",
        status=UserActivityLog.STATUS_SUCCESS,
        description=f'Deleted server group "{group_name}"',
        entity_type="server_group",
        entity_id=group_id,
        entity_name=group_name,
    )
    return JsonResponse({"success": True})


@login_required
@require_feature("servers")
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
@require_feature("servers")
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
@require_feature("servers")
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
@require_feature("servers")
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
            category="servers",
            action="servers_bulk_update",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f"Bulk updated {updated_count} servers",
            entity_type="server",
            entity_name="bulk",
            metadata={
                "server_ids": server_ids[:200],
                "updated_fields": sorted(updates.keys()),
                "updated_count": updated_count,
            },
        )
    return JsonResponse({"success": True})


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def group_bulk_action_create(request, group_id):
    group = get_object_or_404(ServerGroup, id=group_id)
    if _get_group_role(group, request.user) not in ["owner", "admin"]:
        return JsonResponse({"error": "Permission denied"}, status=403)
    project = active_project_for_user(request.user, request=request)
    if project is None or not user_can_write_project(request.user, project):
        return JsonResponse({"error": "Project operator role required"}, status=403)
    try:
        data = json.loads(request.body or b"{}")
        operation = create_bulk_operation(
            group=group,
            project=project,
            requested_by=request.user,
            action=str(data.get("action") or "").strip(),
            parameters=data.get("parameters"),
        )
    except (json.JSONDecodeError, ServerBulkOperationError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    log_user_activity(
        user=request.user,
        request=request,
        category="servers",
        action="server_group_bulk_action_queued",
        status=UserActivityLog.STATUS_SUCCESS,
        description=f'Queued {operation.action} for server group "{group.name}"',
        entity_type="server_bulk_operation",
        entity_id=operation.pk,
        entity_name=group.name,
        metadata={
            "group_id": group.pk,
            "action": operation.action,
            "target_count": operation.total_count,
        },
    )
    return JsonResponse({"success": True, "operation": serialize_bulk_operation(operation)}, status=202)


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def group_bulk_action_detail(request, operation_id):
    operation = get_object_or_404(ServerBulkOperation.objects.select_related("group"), pk=operation_id)
    if _get_group_role(operation.group, request.user) not in ["owner", "admin"]:
        return JsonResponse({"error": "Permission denied"}, status=403)
    project = active_project_for_user(request.user, request=request)
    if project is None or operation.project_id != project.id:
        return JsonResponse({"error": "Permission denied"}, status=403)
    return JsonResponse({"success": True, "operation": serialize_bulk_operation(operation)})
