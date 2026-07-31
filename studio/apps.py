import contextlib

from django.apps import AppConfig


class StudioConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "studio"
    verbose_name = "Agent Studio"

    def ready(self) -> None:
        from app.agent_kernel import mcp_runtime_registry, skill_promotion_registry, skill_provider_registry
        from app.prometheus_registry import register_prometheus_provider
        from app.runtime_limits import register_pipeline_run_limit_provider
        from app.smoke_seed_provider import register_smoke_pipeline_seed_provider
        from studio import signals as _signals  # noqa: F401
        from studio.assistant_action_registry import register_assistant_actions
        from studio.mcp.mcp_runtime_adapter import StudioMCPRuntimeProvider
        from studio.prometheus_metrics import studio_prometheus_lines
        from studio.runtime_limit_provider import DjangoPipelineRunLimitProvider
        from studio.skill_adapter import StudioSkillProvider
        from studio.skill_promotion import StudioSkillPromotionGateway
        from studio.smoke_seed_provider import DjangoSmokePipelineSeedProvider

        mcp_runtime_registry.register(StudioMCPRuntimeProvider())
        register_pipeline_run_limit_provider(DjangoPipelineRunLimitProvider())
        register_prometheus_provider("studio", studio_prometheus_lines)
        skill_provider_registry.register(StudioSkillProvider())
        skill_promotion_registry.register(StudioSkillPromotionGateway())
        register_smoke_pipeline_seed_provider(DjangoSmokePipelineSeedProvider())
        register_assistant_actions()

        from app.monitoring_events import server_alert_opened
        from studio.trigger_dispatch import launch_monitoring_triggers_for_alert_id

        def _on_server_alert_opened(sender, alert_id: int, **kwargs: object) -> None:
            with contextlib.suppress(Exception):
                launch_monitoring_triggers_for_alert_id(alert_id)

        server_alert_opened.connect(_on_server_alert_opened, weak=False)
