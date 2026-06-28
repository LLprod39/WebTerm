from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from app.plugins.catalog import project_plugin_catalog

EnabledPluginIdsProvider = Callable[[], set[str]]
PluginNodeExecutionProvider = Callable[[dict[str, Any]], dict[str, Any]]

_enabled_plugin_ids_provider: EnabledPluginIdsProvider | None = None
_plugin_node_execution_provider: PluginNodeExecutionProvider | None = None


def register_enabled_plugin_ids_provider(provider: EnabledPluginIdsProvider | None) -> None:
    global _enabled_plugin_ids_provider
    _enabled_plugin_ids_provider = provider


def register_plugin_node_execution_provider(provider: PluginNodeExecutionProvider | None) -> None:
    global _plugin_node_execution_provider
    _plugin_node_execution_provider = provider


def enabled_plugin_ids_for_studio() -> set[str]:
    if _enabled_plugin_ids_provider is None:
        return set()
    try:
        return set(_enabled_plugin_ids_provider())
    except Exception:
        return set()


def active_studio_nodes(enabled_plugin_ids: set[str] | None = None) -> list[dict]:
    enabled = enabled_plugin_ids_for_studio() if enabled_plugin_ids is None else enabled_plugin_ids
    nodes: list[dict] = []
    for plugin in project_plugin_catalog(enabled):
        for node in plugin.get("surfaces", {}).get("studio_nodes", []):
            nodes.append({"plugin_id": plugin["id"], **node})
    return nodes


def _list(value: Any, default: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(default)
    return [str(item).strip() for item in value if str(item or "").strip()]


def _schema(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and value.get("type") == "object":
        return deepcopy(value)
    return {"type": "object", "properties": {}, "additionalProperties": True}


def _node_type(plugin_id: str, node: dict[str, Any]) -> str:
    explicit = str(node.get("type") or "").strip()
    if explicit:
        return explicit
    node_id = str(node.get("id") or "node").strip() or "node"
    return f"plugin/{plugin_id}/{node_id}"


def plugin_studio_node_manifests(enabled_plugin_ids: set[str] | None = None) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    for node in active_studio_nodes(enabled_plugin_ids):
        plugin_id = str(node.get("plugin_id") or "").strip()
        node_id = str(node.get("id") or "").strip()
        title = str(node.get("title") or node_id or _node_type(plugin_id, node)).strip()
        description = str(node.get("description") or node.get("purpose") or title).strip()
        metadata = {
            "plugin_id": plugin_id,
            "plugin_node_id": node_id,
            "title": title,
            "label": str(node.get("label") or title),
            "palette_description": str(node.get("palette_description") or description),
            "executor_ref": str(node.get("executor_ref") or ""),
            "required_permission": str(node.get("required_permission") or ""),
            "required_secret": str(node.get("required_secret") or ""),
            "connector_id": str(node.get("connector_id") or ""),
            "icon": str(node.get("icon") or "Puzzle"),
            "icon_class_name": str(node.get("icon_class_name") or "text-teal-400"),
        }
        metadata.update(deepcopy(node.get("metadata") if isinstance(node.get("metadata"), dict) else {}))
        manifests.append(
            {
                "type": _node_type(plugin_id, node),
                "category": str(node.get("category") or "Plugin"),
                "purpose": description,
                "source_handles": _list(node.get("source_handles"), ["success", "error", "out"]),
                "risk_level": str(node.get("risk_level") or node.get("risk_tier") or "read_only"),
                "mutates_state": bool(node.get("mutates_state", False)),
                "supports_dry_run": bool(node.get("supports_dry_run", False)),
                "requires_approval_by_default": bool(node.get("requires_approval_by_default", False)),
                "recommended_verification": _list(node.get("recommended_verification"), []),
                "tags": sorted({"plugin", "marketplace", *(_list(node.get("tags"), []))}),
                "input_schema": _schema(node.get("input_schema") or node.get("schema")),
                "output_schema": _schema(node.get("output_schema")),
                "metadata": metadata,
            }
        )
    return manifests


def get_plugin_studio_node_manifest(node_type: str) -> dict[str, Any] | None:
    normalized = str(node_type or "").strip()
    if not normalized:
        return None
    for manifest in plugin_studio_node_manifests():
        if manifest.get("type") == normalized:
            return manifest
    return None


def execute_plugin_studio_node(payload: dict[str, Any]) -> dict[str, Any]:
    if _plugin_node_execution_provider is None:
        return {
            "status": "failed",
            "error": "No plugin Studio node execution provider is registered.",
        }
    return _plugin_node_execution_provider(payload)
