"""Project tenant boundary and team membership models."""

from __future__ import annotations

import uuid

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q


class Project(models.Model):
    """A tenant boundary for operational resources owned by a team."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=100, unique=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="owned_projects")
    is_default = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner"],
                condition=Q(is_default=True),
                name="core_one_default_project_per_owner",
            ),
        ]
        indexes = [models.Index(fields=["owner", "is_archived"], name="core_ui_pr_owner_i_553ce9_idx")]

    def __str__(self) -> str:
        return self.name


class ProjectMembership(models.Model):
    """A user's role and selected project inside the tenant boundary."""

    ROLE_OWNER = "owner"
    ROLE_ADMIN = "admin"
    ROLE_OPERATOR = "operator"
    ROLE_VIEWER = "viewer"
    ROLE_CHOICES = [
        (ROLE_OWNER, "Owner"),
        (ROLE_ADMIN, "Admin"),
        (ROLE_OPERATOR, "Operator"),
        (ROLE_VIEWER, "Viewer"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="project_memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_VIEWER)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["project", "user"]
        constraints = [
            models.UniqueConstraint(fields=["project", "user"], name="core_unique_project_member"),
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(is_active=True),
                name="core_one_active_project_per_user",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"], name="core_ui_pr_user_id_81b66d_idx"),
            models.Index(fields=["project", "role"], name="core_ui_pr_project_66f2e2_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.project.slug}:{self.user.username}:{self.role}"
