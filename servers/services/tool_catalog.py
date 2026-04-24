from __future__ import annotations

from servers.agent_tools import AGENT_TOOLS


def list_agent_tool_names() -> tuple[str, ...]:
    return tuple(sorted(AGENT_TOOLS.keys()))
