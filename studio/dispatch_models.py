from __future__ import annotations

from django.db import models


class PipelineDispatchControl(models.Model):
    """Singleton row used to serialize cross-process concurrency decisions."""

    name = models.CharField(max_length=32, unique=True, default="global")
    updated_at = models.DateTimeField(auto_now=True)


class PipelineRunDispatch(models.Model):
    """Durable queue item owned by the pipeline execution plane."""

    STATUS_QUEUED = "queued"
    STATUS_CLAIMED = "claimed"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CANCELED = "canceled"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_CLAIMED, "Claimed"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELED, "Canceled"),
    ]

    run = models.OneToOneField(
        "studio.PipelineRun",
        on_delete=models.CASCADE,
        related_name="dispatch",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    metadata = models.JSONField(default=dict, blank=True)
    queued_at = models.DateTimeField(auto_now_add=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    claimed_by = models.CharField(max_length=120, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["queued_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(max_attempts__gte=1),
                name="studio_dispatch_max_attempts_gte_1",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "queued_at"], name="studio_dispatch_status_idx"),
            models.Index(fields=["claimed_by", "status"], name="studio_dispatch_worker_idx"),
        ]

    def __str__(self) -> str:
        return f"pipeline run={self.run_id} [{self.status}]"
