from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

MCP_MUTATING_TOOL_RE = re.compile(
    r"(^|[_\-.])(add|apply|assign|create|delete|disable|enable|grant|patch|remove|restart|revoke|set|start|stop|update|write)([_\-.]|$)",
    re.IGNORECASE,
)
READ_ONLY_MCP_TOOL_RE = re.compile(
    r"(^|[_\-.])(current|describe|find|get|list|lookup|read|search|status|verify)([_\-.]|$)",
    re.IGNORECASE,
)
AGENT_MUTATING_TOOLS = frozenset({"ssh_execute", "send_ctrl_c"})


@dataclass(frozen=True, slots=True)
class DynamicAgentPolicy:
    command: str
    reasons: tuple[str, ...]
    risky_tools: tuple[str, ...]


def _is_nonblank(value: Any) -> bool:
    return bool(str(value or "").strip())


def _non_empty_sequence(value: Any) -> bool:
    return isinstance(value, (list, tuple, set)) and any(str(item or "").strip() for item in value)


def _enabled_agent_tools(data: dict[str, Any]) -> set[str] | None:
    raw_tools = data.get("allowed_tools")
    if raw_tools is None:
        raw_tools = data.get("tools")
    if raw_tools is None:
        raw_tools = data.get("enabled_tools")
    if raw_tools is None:
        tools_config = data.get("tools_config")
        if isinstance(tools_config, dict):
            return {str(name).strip() for name, enabled in tools_config.items() if enabled and str(name).strip()}
        return None
    if isinstance(raw_tools, dict):
        return {str(name).strip() for name, enabled in raw_tools.items() if enabled and str(name).strip()}
    if isinstance(raw_tools, (list, tuple, set)):
        return {str(name).strip() for name in raw_tools if str(name).strip()}
    return None


def _mutating_mcp_agent_tools(tool_names: set[str]) -> list[str]:
    mutating = []
    for tool_name in tool_names:
        if not tool_name.startswith("mcp_"):
            continue
        if MCP_MUTATING_TOOL_RE.search(tool_name) or not READ_ONLY_MCP_TOOL_RE.search(tool_name):
            mutating.append(tool_name)
    return sorted(mutating)


def classify_dynamic_agent_policy(data: dict[str, Any]) -> DynamicAgentPolicy | None:
    enabled_tools = _enabled_agent_tools(data)
    permission_mode = str(data.get("permission_mode") or "").strip().upper()
    read_only_mode = permission_mode in {"PLAN", "READ_ONLY"}
    uses_default_tool_set = enabled_tools is None
    uses_server_scope = _non_empty_sequence(data.get("server_ids")) or _is_nonblank(data.get("server_id"))
    uses_mcp_scope = _non_empty_sequence(data.get("mcp_server_ids")) or _is_nonblank(data.get("mcp_server_id"))
    uses_saved_config = _is_nonblank(data.get("agent_config_id"))
    mutating_tools = sorted((enabled_tools or set()) & AGENT_MUTATING_TOOLS)
    if read_only_mode:
        mutating_tools = [tool_name for tool_name in mutating_tools if tool_name != "ssh_execute"]
    mutating_mcp_tools = _mutating_mcp_agent_tools(enabled_tools or set())

    reasons: list[str] = []
    if uses_saved_config:
        reasons.append("Saved agent config may include servers, MCP tools, or broad tool access.")
    if uses_mcp_scope and uses_default_tool_set:
        reasons.append(
            "Agent has MCP server access with default tools; tool mutation semantics are runtime-discovered."
        )
    if mutating_mcp_tools:
        reasons.append("Agent can use mutating or unknown MCP tools: " + ", ".join(mutating_mcp_tools[:8]) + ".")
    if mutating_tools:
        reasons.append("Agent can use mutating runtime tools: " + ", ".join(mutating_tools) + ".")
    if uses_default_tool_set and uses_server_scope:
        reasons.append("Agent uses default tool set with server access, which includes SSH execution.")
        mutating_tools.append("send_ctrl_c" if read_only_mode else "ssh_execute")
    if data.get("requires_approval"):
        reasons.append("Agent node metadata requires human approval.")
    if not reasons:
        return None

    command_parts = []
    if uses_saved_config:
        command_parts.append(f"agent_config:{str(data.get('agent_config_id')).strip()}")
    if uses_mcp_scope:
        command_parts.append("mcp_scope")
    risky_tools = sorted(set(mutating_tools + mutating_mcp_tools))
    if risky_tools:
        command_parts.append("tools:" + ",".join(risky_tools[:8]))
    return DynamicAgentPolicy(
        command=" ".join(command_parts) or "dynamic_agent",
        reasons=tuple(reasons),
        risky_tools=tuple(risky_tools),
    )
