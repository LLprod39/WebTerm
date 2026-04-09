"""
Server Management Models
"""

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class ServerGroup(models.Model):
    """Groups for organizing servers"""

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=7, default="#3b82f6")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="server_groups")
    created_at = models.DateTimeField(auto_now_add=True)
    tags = models.ManyToManyField("ServerGroupTag", blank=True, related_name="groups")

    # Group-level rules
    rules = models.TextField(blank=True, help_text="Правила для группы серверов: специфичные политики, ограничения")
    forbidden_commands = models.JSONField(default=list, blank=True, help_text="Запрещённые команды для этой группы")
    environment_vars = models.JSONField(default=dict, blank=True, help_text="Переменные окружения для группы")

    class Meta:
        unique_together = ["name", "user"]
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_context_for_ai(self) -> str:
        """Get formatted context for AI agents"""
        parts = []

        if self.description:
            parts.append(f"Группа: {self.name}\n{self.description}")

        if self.rules:
            parts.append(f"Правила группы:\n{self.rules}")

        if self.forbidden_commands:
            cmds = ", ".join(self.forbidden_commands)
            parts.append(f"⛔ Запрещено в группе: {cmds}")

        return "\n".join(parts) if parts else ""


class ServerGroupTag(models.Model):
    """Tags for server groups"""

    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7, default="#6b7280")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="server_group_tags")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["name", "user"]
        ordering = ["name"]

    def __str__(self):
        return self.name


class ServerGroupMember(models.Model):
    """Memberships with roles"""

    ROLE_CHOICES = [
        ("owner", "Owner"),
        ("admin", "Admin"),
        ("member", "Member"),
        ("viewer", "Viewer"),
    ]
    group = models.ForeignKey(ServerGroup, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="server_group_memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="member")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["group", "user"]

    def __str__(self):
        return f"{self.group.name} - {self.user.username} ({self.role})"


class ServerGroupSubscription(models.Model):
    """Subscriptions for notifications or favorites"""

    KIND_CHOICES = [
        ("follow", "Follow"),
        ("favorite", "Favorite"),
    ]
    group = models.ForeignKey(ServerGroup, on_delete=models.CASCADE, related_name="subscriptions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="server_group_subscriptions")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default="follow")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["group", "user", "kind"]


class ServerGroupPermission(models.Model):
    """Optional granular permissions overrides"""

    group = models.ForeignKey(ServerGroup, on_delete=models.CASCADE, related_name="permissions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="server_group_permissions")
    can_view = models.BooleanField(default=True)
    can_execute = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_manage_members = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["group", "user"]


class Server(models.Model):
    """Server configuration"""

    SERVER_TYPE_CHOICES = [
        ("ssh", "SSH (Linux)"),
        ("rdp", "RDP (Windows)"),
    ]

    AUTH_METHOD_CHOICES = [
        ("password", "Password"),
        ("key", "SSH Key"),
        ("key_password", "SSH Key + Password"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="servers")
    group = models.ForeignKey(ServerGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name="servers")

    # Server info
    name = models.CharField(max_length=200)  # Display name
    server_type = models.CharField(
        max_length=10,
        choices=SERVER_TYPE_CHOICES,
        default="ssh",
        help_text="SSH для Linux, RDP для Windows",
    )
    host = models.CharField(max_length=255)
    port = models.IntegerField(default=22)
    username = models.CharField(max_length=100)

    # Authentication
    auth_method = models.CharField(max_length=20, choices=AUTH_METHOD_CHOICES, default="password")
    encrypted_password = models.TextField(blank=True)  # Encrypted password if using password auth
    key_path = models.CharField(max_length=500, blank=True)  # Path to SSH key
    salt = models.BinaryField(null=True, blank=True)  # For password encryption

    # Additional info
    tags = models.CharField(max_length=500, blank=True)  # Comma-separated tags
    notes = models.TextField(blank=True)
    corporate_context = models.TextField(
        blank=True, help_text="Корпоративные требования: прокси, VPN, env переменные, условия доступа"
    )
    is_active = models.BooleanField(default=True)

    # Network Context для корпоративных сетей
    network_config = models.JSONField(
        default=dict, blank=True, help_text="Контекст корпоративной сети: прокси, VPN, firewall, env variables"
    )
    trusted_host_keys = models.JSONField(
        default=list,
        blank=True,
        help_text="Доверенные SSH host keys для strict host verification (TOFU).",
    )

    # Helper fields для UI (заполняются автоматически из network_config)
    has_proxy = models.BooleanField(default=False, help_text="Сервер работает через прокси")
    requires_vpn = models.BooleanField(default=False, help_text="Требуется VPN для подключения")
    behind_firewall = models.BooleanField(default=True, help_text="Сервер за корпоративным файрволлом")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_connected = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "-updated_at"]),
            models.Index(fields=["group", "user"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.host}:{self.port})"

    def is_rdp(self) -> bool:
        return (self.server_type or "ssh") == "rdp"

    def is_ssh(self) -> bool:
        return not self.is_rdp()

    def get_rdp_port(self) -> int:
        if self.is_rdp():
            try:
                return int(self.port or 3389)
            except Exception:
                return 3389
        try:
            return int(self.port or 22)
        except Exception:
            return 22

    def get_connection_string(self) -> str:
        """Get SSH connection string"""
        return f"{self.username}@{self.host}:{self.port}"

    def get_network_context_summary(self) -> str:
        """Получить описание сетевого контекста для AI"""
        parts = []

        # Сначала из corporate_context (приоритет - текстовые заметки)
        if self.corporate_context:
            parts.append(self.corporate_context.strip())

        # Дополнительно из network_config если есть
        if self.network_config:
            nc = self.network_config

            # Прокси
            if nc.get("proxy", {}).get("http_proxy"):
                parts.append(f"Прокси: {nc['proxy']['http_proxy']}")

            # VPN
            if nc.get("vpn", {}).get("required"):
                vpn_type = nc["vpn"].get("type", "VPN")
                parts.append(f"VPN: {vpn_type}")

            # Bastion
            if nc.get("network", {}).get("bastion_host"):
                parts.append(f"Bastion: {nc['network']['bastion_host']}")

            # Firewall
            if nc.get("firewall", {}).get("inbound_ports"):
                ports = nc["firewall"]["inbound_ports"]
                parts.append(f"Порты: {','.join(map(str, ports))}")

        return "\n".join(parts) if parts else "Стандартная сеть"

    def update_network_flags(self):
        """Обновить helper flags на основе network_config"""
        if not self.network_config:
            return

        nc = self.network_config

        # Proxy
        self.has_proxy = bool(nc.get("proxy", {}).get("http_proxy"))

        # VPN
        self.requires_vpn = bool(nc.get("vpn", {}).get("required"))

        # Firewall (по умолчанию True для корпоративных сетей)
        if nc.get("firewall"):
            self.behind_firewall = True


class ServerShare(models.Model):
    """Explicit server sharing between users."""

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="shares")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="server_shares")
    shared_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="server_shares_sent",
    )
    share_context = models.BooleanField(
        default=True,
        help_text="Передавать ли AI-контекст сервера (corporate/network/group/global rules) пользователю с доступом",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Если задано, доступ автоматически истекает в это время",
    )
    is_revoked = models.BooleanField(default=False)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["server", "user"]
        indexes = [
            models.Index(fields=["user", "is_revoked"]),
            models.Index(fields=["server", "is_revoked"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"{self.server.name} -> {self.user.username}"

    def is_active(self) -> bool:
        if self.is_revoked:
            return False
        return not (self.expires_at and timezone.now() >= self.expires_at)


class ServerConnection(models.Model):
    """Active server connections"""

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="connections")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="server_connections")
    connection_id = models.CharField(max_length=100, unique=True)  # Internal connection ID
    status = models.CharField(max_length=20, default="connected")  # connected, disconnected, error
    connected_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    disconnected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-connected_at"]
        indexes = [
            models.Index(fields=["user", "status", "-last_seen_at"]),
            models.Index(fields=["status", "-last_seen_at"]),
        ]

    def __str__(self):
        return f"{self.server.name} - {self.status}"


class ServerCommandHistory(models.Model):
    """History of commands executed on servers"""

    ACTOR_HUMAN = "human"
    ACTOR_AGENT = "agent"
    ACTOR_PIPELINE = "pipeline"
    ACTOR_SYSTEM = "system"
    ACTOR_CHOICES = [
        (ACTOR_HUMAN, "Human"),
        (ACTOR_AGENT, "Agent"),
        (ACTOR_PIPELINE, "Pipeline"),
        (ACTOR_SYSTEM, "System"),
    ]

    SOURCE_TERMINAL = "terminal"
    SOURCE_AGENT = "agent"
    SOURCE_PIPELINE = "pipeline"
    SOURCE_API = "api"
    SOURCE_SYSTEM = "system"
    SOURCE_CHOICES = [
        (SOURCE_TERMINAL, "Terminal"),
        (SOURCE_AGENT, "Agent"),
        (SOURCE_PIPELINE, "Pipeline"),
        (SOURCE_API, "API"),
        (SOURCE_SYSTEM, "System"),
    ]

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="command_history")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    actor_kind = models.CharField(max_length=20, choices=ACTOR_CHOICES, default=ACTOR_HUMAN)
    source_kind = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_TERMINAL)
    session_id = models.CharField(max_length=120, blank=True)
    cwd = models.CharField(max_length=500, blank=True)
    command = models.TextField()
    output = models.TextField(blank=True)
    exit_code = models.IntegerField(null=True, blank=True)
    executed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-executed_at"]
        indexes = [
            models.Index(fields=["server", "-executed_at"]),
        ]

    def __str__(self):
        return f"{self.server.name}: {self.command[:50]}"


class GlobalServerRules(models.Model):
    """
    Global rules for all servers belonging to a user.
    These rules apply to every server unless overridden.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="global_server_rules")
    rules = models.TextField(
        blank=True,
        help_text="Общие правила для всех серверов: политики безопасности, запрещённые команды, корпоративные требования",
    )
    forbidden_commands = models.JSONField(
        default=list, blank=True, help_text='Список запрещённых команд/паттернов: ["rm -rf /", "shutdown", ...]'
    )
    required_checks = models.JSONField(
        default=list, blank=True, help_text='Обязательные проверки перед выполнением: ["df -h", "free -m", ...]'
    )
    environment_vars = models.JSONField(
        default=dict, blank=True, help_text="Глобальные переменные окружения для всех серверов"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Global Server Rules"
        verbose_name_plural = "Global Server Rules"

    def __str__(self):
        return f"Global rules for {self.user.username}"

    def get_context_for_ai(self) -> str:
        """Get formatted context for AI agents"""
        parts = []

        if self.rules:
            parts.append(f"=== ГЛОБАЛЬНЫЕ ПРАВИЛА ===\n{self.rules}")

        if self.forbidden_commands:
            cmds = ", ".join(self.forbidden_commands)
            parts.append(f"⛔ Запрещённые команды: {cmds}")

        if self.required_checks:
            checks = ", ".join(self.required_checks)
            parts.append(f"✅ Обязательные проверки: {checks}")

        return "\n\n".join(parts) if parts else ""


class ServerKnowledge(models.Model):
    """
    AI-generated and manual knowledge about a specific server.
    Accumulated knowledge helps AI work more effectively.
    """

    CATEGORY_CHOICES = [
        ("system", "Система"),
        ("services", "Сервисы"),
        ("network", "Сеть"),
        ("security", "Безопасность"),
        ("performance", "Производительность"),
        ("storage", "Хранилище"),
        ("packages", "Пакеты/ПО"),
        ("config", "Конфигурация"),
        ("issues", "Известные проблемы"),
        ("solutions", "Решения"),
        ("other", "Другое"),
    ]

    SOURCE_CHOICES = [
        ("manual", "Ручной ввод"),
        ("ai_auto", "AI автоматически"),
        ("ai_task", "AI после задачи"),
    ]

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="knowledge")
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default="other")
    title = models.CharField(max_length=200)
    content = models.TextField(help_text="Содержимое заметки/знания")
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="manual")
    confidence = models.FloatField(default=1.0, help_text="Уверенность в актуальности (0.0-1.0)")
    is_active = models.BooleanField(default=True)
    task_id = models.IntegerField(null=True, blank=True, help_text="ID задачи, после которой создано знание")
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verified_at = models.DateTimeField(null=True, blank=True, help_text="Когда последний раз проверялось")

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Server Knowledge"
        verbose_name_plural = "Server Knowledge"
        indexes = [
            models.Index(fields=["server", "category", "-updated_at"]),
        ]

    def __str__(self):
        return f"{self.server.name}: {self.title}"


class ServerHealthCheck(models.Model):
    """Periodic health check results for a server."""

    STATUS_HEALTHY = "healthy"
    STATUS_WARNING = "warning"
    STATUS_CRITICAL = "critical"
    STATUS_UNREACHABLE = "unreachable"
    STATUS_CHOICES = [
        (STATUS_HEALTHY, "Healthy"),
        (STATUS_WARNING, "Warning"),
        (STATUS_CRITICAL, "Critical"),
        (STATUS_UNREACHABLE, "Unreachable"),
    ]

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="health_checks")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_HEALTHY)

    cpu_percent = models.FloatField(null=True, blank=True)
    memory_percent = models.FloatField(null=True, blank=True)
    memory_used_mb = models.IntegerField(null=True, blank=True)
    memory_total_mb = models.IntegerField(null=True, blank=True)
    disk_percent = models.FloatField(null=True, blank=True)
    disk_used_gb = models.FloatField(null=True, blank=True)
    disk_total_gb = models.FloatField(null=True, blank=True)
    load_1m = models.FloatField(null=True, blank=True)
    load_5m = models.FloatField(null=True, blank=True)
    load_15m = models.FloatField(null=True, blank=True)
    uptime_seconds = models.BigIntegerField(null=True, blank=True)
    process_count = models.IntegerField(null=True, blank=True)

    response_time_ms = models.IntegerField(null=True, blank=True)
    is_deep = models.BooleanField(default=False)
    raw_output = models.JSONField(default=dict, blank=True)
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-checked_at"]
        indexes = [
            models.Index(fields=["server", "-checked_at"]),
            models.Index(fields=["status", "-checked_at"]),
        ]

    def __str__(self):
        return f"{self.server.name}: {self.status} @ {self.checked_at}"


class ServerAlert(models.Model):
    """Alerts generated by server health monitoring."""

    TYPE_CPU = "cpu"
    TYPE_MEMORY = "memory"
    TYPE_DISK = "disk"
    TYPE_SERVICE = "service"
    TYPE_LOG_ERROR = "log_error"
    TYPE_UNREACHABLE = "unreachable"
    TYPE_CHOICES = [
        (TYPE_CPU, "High CPU"),
        (TYPE_MEMORY, "High Memory"),
        (TYPE_DISK, "High Disk"),
        (TYPE_SERVICE, "Failed Service"),
        (TYPE_LOG_ERROR, "Log Error"),
        (TYPE_UNREACHABLE, "Unreachable"),
    ]

    SEVERITY_INFO = "info"
    SEVERITY_WARNING = "warning"
    SEVERITY_CRITICAL = "critical"
    SEVERITY_CHOICES = [
        (SEVERITY_INFO, "Info"),
        (SEVERITY_WARNING, "Warning"),
        (SEVERITY_CRITICAL, "Critical"),
    ]

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="alerts")
    alert_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default=SEVERITY_WARNING)
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="resolved_alerts"
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["server", "-created_at"]),
            models.Index(fields=["is_resolved", "-created_at"]),
            models.Index(fields=["severity", "-created_at"]),
        ]

    def __str__(self):
        return f"[{self.severity}] {self.server.name}: {self.title}"


class ServerWatcherDraft(models.Model):
    """Persisted watcher suggestion for operator review."""

    STATUS_OPEN = "open"
    STATUS_ACKNOWLEDGED = "acknowledged"
    STATUS_RESOLVED = "resolved"
    STATUS_SUPPRESSED = "suppressed"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_ACKNOWLEDGED, "Acknowledged"),
        (STATUS_RESOLVED, "Resolved"),
        (STATUS_SUPPRESSED, "Suppressed"),
    ]

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="watcher_drafts")
    fingerprint = models.CharField(max_length=64)
    severity = models.CharField(max_length=20, choices=ServerAlert.SEVERITY_CHOICES, default=ServerAlert.SEVERITY_WARNING)
    recommended_role = models.CharField(max_length=50, default="infra_scout")
    objective = models.TextField()
    reasons = models.JSONField(default=list, blank=True)
    memory_excerpt = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acknowledged_server_watcher_drafts",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_seen_at"]
        unique_together = ["server", "fingerprint"]
        indexes = [
            models.Index(fields=["server", "status", "-last_seen_at"]),
            models.Index(fields=["status", "-last_seen_at"]),
        ]

    def __str__(self):
        return f"{self.server.name}: {self.objective[:80]}"


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
    rdp_semantic_capture_enabled = models.BooleanField(default=False)
    human_habits_capture_enabled = models.BooleanField(default=True)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user_id"]

    def __str__(self):
        return f"Memory policy for {self.user.username}"


class BackgroundWorkerState(models.Model):
    """Lease and heartbeat state for long-running background workers."""

    KIND_MEMORY_DREAMS = "memory_dreams"
    KIND_AGENT_EXECUTION = "agent_execution"
    KIND_WATCHERS = "watchers"
    KIND_CHOICES = [
        (KIND_MEMORY_DREAMS, "Memory Dreams"),
        (KIND_AGENT_EXECUTION, "Agent Execution"),
        (KIND_WATCHERS, "Watchers"),
    ]

    STATUS_IDLE = "idle"
    STATUS_RUNNING = "running"
    STATUS_ERROR = "error"
    STATUS_STOPPED = "stopped"
    STATUS_CHOICES = [
        (STATUS_IDLE, "Idle"),
        (STATUS_RUNNING, "Running"),
        (STATUS_ERROR, "Error"),
        (STATUS_STOPPED, "Stopped"),
    ]

    worker_kind = models.CharField(max_length=40, choices=KIND_CHOICES)
    worker_key = models.CharField(max_length=80, default="default")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_IDLE)
    hostname = models.CharField(max_length=255, blank=True)
    pid = models.IntegerField(null=True, blank=True)
    command = models.CharField(max_length=255, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    last_started_at = models.DateTimeField(null=True, blank=True)
    last_stopped_at = models.DateTimeField(null=True, blank=True)
    last_cycle_started_at = models.DateTimeField(null=True, blank=True)
    last_cycle_finished_at = models.DateTimeField(null=True, blank=True)
    last_summary = models.JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["worker_kind", "worker_key"]
        unique_together = ["worker_kind", "worker_key"]
        indexes = [
            models.Index(fields=["worker_kind", "worker_key"]),
            models.Index(fields=["worker_kind", "status", "-heartbeat_at"]),
        ]

    def __str__(self):
        return f"{self.worker_kind}:{self.worker_key} ({self.status})"


class ServerMemoryEvent(models.Model):
    """L0 inbox event for any interaction or signal related to a server."""

    SOURCE_TERMINAL = "terminal"
    SOURCE_AGENT_RUN = "agent_run"
    SOURCE_AGENT_EVENT = "agent_event"
    SOURCE_MONITORING = "monitoring"
    SOURCE_WATCHER = "watcher"
    SOURCE_PIPELINE = "pipeline"
    SOURCE_RDP = "rdp"
    SOURCE_MANUAL = "manual_knowledge"
    SOURCE_SYSTEM = "system"
    SOURCE_CHOICES = [
        (SOURCE_TERMINAL, "Terminal"),
        (SOURCE_AGENT_RUN, "Agent Run"),
        (SOURCE_AGENT_EVENT, "Agent Event"),
        (SOURCE_MONITORING, "Monitoring"),
        (SOURCE_WATCHER, "Watcher"),
        (SOURCE_PIPELINE, "Pipeline"),
        (SOURCE_RDP, "RDP"),
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
    KIND_RDP = "rdp_session"
    KIND_PIPELINE = "pipeline_operation"
    KIND_MISC = "misc"
    KIND_CHOICES = [
        (KIND_TERMINAL, "Terminal Session"),
        (KIND_AGENT, "Agent Investigation"),
        (KIND_DEPLOY, "Deploy Operation"),
        (KIND_INCIDENT, "Incident"),
        (KIND_MONITORING, "Monitoring Window"),
        (KIND_RDP, "RDP Session"),
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


class ServerGroupKnowledge(models.Model):
    """Knowledge applicable to a group of servers"""

    CATEGORY_CHOICES = [
        ("policy", "Политика"),
        ("access", "Доступ"),
        ("deployment", "Деплой"),
        ("monitoring", "Мониторинг"),
        ("backup", "Бэкапы"),
        ("network", "Сеть"),
        ("other", "Другое"),
    ]

    SOURCE_CHOICES = [
        ("manual", "Ручной ввод"),
        ("ai_auto", "AI автоматически"),
    ]

    group = models.ForeignKey(ServerGroup, on_delete=models.CASCADE, related_name="knowledge")
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default="other")
    title = models.CharField(max_length=200)
    content = models.TextField()
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="manual")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.group.name}: {self.title}"


class ServerAgent(models.Model):
    """User-configurable agent that runs on servers. Supports mini (command list) and full (ReAct) modes."""

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
    name = models.CharField(max_length=200)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default=MODE_MINI)
    agent_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default=TYPE_CUSTOM)
    commands = models.JSONField(default=list, help_text="List of shell commands (mini mode)")
    servers = models.ManyToManyField(Server, blank=True, related_name="agents")
    ai_prompt = models.TextField(blank=True, help_text="Extra instruction for AI analysis")

    # Full-agent fields
    goal = models.TextField(blank=True, help_text="Goal for the agent to achieve (full mode)")
    system_prompt = models.TextField(blank=True, help_text="System prompt defining agent role and style")
    max_iterations = models.IntegerField(default=20, help_text="Max ReAct loop iterations (1-100)")
    allow_multi_server = models.BooleanField(default=False, help_text="Allow simultaneous multi-server connections")
    tools_config = models.JSONField(default=dict, blank=True, help_text="Tool availability overrides")
    stop_conditions = models.JSONField(default=list, blank=True, help_text="Conditions to stop the agent early")
    session_timeout_seconds = models.IntegerField(default=600, help_text="Max session duration in seconds")
    max_connections = models.IntegerField(default=5, help_text="Max simultaneous SSH connections")

    # GAP 7: per-agent memory policy overrides
    memory_policy_override = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Per-agent memory policy overrides. Supported keys: "
            "nearline_event_threshold (int), dream_mode (str: heuristic|nightly_llm|hybrid), "
            "raw_event_retention_days (int), episode_retention_days (int), "
            "rdp_semantic_capture_enabled (bool), human_habits_capture_enabled (bool), "
            "is_enabled (bool). Empty dict = use user-level policy."
        ),
    )

    schedule_minutes = models.IntegerField(default=0, help_text="0 = manual only")
    is_enabled = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "-updated_at"]),
            models.Index(fields=["user", "mode"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_mode_display()} / {self.get_agent_type_display()})"

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
    duration_ms = models.IntegerField(default=0)
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
            models.Index(fields=["agent", "-started_at"]),
            models.Index(fields=["server", "-started_at"]),
            models.Index(fields=["status", "-started_at"]),
        ]

    def __str__(self):
        agent_name = self.agent.name if self.agent_id and self.agent else "Agent"
        server_name = self.server.name if self.server_id and self.server else "no-server"
        return f"{agent_name} on {server_name} [{self.status}]"


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
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["queued_at", "id"]
        indexes = [
            models.Index(fields=["status", "queued_at"]),
            models.Index(fields=["run", "status", "-queued_at"]),
            models.Index(fields=["agent", "status", "-queued_at"]),
        ]

    def __str__(self):
        return f"run={self.run_id} {self.dispatch_kind} [{self.status}]"


class AgentRunEvent(models.Model):
    """Persistent event log for long-running agent runs."""

    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=80)
    task_id = models.IntegerField(null=True, blank=True)
    message = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["run", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
        ]

    def __str__(self):
        return f"run={self.run_id} {self.event_type}"
