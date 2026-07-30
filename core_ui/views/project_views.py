"""Project and team membership API."""

from __future__ import annotations

import json

from django.contrib.auth.models import User
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core_ui.models.projects import Project, ProjectMembership
from core_ui.projects import (
    activate_project,
    active_project_for_user,
    create_project,
    projects_for_user,
    user_can_manage_project,
)


def _body(request) -> dict:
    try:
        payload = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _project_payload(project: Project, user) -> dict:
    membership = project.memberships.filter(user=user).first()
    return {
        "id": str(project.public_id),
        "name": project.name,
        "slug": project.slug,
        "role": membership.role if membership else "",
        "is_active": bool(membership and membership.is_active),
        "is_default": project.is_default,
        "member_count": project.memberships.count(),
        "can_manage": bool(membership and membership.role in {"owner", "admin"}),
        "created_at": project.created_at.isoformat(),
    }


def _member_payload(membership: ProjectMembership) -> dict:
    return {
        "user_id": membership.user_id,
        "username": membership.user.username,
        "email": membership.user.email or "",
        "role": membership.role,
        "is_active": membership.is_active,
        "joined_at": membership.created_at.isoformat(),
    }


def _member_project(user, public_id) -> Project | None:
    return projects_for_user(user).filter(public_id=public_id).first()


@require_http_methods(["GET", "POST"])
def api_projects(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    if request.method == "POST":
        data = _body(request)
        try:
            project = create_project(
                owner=request.user,
                name=str(data.get("name") or ""),
                activate=bool(data.get("activate", True)),
            )
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        return JsonResponse({"project": _project_payload(project, request.user)}, status=201)

    active = active_project_for_user(request.user)
    projects = [_project_payload(project, request.user) for project in projects_for_user(request.user)]
    return JsonResponse({"projects": projects, "active_project_id": str(active.public_id) if active else None})


@require_http_methods(["POST"])
def api_project_activate(request, project_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    project = _member_project(request.user, project_id)
    if project is None:
        return JsonResponse({"error": "Project not found"}, status=404)
    activate_project(request.user, project)
    return JsonResponse({"success": True, "project": _project_payload(project, request.user)})


@require_http_methods(["GET", "POST"])
def api_project_members(request, project_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    project = _member_project(request.user, project_id)
    if project is None:
        return JsonResponse({"error": "Project not found"}, status=404)

    if request.method == "POST":
        if not user_can_manage_project(request.user, project):
            return JsonResponse({"error": "Project admin role required"}, status=403)
        data = _body(request)
        identity = str(data.get("username") or data.get("email") or "").strip()
        role = str(data.get("role") or ProjectMembership.ROLE_VIEWER).strip().lower()
        allowed_roles = {ProjectMembership.ROLE_ADMIN, ProjectMembership.ROLE_OPERATOR, ProjectMembership.ROLE_VIEWER}
        if not identity or role not in allowed_roles:
            return JsonResponse({"error": "A valid username/email and role are required"}, status=400)
        target = User.objects.filter(Q(username__iexact=identity) | Q(email__iexact=identity), is_active=True).first()
        if target is None:
            return JsonResponse({"error": "User not found"}, status=404)
        membership, created = ProjectMembership.objects.get_or_create(
            project=project,
            user=target,
            defaults={"role": role},
        )
        if not created and membership.role != ProjectMembership.ROLE_OWNER:
            membership.role = role
            membership.save(update_fields=["role", "updated_at"])
        return JsonResponse({"member": _member_payload(membership)}, status=201 if created else 200)

    memberships = project.memberships.select_related("user").order_by("user__username", "user_id")
    return JsonResponse({"members": [_member_payload(item) for item in memberships]})


@require_http_methods(["PATCH", "DELETE"])
def api_project_member_detail(request, project_id, user_id: int):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    project = _member_project(request.user, project_id)
    if project is None:
        return JsonResponse({"error": "Project not found"}, status=404)
    if not user_can_manage_project(request.user, project):
        return JsonResponse({"error": "Project admin role required"}, status=403)
    membership = project.memberships.select_related("user").filter(user_id=user_id).first()
    if membership is None:
        return JsonResponse({"error": "Project member not found"}, status=404)
    if membership.role == ProjectMembership.ROLE_OWNER or membership.user_id == project.owner_id:
        return JsonResponse({"error": "Project owner cannot be changed or removed"}, status=409)

    if request.method == "DELETE":
        membership.delete()
        return JsonResponse({"success": True})

    role = str(_body(request).get("role") or "").strip().lower()
    allowed_roles = {ProjectMembership.ROLE_ADMIN, ProjectMembership.ROLE_OPERATOR, ProjectMembership.ROLE_VIEWER}
    if role not in allowed_roles:
        return JsonResponse({"error": "Invalid project role"}, status=400)
    membership.role = role
    membership.save(update_fields=["role", "updated_at"])
    return JsonResponse({"member": _member_payload(membership)})
