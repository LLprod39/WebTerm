from __future__ import annotations

from django.conf import settings
from django.db import models


class PluginSecretBinding(models.Model):
    installation = models.ForeignKey(
        "plugin_marketplace.PluginInstallation", on_delete=models.CASCADE, related_name="secret_bindings"
    )
    key = models.CharField(max_length=120)
    secret_ref = models.CharField(max_length=240)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="plugin_secret_bindings",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["installation_id", "key"]
        constraints = [models.UniqueConstraint(fields=["installation", "key"], name="pm_secret_install_key_uniq")]

    def __str__(self) -> str:
        return f"{self.installation.plugin_id}:{self.key}"
