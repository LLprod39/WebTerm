from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.plugins.catalog import project_plugin_catalog

EnabledPluginIdsProvider = Callable[[], set[str]]
HookExecutionProvider = Callable[[dict[str, Any]], dict[str, Any]]

_enabled_plugin_ids_provider: EnabledPluginIdsProvider | None = None
_hook_execution_provider: HookExecutionProvider | None = None


def register_enabled_plugin_ids_provider(provider: EnabledPluginIdsProvider) -> None:
    global _enabled_plugin_ids_provider
    _enabled_plugin_ids_provider = provider


def register_plugin_hook_execution_provider(provider: HookExecutionProvider) -> None:
    global _hook_execution_provider
    _hook_execution_provider = provider


def _enabled_plugin_ids() -> set[str]:
    if _enabled_plugin_ids_provider is None:
        return set()
    try:
        return _enabled_plugin_ids_provider()
    except Exception:
        return set()


def active_hooks(enabled_plugin_ids: set[str] | None = None) -> list[dict[str, Any]]:
    enabled = enabled_plugin_ids if enabled_plugin_ids is not None else _enabled_plugin_ids()
    hooks: list[dict[str, Any]] = []
    for plugin in project_plugin_catalog(enabled):
        for hook in plugin.get("surfaces", {}).get("hooks", []):
            hooks.append({"plugin_id": plugin["id"], **hook})
    return hooks


def emit_plugin_hook_event(
    event: str,
    payload: dict[str, Any] | None = None,
    *,
    user: Any = None,
    enabled_plugin_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    if _hook_execution_provider is None:
        return []
    results: list[dict[str, Any]] = []
    for hook in active_hooks(enabled_plugin_ids):
        if str(hook.get("event") or "") != event:
            continue
        results.append(
            _hook_execution_provider(
                {
                    "plugin_id": hook["plugin_id"],
                    "hook_id": hook["id"],
                    "event": event,
                    "payload": payload or {},
                    "user": user,
                }
            )
        )
    return results
