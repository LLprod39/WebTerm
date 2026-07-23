from django.apps import AppConfig


class ServersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "servers"

    def ready(self):
        from app.admin_metrics_provider import register_admin_server_metrics_provider
        from app.agent_kernel import operator_provider_registry, ops_runtime_registry
        from app.agent_tool_catalog import register_agent_tool_catalog_provider
        from app.chat_server_provider import register_chat_server_provider
        from app.command_history_provider import register_command_history_provider
        from app.pipeline_agent_provider import register_pipeline_agent_provider
        from app.pipeline_memory_provider import register_pipeline_memory_provider
        from app.pipeline_ssh_provider import register_pipeline_ssh_provider
        from app.runtime_limits import register_agent_run_limit_provider, register_terminal_session_limit_provider
        from app.server_alert_provider import register_server_alert_provider
        from app.smoke_seed_provider import register_smoke_server_seed_provider
        from app.studio_server_access import register_studio_server_access_provider
        from app.tools.server_secret_provider import (
            register_server_auth_secret_provider,
            register_server_sudo_secret_provider,
        )
        from app.tools.server_tool_gateway import register_server_tool_gateway
        from app.tools.ssh_host_key_provider import register_ssh_host_key_provider
        from servers.admin_metrics_provider import DjangoAdminServerMetricsProvider
        from servers.agent_tool_catalog_provider import DjangoAgentToolCatalogProvider
        from servers.assistant_actions import register_assistant_actions
        from servers.chat_server_provider import DjangoChatServerProvider
        from servers.command_history_provider import DjangoCommandHistoryProvider
        from servers.operator_provider import ServersOperatorProvider
        from servers.ops_runtime_adapter import ServersOpsRuntimeProvider
        from servers.pipeline_agent_provider import DjangoPipelineAgentProvider
        from servers.pipeline_memory_provider import DjangoPipelineMemoryProvider
        from servers.pipeline_ssh_provider import DjangoPipelineSshProvider
        from servers.runtime_limit_provider import DjangoAgentRunLimitProvider, DjangoTerminalSessionLimitProvider
        from servers.secret_utils import get_server_auth_secret, get_server_sudo_secret
        from servers.server_alert_provider import DjangoServerAlertProvider
        from servers.smoke_seed_provider import DjangoSmokeServerSeedProvider
        from servers.ssh_host_keys import ensure_server_known_hosts, parse_host_port_value, tofu_known_hosts_for_host
        from servers.studio_server_access_provider import DjangoStudioServerAccessProvider
        from servers.tool_gateway import DjangoServerToolGateway

        ops_runtime_registry.register(ServersOpsRuntimeProvider())
        operator_provider_registry.register(ServersOperatorProvider())
        register_admin_server_metrics_provider(DjangoAdminServerMetricsProvider())
        register_agent_tool_catalog_provider(DjangoAgentToolCatalogProvider())
        register_agent_run_limit_provider(DjangoAgentRunLimitProvider())
        register_chat_server_provider(DjangoChatServerProvider())
        register_command_history_provider(DjangoCommandHistoryProvider())
        register_pipeline_agent_provider(DjangoPipelineAgentProvider())
        register_pipeline_memory_provider(DjangoPipelineMemoryProvider())
        register_pipeline_ssh_provider(DjangoPipelineSshProvider())
        register_server_alert_provider(DjangoServerAlertProvider())
        register_smoke_server_seed_provider(DjangoSmokeServerSeedProvider())
        register_studio_server_access_provider(DjangoStudioServerAccessProvider())
        register_terminal_session_limit_provider(DjangoTerminalSessionLimitProvider())
        register_server_tool_gateway(DjangoServerToolGateway())
        register_server_auth_secret_provider(get_server_auth_secret)
        register_server_sudo_secret_provider(get_server_sudo_secret)
        register_ssh_host_key_provider(
            ensure_server_known_hosts=ensure_server_known_hosts,
            tofu_known_hosts_for_host=tofu_known_hosts_for_host,
            parse_host_port_value=parse_host_port_value,
        )
        register_assistant_actions()
        from servers.operator_mutate_tools import register_operator_mutate_tools
        from servers.operator_tools import register_operator_tools

        register_operator_tools()
        register_operator_mutate_tools()

        from . import signals  # noqa: F401
