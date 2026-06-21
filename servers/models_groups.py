"""Server group and group-access models."""

from django.contrib.auth.models import User
from django.db import models


class ServerGroup(models.Model):
    """Groups for organizing servers"""

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=7, default="#3b82f6")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="server_groups")
    created_at = models.DateTimeField(auto_now_add=True)
    tags = models.ManyToManyField("ServerGroupTag", blank=True, related_name="groups")

    # Group-level rules
    rules = models.TextField(blank=True, help_text="Правила для группы серверов: специфичные политики, ограничения")
    forbidden_commands = models.JSONField(default=list, blank=True, help_text="Запрещённые команды для этой группы")
    environment_vars = models.JSONField(default=dict, blank=True, help_text="Переменные окружения для группы")

    class Meta:
        unique_together = ["name", "user"]
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_context_for_ai(self) -> str:
        """Get formatted context for AI agents"""
        parts = []

        if self.description:
            parts.append(f"Группа: {self.name}\n{self.description}")

        if self.rules:
            parts.append(f"Правила группы:\n{self.rules}")

        if self.forbidden_commands:
            cmds = ", ".join(self.forbidden_commands)
            parts.append(f"⛔ Запрещено в группе: {cmds}")

        return "\n".join(parts) if parts else ""


class ServerGroupTag(models.Model):
    """Tags for server groups"""

    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7, default="#6b7280")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="server_group_tags")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["name", "user"]
        ordering = ["name"]

    def __str__(self):
        return self.name


class ServerGroupMember(models.Model):
    """Memberships with roles"""

    ROLE_CHOICES = [
        ("owner", "Owner"),
        ("admin", "Admin"),
        ("member", "Member"),
        ("viewer", "Viewer"),
    ]
    group = models.ForeignKey(ServerGroup, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="server_group_memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="member")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["group", "user"]
        indexes = [
            models.Index(fields=["group", "user"]),
            models.Index(fields=["user"]),
        ]

    def __str__(self):
        return f"{self.group.name} - {self.user.username} ({self.role})"


class ServerGroupSubscription(models.Model):
    """Subscriptions for notifications or favorites"""

    KIND_CHOICES = [
        ("follow", "Follow"),
        ("favorite", "Favorite"),
    ]
    group = models.ForeignKey(ServerGroup, on_delete=models.CASCADE, related_name="subscriptions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="server_group_subscriptions")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default="follow")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["group", "user", "kind"]
        indexes = [
            models.Index(fields=["user", "kind"]),
        ]


class ServerGroupPermission(models.Model):
    """Optional granular permissions overrides"""

    group = models.ForeignKey(ServerGroup, on_delete=models.CASCADE, related_name="permissions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="server_group_permissions")
    can_view = models.BooleanField(default=True)
    can_execute = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_manage_members = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["group", "user"]
        indexes = [
            models.Index(fields=["group"]),
            models.Index(fields=["user"]),
        ]


