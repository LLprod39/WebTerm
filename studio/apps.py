import contextlib

from django.apps import AppConfig


class StudioConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "studio"
    verbose_name = "Agent Studio"


    def ready(self) -> None:
        from app.agent_kernel import skill_provider_registry
        from studio.skill_adapter import StudioSkillProvider

        skill_provider_registry.register(StudioSkillProvider())

        from servers.signals import server_alert_opened
        from studio.trigger_dispatch import launch_monitoring_triggers_for_alert_id

        def _on_server_alert_opened(sender, alert_id: int, **kwargs: object) -> None:
            with contextlib.suppress(Exception):
                launch_monitoring_triggers_for_alert_id(alert_id)

        server_alert_opened.connect(_on_server_alert_opened, weak=False)
