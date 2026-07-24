"""Activity / audit and LLM usage log models."""

from django.contrib.auth.models import User
from django.db import models


class UserActivityLog(models.Model):
    """Unified activity log for user actions in UI and API."""

    STATUS_INFO = "info"
    STATUS_SUCCESS = "success"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_INFO, "Info"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_ERROR, "Error"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
    )
    username_snapshot = models.CharField(max_length=150, blank=True, default="")
    category = models.CharField(max_length=40, default="other")
    action = models.CharField(max_length=80)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_INFO)
    description = models.TextField(blank=True, default="")
    entity_type = models.CharField(max_length=40, blank=True, default="")
    entity_id = models.CharField(max_length=64, blank=True, default="")
    entity_name = models.CharField(max_length=255, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["category", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self):
        actor = self.username_snapshot or (self.user.username if self.user_id else "unknown")
        return f"{actor}: {self.action} ({self.status})"


class LLMUsageLog(models.Model):
    """Tracks LLM API calls for monitoring and cost estimation."""

    provider = models.CharField(max_length=20)  # gemini, grok, openai, claude, ollama
    model_name = models.CharField(max_length=100)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    duration_ms = models.IntegerField(default=0)
    status = models.CharField(max_length=20, default="success")  # success, error, timeout
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["provider", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.provider}/{self.model_name} ({self.status})"
