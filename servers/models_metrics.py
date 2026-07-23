"""Extended metric time series, rollups, and TLS certificate inventory."""

from django.db import models

from servers.models_inventory import Server


class ServerMetricSample(models.Model):
    """One collector-v2 snapshot of extended server metrics (raw series)."""

    SOURCE_QUICK = "quick"
    SOURCE_DEEP = "deep"
    SOURCE_CHOICES = [
        (SOURCE_QUICK, "Quick check"),
        (SOURCE_DEEP, "Deep check"),
    ]

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="metric_samples")
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default=SOURCE_QUICK)

    cpu_percent = models.FloatField(null=True, blank=True)
    cpu_iowait_percent = models.FloatField(null=True, blank=True)
    cpu_steal_percent = models.FloatField(null=True, blank=True)
    cpu_count = models.IntegerField(null=True, blank=True)
    load_1m = models.FloatField(null=True, blank=True)
    load_5m = models.FloatField(null=True, blank=True)
    load_15m = models.FloatField(null=True, blank=True)

    memory_total_mb = models.IntegerField(null=True, blank=True)
    memory_available_mb = models.IntegerField(null=True, blank=True)
    memory_percent = models.FloatField(null=True, blank=True)
    swap_total_mb = models.IntegerField(null=True, blank=True)
    swap_used_mb = models.IntegerField(null=True, blank=True)
    swap_percent = models.FloatField(null=True, blank=True)

    disk_mounts = models.JSONField(default=list, blank=True)

    net_rx_bps = models.FloatField(null=True, blank=True)
    net_tx_bps = models.FloatField(null=True, blank=True)
    net_errors_per_sec = models.FloatField(null=True, blank=True)
    tcp_retrans_per_sec = models.FloatField(null=True, blank=True)
    tcp_established = models.IntegerField(null=True, blank=True)

    fd_used = models.BigIntegerField(null=True, blank=True)
    fd_max = models.BigIntegerField(null=True, blank=True)
    process_count = models.IntegerField(null=True, blank=True)
    zombie_count = models.IntegerField(null=True, blank=True)
    top_processes = models.JSONField(default=dict, blank=True)

    journal_err_10m = models.IntegerField(null=True, blank=True)
    journal_warn_10m = models.IntegerField(null=True, blank=True)
    reboot_required = models.BooleanField(null=True, blank=True)
    ntp_synchronized = models.BooleanField(null=True, blank=True)
    uptime_seconds = models.BigIntegerField(null=True, blank=True)

    extra = models.JSONField(default=dict, blank=True)
    collected_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-collected_at"]
        indexes = [
            models.Index(fields=["server", "-collected_at"]),
        ]

    def __str__(self):
        return f"{self.server.name}: sample @ {self.collected_at}"


class ServerMetricRollup(models.Model):
    """Downsampled aggregate of one metric over an hour/day bucket."""

    GRANULARITY_HOUR = "hour"
    GRANULARITY_DAY = "day"
    GRANULARITY_CHOICES = [
        (GRANULARITY_HOUR, "Hour"),
        (GRANULARITY_DAY, "Day"),
    ]

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="metric_rollups")
    metric_key = models.CharField(max_length=120)
    granularity = models.CharField(max_length=10, choices=GRANULARITY_CHOICES)
    bucket_start = models.DateTimeField()

    value_min = models.FloatField()
    value_avg = models.FloatField()
    value_max = models.FloatField()
    value_last = models.FloatField()
    sample_count = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-bucket_start"]
        constraints = [
            models.UniqueConstraint(
                fields=["server", "metric_key", "granularity", "bucket_start"],
                name="uniq_server_metric_rollup_bucket",
            ),
        ]
        indexes = [
            models.Index(fields=["server", "metric_key", "granularity", "-bucket_start"]),
            models.Index(fields=["granularity", "bucket_start"]),
        ]

    def __str__(self):
        return f"{self.server.name}: {self.metric_key} [{self.granularity}] @ {self.bucket_start}"


class ServerPrediction(models.Model):
    """Persisted deterministic forecast for one (server, kind, target) triple.

    One row per triple: it re-activates on recurrence and resolves when the
    trend disappears, so alerting/watcher layers get stable identities.
    """

    STATUS_ACTIVE = "active"
    STATUS_RESOLVED = "resolved"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_RESOLVED, "Resolved"),
    ]

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="predictions")
    kind = models.CharField(max_length=30)
    target = models.CharField(max_length=150)
    severity = models.CharField(max_length=10, default="info")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)

    eta_days = models.FloatField(null=True, blank=True)
    predicted_for = models.DateTimeField(null=True, blank=True)
    current_value = models.FloatField(null=True, blank=True)
    threshold = models.FloatField(null=True, blank=True)
    unit = models.CharField(max_length=20, blank=True)
    slope_per_day = models.FloatField(null=True, blank=True)
    confidence = models.FloatField(default=0.5)
    evidence = models.JSONField(default=dict, blank=True)

    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_seen_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["server", "kind", "target"],
                name="uniq_server_prediction_kind_target",
            ),
        ]
        indexes = [
            models.Index(fields=["server", "status", "-last_seen_at"]),
            models.Index(fields=["status", "severity", "-last_seen_at"]),
        ]

    def __str__(self):
        return f"{self.server.name}: {self.kind} {self.target} [{self.status}]"


class ServerAiInsight(models.Model):
    """LLM analysis verdict for one physical endpoint or the whole fleet."""

    KIND_SERVER = "server"
    KIND_FLEET = "fleet"
    KIND_CHOICES = [
        (KIND_SERVER, "Server"),
        (KIND_FLEET, "Fleet"),
    ]

    VERDICT_LOW = "low"
    VERDICT_MEDIUM = "medium"
    VERDICT_HIGH = "high"
    VERDICT_CRITICAL = "critical"
    VERDICT_UNKNOWN = "unknown"
    VERDICT_CHOICES = [
        (VERDICT_LOW, "Low risk"),
        (VERDICT_MEDIUM, "Medium risk"),
        (VERDICT_HIGH, "High risk"),
        (VERDICT_CRITICAL, "Critical risk"),
        (VERDICT_UNKNOWN, "Unknown"),
    ]

    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_SERVER)
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="ai_insights", null=True, blank=True)
    endpoint_key = models.CharField(max_length=270, blank=True, db_index=True)

    verdict = models.CharField(max_length=10, choices=VERDICT_CHOICES, default=VERDICT_UNKNOWN)
    content = models.TextField(blank=True)
    context_fingerprint = models.CharField(max_length=64, blank=True)
    model_used = models.CharField(max_length=100, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["kind", "endpoint_key", "-created_at"]),
            models.Index(fields=["server", "-created_at"]),
        ]

    def __str__(self):
        target = self.endpoint_key or "fleet"
        return f"AI insight [{self.verdict}] {target} @ {self.created_at}"


class ServerCertificate(models.Model):
    """TLS certificate observed on a server's listening port."""

    SOURCE_LISTEN = "listen"
    SOURCE_CHOICES = [
        (SOURCE_LISTEN, "Listening port"),
    ]

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="certificates")
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_LISTEN)
    port = models.IntegerField()
    endpoint = models.CharField(max_length=255, blank=True)

    subject = models.TextField(blank=True)
    issuer = models.TextField(blank=True)
    serial = models.CharField(max_length=128, blank=True)
    fingerprint_sha256 = models.CharField(max_length=128, blank=True)
    not_before = models.DateTimeField(null=True, blank=True)
    not_after = models.DateTimeField(null=True, blank=True)
    sans = models.JSONField(default=list, blank=True)

    previous_fingerprint = models.CharField(max_length=128, blank=True)
    fingerprint_changed_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["not_after"]
        constraints = [
            models.UniqueConstraint(
                fields=["server", "source", "port"],
                name="uniq_server_certificate_source_port",
            ),
        ]
        indexes = [
            models.Index(fields=["server", "is_active"]),
            models.Index(fields=["is_active", "not_after"]),
        ]

    def __str__(self):
        return (
            f"{self.server.name}:{self.port} exp {self.not_after:%Y-%m-%d}"
            if self.not_after
            else f"{self.server.name}:{self.port}"
        )
