"""Project lifecycle, selection, and authorization helpers."""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils.text import slugify

from core_ui.models.projects import Project, ProjectMembership

PROJECT_MANAGE_ROLES = {ProjectMembership.ROLE_OWNER, ProjectMembership.ROLE_ADMIN}
PROJECT_WRITE_ROLES = {*PROJECT_MANAGE_ROLES, ProjectMembership.ROLE_OPERATOR}


def _default_slug(user_id: int) -> str:
    return f"personal-{int(user_id)}"


@transaction.atomic
def ensure_default_project(user) -> Project:
    """Return the user's compatibility project, creating it when necessary."""
    if not user or not getattr(user, "is_authenticated", True) or not getattr(user, "pk", None):
        raise ValueError("A persisted user is required")
    get_user_model().objects.select_for_update().filter(pk=user.pk).exists()

    project = Project.objects.select_for_update().filter(owner=user, is_default=True).first()
    if project is None:
        project, _created = Project.objects.get_or_create(
            slug=_default_slug(user.pk),
            defaults={"name": f"{user.username}'s project", "owner": user, "is_default": True},
        )
        if project.owner_id != user.id:
            raise ValueError("Default project slug collision")
        if not project.is_default:
            project.is_default = True
            project.save(update_fields=["is_default", "updated_at"])

    membership, _created = ProjectMembership.objects.get_or_create(
        project=project,
        user=user,
        defaults={"role": ProjectMembership.ROLE_OWNER},
    )
    updates: list[str] = []
    if membership.role != ProjectMembership.ROLE_OWNER:
        membership.role = ProjectMembership.ROLE_OWNER
        updates.append("role")
    if not ProjectMembership.objects.filter(user=user, is_active=True).exists():
        membership.is_active = True
        updates.append("is_active")
    if updates:
        membership.save(update_fields=[*updates, "updated_at"])
    return project


def projects_for_user(user):
    if not user or not getattr(user, "is_authenticated", False):
        return Project.objects.none()
    return Project.objects.filter(memberships__user=user, is_archived=False).distinct().order_by("name", "id")


def active_project_for_user(user, *, request=None) -> Project | None:
    if not user or not getattr(user, "is_authenticated", False):
        return None
    cache_key = getattr(user, "pk", None)
    if request is not None:
        cache = getattr(request, "_webterm_active_project_cache", None)
        if cache is None:
            cache = {}
            request._webterm_active_project_cache = cache
        if cache_key in cache:
            return cache[cache_key]
    membership = (
        ProjectMembership.objects.select_related("project")
        .filter(user=user, is_active=True, project__is_archived=False)
        .first()
    )
    project = membership.project if membership else None
    if project is None:
        # Compatibility fallback for already-provisioned users. Read paths must
        # never acquire row locks or create tenant rows.
        project = Project.objects.filter(owner=user, is_default=True, is_archived=False).first()
    if request is not None:
        request._webterm_active_project_cache[cache_key] = project
    return project


def membership_for(user, project: Project | None = None) -> ProjectMembership | None:
    if not user or not getattr(user, "is_authenticated", False):
        return None
    project = project or active_project_for_user(user)
    if project is None:
        return None
    return ProjectMembership.objects.filter(project=project, user=user).first()


def user_can_manage_project(user, project: Project) -> bool:
    membership = membership_for(user, project)
    return bool(membership and membership.role in PROJECT_MANAGE_ROLES)


def user_can_write_project(user, project: Project) -> bool:
    membership = membership_for(user, project)
    return bool(membership and membership.role in PROJECT_WRITE_ROLES)


def project_has_resources(project: Project) -> bool:
    """Return whether a personal project contains tenant-bound user data."""
    related_managers = (
        "servers",
        "server_agents",
        "playbooks",
        "studio_mcp_servers",
        "studio_agent_configs",
        "studio_pipelines",
        "studio_skill_access",
    )
    for related_name in related_managers:
        manager = getattr(project, related_name, None)
        if manager is not None and manager.exists():
            return True
    return False


def activate_first_shared_project_if_personal_empty(user, project: Project) -> bool:
    """Preserve legacy share onboarding without moving users who already own data."""
    current = (
        ProjectMembership.objects.select_related("project")
        .filter(user=user, is_active=True, project__is_archived=False)
        .first()
    )
    if current is None:
        activate_project(user, project)
        return True
    if current.project_id == project.id:
        return False
    if not current.project.is_default or project_has_resources(current.project):
        return False
    other_team_count = (
        ProjectMembership.objects.filter(user=user, project__is_default=False, project__is_archived=False)
        .exclude(project=project)
        .count()
    )
    if other_team_count:
        return False
    activate_project(user, project)
    return True


@transaction.atomic
def activate_project(user, project: Project) -> ProjectMembership:
    get_user_model().objects.select_for_update().filter(pk=user.pk).exists()
    membership = (
        ProjectMembership.objects.select_for_update()
        .select_related("project")
        .filter(user=user, project=project, project__is_archived=False)
        .first()
    )
    if membership is None:
        raise PermissionError("Project membership required")
    ProjectMembership.objects.filter(user=user, is_active=True).exclude(pk=membership.pk).update(is_active=False)
    if not membership.is_active:
        membership.is_active = True
        membership.save(update_fields=["is_active", "updated_at"])
    return membership


@transaction.atomic
def create_project(*, owner, name: str, activate: bool = True) -> Project:
    cleaned_name = str(name or "").strip()
    if not cleaned_name:
        raise ValueError("Project name is required")
    get_user_model().objects.select_for_update().filter(pk=owner.pk).exists()
    base = slugify(cleaned_name)[:72] or "project"
    slug = f"{base}-{uuid.uuid4().hex[:8]}"
    project = Project.objects.create(name=cleaned_name[:120], slug=slug, owner=owner)
    membership = ProjectMembership.objects.create(
        project=project,
        user=owner,
        role=ProjectMembership.ROLE_OWNER,
    )
    if activate:
        ProjectMembership.objects.filter(user=owner, is_active=True).exclude(pk=membership.pk).update(is_active=False)
        membership.is_active = True
        membership.save(update_fields=["is_active", "updated_at"])
    return project


def assign_active_project(instance, *, user_field: str) -> None:
    """Populate a project on legacy-compatible model creation."""
    if getattr(instance, "project_id", None):
        return
    user_id = getattr(instance, f"{user_field}_id", None)
    if not user_id:
        return
    user = getattr(instance, user_field)
    project = active_project_for_user(user)
    if project is None:
        project = ensure_default_project(user)
    if project is not None:
        if not user_can_write_project(user, project):
            raise PermissionDenied("Project operator role required")
        instance.project_id = project.id
