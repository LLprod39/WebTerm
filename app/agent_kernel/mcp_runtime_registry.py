"""
Global registry for MCPRuntimeProvider implementations.

Feature apps register concrete MCP runtime adapters here so server agents can
load and execute MCP tools through an app-level port.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent_kernel.domain.specs import MCPRuntimeProvider

_registry: MCPRuntimeProvider | None = None


def register(provider: MCPRuntimeProvider) -> None:
    global _registry
    _registry = provider


def get() -> MCPRuntimeProvider | None:
    return _registry
