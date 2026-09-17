"""Telegram hub: multi-bot polling, account linking, and AI assistant bridge."""

from django.apps import AppConfig


class TelegramHubConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "telegram_hub"
    verbose_name = "Telegram Hub"

    def ready(self) -> None:
        # Register signal handlers for user deactivation revoke.
        from telegram_hub import signals  # noqa: F401
