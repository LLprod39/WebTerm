"""App-level feature permissions (user + group)."""

from django.contrib.auth.models import Group, User
from django.db import models

FEATURE_CHOICES = [
    ("servers", "Servers"),
    ("dashboard", "Dashboard"),
    ("agents", "Agents"),
    ("chat", "Chat"),
    ("automation", "Automation"),
    ("ai_connections_personal", "Personal AI Connections"),
    ("ai_connections_admin", "AI Connections Administration"),
    ("studio", "Studio"),
    ("studio_pipelines", "Studio Pipelines"),
    ("studio_runs", "Studio Runs"),
    ("studio_agents", "Studio Agents"),
    ("studio_skills", "Studio Skills"),
    ("studio_mcp", "Studio MCP"),
    ("studio_notifications", "Studio Notifications"),
    ("kubernetes", "Kubernetes"),
    ("kubernetes_admin_read", "Kubernetes Admin Read"),
    ("kubernetes_admin_write", "Kubernetes Admin Write"),
    ("kubernetes_break_glass", "Kubernetes Break Glass"),
    ("kubernetes_secret_read", "Kubernetes Secret Read"),
    ("mars", "MARS"),
    ("settings", "Settings"),
    ("orchestrator", "Orchestrator"),
    ("knowledge_base", "Knowledge Base"),
    ("web_research", "Web Research"),
]

# Features allowed by default for non-staff users (aligned with pilot_user).
# Settings remain opt-in, and the admin dashboard stays staff-only.
DEFAULT_ALLOWED_FEATURES = {"servers", "agents", "dashboard", "chat", "ai_connections_personal"}
# Features that must be granted explicitly even for staff users.
EXPLICIT_OPT_IN_FEATURES = {
    "kubernetes",
    "kubernetes_admin_read",
    "kubernetes_admin_write",
    "kubernetes_break_glass",
    "kubernetes_secret_read",
    "mars",
    "web_research",
    "ai_connections_admin",
}
STAFF_ONLY_FEATURES = set()


class UserAppPermission(models.Model):
    """Per-user, per-feature permission. Used for flexible access to app sections (tabs)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="app_permissions")
    feature = models.CharField(max_length=30, choices=FEATURE_CHOICES)
    allowed = models.BooleanField(default=True)

    class Meta:
        unique_together = ["user", "feature"]
        ordering = ["user", "feature"]
        indexes = [
            models.Index(fields=["user", "feature"]),
        ]

    def __str__(self):
        return f"{self.user.username} / {self.feature} = {self.allowed}"


class GroupAppPermission(models.Model):
    """Per-group, per-feature permission. Used as shared access policy with user-level overrides."""

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="app_permissions")
    feature = models.CharField(max_length=30, choices=FEATURE_CHOICES)
    allowed = models.BooleanField(default=True)

    class Meta:
        unique_together = ["group", "feature"]
        ordering = ["group", "feature"]
        indexes = [
            models.Index(fields=["group", "feature"]),
        ]

    def __str__(self):
        return f"{self.group.name} / {self.feature} = {self.allowed}"
