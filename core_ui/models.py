"""
Core UI models: app-level permissions, chat sessions, managed secrets, and shared preferences.
"""

from django.contrib.auth.models import Group, User
from django.db import models

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
    ROLE_SYSTEM = "system"
    ROLE_CHOICES = [(ROLE_USER, "User"), (ROLE_ASSISTANT, "Assistant"), (ROLE_SYSTEM, "System")]

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["session", "created_at"]),
        ]

    def __str__(self):
        return f"{self.session_id} [{self.role}]: {self.content[:50]}..."


class AssistantAction(models.Model):
    """Structured assistant action proposed from chat and executed through an allowlist."""

    STATUS_PROPOSED = "proposed"
    STATUS_REQUIRES_CONFIRMATION = "requires_confirmation"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PROPOSED, "Proposed"),
        (STATUS_REQUIRES_CONFIRMATION, "Requires confirmation"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    RISK_READ = "read"
    RISK_INTERNAL_WRITE = "internal_write"
    RISK_EXTERNAL = "external"
    RISK_MUTATING = "mutating"
    RISK_DANGEROUS = "dangerous"
    RISK_CHOICES = [
        (RISK_READ, "Read"),
        (RISK_INTERNAL_WRITE, "Internal write"),
        (RISK_EXTERNAL, "External"),
        (RISK_MUTATING, "Mutating"),
        (RISK_DANGEROUS, "Dangerous"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="assistant_actions")
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="actions")
    message = models.ForeignKey(
        ChatMessage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="actions",
    )
    action_type = models.CharField(max_length=120)
    title = models.CharField(max_length=200, blank=True, default="")
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_PROPOSED)
    risk = models.CharField(max_length=30, choices=RISK_CHOICES, default=RISK_READ)
    required_feature = models.CharField(max_length=40, blank=True, default="")
    requires_confirmation = models.BooleanField(default=False)
    input_payload = models.JSONField(default=dict, blank=True)
    safe_preview = models.JSONField(default=dict, blank=True)
    result_payload = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default="")
    target_url = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="cu_asst_user_created_idx"),
            models.Index(fields=["session", "created_at"], name="cu_asst_session_created_idx"),
            models.Index(fields=["status", "-updated_at"], name="cu_asst_status_updated_idx"),
            models.Index(fields=["action_type"], name="cu_asst_type_idx"),
        ]

    def __str__(self):
        return f"{self.action_type} [{self.status}]"


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
    ("kubernetes", "Kubernetes"),
    ("mars", "MARS"),
    ("settings", "Settings"),
    ("orchestrator", "Orchestrator"),
    ("knowledge_base", "Knowledge Base"),
]

# Features allowed by default for non-staff users.
# Settings remain opt-in, and the admin dashboard stays staff-only.
DEFAULT_ALLOWED_FEATURES = {"servers", "agents", "knowledge_base", "dashboard"}
# Features that must be granted explicitly even for staff users.
EXPLICIT_OPT_IN_FEATURES = {"kubernetes", "mars"}
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

    provider = models.CharField(max_length=20)  # gemini, grok, openai, fair, claude, ollama
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


# -----------------------------------------
# Dashboard Layouts
# -----------------------------------------


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
