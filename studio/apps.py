import contextlib

from django.apps import AppConfig


class StudioConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "studio"
    verbose_name = "Agent Studio"

    def ready(self) -> None:
        from app.agent_kernel import mcp_runtime_registry, skill_promotion_registry, skill_provider_registry
        from studio.mcp_runtime_adapter import StudioMCPRuntimeProvider
        from studio.skill_adapter import StudioSkillProvider
        from studio.skill_promotion import StudioSkillPromotionGateway

        mcp_runtime_registry.register(StudioMCPRuntimeProvider())
        skill_provider_registry.register(StudioSkillProvider())
        skill_promotion_registry.register(StudioSkillPromotionGateway())

        from servers.signals import server_alert_opened
        from studio.trigger_dispatch import launch_monitoring_triggers_for_alert_id

        def _on_server_alert_opened(sender, alert_id: int, **kwargs: object) -> None:
            with contextlib.suppress(Exception):
                launch_monitoring_triggers_for_alert_id(alert_id)

        server_alert_opened.connect(_on_server_alert_opened, weak=False)
