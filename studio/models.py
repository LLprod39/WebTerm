"""
Agent Studio Models

Provides the building blocks for a DevOps n8n-like agent automation platform:
- MCPServerPool: reusable MCP server definitions (stdio/sse)
- AgentConfig: standalone agent configuration (system prompt, tools, MCP, servers)
- Pipeline: visual pipeline definition (nodes + edges as JSON)
- PipelineTrigger: webhook/cron/manual/monitoring triggers for pipelines
- PipelineRun: execution record for a pipeline run
- PipelineTemplate: bundled pipeline templates for quick start
"""

import secrets

from django.contrib.auth.models import User
from django.db import models

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

    def __str__(self):
        return f"{self.name} ({self.transport})"

    def to_mcp_config(self) -> dict:
        """Return dict for Claude/Cursor MCP config format."""
        if self.transport == self.TRANSPORT_SSE:
            return {"url": self.url}
        config: dict = {"command": self.command, "args": self.args}
        if self.env:
            config["env"] = self.env
        return config


def _collect_monitoring_filters(data: dict | None) -> dict:
    raw_data = data if isinstance(data, dict) else {}
    nested = raw_data.get("monitoring_filters") if isinstance(raw_data.get("monitoring_filters"), dict) else {}
    filters: dict[str, object] = dict(nested)

    if isinstance(raw_data.get("server_ids"), list):
        server_ids = [int(item) for item in raw_data.get("server_ids", []) if str(item).strip().isdigit()]
        if server_ids:
            filters["server_ids"] = server_ids

    for key in ("severities", "alert_types", "container_names"):
        raw_values = raw_data.get(key)
        if isinstance(raw_values, list):
            values = [str(item or "").strip() for item in raw_values if str(item or "").strip()]
            if values:
                filters[key] = values

    match_text = str(raw_data.get("match_text") or "").strip()
    if match_text:
        filters["match_text"] = match_text

    return filters


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
    mcp_servers = models.ManyToManyField(
        MCPServerPool,
        blank=True,
        related_name="agent_configs",
    )
    skill_slugs = models.JSONField(
        default=list,
        blank=True,
        help_text='List of attached skill slugs, e.g. ["keycloak-safety", "keycloak-prod-profile"]',
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

    def __str__(self):
        return self.name

    def to_dict(self) -> dict:
        from .skill_policy import compile_skill_policies
        from .skill_registry import resolve_skills

        skills, skill_errors = resolve_skills(self.skill_slugs or [])
        _, policy_errors = compile_skill_policies(skills)
        return {
            "id": self.pk,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "system_prompt": self.system_prompt,
            "instructions": self.instructions,
            "model": self.model,
            "max_iterations": self.max_iterations,
            "allowed_tools": self.allowed_tools,
            "mcp_servers": list(self.mcp_servers.filter(owner=self.owner).values("id", "name", "transport")),
            "skill_slugs": list(self.skill_slugs or []),
            "skills": [skill.to_summary_dict() for skill in skills],
            "skill_errors": [*skill_errors, *policy_errors],
            "server_scope": list(self.server_scope.filter(user=self.owner).values("id", "name")),
        }


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

    def __str__(self):
        return self.name

    def get_last_run(self):
        live_run = self.runs.filter(
            status__in=[
                PipelineRun.STATUS_PENDING,
                PipelineRun.STATUS_RUNNING,
            ]
        ).order_by("-created_at", "-id").first()
        if live_run:
            return live_run
        return self.runs.order_by("-created_at", "-id").first()

    def get_trigger_summary(self) -> dict:
        triggers = list(self.triggers.all())
        active_triggers = [trigger for trigger in triggers if trigger.is_active]
        last_triggered_at = None
        for trigger in active_triggers:
            if trigger.last_triggered_at and (last_triggered_at is None or trigger.last_triggered_at > last_triggered_at):
                last_triggered_at = trigger.last_triggered_at
        return {
            "active_total": len(active_triggers),
            "active_manual": sum(1 for trigger in active_triggers if trigger.trigger_type == PipelineTrigger.TYPE_MANUAL),
            "active_webhook": sum(1 for trigger in active_triggers if trigger.trigger_type == PipelineTrigger.TYPE_WEBHOOK),
            "active_schedule": sum(1 for trigger in active_triggers if trigger.trigger_type == PipelineTrigger.TYPE_SCHEDULE),
            "active_monitoring": sum(
                1 for trigger in active_triggers if trigger.trigger_type == PipelineTrigger.TYPE_MONITORING
            ),
            "last_triggered_at": last_triggered_at.isoformat() if last_triggered_at else None,
        }

    def to_list_dict(self) -> dict:
        last_run = self.get_last_run()
        return {
            "id": self.pk,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "tags": self.tags,
            "is_shared": self.is_shared,
            "is_template": self.is_template,
            "graph_version": self.graph_version,
            "node_count": len(self.nodes) if self.nodes else 0,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "trigger_summary": self.get_trigger_summary(),
            "last_run": {
                "id": last_run.pk,
                "status": last_run.status,
                "started_at": last_run.started_at.isoformat() if last_run.started_at else None,
                "finished_at": last_run.finished_at.isoformat() if last_run.finished_at else None,
            }
            if last_run
            else None,
        }

    def to_detail_dict(self) -> dict:
        d = self.to_list_dict()
        d["nodes"] = self.nodes
        d["edges"] = self.edges
        d["triggers"] = [t.to_dict() for t in self.triggers.order_by("created_at", "id")]
        return d

    def sync_triggers_from_nodes(self):
        trigger_type_map = {
            "trigger/manual": PipelineTrigger.TYPE_MANUAL,
            "trigger/webhook": PipelineTrigger.TYPE_WEBHOOK,
            "trigger/schedule": PipelineTrigger.TYPE_SCHEDULE,
            "trigger/monitoring": PipelineTrigger.TYPE_MONITORING,
        }
        keep_node_ids: set[str] = set()

        for node in self.nodes or []:
            node_type = str(node.get("type") or "")
            trigger_type = trigger_type_map.get(node_type)
            node_id = str(node.get("id") or "").strip()
            if not trigger_type or not node_id:
                continue

            data = node.get("data") or {}
            payload_map = data.get("webhook_payload_map")
            if not isinstance(payload_map, dict):
                payload_map = {}
            monitoring_filters = _collect_monitoring_filters(data)

            defaults = {
                "name": (str(data.get("label") or "").strip() or node_id),
                "trigger_type": trigger_type,
                "is_active": bool(data.get("is_active", True)),
                "cron_expression": str(data.get("cron_expression") or "").strip(),
                "webhook_payload_map": payload_map,
                "monitoring_filters": monitoring_filters,
            }
            existing = list(self.triggers.filter(node_id=node_id).order_by("id"))
            if existing:
                trigger = existing[0]
                created = False
                if len(existing) > 1:
                    self.triggers.filter(node_id=node_id).exclude(pk=trigger.pk).delete()
            else:
                trigger = PipelineTrigger.objects.create(
                    pipeline=self,
                    node_id=node_id,
                    **defaults,
                )
                created = True

            if not created:
                changed = False
                for field, value in defaults.items():
                    if getattr(trigger, field) != value:
                        setattr(trigger, field, value)
                        changed = True
                if changed:
                    trigger.save()

            keep_node_ids.add(node_id)

        if keep_node_ids:
            self.triggers.exclude(node_id__in=keep_node_ids).delete()
        else:
            self.triggers.all().delete()


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
        help_text='Map incoming payload fields to pipeline context vars',
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
            "Alert filter for monitoring triggers: "
            "{server_ids, severities, alert_types, container_names, match_text}"
        ),
    )
    last_triggered_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["pipeline", "trigger_type"]
        verbose_name = "Pipeline Trigger"
        verbose_name_plural = "Pipeline Triggers"

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
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_STOPPED, "Stopped"),
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

    def __str__(self):
        return f"{self.pipeline.name} run #{self.pk} [{self.status}]"

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> dict:
        trigger = getattr(self, "trigger", None)
        return {
            "id": self.pk,
            "pipeline_id": self.pipeline_id,
            "pipeline_name": self.pipeline.name,
            "status": self.status,
            "node_states": self.node_states,
            "nodes_snapshot": self.nodes_snapshot,
            "context": self.context,
            "summary": self.summary,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "created_at": self.created_at.isoformat(),
            "triggered_by": self.triggered_by.username if self.triggered_by else None,
            "trigger_id": trigger.pk if trigger else None,
            "entry_node_id": self.entry_node_id,
            "trigger_type": trigger.trigger_type if trigger else "manual",
            "trigger_name": trigger.name if trigger else "",
            "trigger_node_id": trigger.node_id if trigger else self.entry_node_id,
        }


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
        return {
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "category": self.category,
            "tags": self.tags,
            "node_count": len(self.nodes),
            "graph_version": self.graph_version,
        }

    def instantiate_for_user(self, user: User) -> "Pipeline":
        """Create a new Pipeline for the given user from this template."""
        nodes = list(self.nodes)
        edges = list(self.edges)

        if self.slug == "server-update-approval":
            from servers.models import Server
            server = Server.objects.filter(user=user).filter(name="backup-01").first()
            if not server:
                server = Server.objects.filter(user=user).order_by("name").first()
            if server:
                server_ids = [server.id]
                for node in nodes:
                    nid = node.get("id")
                    if nid in ("n2", "n8", "n10"):
                        data = dict(node.get("data") or {})
                        data["server_ids"] = server_ids
                        node = dict(node)
                        node["data"] = data
                        for i, n in enumerate(nodes):
                            if n.get("id") == nid:
                                nodes[i] = node
                                break

        pipeline = Pipeline.objects.create(
            name=self.name,
            description=self.description,
            icon=self.icon,
            tags=self.tags,
            nodes=nodes,
            edges=edges,
            graph_version=self.graph_version or CURRENT_PIPELINE_GRAPH_VERSION,
            owner=user,
        )
        pipeline.sync_triggers_from_nodes()
        return pipeline


class StudioSkillAccess(models.Model):
    """Ownership and sharing metadata for filesystem-backed Studio skills."""

    slug = models.SlugField(max_length=100, unique=True)
    owner = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_studio_skills",
    )
    is_shared = models.BooleanField(default=False, help_text="Visible to all users with skill access")
    shared_with = models.ManyToManyField(
        User,
        blank=True,
        related_name="shared_studio_skills",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slug"]
        verbose_name = "Studio Skill Access"
        verbose_name_plural = "Studio Skill Access"

    def __str__(self):
        return self.slug
