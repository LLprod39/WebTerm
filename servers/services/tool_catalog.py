from __future__ import annotations

from servers.agents.agent_tools import get_all_agent_tools


def list_agent_tool_names() -> tuple[str, ...]:
    return tuple(sorted(get_all_agent_tools().keys()))
