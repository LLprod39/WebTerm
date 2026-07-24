"""Per-user terminal and dashboard preference models."""

from django.contrib.auth.models import User
from django.db import models


class TerminalPreference(models.Model):
    """Per-user terminal appearance/behaviour settings (synced to DB)."""

    CURSOR_BLOCK = "block"
    CURSOR_BAR = "bar"
    CURSOR_UNDERLINE = "underline"
    CURSOR_CHOICES = [
        (CURSOR_BLOCK, "Block"),
        (CURSOR_BAR, "Bar"),
        (CURSOR_UNDERLINE, "Underline"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="terminal_preference",
    )
    theme_name = models.CharField(max_length=40, default="one_dark")
    theme_colors = models.JSONField(default=dict, blank=True)
    font_size = models.PositiveSmallIntegerField(default=14)
    font_family = models.CharField(max_length=80, default="JetBrains Mono")
    line_height = models.FloatField(default=1.4)
    cursor_style = models.CharField(
        max_length=10,
        choices=CURSOR_CHOICES,
        default=CURSOR_BLOCK,
    )
    cursor_blink = models.BooleanField(default=True)
    scrollback = models.PositiveIntegerField(default=5000)
    intercept_editors = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["user"]),
        ]

    def __str__(self):
        return f"{self.user.username}: {self.theme_name} {self.font_size}px"


class DashboardLayout(models.Model):
    """Stores user-specific dashboard layouts and widget configurations."""

    DASHBOARD_TYPES = [
        ("admin", "Admin Dashboard"),
        ("user", "User Dashboard"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="dashboard_layouts")
    dashboard_type = models.CharField(max_length=20, choices=DASHBOARD_TYPES)
    layout_data = models.JSONField(
        default=dict,
        help_text="JSON mapping of widget IDs to their grid positions and sizes.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["user", "dashboard_type"]
        indexes = [
            models.Index(fields=["user", "dashboard_type"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.dashboard_type} layout"
