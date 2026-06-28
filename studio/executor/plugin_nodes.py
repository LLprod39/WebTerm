from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from asgiref.sync import sync_to_async

from app.plugins.studio_nodes import (
    execute_plugin_studio_node,
    get_plugin_studio_node_manifest,
    plugin_studio_node_manifests,
)
from studio.executor.nodes.base import BaseNode, NodeResult
from studio.executor.registry import registry

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


class PluginStudioNode(BaseNode):
    node_type = "plugin/base"

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
        manifest = await sync_to_async(get_plugin_studio_node_manifest, thread_sensitive=True)(self.node_type)
        if manifest is None:
            return NodeResult(error=f"Plugin Studio node is disabled or unknown: {self.node_type}")
        metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
        result = await sync_to_async(execute_plugin_studio_node, thread_sensitive=True)(
            {
                "plugin_id": metadata.get("plugin_id"),
                "node_type": self.node_type,
                "node_id": self.node_id,
                "data": dict(self.node_data or {}),
                "manifest": manifest,
                "user": ctx.user,
                "pipeline": ctx.pipeline,
                "run_id": ctx.run_id,
            }
        )
        status = str(result.get("status") or "")
        if status == "failed":
            return NodeResult(error=str(result.get("error") or "Plugin Studio node execution failed."))
        return NodeResult(output=dict(result))


def _class_name(node_type: str) -> str:
    suffix = re.sub(r"[^A-Za-z0-9]+", "_", node_type).strip("_") or "node"
    return f"PluginStudioNode_{suffix}"


def _node_class(node_type: str) -> type[PluginStudioNode]:
    return type(
        _class_name(node_type),
        (PluginStudioNode,),
        {"node_type": node_type, "__module__": __name__},
    )


def sync_plugin_node_registry() -> None:
    for manifest in plugin_studio_node_manifests():
        node_type = str(manifest.get("type") or "").strip()
        if not node_type or node_type in registry:
            continue
        registry.register(_node_class(node_type))


async def sync_plugin_node_registry_async() -> None:
    await sync_to_async(sync_plugin_node_registry, thread_sensitive=True)()


def clear_plugin_node_registry() -> None:
    snapshot = registry.snapshot()
    filtered = {node_type: node_class for node_type, node_class in snapshot.items() if not node_type.startswith("plugin/")}
    if len(filtered) != len(snapshot):
        registry.replace_all(filtered)


async def clear_plugin_node_registry_async() -> None:
    await sync_to_async(clear_plugin_node_registry, thread_sensitive=True)()
