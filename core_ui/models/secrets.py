"""Managed secret envelopes stored server-side."""

from django.db import models


class ManagedSecret(models.Model):
    """Encrypted secret envelope stored server-side and addressed by namespace/object id."""

    namespace = models.CharField(max_length=50)
    object_id = models.PositiveIntegerField()
    key = models.CharField(max_length=50, default="default")
    ciphertext = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["namespace", "object_id", "key"]
        ordering = ["namespace", "object_id", "key"]
        indexes = [
            models.Index(fields=["namespace", "object_id"]),
            models.Index(fields=["updated_at"]),
        ]

    def __str__(self):
        return f"{self.namespace}:{self.object_id}:{self.key}"
