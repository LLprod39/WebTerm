"""Server rules and knowledge models."""

from django.contrib.auth.models import User
from django.db import models

from servers.models_groups import ServerGroup
from servers.models_inventory import Server


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
        indexes = [
            models.Index(fields=["group", "-updated_at"]),
        ]

    def __str__(self):
        return f"{self.group.name}: {self.title[:50]}"

