"""
Access management views for users, groups, and feature permissions.
"""

import json
from collections import defaultdict
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from loguru import logger

from core_ui.access import (
    PROFILE_STAFF_FLAGS,
    VALID_ACCESS_PROFILES,
    access_feature_labels,
    access_feature_slugs,
    access_profile_permissions,
    build_user_access_payload,
    feature_allowed_for_user,
    load_group_permission_sources,
    load_user_explicit_permissions,
)
from core_ui.api_errors import internal_error_response
from core_ui.context_processors import user_can_feature
from core_ui.decorators import require_feature
from core_ui.models import GroupAppPermission, UserAppPermission


def require_access_admin(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            return JsonResponse({"error": "Only admins can manage access"}, status=403)
        return view_func(request, *args, **kwargs)

    return _wrapped


def _access_feature_slugs():
    return access_feature_slugs()


def _feature_allowed_for_user(
    user, feature: str, explicit_permissions: dict, group_permissions: dict | None = None
) -> bool:
    return feature_allowed_for_user(user, feature, explicit_permissions, group_permissions)


def _build_user_access_payload(user, explicit_permissions: dict, group_permission_sources: dict | None = None) -> dict:
    return build_user_access_payload(user, explicit_permissions, group_permission_sources)


def _apply_access_profile(user, profile: str) -> None:
    """Apply one of predefined access profiles to user permissions."""
    profile = (profile or "").strip()
    if profile not in VALID_ACCESS_PROFILES:
        raise ValueError("Invalid access profile")

    if profile == "custom":
        return

    if profile == "reset_defaults":
        UserAppPermission.objects.filter(user=user).delete()
        return

    if profile == "server_only" and user.is_superuser:
        raise ValueError("Cannot apply server-only profile to superuser")

    target = access_profile_permissions(profile)
    staff_target = PROFILE_STAFF_FLAGS.get(profile, False)
    if user.is_staff != staff_target:
        user.is_staff = staff_target
        user.save(update_fields=["is_staff"])

    with transaction.atomic():
        UserAppPermission.objects.bulk_create(
            [UserAppPermission(user=user, feature=feature, allowed=allowed) for feature, allowed in target.items()],
            update_conflicts=True,
            unique_fields=["user", "feature"],
            update_fields=["allowed"],
        )


def _apply_explicit_permissions(model, owner_field: str, owner, permissions: dict | None) -> None:
    """Bulk-apply explicit per-feature permissions: empty value deletes, else upserts."""
    if permissions is None:
        return

    valid_features = set(_access_feature_slugs())
    items = {f: v for f, v in dict(permissions).items() if f in valid_features}
    to_delete = [f for f, v in items.items() if v is None or v == ""]
    to_upsert = {f: bool(v) for f, v in items.items() if not (v is None or v == "")}
    with transaction.atomic():
        if to_delete:
            model.objects.filter(**{owner_field: owner, "feature__in": to_delete}).delete()
        if to_upsert:
            model.objects.bulk_create(
                [model(**{owner_field: owner, "feature": f, "allowed": allowed}) for f, allowed in to_upsert.items()],
                update_conflicts=True,
                unique_fields=[owner_field, "feature"],
                update_fields=["allowed"],
            )


def _apply_user_explicit_permissions(user, permissions: dict | None) -> None:
    _apply_explicit_permissions(UserAppPermission, "user", user, permissions)


def _apply_group_explicit_permissions(group, permissions: dict | None) -> None:
    _apply_explicit_permissions(GroupAppPermission, "group", group, permissions)


def _get_access_data():
    """Return context data for legacy access management templates."""
    users = list(User.objects.all().prefetch_related("groups").order_by("username"))
    groups = Group.objects.all().prefetch_related("user_set").order_by("name")
    permissions = UserAppPermission.objects.select_related("user").all().order_by("user__username", "feature")

    explicit_by_user: dict[int, dict[str, bool]] = defaultdict(dict)
    for permission in permissions:
        explicit_by_user[permission.user_id][permission.feature] = bool(permission.allowed)

    users_with_access = []
    for user in users:
        access = _build_user_access_payload(user, explicit_by_user.get(user.id, {}))
        users_with_access.append(
            {
                "user": user,
                "access_profile": access["access_profile"],
                "effective_permissions": access["effective_permissions"],
                "explicit_permissions": access["explicit_permissions"],
            }
        )

    return {
        "users": users,
        "users_with_access": users_with_access,
        "groups": groups,
        "permissions": permissions,
        "feature_slugs": _access_feature_slugs(),
    }


@login_required
def settings_access_view(request):
    """Legacy access management page."""
    if not user_can_feature(request.user, "settings"):
        return redirect("index")
    tab = request.GET.get("tab", "users")
    if tab not in ("users", "groups", "permissions"):
        tab = "users"
    context = _get_access_data()
    context["active_tab"] = tab
    return render(request, "settings_access.html", context)


@login_required
def settings_users_view(request):
    """Redirect to the users tab on the legacy access management page."""
    if not user_can_feature(request.user, "settings"):
        return redirect("index")
    return redirect(reverse("settings_access") + "?tab=users")


@login_required
def settings_groups_view(request):
    """Redirect to the groups tab on the legacy access management page."""
    if not user_can_feature(request.user, "settings"):
        return redirect("index")
    return redirect(reverse("settings_access") + "?tab=groups")


@login_required
def settings_permissions_view(request):
    """Redirect to the permissions tab on the legacy access management page."""
    if not user_can_feature(request.user, "settings"):
        return redirect("index")
    return redirect(reverse("settings_access") + "?tab=permissions")


@login_required
@require_feature("settings")
@require_access_admin
@require_http_methods(["GET", "POST"])
def api_access_users(request):
    """
    GET /api/access/users/ - list users.
    POST /api/access/users/ - create a user.
    """
    if request.method == "GET":
        users = User.objects.all().prefetch_related("groups").order_by("username")
        features = access_feature_labels()

        data = []
        for user in users:
            explicit = load_user_explicit_permissions(user)
            group_sources = load_group_permission_sources(user)
            access = _build_user_access_payload(user, explicit, group_sources)
            data.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email or "",
                    "is_staff": user.is_staff,
                    "is_active": user.is_active,
                    "is_superuser": user.is_superuser,
                    "date_joined": user.date_joined.isoformat(),
                    "groups": [{"id": group.id, "name": group.name} for group in user.groups.all()],
                    "access_profile": access["access_profile"],
                    "effective_permissions": access["effective_permissions"],
                    "explicit_permissions": access["explicit_permissions"],
                    "group_permissions": access["group_permissions"],
                    "group_permission_sources": access["group_permission_sources"],
                    "permission_sources": access["permission_sources"],
                }
            )
        return JsonResponse({"users": data, "features": features})

    try:
        data = json.loads(request.body)
        username = data.get("username", "").strip()
        email = data.get("email", "").strip()
        password = data.get("password", "")
        is_staff = data.get("is_staff", False)
        is_active = data.get("is_active", True)
        access_profile = (data.get("access_profile") or "").strip()

        if not username:
            return JsonResponse({"error": "Username is required"}, status=400)
        if not password:
            return JsonResponse({"error": "Password is required"}, status=400)
        if User.objects.filter(username=username).exists():
            return JsonResponse({"error": "Username already exists"}, status=400)

        user = User.objects.create_user(username=username, email=email, password=password)
        user.is_staff = is_staff
        user.is_active = is_active
        user.save()

        group_ids = data.get("groups", [])
        if group_ids:
            user.groups.set(Group.objects.filter(id__in=group_ids))

        if access_profile:
            _apply_access_profile(user, access_profile)
        else:
            _apply_access_profile(user, "pilot_user")

        _apply_user_explicit_permissions(user, data.get("explicit_permissions"))

        explicit = load_user_explicit_permissions(user)
        group_sources = load_group_permission_sources(user)
        access = _build_user_access_payload(user, explicit, group_sources)

        return JsonResponse(
            {
                "success": True,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "is_staff": user.is_staff,
                    "is_active": user.is_active,
                    "access_profile": access["access_profile"],
                    "groups": [{"id": group.id, "name": group.name} for group in user.groups.all()],
                    "effective_permissions": access["effective_permissions"],
                    "explicit_permissions": access["explicit_permissions"],
                    "group_permissions": access["group_permissions"],
                    "group_permission_sources": access["group_permission_sources"],
                    "permission_sources": access["permission_sources"],
                },
            }
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as exc:
        logger.exception("api_access_users POST error: %s", exc)
        return internal_error_response(request, exc)


@login_required
@require_feature("settings")
@require_access_admin
@require_http_methods(["GET", "PUT", "DELETE"])
def api_access_user_detail(request, user_id):
    """
    GET /api/access/users/<id>/ - get a user.
    PUT /api/access/users/<id>/ - update a user.
    DELETE /api/access/users/<id>/ - delete a user.
    """
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)

    if request.method == "GET":
        explicit = load_user_explicit_permissions(user)
        group_sources = load_group_permission_sources(user)
        access = _build_user_access_payload(user, explicit, group_sources)
        return JsonResponse(
            {
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email or "",
                    "is_staff": user.is_staff,
                    "is_active": user.is_active,
                    "is_superuser": user.is_superuser,
                    "date_joined": user.date_joined.isoformat(),
                    "groups": [{"id": group.id, "name": group.name} for group in user.groups.all()],
                    "access_profile": access["access_profile"],
                    "effective_permissions": access["effective_permissions"],
                    "explicit_permissions": access["explicit_permissions"],
                    "group_permissions": access["group_permissions"],
                    "group_permission_sources": access["group_permission_sources"],
                    "permission_sources": access["permission_sources"],
                }
            }
        )

    if request.method == "PUT":
        try:
            data = json.loads(request.body)

            if user.is_superuser and user.id != request.user.id:
                return JsonResponse({"error": "Cannot edit superuser"}, status=403)

            if "email" in data:
                user.email = data["email"].strip()
            if "is_staff" in data:
                user.is_staff = bool(data["is_staff"])
            if "is_active" in data:
                user.is_active = bool(data["is_active"])
            if "username" in data and data["username"].strip():
                new_username = data["username"].strip()
                if new_username != user.username:
                    if User.objects.filter(username=new_username).exists():
                        return JsonResponse({"error": "Username already exists"}, status=400)
                    user.username = new_username

            user.save()

            if "groups" in data:
                user.groups.set(Group.objects.filter(id__in=data["groups"]))

            if "access_profile" in data:
                _apply_access_profile(user, data.get("access_profile"))

            if "explicit_permissions" in data:
                _apply_user_explicit_permissions(user, data.get("explicit_permissions"))

            explicit = load_user_explicit_permissions(user)
            group_sources = load_group_permission_sources(user)
            access = _build_user_access_payload(user, explicit, group_sources)

            return JsonResponse(
                {
                    "success": True,
                    "user": {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                        "is_staff": user.is_staff,
                        "is_active": user.is_active,
                        "access_profile": access["access_profile"],
                        "groups": [{"id": group.id, "name": group.name} for group in user.groups.all()],
                        "effective_permissions": access["effective_permissions"],
                        "explicit_permissions": access["explicit_permissions"],
                        "group_permissions": access["group_permissions"],
                        "group_permission_sources": access["group_permission_sources"],
                        "permission_sources": access["permission_sources"],
                    },
                }
            )
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as exc:
            logger.exception("api_access_user_detail PUT error: %s", exc)
            return internal_error_response(request, exc)

    if user.id == request.user.id:
        return JsonResponse({"error": "Cannot delete yourself"}, status=400)
    if user.is_superuser:
        return JsonResponse({"error": "Cannot delete superuser"}, status=403)

    user.delete()
    return JsonResponse({"success": True, "message": "User deleted"})


@login_required
@require_feature("settings")
@require_access_admin
@require_http_methods(["POST"])
def api_access_user_password(request, user_id):
    """Change a user's password."""
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)

    if user.is_superuser and user.id != request.user.id:
        return JsonResponse({"error": "Cannot change superuser password"}, status=403)

    try:
        data = json.loads(request.body)
        new_password = data.get("password", "")

        if not new_password or len(new_password) < 4:
            return JsonResponse({"error": "Password must be at least 4 characters"}, status=400)

        user.set_password(new_password)
        user.save()

        return JsonResponse({"success": True, "message": "Password changed"})
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as exc:
        logger.exception("api_access_user_password error: %s", exc)
        return internal_error_response(request, exc)


@login_required
@require_feature("settings")
@require_access_admin
@require_http_methods(["POST"])
def api_access_user_profile(request, user_id):
    """Apply an access profile to a user."""
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)

    if user.is_superuser and user.id != request.user.id:
        return JsonResponse({"error": "Cannot edit superuser"}, status=403)

    try:
        data = json.loads(request.body)
        profile = (data.get("profile") or "").strip()
        if not profile:
            return JsonResponse({"error": "profile is required"}, status=400)

        _apply_access_profile(user, profile)

        explicit = load_user_explicit_permissions(user)
        group_sources = load_group_permission_sources(user)
        access = _build_user_access_payload(user, explicit, group_sources)

        return JsonResponse(
            {
                "success": True,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "is_staff": user.is_staff,
                    "is_active": user.is_active,
                },
                "access_profile": access["access_profile"],
                "effective_permissions": access["effective_permissions"],
                "explicit_permissions": access["explicit_permissions"],
                "group_permissions": access["group_permissions"],
                "group_permission_sources": access["group_permission_sources"],
                "permission_sources": access["permission_sources"],
            }
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as exc:
        logger.exception("api_access_user_profile error: %s", exc)
        return internal_error_response(request, exc)
