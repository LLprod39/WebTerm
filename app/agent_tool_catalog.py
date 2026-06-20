from __future__ import annotations

from typing import Protocol


class AgentToolCatalogProvider(Protocol):
    def list_agent_tool_names(self) -> tuple[str, ...]: ...


_agent_tool_catalog_provider: AgentToolCatalogProvider | None = None


def register_agent_tool_catalog_provider(provider: AgentToolCatalogProvider | None) -> None:
    global _agent_tool_catalog_provider
    _agent_tool_catalog_provider = provider


def list_agent_tool_names() -> tuple[str, ...]:
    if _agent_tool_catalog_provider is None:
        return ()
    return tuple(sorted(_agent_tool_catalog_provider.list_agent_tool_names()))
