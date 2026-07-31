"""Operational playbooks / runbooks and their execution history."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models


class Playbook(models.Model):
    """Reusable multi-host automation definition (runbook or ansible-sourced)."""

    KIND_RUNBOOK = "runbook"
    KIND_ANSIBLE = "ansible"
    KIND_CHOICES = [
        (KIND_RUNBOOK, "Runbook"),
        (KIND_ANSIBLE, "Ansible"),
    ]

    CATEGORY_DEPLOY = "deploy"
    CATEGORY_PATCH = "patch"
    CATEGORY_DIAGNOSE = "diagnose"
    CATEGORY_SECURITY = "security"
    CATEGORY_MAINTENANCE = "maintenance"
    CATEGORY_CUSTOM = "custom"
    CATEGORY_CHOICES = [
        (CATEGORY_DEPLOY, "Deploy"),
        (CATEGORY_PATCH, "Patch"),
        (CATEGORY_DIAGNOSE, "Diagnose"),
        (CATEGORY_SECURITY, "Security"),
        (CATEGORY_MAINTENANCE, "Maintenance"),
        (CATEGORY_CUSTOM, "Custom"),
    ]

    VISIBILITY_PRIVATE = "private"
    VISIBILITY_SHARED = "shared"
    VISIBILITY_CHOICES = [
        (VISIBILITY_PRIVATE, "Private"),
        (VISIBILITY_SHARED, "Shared"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="playbooks")
    project = models.ForeignKey(
        "core_ui.Project",
        on_delete=models.CASCADE,
        related_name="playbooks",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_RUNBOOK)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default=CATEGORY_CUSTOM)
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default=VISIBILITY_PRIVATE)
    tasks = models.JSONField(default=list, blank=True, help_text="Ordered task list")
    source_yaml = models.TextField(blank=True, default="", help_text="Original Ansible YAML if imported")
    tags = models.JSONField(default=list, blank=True)
    fidelity = models.JSONField(
        default=dict,
        blank=True,
        help_text="Import fidelity: runnable/total/unsupported modules",
    )
    compatibility = models.JSONField(
        default=dict,
        blank=True,
        help_text="Latest deterministic Ansible compatibility report",
    )
    active_compatibility_revision = models.ForeignKey(
        "PlaybookCompatibilityRevision",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="active_for_playbooks",
    )
    origin_revision = models.ForeignKey(
        "PlaybookRevision",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="origin_for_playbooks",
    )
    published_revision = models.ForeignKey(
        "PlaybookRevision",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_for_playbooks",
    )
    forked_from_revision = models.ForeignKey(
        "PlaybookRevision",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="forked_playbooks",
    )
    is_archived = models.BooleanField(default=False)
    is_template_clone = models.BooleanField(default=False)
    template_slug = models.CharField(max_length=80, blank=True, default="")
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_run_status = models.CharField(max_length=20, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["project", "-updated_at"], name="servers_pla_project_0f003a_idx"),
            models.Index(fields=["user", "-updated_at"]),
            models.Index(fields=["user", "category"]),
            models.Index(fields=["visibility", "-updated_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.kind})"

    def save(self, *args, **kwargs):
        from core_ui.projects import assign_active_project

        assign_active_project(self, user_field="user")
        return super().save(*args, **kwargs)

    @property
    def task_count(self) -> int:
        return len(self.tasks) if isinstance(self.tasks, list) else 0


class PlaybookCompatibilityRevision(models.Model):
    """AI/deterministic adaptation proposal that never overwrites source_yaml."""

    STATUS_DRAFT = "draft"
    STATUS_VALIDATED = "validated"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_VALIDATED, "Validated"),
        (STATUS_REJECTED, "Rejected"),
    ]

    playbook = models.ForeignKey(Playbook, on_delete=models.CASCADE, related_name="compatibility_revisions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="playbook_compatibility_revisions")
    source_hash = models.CharField(max_length=64)
    adapted_yaml = models.TextField()
    inventory_bindings = models.JSONField(default=dict, blank=True)
    report = models.JSONField(default=dict, blank=True)
    semantic_guard = models.JSONField(default=dict, blank=True)
    change_summary = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    source_revision = models.ForeignKey(
        "PlaybookRevision",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legacy_compatibility_inputs",
    )
    result_revision = models.ForeignKey(
        "PlaybookRevision",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legacy_compatibility_outputs",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["playbook", "-created_at"],
                name="servers_pla_playboo_compat_idx",
            )
        ]

    def __str__(self) -> str:
        return f"Compatibility revision #{self.pk} for {self.playbook_id} ({self.status})"


class PlaybookRun(models.Model):
    """Single multi-host execution of a playbook snapshot."""

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_PARTIAL = "partial"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_PARTIAL, "Partial"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    playbook = models.ForeignKey(
        Playbook,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="runs",
    )
    project = models.ForeignKey(
        "core_ui.Project",
        on_delete=models.CASCADE,
        related_name="playbook_runs",
    )
    revision = models.ForeignKey(
        "PlaybookRevision",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="runs",
    )
    validation = models.ForeignKey(
        "PlaybookValidation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="runs",
    )
    binding_profile = models.ForeignKey(
        "PlaybookBindingProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="runs",
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="playbook_runs")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    playbook_snapshot = models.JSONField(default=dict, blank=True)
    target_server_ids = models.JSONField(default=list, blank=True)
    target_group_ids = models.JSONField(default=list, blank=True)
    options = models.JSONField(default=dict, blank=True)
    variable_manifest = models.JSONField(
        default=dict,
        blank=True,
        help_text="Redacted variable names and managed-secret references; never raw secret values.",
    )
    execution_fingerprint = models.JSONField(default=dict, blank=True)
    host_results = models.JSONField(default=list, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    progress = models.JSONField(
        default=dict,
        blank=True,
        help_text="Live execution progress: current play/task, counters",
    )
    live_log = models.TextField(
        blank=True,
        default="",
        help_text="Streamed engine output (tail) updated while the run is active",
    )
    inventory_preview = models.TextField(blank=True, default="")
    cancel_requested = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    terminal_notified_at = models.DateTimeField(null=True, blank=True)
    terminal_notification_claimed_at = models.DateTimeField(null=True, blank=True)
    terminal_notification_attempts = models.PositiveIntegerField(default=0)
    terminal_notification_last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "-created_at"], name="servers_pbr_project_1a80ab_idx"),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["playbook", "-created_at"]),
        ]

    def __str__(self) -> str:
        name = ""
        if isinstance(self.playbook_snapshot, dict):
            name = str(self.playbook_snapshot.get("name") or "")
        return f"Run #{self.pk} {name} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.project_id:
            if self.playbook_id:
                self.project_id = self.playbook.project_id
            else:
                from core_ui.projects import assign_active_project

                assign_active_project(self, user_field="user")
        return super().save(*args, **kwargs)


class PlaybookRunDispatch(models.Model):
    """Durable, leased queue item for a prepared playbook run."""

    STATUS_QUEUED = "queued"
    STATUS_CLAIMED = "claimed"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CANCELED = "canceled"
    STATUS_INTERRUPTED = "interrupted"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_CLAIMED, "Claimed"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELED, "Canceled"),
        (STATUS_INTERRUPTED, "Interrupted"),
    ]

    run = models.OneToOneField(PlaybookRun, on_delete=models.CASCADE, related_name="dispatch")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="playbook_run_dispatches")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    metadata = models.JSONField(default=dict, blank=True)
    queued_at = models.DateTimeField(auto_now_add=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    claimed_by = models.CharField(max_length=120, blank=True, default="")
    attempt_count = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True, default="")
    mutation_safe_to_retry = models.BooleanField(
        default=False,
        help_text="Must be explicitly true before an expired claim may be requeued.",
    )

    class Meta:
        ordering = ["queued_at", "id"]
        indexes = [
            models.Index(fields=["status", "queued_at"], name="pb_dispatch_queue_idx"),
            models.Index(fields=["status", "lease_expires_at"], name="pb_dispatch_lease_idx"),
        ]

    def __str__(self) -> str:
        return f"Playbook run {self.run_id} dispatch [{self.status}]"
