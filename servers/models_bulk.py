"""Durable group-wide server mutation jobs."""

from django.contrib.auth.models import User
from django.db import models

from servers.models_groups import ServerGroup


class ServerBulkOperation(models.Model):
    """A resumable, idempotent operation over a snapshot of group servers."""

    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    ACTION_SET_ACTIVE = "set_active"
    ACTION_SET_AI_READ_ONLY = "set_ai_read_only"
    ACTION_SET_TAGS = "set_tags"
    ACTION_CHOICES = [
        (ACTION_SET_ACTIVE, "Set active state"),
        (ACTION_SET_AI_READ_ONLY, "Set AI read-only state"),
        (ACTION_SET_TAGS, "Replace tags"),
    ]

    group = models.ForeignKey(ServerGroup, on_delete=models.CASCADE, related_name="bulk_operations")
    project = models.ForeignKey("core_ui.Project", on_delete=models.CASCADE, related_name="server_bulk_operations")
    requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="requested_server_bulk_operations",
    )
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    parameters = models.JSONField(default=dict, blank=True)
    target_server_ids = models.JSONField(default=list)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    total_count = models.PositiveIntegerField(default=0)
    processed_count = models.PositiveIntegerField(default=0)
    succeeded_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    failures = models.JSONField(default=list, blank=True)
    claimed_by = models.CharField(max_length=160, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "lease_expires_at"], name="srv_bulk_status_lease_idx"),
            models.Index(fields=["group", "-created_at"], name="srv_bulk_group_created_idx"),
            models.Index(fields=["project", "status"], name="srv_bulk_project_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.group_id}:{self.action}:{self.status}"
