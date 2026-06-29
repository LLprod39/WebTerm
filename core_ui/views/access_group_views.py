"""
Access management views for groups and feature permissions.
"""

import json
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from loguru import logger

from core_ui.access import access_feature_labels
from core_ui.decorators import require_feature
from core_ui.models import GroupAppPermission, UserAppPermission
from core_ui.views.access_views import _access_feature_slugs, _apply_group_explicit_permissions, require_access_admin


@login_required
@require_feature("settings")
@require_access_admin
@require_http_methods(["GET", "POST"])
def api_access_groups(request):
    """
    GET /api/access/groups/ - list groups.
    POST /api/access/groups/ - create a group.
    """
    if request.method == "GET":
        groups = Group.objects.all().prefetch_related("user_set").order_by("name")
        permissions_by_group: dict[int, dict[str, bool]] = defaultdict(dict)
        for row in GroupAppPermission.objects.all().values("group_id", "feature", "allowed"):
            permissions_by_group[row["group_id"]][row["feature"]] = bool(row["allowed"])
        data = [
            {
                "id": group.id,
                "name": group.name,
                "members": [{"id": user.id, "username": user.username} for user in group.user_set.all()],
                "member_count": group.user_set.count(),
                "explicit_permissions": permissions_by_group.get(group.id, {}),
            }
            for group in groups
        ]
        return JsonResponse({"groups": data, "features": access_feature_labels()})

    try:
        data = json.loads(request.body)
        name = data.get("name", "").strip()

        if not name:
            return JsonResponse({"error": "Group name is required"}, status=400)
        if Group.objects.filter(name=name).exists():
            return JsonResponse({"error": "Group already exists"}, status=400)

        group = Group.objects.create(name=name)

        member_ids = data.get("members", [])
        if member_ids:
            group.user_set.set(User.objects.filter(id__in=member_ids))

        _apply_group_explicit_permissions(group, data.get("explicit_permissions") or data.get("permissions"))

        return JsonResponse(
            {
                "success": True,
                "group": {
                    "id": group.id,
                    "name": group.name,
                    "member_count": group.user_set.count(),
                    "members": [{"id": user.id, "username": user.username} for user in group.user_set.all()],
                    "explicit_permissions": {
                        row.feature: bool(row.allowed)
                        for row in GroupAppPermission.objects.filter(group=group).only("feature", "allowed")
                    },
                },
            }
        )
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as exc:
        logger.exception("api_access_groups POST error: %s", exc)
        return JsonResponse({"error": str(exc)}, status=500)


@login_required
@require_feature("settings")
@require_access_admin
@require_http_methods(["GET", "PUT", "DELETE"])
def api_access_group_detail(request, group_id):
    """
    GET /api/access/groups/<id>/ - get a group.
    PUT /api/access/groups/<id>/ - update a group.
    DELETE /api/access/groups/<id>/ - delete a group.
    """
    try:
        group = Group.objects.prefetch_related("user_set").get(id=group_id)
    except Group.DoesNotExist:
        return JsonResponse({"error": "Group not found"}, status=404)

    if request.method == "GET":
        return JsonResponse(
            {
                "group": {
                    "id": group.id,
                    "name": group.name,
                    "members": [{"id": user.id, "username": user.username} for user in group.user_set.all()],
                    "explicit_permissions": {
                        row.feature: bool(row.allowed)
                        for row in GroupAppPermission.objects.filter(group=group).only("feature", "allowed")
                    },
                }
            }
        )

    if request.method == "PUT":
        try:
            data = json.loads(request.body)

            if "name" in data and data["name"].strip():
                new_name = data["name"].strip()
                if new_name != group.name:
                    if Group.objects.filter(name=new_name).exists():
                        return JsonResponse({"error": "Group name already exists"}, status=400)
                    group.name = new_name
                    group.save()

            if "members" in data:
                group.user_set.set(User.objects.filter(id__in=data["members"]))

            if "explicit_permissions" in data or "permissions" in data:
                _apply_group_explicit_permissions(group, data.get("explicit_permissions") or data.get("permissions"))

            return JsonResponse(
                {
                    "success": True,
                    "group": {
                        "id": group.id,
                        "name": group.name,
                        "member_count": group.user_set.count(),
                        "members": [{"id": user.id, "username": user.username} for user in group.user_set.all()],
                        "explicit_permissions": {
                            row.feature: bool(row.allowed)
                            for row in GroupAppPermission.objects.filter(group=group).only("feature", "allowed")
                        },
                    },
                }
            )
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as exc:
            logger.exception("api_access_group_detail PUT error: %s", exc)
            return JsonResponse({"error": str(exc)}, status=500)

    group.delete()
    return JsonResponse({"success": True, "message": "Group deleted"})


@login_required
@require_feature("settings")
@require_access_admin
@require_http_methods(["POST", "DELETE"])
def api_access_group_members(request, group_id):
    """
    POST /api/access/groups/<id>/members/ - add a user to a group.
    DELETE /api/access/groups/<id>/members/ - remove a user from a group.
    """
    try:
        group = Group.objects.get(id=group_id)
    except Group.DoesNotExist:
        return JsonResponse({"error": "Group not found"}, status=404)

    try:
        data = json.loads(request.body)
        user_id = data.get("user_id")

        if not user_id:
            return JsonResponse({"error": "user_id is required"}, status=400)

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)

        if request.method == "POST":
            group.user_set.add(user)
            return JsonResponse({"success": True, "message": f"{user.username} added to {group.name}"})

        group.user_set.remove(user)
        return JsonResponse({"success": True, "message": f"{user.username} removed from {group.name}"})

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as exc:
        logger.exception("api_access_group_members error: %s", exc)
        return JsonResponse({"error": str(exc)}, status=500)


@login_required
@require_feature("settings")
@require_access_admin
@require_http_methods(["GET", "POST"])
def api_access_permissions(request):
    """
    GET /api/access/permissions/ - list permissions.
    POST /api/access/permissions/ - create or update a permission.
    """
    if request.method == "GET":
        permissions = UserAppPermission.objects.select_related("user").all().order_by("user__username", "feature")
        data = [
            {
                "id": permission.id,
                "user_id": permission.user.id,
                "username": permission.user.username,
                "feature": permission.feature,
                "feature_display": permission.get_feature_display(),
                "allowed": permission.allowed,
            }
            for permission in permissions
        ]

        group_permissions = GroupAppPermission.objects.select_related("group").all().order_by("group__name", "feature")
        group_data = [
            {
                "id": permission.id,
                "group_id": permission.group.id,
                "group_name": permission.group.name,
                "feature": permission.feature,
                "feature_display": permission.get_feature_display(),
                "allowed": permission.allowed,
            }
            for permission in group_permissions
        ]

        return JsonResponse({"permissions": data, "group_permissions": group_data, "features": access_feature_labels()})

    try:
        data = json.loads(request.body)
        user_id = data.get("user_id")
        feature = data.get("feature", "").strip()
        allowed = data.get("allowed", True)

        if not user_id:
            return JsonResponse({"error": "user_id is required"}, status=400)
        if not feature:
            return JsonResponse({"error": "feature is required"}, status=400)

        valid_features = _access_feature_slugs()
        if feature not in valid_features:
            return JsonResponse({"error": f"Invalid feature. Valid: {valid_features}"}, status=400)

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)

        if user.is_superuser and user.id != request.user.id:
            return JsonResponse({"error": "Cannot edit superuser"}, status=403)

        permission, created = UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": bool(allowed)},
        )

        return JsonResponse(
            {
                "success": True,
                "created": created,
                "permission": {
                    "id": permission.id,
                    "user_id": permission.user.id,
                    "username": permission.user.username,
                    "feature": permission.feature,
                    "allowed": permission.allowed,
                },
            }
        )
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as exc:
        logger.exception("api_access_permissions POST error: %s", exc)
        return JsonResponse({"error": str(exc)}, status=500)


@login_required
@require_feature("settings")
@require_access_admin
@require_http_methods(["GET", "POST"])
def api_access_group_permissions(request):
    """Group-level feature permissions."""
    if request.method == "GET":
        permissions = GroupAppPermission.objects.select_related("group").all().order_by("group__name", "feature")
        data = [
            {
                "id": row.id,
                "group_id": row.group_id,
                "group_name": row.group.name,
                "feature": row.feature,
                "feature_display": row.get_feature_display(),
                "allowed": row.allowed,
            }
            for row in permissions
        ]
        return JsonResponse({"permissions": data, "features": access_feature_labels()})

    try:
        data = json.loads(request.body)
        group_id = data.get("group_id")
        feature = str(data.get("feature") or "").strip()
        allowed = data.get("allowed", True)

        if not group_id:
            return JsonResponse({"error": "group_id is required"}, status=400)
        if not feature:
            return JsonResponse({"error": "feature is required"}, status=400)
        if feature not in _access_feature_slugs():
            return JsonResponse({"error": "Invalid feature"}, status=400)

        try:
            group = Group.objects.get(id=group_id)
        except Group.DoesNotExist:
            return JsonResponse({"error": "Group not found"}, status=404)

        permission, created = GroupAppPermission.objects.update_or_create(
            group=group,
            feature=feature,
            defaults={"allowed": bool(allowed)},
        )
        return JsonResponse(
            {
                "success": True,
                "created": created,
                "permission": {
                    "id": permission.id,
                    "group_id": permission.group_id,
                    "group_name": permission.group.name,
                    "feature": permission.feature,
                    "feature_display": permission.get_feature_display(),
                    "allowed": permission.allowed,
                },
            }
        )
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as exc:
        logger.exception("api_access_group_permissions error: %s", exc)
        return JsonResponse({"error": str(exc)}, status=500)


@login_required
@require_feature("settings")
@require_access_admin
@require_http_methods(["PUT", "DELETE"])
def api_access_permission_detail(request, perm_id):
    """
    PUT /api/access/permissions/<id>/ - update a permission.
    DELETE /api/access/permissions/<id>/ - delete a permission.
    """
    try:
        permission = UserAppPermission.objects.select_related("user").get(id=perm_id)
    except UserAppPermission.DoesNotExist:
        return JsonResponse({"error": "Permission not found"}, status=404)

    if permission.user.is_superuser and permission.user.id != request.user.id:
        return JsonResponse({"error": "Cannot edit superuser"}, status=403)

    if request.method == "PUT":
        try:
            data = json.loads(request.body)
            if "allowed" in data:
                permission.allowed = bool(data["allowed"])
                permission.save()

            return JsonResponse(
                {
                    "success": True,
                    "permission": {
                        "id": permission.id,
                        "user_id": permission.user.id,
                        "username": permission.user.username,
                        "feature": permission.feature,
                        "allowed": permission.allowed,
                    },
                }
            )
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as exc:
            logger.exception("api_access_permission_detail PUT error: %s", exc)
            return JsonResponse({"error": str(exc)}, status=500)

    permission.delete()
    return JsonResponse({"success": True, "message": "Permission deleted"})


@login_required
@require_feature("settings")
@require_access_admin
@require_http_methods(["PUT", "DELETE"])
def api_access_group_permission_detail(request, perm_id):
    """Update or delete a group-level permission."""
    try:
        permission = GroupAppPermission.objects.select_related("group").get(id=perm_id)
    except GroupAppPermission.DoesNotExist:
        return JsonResponse({"error": "Permission not found"}, status=404)

    if request.method == "PUT":
        try:
            data = json.loads(request.body)
            if "allowed" in data:
                permission.allowed = bool(data["allowed"])
                permission.save(update_fields=["allowed"])

            return JsonResponse(
                {
                    "success": True,
                    "permission": {
                        "id": permission.id,
                        "group_id": permission.group_id,
                        "group_name": permission.group.name,
                        "feature": permission.feature,
                        "feature_display": permission.get_feature_display(),
                        "allowed": permission.allowed,
                    },
                }
            )
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as exc:
            logger.exception("api_access_group_permission_detail PUT error: %s", exc)
            return JsonResponse({"error": str(exc)}, status=500)

    permission.delete()
    return JsonResponse({"success": True, "message": "Permission deleted"})
