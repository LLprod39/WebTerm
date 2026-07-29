import secrets

from django.contrib.auth.models import User
from django.db import models, transaction

from app.sudo_policy import SUDO_POLICY_CHOICES, SUDO_POLICY_DISABLED

from .approval_models import ApprovalRequest  # noqa: F401
from .model_serializers import (
    agent_config_to_dict,
    pipeline_get_last_run,
    pipeline_get_trigger_summary,
    pipeline_run_to_dict,
    pipeline_template_to_dict,
    pipeline_to_detail_dict,
    pipeline_to_list_dict,
)
from .pipeline_draft_models import PipelineDraftRevision, PipelineDraftSession  # noqa: F401
from .pipeline_model_services import instantiate_template_for_user, sync_pipeline_triggers_from_nodes
from .skill_access_models import StudioSkillAccess  # noqa: F401

CURRENT_PIPELINE_GRAPH_VERSION = 2


class MCPServerPool(models.Model):
    """
    Reusable MCP server configuration stored per user.
    Can be attached to any AgentConfig.
    """

    TRANSPORT_STDIO = "stdio"
    TRANSPORT_SSE = "sse"
    TRANSPORT_CHOICES = [
        (TRANSPORT_STDIO, "stdio (subprocess)"),
        (TRANSPORT_SSE, "SSE (HTTP stream)"),
    ]

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    transport = models.CharField(max_length=10, choices=TRANSPORT_CHOICES, default=TRANSPORT_STDIO)

    # stdio: command + args
    command = models.CharField(max_length=500, blank=True, help_text='e.g. "npx" or "python"')
    args = models.JSONField(
        default=list,
        blank=True,
        help_text='e.g. ["-y", "@modelcontextprotocol/server-github"]',
    )
    env = models.JSONField(
        default=dict,
        blank=True,
        help_text='Environment variables, e.g. {"GITHUB_TOKEN": "..."}',
    )

    # sse: url
    url = models.CharField(max_length=500, blank=True, help_text="SSE endpoint URL")
    headers = models.JSONField(
        default=dict,
        blank=True,
        help_text='Extra HTTP headers for SSE transport, e.g. {"X-Api-Version": "1"}. '
        "For auth, store MCP_BEARER_TOKEN / MCP_AUTHORIZATION as a managed secret instead.",
    )

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mcp_pool")
    is_shared = models.BooleanField(default=False, help_text="Visible to all users")
    shared_with = models.ManyToManyField(
        User,
        blank=True,
        related_name="shared_studio_mcp_servers",
        help_text="Specific users who can view and use this MCP server",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Last test result
    last_test_ok = models.BooleanField(null=True, blank=True)
    last_test_at = models.DateTimeField(null=True, blank=True)
    last_test_error = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "MCP Server"
        verbose_name_plural = "MCP Servers"
        indexes = [
            models.Index(fields=["owner", "name"]),
            models.Index(fields=["is_shared"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.transport})"

    def to_mcp_config(self) -> dict:
        """Return dict for Claude/Cursor MCP config format."""
        if self.transport == self.TRANSPORT_SSE:
            config: dict = {"url": self.url}
            if self.headers:
                config["headers"] = self.headers
            return config
        config = {"command": self.command, "args": self.args}
        if self.env:
            config["env"] = self.env
        return config


class AgentConfig(models.Model):
    """
    Standalone agent configuration — can be used as a node inside a Pipeline.
    Independent from servers.ServerAgent (which is server-bound).
    """

    TOOL_CHOICES = [
        ("ssh_execute", "SSH Execute"),
        ("read_console", "Read Console"),
        ("send_ctrl_c", "Send Ctrl+C"),
        ("open_connection", "Open Connection"),
        ("close_connection", "Close Connection"),
        ("wait_for_output", "Wait for Output"),
        ("report", "Report"),
        ("ask_user", "Ask User"),
        ("analyze_output", "Analyze Output"),
    ]

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=10, blank=True, default="🤖")

    system_prompt = models.TextField(
        blank=True,
        help_text="System prompt injected before the agent goal",
    )
    instructions = models.TextField(
        blank=True,
        help_text="Additional instructions / rules for this agent",
    )

    model = models.CharField(
        max_length=100,
        default="gemini-2.0-flash-exp",
        help_text="LLM model identifier",
    )
    max_iterations = models.PositiveIntegerField(default=10)

    allowed_tools = models.JSONField(
        default=list,
        blank=True,
        help_text='List of enabled tool names, e.g. ["ssh_execute", "report"]',
    )
    sudo_policy = models.CharField(
        max_length=20,
        choices=SUDO_POLICY_CHOICES,
        default=SUDO_POLICY_DISABLED,
        help_text="Controlled sudo policy for SSH tools used by this agent.",
    )
    mcp_servers = models.ManyToManyField(
        MCPServerPool,
        blank=True,
        related_name="agent_configs",
    )
    skill_slugs = models.JSONField(
        default=list,
        blank=True,
        help_text='List of attached skill slugs, e.g. ["kubernetes-safety"]',
    )

    # Servers this agent is allowed to operate on (empty = all accessible servers)
    server_scope = models.ManyToManyField(
        "servers.Server",
        blank=True,
        related_name="agent_configs",
    )

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="agent_configs")
    is_shared = models.BooleanField(default=False)
    shared_with = models.ManyToManyField(
        User,
        blank=True,
        related_name="shared_studio_agent_configs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Agent Config"
        verbose_name_plural = "Agent Configs"
        indexes = [
            models.Index(fields=["owner", "-updated_at"]),
        ]

    def __str__(self):
        return self.name

    def to_dict(self) -> dict:
        return agent_config_to_dict(self)


class Pipeline(models.Model):
    """
    Visual pipeline definition — stores nodes and edges as JSON (React Flow format).
    """

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=10, blank=True, default="⚡")
    tags = models.JSONField(default=list, blank=True)

    # React Flow graph
    nodes = models.JSONField(
        default=list,
        help_text="List of React Flow nodes: [{id, type, position, data}]",
    )
    edges = models.JSONField(
        default=list,
        help_text="List of React Flow edges: [{id, source, target, ...}]",
    )
    graph_version = models.PositiveSmallIntegerField(
        default=CURRENT_PIPELINE_GRAPH_VERSION,
        help_text="Pipeline graph contract version.",
    )

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pipelines")
    is_shared = models.BooleanField(default=False)
    shared_with = models.ManyToManyField(
        User,
        blank=True,
        related_name="shared_studio_pipelines",
    )
    is_template = models.BooleanField(default=False, help_text="Bundled template, not user-created")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Pipeline"
        verbose_name_plural = "Pipelines"
        indexes = [
            models.Index(fields=["owner", "-updated_at"]),
            models.Index(fields=["is_shared"]),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        touches_nodes = self._state.adding or update_fields is None or "nodes" in set(update_fields)
        if not touches_nodes:
            return super().save(*args, **kwargs)

        from studio.pipeline_secrets import persist_pipeline_secrets, secure_pipeline_nodes_for_storage

        with transaction.atomic():
            if self.pk and not self._state.adding:
                type(self).objects.select_for_update().filter(pk=self.pk).exists()
            safe_nodes, next_secrets = secure_pipeline_nodes_for_storage(self.pk, self.nodes)
            self.nodes = safe_nodes
            result = super().save(*args, **kwargs)
            persist_pipeline_secrets(self.pk, next_secrets)
        return result

    def get_last_run(self):
        return pipeline_get_last_run(self)

    def get_trigger_summary(self) -> dict:
        return pipeline_get_trigger_summary(self)

    def to_list_dict(self) -> dict:
        return pipeline_to_list_dict(self)

    def to_detail_dict(self) -> dict:
        return pipeline_to_detail_dict(self)

    def sync_triggers_from_nodes(self):
        sync_pipeline_triggers_from_nodes(self)


class PipelineTrigger(models.Model):
    """
    Trigger configuration for a pipeline — webhook, cron, monitoring alert, or manual.
    """

    TYPE_MANUAL = "manual"
    TYPE_WEBHOOK = "webhook"
    TYPE_SCHEDULE = "schedule"
    TYPE_MONITORING = "monitoring"
    TYPE_CHOICES = [
        (TYPE_MANUAL, "Manual"),
        (TYPE_WEBHOOK, "Webhook"),
        (TYPE_SCHEDULE, "Schedule (cron)"),
        (TYPE_MONITORING, "Monitoring alert"),
    ]

    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name="triggers")
    node_id = models.CharField(max_length=100, blank=True, default="")
    name = models.CharField(max_length=100, blank=True, default="")
    trigger_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_MANUAL)
    is_active = models.BooleanField(default=True)

    # Webhook
    webhook_token = models.CharField(max_length=64, unique=True, blank=True)
    webhook_payload_map = models.JSONField(
        default=dict,
        blank=True,
        help_text="Map incoming payload fields to pipeline context vars",
    )

    # Schedule (cron)
    cron_expression = models.CharField(
        max_length=100,
        blank=True,
        help_text='Standard cron: "*/5 * * * *"',
    )
    monitoring_filters = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Alert filter for monitoring triggers: {server_ids, severities, alert_types, container_names, match_text}"
        ),
    )
    last_triggered_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["pipeline", "trigger_type"]
        verbose_name = "Pipeline Trigger"
        verbose_name_plural = "Pipeline Triggers"
        indexes = [
            models.Index(fields=["pipeline", "trigger_type"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.pipeline.name} / {self.get_trigger_type_display()}"

    def save(self, *args, **kwargs):
        if not self.webhook_token:
            self.webhook_token = secrets.token_hex(32)
        super().save(*args, **kwargs)

    def to_dict(self) -> dict:
        return {
            "id": self.pk,
            "pipeline_id": self.pipeline_id,
            "node_id": self.node_id,
            "name": self.name,
            "trigger_type": self.trigger_type,
            "is_active": self.is_active,
            "webhook_token": self.webhook_token,
            "webhook_url": f"/api/studio/triggers/{self.webhook_token}/receive/",
            "cron_expression": self.cron_expression,
            "webhook_payload_map": self.webhook_payload_map,
            "monitoring_filters": self.monitoring_filters,
            "last_triggered_at": self.last_triggered_at.isoformat() if self.last_triggered_at else None,
        }


class PipelineRun(models.Model):
    """
    Single execution of a Pipeline.
    node_states tracks status and output per node.
    """

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_STOPPED = "stopped"
    STATUS_HIBERNATING = "hibernating"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_STOPPED, "Stopped"),
        (STATUS_HIBERNATING, "Hibernating"),
    ]

    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name="runs")
    triggered_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pipeline_runs",
    )
    trigger = models.ForeignKey(
        PipelineTrigger,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="runs",
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    # Snapshot of pipeline graph at run time
    nodes_snapshot = models.JSONField(default=list)
    edges_snapshot = models.JSONField(default=list)
    entry_node_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Selected trigger node id used as the run entry point.",
    )

    # Per-node execution state
    # {node_id: {status, output, error, agent_run_id, started_at, finished_at}}
    node_states = models.JSONField(default=dict)

    # Context passed to the run (from trigger payload or manual input)
    context = models.JSONField(default=dict, blank=True)
    trigger_data = models.JSONField(default=dict, blank=True)
    runtime_control = models.JSONField(
        default=dict,
        blank=True,
        help_text="Runtime control mailbox for cross-process pipeline control: {stop_requested}",
    )
    routing_state = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Ephemeral in-process routing state for V2 pipeline runs: "
            "{activated_nodes, completed_nodes, pending_merges, queued_nodes, entry_node_id}"
        ),
    )

    # Final summary output
    summary = models.TextField(blank=True)
    error = models.TextField(blank=True)

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Pipeline Run"
        verbose_name_plural = "Pipeline Runs"
        indexes = [
            models.Index(fields=["pipeline", "status"]),
            models.Index(fields=["pipeline", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.pipeline.name} run #{self.pk} [{self.status}]"

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> dict:
        return pipeline_run_to_dict(self)


class PipelineTemplate(models.Model):
    """
    Bundled pipeline template for quick start.
    Loaded from studio/fixtures/templates.json or via management command.
    """

    slug = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=10, blank=True, default="📦")
    category = models.CharField(max_length=50, blank=True, default="DevOps")
    tags = models.JSONField(default=list, blank=True)

    # Full pipeline definition (same structure as Pipeline.nodes/edges)
    nodes = models.JSONField(default=list)
    edges = models.JSONField(default=list)
    graph_version = models.PositiveSmallIntegerField(
        default=CURRENT_PIPELINE_GRAPH_VERSION,
        help_text="Template graph contract version.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "Pipeline Template"
        verbose_name_plural = "Pipeline Templates"

    def __str__(self):
        return f"[{self.category}] {self.name}"

    def to_dict(self) -> dict:
        return pipeline_template_to_dict(self)

    def instantiate_for_user(self, user: User) -> "Pipeline":
        """Create a new Pipeline for the given user from this template."""
        return instantiate_template_for_user(self, user)
