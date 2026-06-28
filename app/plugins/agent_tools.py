from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from app.plugins.catalog import project_plugin_catalog

EnabledPluginIdsProvider = Callable[[], set[str]]
PluginAgentToolExecutionProvider = Callable[[dict[str, Any]], dict[str, Any]]

_enabled_plugin_ids_provider: EnabledPluginIdsProvider | None = None
_plugin_agent_tool_execution_provider: PluginAgentToolExecutionProvider | None = None


def register_enabled_plugin_ids_provider(provider: EnabledPluginIdsProvider | None) -> None:
    global _enabled_plugin_ids_provider
    _enabled_plugin_ids_provider = provider


def register_plugin_agent_tool_execution_provider(provider: PluginAgentToolExecutionProvider | None) -> None:
    global _plugin_agent_tool_execution_provider
    _plugin_agent_tool_execution_provider = provider


def enabled_plugin_ids_for_agent_tools() -> set[str]:
    if _enabled_plugin_ids_provider is None:
        return set()
    try:
        return set(_enabled_plugin_ids_provider())
    except Exception:
        return set()


def active_agent_tools(enabled_plugin_ids: set[str] | None = None) -> list[dict]:
    enabled = enabled_plugin_ids_for_agent_tools() if enabled_plugin_ids is None else enabled_plugin_ids
    tools: list[dict] = []
    for plugin in project_plugin_catalog(enabled):
        for tool in plugin.get("surfaces", {}).get("agent_tools", []):
            tools.append({"plugin_id": plugin["id"], **tool})
    return tools


def plugin_agent_tool_specs(enabled_plugin_ids: set[str] | None = None) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    for tool in active_agent_tools(enabled_plugin_ids):
        name = str(tool.get("name") or tool.get("id") or "").strip()
        tool_spec = tool.get("tool_spec")
        if not name or not isinstance(tool_spec, dict):
            continue
        specs[name] = {
            "plugin_id": str(tool.get("plugin_id") or ""),
            "plugin_tool_id": str(tool.get("id") or name),
            "description": str(tool.get("description") or tool.get("title") or name),
            "params": deepcopy(tool.get("params") if isinstance(tool.get("params"), dict) else {}),
            "tool_spec": deepcopy(tool_spec),
            "required_permission": str(tool.get("required_permission") or ""),
            "executor_ref": str(tool.get("executor_ref") or ""),
        }
    return specs


def execute_plugin_agent_tool(payload: dict[str, Any]) -> dict[str, Any]:
    if _plugin_agent_tool_execution_provider is None:
        return {"success": False, "result": "No plugin agent tool execution provider is registered."}
    return _plugin_agent_tool_execution_provider(payload)
