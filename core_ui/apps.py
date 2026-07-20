from django.apps import AppConfig


class CoreUiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core_ui'

    def ready(self):
        from django.db.backends.signals import connection_created

        import core_ui.checks  # noqa: F401
        import core_ui.logging_setup  # noqa: F401
        import core_ui.signals  # noqa: F401
        from app.core.llm_budget import register_llm_budget_status_provider, register_llm_budget_user_provider
        from app.core.llm_secrets import register_llm_api_key_provider
        from app.core.llm_usage_sink import register_llm_usage_context_provider, register_llm_usage_recorder
        from app.tools.activity_provider import register_tool_activity_logger, register_tool_audit_context_provider
        from core_ui.activity import log_user_activity_async
        from core_ui.audit import get_audit_context
        from core_ui.managed_secrets import get_llm_api_key
        from core_ui.services.llm_budget import get_current_llm_budget_user_id, get_user_daily_budget_status
        from core_ui.services.llm_usage import capture_llm_usage_audit_context, record_llm_usage
        from core_ui.services.operator_web_tools import register_operator_web_tools

        core_ui.logging_setup.configure_loguru_sinks()
        register_llm_api_key_provider(get_llm_api_key)
        register_llm_budget_user_provider(get_current_llm_budget_user_id)
        register_llm_budget_status_provider(get_user_daily_budget_status)
        register_llm_usage_context_provider(capture_llm_usage_audit_context)
        register_llm_usage_recorder(record_llm_usage)
        register_tool_audit_context_provider(get_audit_context)
        register_tool_activity_logger(log_user_activity_async)
        register_operator_web_tools()

        def _sqlite_wal_mode(sender, connection, **kwargs):
            if connection.vendor == "sqlite":
                with connection.cursor() as cursor:
                    cursor.execute("PRAGMA journal_mode=WAL")

        connection_created.connect(_sqlite_wal_mode)
