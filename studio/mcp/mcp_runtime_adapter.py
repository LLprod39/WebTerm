from __future__ import annotations

from typing import Any

from studio.mcp.mcp_tool_runtime import build_mcp_tools_description, execute_bound_mcp_tool, load_mcp_tool_bindings


class StudioMCPRuntimeProvider:
    """Adapts studio MCP runtime functions to the app-level provider protocol."""

    async def load_mcp_tool_bindings(self, mcp_servers: list[Any]) -> tuple[dict[str, Any], list[str]]:
        return await load_mcp_tool_bindings(mcp_servers)

    def build_mcp_tools_description(self, bindings: dict[str, Any]) -> str:
        return build_mcp_tools_description(bindings)

    async def execute_bound_mcp_tool(
        self,
        bindings: dict[str, Any],
        action_name: str,
        args: dict[str, Any],
    ) -> str:
        return await execute_bound_mcp_tool(bindings, action_name, args)
