from __future__ import annotations

from django.conf import settings
from django.db import models


class PipelineNodeDeadLetter(models.Model):
    """Terminal per-node failure retained for explicit operator review."""

    STATUS_OPEN = "open"
    STATUS_RESOLVED = "resolved"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_RESOLVED, "Resolved"),
    ]

    run = models.ForeignKey(
        "studio.PipelineRun",
        on_delete=models.CASCADE,
        related_name="dead_letters",
    )
    node_id = models.CharField(max_length=100)
    node_type = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    attempt_count = models.PositiveSmallIntegerField(default=1)
    max_attempts = models.PositiveSmallIntegerField(default=1)
    last_error = models.TextField(blank=True)
    node_state = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resolved_pipeline_dead_letters",
    )
    resolution_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["run", "node_id"], name="studio_dead_letter_run_node_unique"),
            models.CheckConstraint(condition=models.Q(max_attempts__gte=1), name="studio_dead_letter_max_gte_1"),
        ]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="studio_dead_status_created_idx"),
            models.Index(fields=["run", "status"], name="studio_dead_run_status_idx"),
        ]

    def __str__(self) -> str:
        return f"pipeline run={self.run_id} node={self.node_id} [{self.status}]"
