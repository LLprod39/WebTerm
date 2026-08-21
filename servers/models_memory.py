"""Layered server memory models."""

import hashlib

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
    metadata = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=180, blank=True, db_index=True)
    payload_hash = models.CharField(max_length=64, blank=True, db_index=True)
    importance_hint = models.FloatField(default=0.5)
    redaction_report = models.JSONField(default=dict, blank=True)
    redaction_hashes = models.JSONField(default=list, blank=True)
    compacted_episode = models.ForeignKey(
        "ServerMemoryEpisode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="compacted_events",
    )
    compacted_at = models.DateTimeField(null=True, blank=True)
    compaction_version = models.PositiveIntegerField(default=1)
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
            models.Index(
                fields=["server", "event_type", "-created_at"],
                name="mem_evt_server_type_time_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["server", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_server_memory_event_idempotency_key",
            ),
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
    LAYER_CANDIDATE = "candidate"
    LAYER_ARCHIVE = "archive"
    LAYER_CHOICES = [
        (LAYER_CANONICAL, "Canonical"),
        (LAYER_CANDIDATE, "Candidate"),
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
    content_hash = models.CharField(max_length=64, blank=True, default="")
    generation_log = models.ForeignKey(
        "ServerMemoryGenerationLog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="snapshots",
    )
    asset = models.ForeignKey(
        "ServerMemoryAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="snapshots",
    )
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
        constraints = [
            models.UniqueConstraint(
                fields=["server", "memory_key"],
                condition=models.Q(is_active=True),
                name="uniq_active_server_memory_snapshot",
            ),
        ]

    def __str__(self):
        return f"{self.server.name}: {self.memory_key} v{self.version}"

    def save(self, *args, **kwargs):
        """Hash content on future writes without fabricating hashes for legacy rows."""
        self.content_hash = hashlib.sha256((self.content or "").encode("utf-8")).hexdigest()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "content" in update_fields:
            kwargs["update_fields"] = set(update_fields) | {"content_hash"}
        return super().save(*args, **kwargs)


class ServerMemoryGenerationLog(models.Model):
    """Redacted provenance for one LLM-assisted memory generation attempt."""

    KIND_DISTILLATION = "distillation"
    KIND_PATTERN_ENHANCEMENT = "pattern_enhancement"
    KIND_CHOICES = [
        (KIND_DISTILLATION, "Memory Distillation"),
        (KIND_PATTERN_ENHANCEMENT, "Pattern Enhancement"),
    ]

    STATUS_STARTED = "started"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_FALLBACK = "fallback"
    STATUS_CHOICES = [
        (STATUS_STARTED, "Started"),
        (STATUS_SUCCEEDED, "Succeeded"),
        (STATUS_FAILED, "Failed"),
        (STATUS_FALLBACK, "Heuristic Fallback"),
    ]

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="memory_generation_logs")
    invocation = models.ForeignKey(
        "core_ui.AIProviderInvocation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="server_memory_generation_logs",
    )
    generation_kind = models.CharField(max_length=32, choices=KIND_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_STARTED)
    model_alias = models.CharField(max_length=80, blank=True, default="")
    prompt_template_key = models.CharField(max_length=80, blank=True, default="")
    prompt_template_version = models.CharField(max_length=32, blank=True, default="")
    prompt_sha256 = models.CharField(max_length=64, db_index=True)
    output_sha256 = models.CharField(max_length=64, blank=True, default="", db_index=True)
    prompt_redacted_ref = models.CharField(max_length=255, blank=True, default="")
    output_redacted_ref = models.CharField(max_length=255, blank=True, default="")
    error_code = models.CharField(max_length=80, blank=True, default="")
    error_redacted_ref = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["server", "generation_kind", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.server.name}: {self.generation_kind}/{self.status}"


class ServerMemoryRevalidation(models.Model):
    """Queue of memory items that need validation after staleness or conflicts."""

    STATUS_OPEN = "open"
    STATUS_SCHEDULED = "scheduled"
    STATUS_VERIFIED_TRUE = "verified_true"
    STATUS_VERIFIED_FALSE = "verified_false"
    STATUS_RESOLVED = "resolved"
    STATUS_SUPERSEDED = "superseded"
    STATUS_EXPIRED_UNVERIFIED = "expired_unverified"
    STATUS_IGNORED_BY_HUMAN = "ignored_by_human"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_VERIFIED_TRUE, "Verified True"),
        (STATUS_VERIFIED_FALSE, "Verified False"),
        (STATUS_RESOLVED, "Resolved (legacy)"),
        (STATUS_SUPERSEDED, "Superseded"),
        (STATUS_EXPIRED_UNVERIFIED, "Expired Unverified"),
        (STATUS_IGNORED_BY_HUMAN, "Ignored by Human"),
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
    decided_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="server_memory_revalidation_decisions",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["status", "-updated_at"]
        indexes = [
            models.Index(fields=["server", "status", "-updated_at"]),
            models.Index(fields=["server", "memory_key", "status"]),
        ]

    def __str__(self):
        return f"{self.server.name}: {self.title}"
