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
    disconnected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-connected_at"]

    def __str__(self):
        return f"{self.server.name} - {self.status}"


class ServerCommandHistory(models.Model):
    """History of commands executed on servers"""

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="command_history")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
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
