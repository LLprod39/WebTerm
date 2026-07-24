"""Chat history models: sessions, messages, assistant actions, turns, artifacts."""

from django.contrib.auth.models import User
from django.db import models


class ChatSession(models.Model):
    """Сессия чата — список сообщений одного диалога."""

    KIND_MANUAL = "manual"
    KIND_DUTY = "duty"
    KIND_INCIDENT = "incident"
    KIND_CHOICES = [
        (KIND_MANUAL, "Manual"),
        (KIND_DUTY, "Duty"),
        (KIND_INCIDENT, "Incident"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_sessions")
    title = models.CharField(max_length=200, default="Новый чат")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_MANUAL)
    pinned_context = models.JSONField(default=dict, blank=True)
    total_usage = models.JSONField(default=dict, blank=True)
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
    undo_payload = models.JSONField(default=dict, blank=True)
    dry_run_preview = models.JSONField(default=dict, blank=True)
    blast_radius = models.JSONField(default=dict, blank=True)
    async_run_ref = models.JSONField(default=dict, blank=True)
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


class ChatTurnState(models.Model):
    """Parked/running operator-loop turn (LLM messages + pending tool confirmation)."""

    STATUS_RUNNING = "running"
    STATUS_AWAITING_CONFIRM = "awaiting_confirm"
    STATUS_AWAITING_ASYNC = "awaiting_async"
    STATUS_RESUMING = "resuming"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"
    STATUS_LIMIT = "limit"
    STATUS_CHOICES = [
        (STATUS_RUNNING, "Running"),
        (STATUS_AWAITING_CONFIRM, "Awaiting confirm"),
        (STATUS_AWAITING_ASYNC, "Awaiting async"),
        (STATUS_RESUMING, "Resuming"),
        (STATUS_DONE, "Done"),
        (STATUS_FAILED, "Failed"),
        (STATUS_LIMIT, "Limit"),
    ]

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="turn_states")
    user_message = models.ForeignKey(
        ChatMessage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="turn_states_as_user",
    )
    assistant_message = models.ForeignKey(
        ChatMessage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="turn_states_as_assistant",
    )
    pending_action = models.ForeignKey(
        AssistantAction,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="turn_states",
    )
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    llm_messages = models.JSONField(default=list, blank=True)
    pending_tool_call = models.JSONField(default=dict, blank=True)
    iteration = models.PositiveIntegerField(default=0)
    total_input_tokens = models.PositiveIntegerField(default=0)
    total_output_tokens = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["session", "status"], name="cu_turn_session_status_idx"),
            models.Index(fields=["session", "-updated_at"], name="cu_turn_session_updated_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["session"],
                condition=models.Q(
                    status__in=[
                        "running",
                        "awaiting_confirm",
                        "awaiting_async",
                        "resuming",
                    ]
                ),
                name="cu_turn_one_active_per_session",
            )
        ]

    def __str__(self):
        return f"turn {self.pk} session={self.session_id} [{self.status}]"


class ChatArtifact(models.Model):
    """Generated artifact (ansible/script/report/chart) attached to a chat session."""

    KIND_ANSIBLE = "ansible"
    KIND_SCRIPT = "script"
    KIND_REPORT = "report"
    KIND_CHART = "chart"
    KIND_OTHER = "other"
    KIND_CHOICES = [
        (KIND_ANSIBLE, "Ansible"),
        (KIND_SCRIPT, "Script"),
        (KIND_REPORT, "Report"),
        (KIND_CHART, "Chart"),
        (KIND_OTHER, "Other"),
    ]

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="artifacts")
    message = models.ForeignKey(
        ChatMessage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="artifacts",
    )
    kind = models.CharField(max_length=30, choices=KIND_CHOICES, default=KIND_OTHER)
    title = models.CharField(max_length=200, blank=True, default="")
    content = models.TextField(blank=True, default="")
    version = models.PositiveIntegerField(default=1)
    metadata = models.JSONField(default=dict, blank=True)
    saved_playbook_id = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["session", "-updated_at"], name="cu_art_session_updated_idx"),
        ]

    def __str__(self):
        return f"{self.kind}:{self.title or self.pk} v{self.version}"
