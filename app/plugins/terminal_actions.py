from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from app.plugins.catalog import project_plugin_catalog

EnabledPluginIdsProvider = Callable[[], set[str]]
PluginTerminalActionExecutionProvider = Callable[[dict[str, Any]], dict[str, Any]]

_enabled_plugin_ids_provider: EnabledPluginIdsProvider | None = None
_plugin_terminal_action_execution_provider: PluginTerminalActionExecutionProvider | None = None


def register_enabled_plugin_ids_provider(provider: EnabledPluginIdsProvider | None) -> None:
    global _enabled_plugin_ids_provider
    _enabled_plugin_ids_provider = provider


def register_plugin_terminal_action_execution_provider(provider: PluginTerminalActionExecutionProvider | None) -> None:
    global _plugin_terminal_action_execution_provider
    _plugin_terminal_action_execution_provider = provider


def enabled_plugin_ids_for_terminal_actions() -> set[str]:
    if _enabled_plugin_ids_provider is None:
        return set()
    try:
        return set(_enabled_plugin_ids_provider())
    except Exception:
        return set()


def active_terminal_actions(enabled_plugin_ids: set[str] | None = None) -> list[dict]:
    enabled = enabled_plugin_ids_for_terminal_actions() if enabled_plugin_ids is None else enabled_plugin_ids
    actions: list[dict] = []
    for plugin in project_plugin_catalog(enabled):
        for action in plugin.get("surfaces", {}).get("terminal_actions", []):
            actions.append({"plugin_id": plugin["id"], **action})
    return actions


def get_terminal_action(plugin_id: str, action_id: str) -> dict[str, Any] | None:
    for action in active_terminal_actions():
        if action.get("plugin_id") == plugin_id and action.get("id") == action_id:
            return deepcopy(action)
    return None


def execute_plugin_terminal_action(payload: dict[str, Any]) -> dict[str, Any]:
    if _plugin_terminal_action_execution_provider is None:
        return {"success": False, "error": "No plugin terminal action execution provider is registered."}
    return _plugin_terminal_action_execution_provider(payload)
