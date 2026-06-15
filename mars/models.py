from __future__ import annotations

from django.conf import settings
from django.db import models


def default_deny_globs() -> list[str]:
    return [
        ".git/**",
        ".venv/**",
        "node_modules/**",
        "dist/**",
        "build/**",
        ".cache/**",
        "__pycache__/**",
        ".env",
        ".env.*",
        "*id_rsa*",
        "*id_ed25519*",
        "*credentials*",
        "*secret*",
    ]


def default_cli_roles() -> dict[str, str]:
    return {"executor": "codex", "reviewer": "gemini"}


class MarsWorkspace(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mars_workspaces")
    name = models.CharField(max_length=160)
    root_path = models.CharField(max_length=1024)
    read_allow_roots = models.JSONField(default=list, blank=True)
    write_allow_roots = models.JSONField(default=list, blank=True)
    deny_globs = models.JSONField(default=default_deny_globs, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        unique_together = ["user", "name"]
        indexes = [
            models.Index(fields=["user", "enabled", "name"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.root_path})"


class MarsSession(models.Model):
    STATUS_INTERVIEW = "interview"
    STATUS_PLAN_READY = "plan_ready"
    STATUS_APPROVED = "approved"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_INTERVIEW, "Interview"),
        (STATUS_PLAN_READY, "Plan ready"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mars_sessions")
    workspace = models.ForeignKey(MarsWorkspace, on_delete=models.CASCADE, related_name="sessions")
    task_brief = models.TextField()
    answers = models.JSONField(default=dict, blank=True)
    interview_questions = models.JSONField(default=list, blank=True)
    selected_skill_slugs = models.JSONField(default=list, blank=True)
    generated_plan = models.TextField(blank=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_INTERVIEW)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        indexes = [
            models.Index(fields=["user", "status", "-updated_at"]),
            models.Index(fields=["workspace", "-updated_at"]),
        ]

    def __str__(self) -> str:
        return f"MARS session #{self.pk} [{self.status}]"


class MarsRun(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_STOPPED = "stopped"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_STOPPED, "Stopped"),
    ]

    session = models.ForeignKey(MarsSession, on_delete=models.CASCADE, related_name="runs")
    workspace = models.ForeignKey(MarsWorkspace, on_delete=models.CASCADE, related_name="runs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mars_runs")
    cli_roles = models.JSONField(default=default_cli_roles, blank=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    runtime_control = models.JSONField(default=dict, blank=True)
    allow_dirty = models.BooleanField(default=False)
    final_report = models.TextField(blank=True)
    codex_summary = models.TextField(blank=True)
    gemini_review = models.TextField(blank=True)
    test_output = models.TextField(blank=True)
    git_before = models.TextField(blank=True)
    git_after = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "status", "-created_at"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["session", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"MARS run #{self.pk} [{self.status}]"


class MarsRunEvent(models.Model):
    run = models.ForeignKey(MarsRun, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=80)
    message = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["run", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"mars_run={self.run_id} {self.event_type}"

