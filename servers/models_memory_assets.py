"""ACL-aware logical memory assets and retrieval audit models."""

from __future__ import annotations

import uuid

from django.contrib.auth.models import Group, User
from django.db import models

from servers.models_inventory import Server
from servers.models_memory import ServerMemoryGenerationLog, ServerMemorySnapshot


class ServerMemoryAsset(models.Model):
    """Stable logical wrapper over versioned ServerMemorySnapshot content."""

    KIND_NOTE = "note"
    KIND_RUNBOOK = "runbook"
    KIND_DECISION = "decision"
    KIND_PATTERN = "pattern"
    KIND_CHOICES = [
        (KIND_NOTE, "Note"),
        (KIND_RUNBOOK, "Runbook"),
        (KIND_DECISION, "Decision"),
        (KIND_PATTERN, "Pattern"),
    ]

    VISIBILITY_INHERIT_SERVER = "inherit_server"
    VISIBILITY_PRIVATE = "private"
    VISIBILITY_PROJECT = "project"
    VISIBILITY_RESTRICTED = "restricted"
    VISIBILITY_AGENT = "agent"
    VISIBILITY_CHOICES = [
        (VISIBILITY_INHERIT_SERVER, "Inherit Server Context Access"),
        (VISIBILITY_PRIVATE, "Private"),
        (VISIBILITY_PROJECT, "Project"),
        (VISIBILITY_RESTRICTED, "Restricted by Explicit Grants"),
        (VISIBILITY_AGENT, "Bound Agent Only"),
    ]

    LIFECYCLE_CANDIDATE = "candidate"
    LIFECYCLE_APPROVED = "approved"
    LIFECYCLE_DEPRECATED = "deprecated"
    LIFECYCLE_ARCHIVED = "archived"
    LIFECYCLE_CHOICES = [
        (LIFECYCLE_CANDIDATE, "Candidate"),
        (LIFECYCLE_APPROVED, "Approved"),
        (LIFECYCLE_DEPRECATED, "Deprecated"),
        (LIFECYCLE_ARCHIVED, "Archived"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    project = models.ForeignKey(
        "core_ui.Project",
        on_delete=models.CASCADE,
        related_name="server_memory_assets",
    )
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="memory_assets")
    current_snapshot = models.ForeignKey(
        ServerMemorySnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_for_assets",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_server_memory_assets",
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_server_memory_assets",
    )
    generation_log = models.ForeignKey(
        ServerMemoryGenerationLog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assets",
    )
    stable_key = models.CharField(max_length=120)
    asset_kind = models.CharField(max_length=24, choices=KIND_CHOICES, default=KIND_NOTE)
    visibility = models.CharField(
        max_length=24,
        choices=VISIBILITY_CHOICES,
        default=VISIBILITY_INHERIT_SERVER,
    )
    lifecycle = models.CharField(max_length=20, choices=LIFECYCLE_CHOICES, default=LIFECYCLE_CANDIDATE)
    title = models.CharField(max_length=200)
    source_ref = models.CharField(max_length=255, blank=True, default="")
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        indexes = [
            models.Index(fields=["project", "server", "lifecycle", "-updated_at"]),
            models.Index(fields=["visibility", "lifecycle", "-updated_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["server", "stable_key"],
                name="servers_mem_asset_unique_stable_key",
            )
        ]

    def __str__(self):
        return f"{self.server.name}: {self.title}"


class ServerMemoryAssetGrant(models.Model):
    """Explicit user or Django-group permission for a restricted asset."""

    PERMISSION_READ = "read"
    PERMISSION_USE = "use"
    PERMISSION_MANAGE = "manage"
    PERMISSION_SHARE = "share"
    PERMISSION_CHOICES = [
        (PERMISSION_READ, "Read"),
        (PERMISSION_USE, "Use"),
        (PERMISSION_MANAGE, "Manage"),
        (PERMISSION_SHARE, "Share"),
    ]

    asset = models.ForeignKey(ServerMemoryAsset, on_delete=models.CASCADE, related_name="grants")
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="server_memory_asset_grants",
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="server_memory_asset_grants",
    )
    granted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="issued_server_memory_asset_grants",
    )
    permission = models.CharField(max_length=16, choices=PERMISSION_CHOICES, default=PERMISSION_READ)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["asset_id", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(user__isnull=False, group__isnull=True) | models.Q(user__isnull=True, group__isnull=False)
                ),
                name="servers_mem_asset_grant_one_subject",
            ),
            models.UniqueConstraint(
                fields=["asset", "user", "permission"],
                condition=models.Q(user__isnull=False),
                name="servers_mem_asset_unique_user_grant",
            ),
            models.UniqueConstraint(
                fields=["asset", "group", "permission"],
                condition=models.Q(group__isnull=False),
                name="servers_mem_asset_unique_group_grant",
            ),
        ]


class ServerMemoryAssetAgentBinding(models.Model):
    """Agent injection policy and optional pinned snapshot for an asset."""

    INJECTION_SUMMARY = "summary"
    INJECTION_REFERENCE = "reference"
    INJECTION_TOOL = "tool"
    INJECTION_MODE_CHOICES = [
        (INJECTION_SUMMARY, "Summary"),
        (INJECTION_REFERENCE, "Reference"),
        (INJECTION_TOOL, "Tool"),
    ]

    asset = models.ForeignKey(ServerMemoryAsset, on_delete=models.CASCADE, related_name="agent_bindings")
    agent = models.ForeignKey(
        "servers.ServerAgent",
        on_delete=models.CASCADE,
        related_name="memory_asset_bindings",
    )
    pinned_snapshot = models.ForeignKey(
        ServerMemorySnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pinned_memory_asset_bindings",
    )
    bound_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="server_memory_asset_bindings_created",
    )
    injection_mode = models.CharField(max_length=20, choices=INJECTION_MODE_CHOICES, default=INJECTION_REFERENCE)
    priority = models.PositiveSmallIntegerField(default=100)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["asset_id", "agent_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "agent"],
                name="servers_mem_asset_unique_agent_binding",
            )
        ]


class ServerMemoryRetrievalAudit(models.Model):
    """Query-safe audit metadata for scoped memory retrieval."""

    STATUS_SUCCEEDED = "succeeded"
    STATUS_DENIED = "denied"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_SUCCEEDED, "Succeeded"),
        (STATUS_DENIED, "Denied"),
        (STATUS_ERROR, "Error"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="server_memory_retrieval_audits",
    )
    project = models.ForeignKey(
        "core_ui.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="server_memory_retrieval_audits",
    )
    agent = models.ForeignKey(
        "servers.ServerAgent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memory_retrieval_audits",
    )
    query_sha256 = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUCCEEDED)
    include_candidates = models.BooleanField(default=False)
    requested_server_count = models.PositiveIntegerField(default=0)
    accessible_server_count = models.PositiveIntegerField(default=0)
    result_count = models.PositiveIntegerField(default=0)
    returned_char_count = models.PositiveIntegerField(default=0)
    requested_top_k = models.PositiveIntegerField(default=0)
    requested_char_budget = models.PositiveIntegerField(default=0)
    result_refs = models.JSONField(default=list, blank=True)
    error_code = models.CharField(max_length=80, blank=True, default="")
    duration_ms = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "project", "-created_at"])]
