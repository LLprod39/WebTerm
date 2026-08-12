"""Server agent and agent-run models."""

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from app.agent_audit_integrity import GENESIS_HASH, HASH_ALGORITHM, calculate_event_hash
from app.sudo_policy import (
    SUDO_POLICY_CHOICES,
    SUDO_POLICY_DISABLED,
)
from servers.models_inventory import Server


class ServerAgent(models.Model):
    """Configured server agent with scheduling."""

    MODE_MINI = "mini"
    MODE_FULL = "full"
    MODE_MULTI = "multi"
    MODE_CHOICES = [
        (MODE_MINI, "Mini Agent"),
        (MODE_FULL, "Full Agent (ReAct)"),
        (MODE_MULTI, "Multi-Agent Pipeline"),
    ]

    TYPE_SECURITY = "security_audit"
    TYPE_LOGS = "log_analyzer"
    TYPE_PERFORMANCE = "performance"
    TYPE_DISK = "disk_report"
    TYPE_DOCKER = "docker_status"
    TYPE_SERVICE = "service_health"
    TYPE_CUSTOM = "custom"
    TYPE_SECURITY_PATROL = "security_patrol"
    TYPE_DEPLOY_WATCHER = "deploy_watcher"
    TYPE_LOG_INVESTIGATOR = "log_investigator"
    TYPE_INFRA_SCOUT = "infra_scout"
    TYPE_MULTI_HEALTH = "multi_health"
    TYPE_CHOICES = [
        (TYPE_SECURITY, "Security Audit"),
        (TYPE_LOGS, "Log Analyzer"),
        (TYPE_PERFORMANCE, "Performance Profile"),
        (TYPE_DISK, "Disk Report"),
        (TYPE_DOCKER, "Docker Status"),
        (TYPE_SERVICE, "Service Health"),
        (TYPE_CUSTOM, "Custom"),
        (TYPE_SECURITY_PATROL, "Security Patrol"),
        (TYPE_DEPLOY_WATCHER, "Deploy Watcher"),
        (TYPE_LOG_INVESTIGATOR, "Log Investigator"),
        (TYPE_INFRA_SCOUT, "Infrastructure Scout"),
        (TYPE_MULTI_HEALTH, "Multi-Server Health"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="server_agents")
    project = models.ForeignKey(
        "core_ui.Project",
        on_delete=models.CASCADE,
        related_name="server_agents",
    )
    name = models.CharField(max_length=200)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default=MODE_MINI)
    agent_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default=TYPE_CUSTOM)
    commands = models.JSONField(default=list, help_text="List of shell commands (mini mode)")
    servers = models.ManyToManyField(Server, blank=True, related_name="agents")
    ai_prompt = models.TextField(blank=True, help_text="Extra instruction for AI analysis")
    provider_binding = models.JSONField(
        default=dict,
        blank=True,
        help_text="Canonical provider binding pinned for this agent and its scheduled runs.",
    )

    # Full-agent fields
    goal = models.TextField(blank=True, help_text="Goal for the agent to achieve (full mode)")
    system_prompt = models.TextField(blank=True, help_text="System prompt defining agent role and style")
    max_iterations = models.IntegerField(default=40, help_text="Max ReAct loop iterations (1-100)")
    allow_multi_server = models.BooleanField(default=False, help_text="Allow simultaneous multi-server connections")
    tools_config = models.JSONField(default=dict, blank=True, help_text="Tool availability overrides")
    sudo_policy = models.CharField(
        max_length=20,
        choices=SUDO_POLICY_CHOICES,
        default=SUDO_POLICY_DISABLED,
        help_text="Controlled sudo policy for SSH commands executed by this agent.",
    )
    stop_conditions = models.JSONField(default=list, blank=True, help_text="Conditions to stop the agent early")
    session_timeout_seconds = models.IntegerField(default=1200, help_text="Max session duration in seconds")
    max_connections = models.IntegerField(default=5, help_text="Max simultaneous SSH connections")
    skill_slugs = models.JSONField(default=list, blank=True, help_text="Studio skills attached to this agent")
    input_artifacts = models.JSONField(
        default=list,
        blank=True,
        help_text="Operator-provided documents, task lists and scripts available to the agent",
    )
    report_delivery = models.JSONField(
        default=dict,
        blank=True,
        help_text="Report delivery settings, for example Telegram delivery",
    )

    # GAP 7: per-agent memory policy overrides
    memory_policy_override = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Per-agent memory policy overrides. Supported keys: "
            "nearline_event_threshold (int), dream_mode (str: heuristic|nightly_llm|hybrid), "
            "raw_event_retention_days (int), episode_retention_days (int), "
            "human_habits_capture_enabled (bool), "
            "is_enabled (bool). Empty dict = use user-level policy."
        ),
    )

    schedule_minutes = models.IntegerField(default=0, help_text="0 = manual only")
    schedule_config = models.JSONField(default=dict, blank=True, help_text="Flexible schedule configuration")
    is_enabled = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["project", "-updated_at"], name="servers_ser_project_5fd502_idx"),
            models.Index(fields=["user", "-updated_at"]),
            models.Index(fields=["user", "mode"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_mode_display()} / {self.get_agent_type_display()})"

    def save(self, *args, **kwargs):
        from core_ui.projects import assign_active_project

        assign_active_project(self, user_field="user")
        return super().save(*args, **kwargs)

    @property
    def is_full(self) -> bool:
        return self.mode == self.MODE_FULL

    @property
    def is_multi(self) -> bool:
        return self.mode == self.MODE_MULTI


class AgentRun(models.Model):
    """Single execution of an agent (mini or full)."""

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_PAUSED = "paused"
    STATUS_WAITING = "waiting"
    STATUS_PLAN_REVIEW = "plan_review"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_STOPPED = "stopped"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_WAITING, "Waiting for user"),
        (STATUS_PLAN_REVIEW, "Awaiting Plan Approval"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_STOPPED, "Stopped"),
    ]

    agent = models.ForeignKey(ServerAgent, on_delete=models.CASCADE, related_name="runs", null=True, blank=True)
    project = models.ForeignKey(
        "core_ui.Project",
        on_delete=models.CASCADE,
        related_name="agent_runs",
        null=True,
        blank=True,
    )
    server = models.ForeignKey(
        Server,
        on_delete=models.SET_NULL,
        related_name="agent_runs",
        null=True,
        blank=True,
    )
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="agent_runs")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    commands_output = models.JSONField(default=list, help_text="[{cmd, stdout, stderr, exit_code, duration_ms}]")
    ai_analysis = models.TextField(blank=True)
    provider_binding_snapshot = models.JSONField(default=dict, blank=True)
    provider_session_id = models.CharField(max_length=255, blank=True, default="")
    provider_execution_mode = models.CharField(max_length=20, default="interactive")
    duration_ms = models.BigIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Full-agent fields
    iterations_log = models.JSONField(
        default=list,
        blank=True,
        help_text="[{iteration, thought, action, tool, args, observation, timestamp}]",
    )
    tool_calls = models.JSONField(
        default=list,
        blank=True,
        help_text="[{tool, args, result, duration_ms, timestamp}]",
    )
    total_iterations = models.IntegerField(default=0)
    connected_servers = models.JSONField(
        default=list,
        blank=True,
        help_text="[{server_id, server_name, connected_at}]",
    )
    runtime_control = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Runtime control mailbox for cross-process run control: "
            "{stop_requested, pause_requested, reply_nonce, reply_ack_nonce, reply_text}"
        ),
    )
    pending_question = models.TextField(blank=True, help_text="Question agent is waiting user to answer")
    final_report = models.TextField(blank=True, help_text="Final structured report from full agent")
    report_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Canonical structured report payload rendered by the agent run UI.",
    )

    # Multi-agent pipeline fields
    plan_tasks = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "[{id, name, description, status, thought, action, args, result, error,"
            " iterations, orchestrator_decision, started_at, completed_at}]"
        ),
    )
    orchestrator_log = models.JSONField(
        default=list,
        blank=True,
        help_text="[{role, content, timestamp}] — orchestrator LLM conversation history",
    )

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["project", "-started_at"], name="servers_run_project_ae7621_idx"),
            models.Index(fields=["agent", "-started_at"]),
            models.Index(fields=["server", "-started_at"]),
            models.Index(fields=["status", "-started_at"]),
        ]

    def __str__(self):
        agent_name = self.agent.name if self.agent_id and self.agent else "Agent"
        server_name = self.server.name if self.server_id and self.server else "no-server"
        return f"{agent_name} on {server_name} [{self.status}]"

    def save(self, *args, **kwargs):
        if not self.project_id:
            if self.agent_id:
                self.project_id = self.agent.project_id
            elif self.server_id:
                self.project_id = self.server.project_id
            elif self.user_id:
                from core_ui.projects import active_project_for_user

                self.project = active_project_for_user(self.user)
        return super().save(*args, **kwargs)


class AgentRunArtifact(models.Model):
    """Persisted report artifact generated from a completed agent run."""

    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="artifacts")
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="agent_run_artifacts",
        null=True,
        blank=True,
    )
    artifact_key = models.CharField(max_length=80)
    name = models.CharField(max_length=255)
    artifact_type = models.CharField(max_length=40, default="JSON")
    description = models.TextField(blank=True)
    content_type = models.CharField(max_length=120, default="application/octet-stream")
    content = models.TextField(blank=True)
    size_bytes = models.BigIntegerField(default=0)
    truncated = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["run", "artifact_key"], name="uniq_agent_run_artifact_key"),
        ]
        indexes = [
            models.Index(fields=["run", "artifact_key"]),
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return f"run={self.run_id} {self.name}"


class AgentDispatchControl(models.Model):
    """Named lock rows used for cross-process agent admission decisions."""

    name = models.CharField(max_length=32, unique=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.name


class AgentRunDispatch(models.Model):
    """Queue item for the dedicated agent execution plane."""

    KIND_LAUNCH = "launch"
    KIND_PLAN_EXECUTION = "plan_execution"
    KIND_CHOICES = [
        (KIND_LAUNCH, "Initial Launch"),
        (KIND_PLAN_EXECUTION, "Plan Execution"),
    ]

    STATUS_QUEUED = "queued"
    STATUS_CLAIMED = "claimed"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CANCELED = "canceled"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_CLAIMED, "Claimed"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELED, "Canceled"),
    ]

    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="dispatches")
    agent = models.ForeignKey(ServerAgent, on_delete=models.CASCADE, related_name="dispatches")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="agent_dispatches")
    dispatch_kind = models.CharField(max_length=30, choices=KIND_CHOICES, default=KIND_LAUNCH)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    server_ids = models.JSONField(default=list, blank=True)
    plan_only = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    queued_at = models.DateTimeField(auto_now_add=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    claimed_by = models.CharField(max_length=120, blank=True)
    attempt_count = models.IntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["queued_at", "id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(max_attempts__gte=1), name="agent_dispatch_max_attempts_gte_1"),
        ]
        indexes = [
            models.Index(fields=["status", "queued_at"]),
            models.Index(fields=["status", "lease_expires_at"], name="agent_dispatch_lease_idx"),
            models.Index(fields=["user", "status", "queued_at"], name="agent_dispatch_user_queue_idx"),
            models.Index(fields=["run", "status", "-queued_at"]),
            models.Index(fields=["agent", "status", "-queued_at"]),
        ]

    def __str__(self):
        return f"run={self.run_id} {self.dispatch_kind} [{self.status}]"


class ImmutableAgentRunEventQuerySet(models.QuerySet):
    """Reject application-level mutation of persisted audit entries."""

    def update(self, **kwargs):
        # Django uses this exact update when a retained event's parent run is deleted.
        if set(kwargs) == {"run"} and kwargs["run"] is None:
            return super().update(**kwargs)
        raise ValidationError("Agent audit events are append-only and cannot be updated.")

    def delete(self):
        raise ValidationError("Agent audit events are append-only and cannot be deleted.")

    def bulk_create(self, objs, **kwargs):
        raise ValidationError("Agent audit events must be appended individually to preserve their hash chain.")

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError("Agent audit events are append-only and cannot be updated.")


class AgentRunEvent(models.Model):
    """Append-only, hash-chained audit event for a long-running agent run."""

    run = models.ForeignKey(AgentRun, on_delete=models.SET_NULL, related_name="events", null=True, blank=True)
    run_ref = models.PositiveBigIntegerField()
    owner_user_ref = models.PositiveBigIntegerField(null=True, blank=True)
    sequence_no = models.PositiveBigIntegerField()
    event_type = models.CharField(max_length=80)
    task_id = models.IntegerField(null=True, blank=True)
    message = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    previous_hash = models.CharField(max_length=64)
    event_hash = models.CharField(max_length=64)
    hash_algorithm = models.CharField(max_length=20, default=HASH_ALGORITHM, editable=False)

    objects = ImmutableAgentRunEventQuerySet.as_manager()

    class Meta:
        ordering = ["run_ref", "sequence_no"]
        base_manager_name = "objects"
        default_manager_name = "objects"
        constraints = [
            models.UniqueConstraint(fields=["run_ref", "sequence_no"], name="agent_event_run_sequence_unique"),
        ]
        indexes = [
            models.Index(fields=["run_ref", "sequence_no"], name="agent_evt_run_seq_idx"),
            models.Index(fields=["event_type", "created_at"], name="agent_evt_type_time_idx"),
            models.Index(fields=["event_hash"], name="agent_evt_hash_idx"),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("Agent audit events are append-only and cannot be updated.")
        if not self.run_id:
            raise ValidationError("A live agent run is required when appending an audit event.")

        with transaction.atomic():
            run = AgentRun.objects.select_for_update().get(pk=self.run_id)
            latest = AgentRunEvent.objects.filter(run_ref=run.pk).order_by("-sequence_no").first()
            self.run_ref = run.pk
            self.owner_user_ref = run.user_id
            if self.owner_user_ref is None and run.agent_id:
                self.owner_user_ref = ServerAgent.objects.values_list("user_id", flat=True).get(pk=run.agent_id)
            self.sequence_no = (latest.sequence_no + 1) if latest else 1
            self.previous_hash = latest.event_hash if latest else GENESIS_HASH
            self.hash_algorithm = HASH_ALGORITHM
            self.created_at = timezone.now()
            self.event_hash = calculate_event_hash(
                run_ref=self.run_ref,
                owner_user_ref=self.owner_user_ref,
                sequence_no=self.sequence_no,
                event_type=self.event_type,
                task_id=self.task_id,
                message=self.message,
                payload=self.payload or {},
                created_at=self.created_at,
                previous_hash=self.previous_hash,
            )
            kwargs.pop("force_insert", None)
            if kwargs.pop("force_update", False) or kwargs.get("update_fields"):
                raise ValidationError("Agent audit events are append-only and cannot be updated.")
            return super().save(*args, force_insert=True, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Agent audit events are append-only and cannot be deleted.")

    def __str__(self):
        return f"run={self.run_ref} seq={self.sequence_no} {self.event_type}"
