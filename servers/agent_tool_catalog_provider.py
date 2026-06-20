from __future__ import annotations

from servers.services.tool_catalog import list_agent_tool_names


class DjangoAgentToolCatalogProvider:
    def list_agent_tool_names(self) -> tuple[str, ...]:
        return list_agent_tool_names()
