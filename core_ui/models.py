"""
Core UI models: app-level permissions, chat sessions, desktop auth, and managed secrets.
"""

from django.contrib.auth.models import Group, User
from django.db import models
from django.utils import timezone

# -----------------------------------------
# Chat history
# -----------------------------------------


class ChatSession(models.Model):
    """Сессия чата — список сообщений одного диалога."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_sessions")
    title = models.CharField(max_length=200, default="Новый чат")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "-updated_at"]),
        ]

    def __str__(self):
        return f"{self.user.username}: {self.title}"


class ChatMessage(models.Model):
    """Одно сообщение в сессии чата."""

    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_CHOICES = [(ROLE_USER, "User"), (ROLE_ASSISTANT, "Assistant")]

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["session", "created_at"]),
        ]

    def __str__(self):
        return f"{self.session_id} [{self.role}]: {self.content[:50]}..."


# -----------------------------------------
# Permissions
# -----------------------------------------


FEATURE_CHOICES = [
    ("servers", "Servers"),
    ("dashboard", "Dashboard"),
    ("agents", "Agents"),
    ("studio", "Studio"),
    ("studio_pipelines", "Studio Pipelines"),
    ("studio_runs", "Studio Runs"),
    ("studio_agents", "Studio Agents"),
    ("studio_skills", "Studio Skills"),
    ("studio_mcp", "Studio MCP"),
    ("studio_notifications", "Studio Notifications"),
    ("settings", "Settings"),
    ("orchestrator", "Orchestrator"),
    ("knowledge_base", "Knowledge Base"),
]

# Features allowed by default for non-staff users.
# Settings remain opt-in, and the admin dashboard stays staff-only.
DEFAULT_ALLOWED_FEATURES = {"servers", "agents", "knowledge_base"}
STAFF_ONLY_FEATURES = {"dashboard"}


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


# -----------------------------------------
# Activity / Audit logs
# -----------------------------------------


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


# -----------------------------------------
# LLM Usage Logs
# -----------------------------------------


class LLMUsageLog(models.Model):
    """Tracks LLM API calls for monitoring and cost estimation."""

    provider = models.CharField(max_length=20)  # gemini, grok, openai, claude
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


class DesktopRefreshToken(models.Model):
    """Server-side refresh token record for WinUI/desktop clients."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="desktop_refresh_tokens")
    token_hash = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=120, blank=True, default="")
    user_agent = models.CharField(max_length=512, blank=True, default="")
    expires_at = models.DateTimeField()
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    replaced_by = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="replaces",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["revoked_at"]),
        ]

    def __str__(self):
        return f"desktop refresh token for {self.user.username}"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and self.expires_at > timezone.now()


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


# -----------------------------------------
# Terminal Preferences
# -----------------------------------------


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
