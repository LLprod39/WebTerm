from __future__ import annotations

import hashlib
import hmac

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class ApprovalRequest(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_EXPIRED, "Expired"),
    ]

    run = models.ForeignKey(
        "studio.PipelineRun",
        on_delete=models.CASCADE,
        related_name="approval_requests",
    )
    node_id = models.CharField(max_length=100)
    token_digest = models.CharField(max_length=64)
    approver = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
        related_name="studio_approval_requests",
    )
    requested_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requested_studio_approvals",
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    response_text = models.TextField(blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="decided_studio_approvals",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run", "node_id"], name="studio_approval_run_node_uniq"),
        ]
        indexes = [
            models.Index(fields=["approver", "status", "expires_at"], name="studio_appr_user_status_idx"),
            models.Index(fields=["status", "expires_at"], name="studio_appr_status_exp_idx"),
        ]

    @staticmethod
    def digest_token(token: str) -> str:
        return hashlib.sha256(str(token).encode("utf-8")).hexdigest()

    def token_matches(self, token: str) -> bool:
        return hmac.compare_digest(self.token_digest, self.digest_token(token))

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    def __str__(self) -> str:
        return f"Approval request for run #{self.run_id}/{self.node_id} [{self.status}]"
