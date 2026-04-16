"""
DEPRECATED: servers/mcp_tool_runtime.py

This module has been moved to studio/mcp_tool_runtime.py.
This file is kept as a thin re-export for backward compatibility.
Update imports to use studio.mcp_tool_runtime directly.
"""
from studio.mcp_tool_runtime import (  # noqa: F401
    MCPBoundTool,
    build_mcp_tools_description,
    execute_bound_mcp_tool,
    load_mcp_tool_bindings,
)

__all__ = [
    "MCPBoundTool",
    "build_mcp_tools_description",
    "execute_bound_mcp_tool",
    "load_mcp_tool_bindings",
]
