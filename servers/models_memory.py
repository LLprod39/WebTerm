"""Layered server memory models."""

from django.contrib.auth.models import User
from django.db import models

from servers.models_inventory import Server


class ServerMemoryPolicy(models.Model):
    """User-level policy controlling layered server memory and dream jobs."""

    DREAM_HEURISTIC = "heuristic"
    DREAM_NIGHTLY_LLM = "nightly_llm"
    DREAM_HYBRID = "hybrid"
    DREAM_MODE_CHOICES = [
        (DREAM_HEURISTIC, "Heuristic"),
        (DREAM_NIGHTLY_LLM, "Nightly LLM"),
        (DREAM_HYBRID, "Hybrid"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="server_memory_policy")
    dream_mode = models.CharField(max_length=20, choices=DREAM_MODE_CHOICES, default=DREAM_HYBRID)
    nightly_model_alias = models.CharField(max_length=50, default="opssummary")
    nearline_event_threshold = models.IntegerField(default=6)
    sleep_start_hour = models.IntegerField(default=1)
    sleep_end_hour = models.IntegerField(default=5)
    raw_event_retention_days = models.IntegerField(default=30)
    episode_retention_days = models.IntegerField(default=90)
    allow_sensitive_raw = models.BooleanField(default=False)
    human_habits_capture_enabled = models.BooleanField(default=True)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user_id"]

    def __str__(self):
        return f"Memory policy for {self.user.username}"

class ServerMemoryEvent(models.Model):
    """L0 inbox event for any interaction or signal related to a server."""

    SOURCE_TERMINAL = "terminal"
    SOURCE_AGENT_RUN = "agent_run"
    SOURCE_AGENT_EVENT = "agent_event"
    SOURCE_MONITORING = "monitoring"
    SOURCE_WATCHER = "watcher"
    SOURCE_PIPELINE = "pipeline"
    SOURCE_MANUAL = "manual_knowledge"
    SOURCE_SYSTEM = "system"
    SOURCE_CHOICES = [
        (SOURCE_TERMINAL, "Terminal"),
        (SOURCE_AGENT_RUN, "Agent Run"),
        (SOURCE_AGENT_EVENT, "Agent Event"),
        (SOURCE_MONITORING, "Monitoring"),
        (SOURCE_WATCHER, "Watcher"),
        (SOURCE_PIPELINE, "Pipeline"),
        (SOURCE_MANUAL, "Manual Knowledge"),
        (SOURCE_SYSTEM, "System"),
    ]

    ACTOR_HUMAN = "human"
    ACTOR_AGENT = "agent"
    ACTOR_WATCHER = "watcher"
    ACTOR_SYSTEM = "system"
    ACTOR_CHOICES = [
        (ACTOR_HUMAN, "Human"),
        (ACTOR_AGENT, "Agent"),
        (ACTOR_WATCHER, "Watcher"),
        (ACTOR_SYSTEM, "System"),
    ]

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="memory_events")
    actor_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="server_memory_events",
    )
    source_kind = models.CharField(max_length=30, choices=SOURCE_CHOICES)
    actor_kind = models.CharField(max_length=20, choices=ACTOR_CHOICES, default=ACTOR_SYSTEM)
    source_ref = models.CharField(max_length=255, blank=True)
    session_id = models.CharField(max_length=120, blank=True)
    event_type = models.CharField(max_length=80)
    raw_text_redacted = models.TextField(blank=True)
    structured_payload = models.JSONField(default=dict, blank=True)
    importance_hint = models.FloatField(default=0.5)
    redaction_report = models.JSONField(default=dict, blank=True)
    redaction_hashes = models.JSONField(default=list, blank=True)
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["server", "-created_at"]),
            models.Index(fields=["server", "source_kind", "-created_at"]),
            models.Index(fields=["server", "session_id", "-created_at"]),
            models.Index(fields=["server", "source_ref", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.server.name}: {self.source_kind}/{self.event_type}"


class ServerMemoryEpisode(models.Model):
    """L1 summary built from multiple memory events."""

    KIND_TERMINAL = "terminal_session"
    KIND_AGENT = "agent_investigation"
    KIND_DEPLOY = "deploy_operation"
    KIND_INCIDENT = "incident"
    KIND_MONITORING = "monitoring_window"
    KIND_PIPELINE = "pipeline_operation"
    KIND_MISC = "misc"
    KIND_CHOICES = [
        (KIND_TERMINAL, "Terminal Session"),
        (KIND_AGENT, "Agent Investigation"),
        (KIND_DEPLOY, "Deploy Operation"),
        (KIND_INCIDENT, "Incident"),
        (KIND_MONITORING, "Monitoring Window"),
        (KIND_PIPELINE, "Pipeline Operation"),
        (KIND_MISC, "Misc"),
    ]

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="memory_episodes")
    episode_kind = models.CharField(max_length=40, choices=KIND_CHOICES, default=KIND_MISC)
    source_kind = models.CharField(max_length=30, blank=True)
    source_ref = models.CharField(max_length=255, blank=True)
    session_id = models.CharField(max_length=120, blank=True)
    title = models.CharField(max_length=255)
    summary = models.TextField()
    event_count = models.IntegerField(default=0)
    importance_score = models.FloatField(default=0.5)
    confidence = models.FloatField(default=0.7)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    first_event_at = models.DateTimeField(null=True, blank=True)
    last_event_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_event_at", "-updated_at"]
        indexes = [
            models.Index(fields=["server", "is_active", "-last_event_at"]),
            models.Index(fields=["server", "episode_kind", "is_active", "-last_event_at"]),
            models.Index(fields=["server", "session_id", "-last_event_at"]),
            models.Index(fields=["server", "source_ref", "-last_event_at"]),
        ]

    def __str__(self):
        return f"{self.server.name}: {self.title}"


class ServerMemorySnapshot(models.Model):
    """L2 canonical or archived memory snapshot used by prompts."""

    LAYER_CANONICAL = "canonical"
    LAYER_ARCHIVE = "archive"
    LAYER_CHOICES = [
        (LAYER_CANONICAL, "Canonical"),
        (LAYER_ARCHIVE, "Archive"),
    ]

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="memory_snapshots")
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="server_memory_snapshots",
    )
    memory_key = models.CharField(max_length=80)
    layer = models.CharField(max_length=20, choices=LAYER_CHOICES, default=LAYER_CANONICAL)
    title = models.CharField(max_length=200)
    content = models.TextField()
    source_kind = models.CharField(max_length=30, blank=True)
    source_ref = models.CharField(max_length=255, blank=True)
    version_group_id = models.CharField(max_length=64)
    version = models.IntegerField(default=1)
    is_active = models.BooleanField(default=True)
    superseded_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="superseded_snapshots",
    )
    importance_score = models.FloatField(default=0.5)
    stability_score = models.FloatField(default=0.5)
    confidence = models.FloatField(default=0.7)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["memory_key", "-version", "-updated_at"]
        indexes = [
            models.Index(fields=["server", "memory_key", "is_active", "-updated_at"]),
            models.Index(fields=["server", "layer", "-updated_at"]),
            models.Index(fields=["server", "version_group_id", "-version"]),
        ]

    def __str__(self):
        return f"{self.server.name}: {self.memory_key} v{self.version}"


class ServerMemoryRevalidation(models.Model):
    """Queue of memory items that need validation after staleness or conflicts."""

    STATUS_OPEN = "open"
    STATUS_RESOLVED = "resolved"
    STATUS_SUPERSEDED = "superseded"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_RESOLVED, "Resolved"),
        (STATUS_SUPERSEDED, "Superseded"),
    ]

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="memory_revalidations")
    source_snapshot = models.ForeignKey(
        ServerMemorySnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revalidation_items",
    )
    memory_key = models.CharField(max_length=80)
    title = models.CharField(max_length=200)
    reason = models.TextField()
    payload = models.JSONField(default=dict, blank=True)
    confidence = models.FloatField(default=0.4)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "-updated_at"]
        indexes = [
            models.Index(fields=["server", "status", "-updated_at"]),
            models.Index(fields=["server", "memory_key", "status"]),
        ]

    def __str__(self):
        return f"{self.server.name}: {self.title}"

