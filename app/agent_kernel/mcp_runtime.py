from __future__ import annotations

from typing import Any

from app.agent_kernel.domain.specs import MCPRuntimeProvider

MCP_RUNTIME_UNREGISTERED_ERROR = "MCP runtime provider is not registered."


async def load_mcp_bindings(
    provider: MCPRuntimeProvider | None,
    mcp_servers: list[Any],
) -> tuple[dict[str, Any], list[str]]:
    if not mcp_servers:
        return {}, []
    if provider is None:
        return {}, [MCP_RUNTIME_UNREGISTERED_ERROR]
    return await provider.load_mcp_tool_bindings(mcp_servers)


def describe_mcp_bindings(provider: MCPRuntimeProvider | None, bindings: dict[str, Any]) -> str:
    if provider is None:
        return ""
    return provider.build_mcp_tools_description(bindings)


async def execute_mcp_binding(
    provider: MCPRuntimeProvider | None,
    bindings: dict[str, Any],
    action_name: str,
    args: dict[str, Any],
) -> str:
    if provider is None:
        return MCP_RUNTIME_UNREGISTERED_ERROR
    return await provider.execute_bound_mcp_tool(bindings, action_name, args)
