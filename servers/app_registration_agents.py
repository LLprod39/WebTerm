"""Register agent and operator adapters owned by the servers application."""


def register_agent_adapters() -> None:
    from app.agent_kernel import operator_provider_registry, ops_runtime_registry
    from app.agent_tool_catalog import register_agent_tool_catalog_provider
    from app.chat_server_provider import register_chat_server_provider
    from app.command_history_provider import register_command_history_provider
    from app.pipeline_agent_provider import register_pipeline_agent_provider
    from app.pipeline_memory_provider import register_pipeline_memory_provider
    from app.runtime_limits import register_agent_run_limit_provider
    from servers.agents.agent_tool_catalog_provider import DjangoAgentToolCatalogProvider
    from servers.chat_server_provider import DjangoChatServerProvider
    from servers.command_history_provider import DjangoCommandHistoryProvider
    from servers.operator.provider import ServersOperatorProvider
    from servers.ops_runtime_adapter import ServersOpsRuntimeProvider
    from servers.pipeline_agent_provider import DjangoPipelineAgentProvider
    from servers.pipeline_memory_provider import DjangoPipelineMemoryProvider
    from servers.runtime_limit_provider import DjangoAgentRunLimitProvider

    ops_runtime_registry.register(ServersOpsRuntimeProvider())
    operator_provider_registry.register(ServersOperatorProvider())
    register_agent_tool_catalog_provider(DjangoAgentToolCatalogProvider())
    register_agent_run_limit_provider(DjangoAgentRunLimitProvider())
    register_chat_server_provider(DjangoChatServerProvider())
    register_command_history_provider(DjangoCommandHistoryProvider())
    register_pipeline_agent_provider(DjangoPipelineAgentProvider())
    register_pipeline_memory_provider(DjangoPipelineMemoryProvider())

    from servers.operator.mutate_tools import register_operator_mutate_tools
    from servers.operator.tools import register_operator_tools

    register_operator_tools()
    register_operator_mutate_tools()
