"""Core server inventory and terminal-session models."""

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from app.sudo_policy import (
    SUDO_AUTH_MODE_CHOICES,
    SUDO_AUTH_MODE_NONE,
)
from servers.model_helpers import server_network_context_summary, update_server_network_flags
from servers.models_groups import ServerGroup


class Server(models.Model):
    """Server configuration"""

    SERVER_TYPE_CHOICES = [
        ("ssh", "SSH (Linux)"),
    ]

    AUTH_METHOD_CHOICES = [
        ("password", "Password"),
        ("key", "SSH Key"),
        ("key_password", "SSH Key + Password"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="servers")
    project = models.ForeignKey(
        "core_ui.Project",
        on_delete=models.CASCADE,
        related_name="servers",
    )
    group = models.ForeignKey(ServerGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name="servers")

    name = models.CharField(max_length=200)  # Display name
    server_type = models.CharField(
        max_length=10,
        choices=SERVER_TYPE_CHOICES,
        default="ssh",
        help_text="SSH-сервер Linux",
    )
    host = models.CharField(max_length=255)
    port = models.IntegerField(default=22)
    username = models.CharField(max_length=100)

    auth_method = models.CharField(max_length=20, choices=AUTH_METHOD_CHOICES, default="password")
    encrypted_password = models.TextField(
        blank=True,
        editable=False,
        help_text="DEPRECATED: migration-only field; remove in the next schema cleanup migration",
    )
    key_path = models.CharField(max_length=500, blank=True)  # Path to SSH key
    salt = models.BinaryField(
        null=True,
        blank=True,
        editable=False,
        help_text="DEPRECATED: migration-only field; remove in the next schema cleanup migration",
    )
    sudo_auth_mode = models.CharField(
        max_length=32,
        choices=SUDO_AUTH_MODE_CHOICES,
        default=SUDO_AUTH_MODE_NONE,
        help_text="How backend may satisfy sudo prompts for this server.",
    )
    encrypted_sudo_password = models.TextField(
        blank=True,
        editable=False,
        help_text="DEPRECATED: migration-only field; remove in the next schema cleanup migration",
    )
    sudo_salt = models.BinaryField(
        null=True,
        blank=True,
        editable=False,
        help_text="DEPRECATED: migration-only field; remove in the next schema cleanup migration",
    )

    tags = models.CharField(max_length=500, blank=True)  # Comma-separated tags
    notes = models.TextField(blank=True)
    corporate_context = models.TextField(
        blank=True, help_text="Корпоративные требования: прокси, VPN, env переменные, условия доступа"
    )
    is_active = models.BooleanField(default=True)

    network_config = models.JSONField(
        default=dict, blank=True, help_text="Контекст корпоративной сети: прокси, VPN, firewall, env variables"
    )
    trusted_host_keys = models.JSONField(
        default=list,
        blank=True,
        help_text="Доверенные SSH host keys для strict host verification (TOFU).",
    )

    has_proxy = models.BooleanField(default=False, help_text="Сервер работает через прокси")
    requires_vpn = models.BooleanField(default=False, help_text="Требуется VPN для подключения")
    behind_firewall = models.BooleanField(default=True, help_text="Сервер за корпоративным файрволлом")

    ai_read_only = models.BooleanField(
        default=True,
        help_text="AI-агент может только читать состояние сервера, но не выполнять изменяющие команды.",
    )

    detected_os = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Detected distro slug aligned with frontend ServerOsKind",
    )
    detected_os_meta = models.JSONField(
        default=dict,
        blank=True,
        help_text="OS detection metadata: id, version, pretty_name, detected_at, uname, ...",
    )
    detected_os_attempted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last automatic or manual OS detection attempt (cooldown for retries)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_connected = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["project", "-updated_at"], name="servers_ser_project_7c37ec_idx"),
            models.Index(fields=["user", "-updated_at"]),
            models.Index(fields=["group", "user"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.host}:{self.port})"

    def save(self, *args, **kwargs):
        from core_ui.projects import assign_active_project

        assign_active_project(self, user_field="user")
        return super().save(*args, **kwargs)

    def is_ssh(self) -> bool:
        return (self.server_type or "ssh") == "ssh"

    def get_connection_string(self) -> str:
        """Get SSH connection string"""
        return f"{self.username}@{self.host}:{self.port}"

    def get_network_context_summary(self) -> str:
        """Получить описание сетевого контекста для AI"""
        return server_network_context_summary(self.corporate_context, self.network_config)

    def update_network_flags(self):
        """Обновить helper flags на основе network_config"""
        update_server_network_flags(self)


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
    can_connect_terminal = models.BooleanField(default=False)
    can_execute_command = models.BooleanField(default=False)
    can_read_files = models.BooleanField(default=False)
    can_write_files = models.BooleanField(default=False)
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


class TerminalAiChatMessage(models.Model):
    """Persistent turn-by-turn history of the terminal AI assistant (F2-9).

    One row per user/assistant message. Scoped to (user, server) so each
    user has an independent conversation per server. Older messages are
    trimmed by the ``servers.services.terminal_ai.history`` service based
    on the ``memory_ttl_requests`` setting.
    """

    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_CHOICES = [
        (ROLE_USER, "User"),
        (ROLE_ASSISTANT, "Assistant"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="terminal_ai_messages")
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="terminal_ai_messages")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            # Fast "last N messages for (user, server)" lookups.
            models.Index(fields=["user", "server", "-created_at"]),
        ]

    def __str__(self):
        # Short debug repr — truncate long assistant outputs.
        preview = (self.text or "")[:60].replace("\n", " ")
        return f"{self.role}: {preview}"


class CommandSnapshot(models.Model):
    """Pre-execution snapshot of a file captured before AI modifies it.

    When the terminal AI is about to run a file-modifying command
    (``sed -i``, redirect ``>``, ``tee``, etc.) the system reads the
    target file via SSH and stores the content here.  The user can later
    view past snapshots and generate a restore command.
    """

    server = models.ForeignKey(
        "servers.Server",
        on_delete=models.CASCADE,
        related_name="command_snapshots",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="command_snapshots",
    )
    command = models.TextField(help_text="Shell command that triggered the snapshot")
    file_path = models.CharField(max_length=1024, help_text="Absolute path on remote server")
    content = models.TextField(blank=True, help_text="File content before modification")
    content_truncated = models.BooleanField(
        default=False,
        help_text="Stored content was truncated at COMMAND_SNAPSHOT_MAX_CONTENT_BYTES and cannot be restored safely",
    )
    content_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA-256 hex digest for dedup / integrity",
    )
    byte_size = models.PositiveIntegerField(default=0, help_text="Original file size in bytes")
    created_at = models.DateTimeField(auto_now_add=True)
    restored_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["server", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["server", "file_path", "-created_at"]),
        ]

    def __str__(self):
        return f"snapshot server={self.server_id} {self.file_path} @ {self.created_at}"

    def save(self, *args, **kwargs):
        content = str(self.content or "")
        encoded = content.encode("utf-8", errors="replace")
        max_bytes = max(1024, int(getattr(settings, "COMMAND_SNAPSHOT_MAX_CONTENT_BYTES", 1024 * 1024) or 0))
        if len(encoded) > max_bytes:
            self.content = encoded[:max_bytes].decode("utf-8", errors="ignore")
            self.content_truncated = True
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {"content", "content_truncated"}
        return super().save(*args, **kwargs)
