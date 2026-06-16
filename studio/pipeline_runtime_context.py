from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER_RE = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})")

_BUILT_IN_RUN_PLACEHOLDERS = {
    "all_outputs",
    "approve_url",
    "created_at",
    "current_node_id",
    "current_node_label",
    "duration_seconds",
    "entry_node_id",
    "finished_at",
    "pipeline_id",
    "pipeline_name",
    "reject_url",
    "run_id",
    "run_status",
    "started_at",
    "summary",
    "timeout_minutes",
    "trigger_name",
    "trigger_node_id",
    "trigger_type",
}
_OUTPUT_PLACEHOLDER_SUFFIXES = ("_output", "_error", "_status")
_SERVER_CONTEXT_NODE_TYPES = {
    "agent/ssh_cmd",
    "ops/server_snapshot",
    "ops/log_query",
    "ops/file_action",
    "ops/package_action",
    "ops/disk_cleanup",
    "ops/backup_restore_check",
    "ops/service_action",
    "ops/docker_action",
    "ops/process_action",
}


def _collect_placeholders(value: Any, output: set[str]) -> None:
    if isinstance(value, str):
        output.update(_PLACEHOLDER_RE.findall(value))
        return
    if isinstance(value, list):
        for item in value:
            _collect_placeholders(item, output)
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_placeholders(item, output)


def _has_context_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return True


def _context_key(data: dict[str, Any], field: str, default_key: str) -> str:
    key = data.get(f"{field}_context_key")
    if _has_context_value(key):
        return str(key).strip()
    return default_key


def _add_runtime_field(output: set[str], key: str, node_ids: set[str]) -> None:
    normalized = str(key or "").strip()
    if normalized and _is_runtime_context_field(normalized, node_ids):
        output.add(normalized)


def _add_implicit_runtime_fields(node: dict[str, Any], output: set[str], node_ids: set[str]) -> None:
    node_type = str(node.get("type") or "")
    data = node.get("data") if isinstance(node.get("data"), dict) else {}

    if node_type in _SERVER_CONTEXT_NODE_TYPES and not _has_context_value(data.get("server_id")):
        _add_runtime_field(output, _context_key(data, "server_id", "server_id"), node_ids)

    if node_type == "ops/log_query":
        source = str(data.get("source") or "journal").strip().lower()
        if source == "service" and not _has_context_value(data.get("service")):
            _add_runtime_field(output, "service_name", node_ids)
        if source == "docker" and not _has_context_value(data.get("container")):
            _add_runtime_field(output, "container_name", node_ids)

    if node_type == "ops/service_action" and not _has_context_value(data.get("service")):
        _add_runtime_field(output, _context_key(data, "service", "service_name"), node_ids)

    if node_type == "ops/docker_action" and not _has_context_value(data.get("container")):
        _add_runtime_field(output, "container_name", node_ids)

    if node_type == "ops/process_action" and not _has_context_value(data.get("pid")):
        _add_runtime_field(output, _context_key(data, "pid", "pid"), node_ids)

    if node_type == "ops/alert_update" and not _has_context_value(data.get("alert_id")):
        _add_runtime_field(output, _context_key(data, "alert_id", "alert_id"), node_ids)


def _is_runtime_context_field(name: str, node_ids: set[str]) -> bool:
    if name in _BUILT_IN_RUN_PLACEHOLDERS:
        return False
    if name in node_ids:
        return False
    return not any(name.endswith(suffix) for suffix in _OUTPUT_PLACEHOLDER_SUFFIXES)


def _nodes_for_entry_branch(nodes: Any, edges: Any, entry_node_id: str | None) -> list[dict[str, Any]]:
    if not isinstance(nodes, list):
        return []
    normalized_nodes = [node for node in nodes if isinstance(node, dict)]
    entry = str(entry_node_id or "").strip()
    if not entry:
        return normalized_nodes
    if not isinstance(edges, list):
        return normalized_nodes

    from .pipeline_routing import build_execution_graph, reachable_nodes_from_entry

    id_to_node, outgoing_edges, _incoming_edges = build_execution_graph(normalized_nodes, edges)
    reachable_ids = reachable_nodes_from_entry(
        entry_node_id=entry,
        id_to_node=id_to_node,
        outgoing_edges=outgoing_edges,
        node_states={},
    )
    return [id_to_node[node_id] for node_id in reachable_ids if node_id in id_to_node]


def validate_pipeline_entry_branch(nodes: Any, edges: Any, entry_node_id: str | None) -> list[str]:
    entry = str(entry_node_id or "").strip()
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return []

    from .pipeline_routing import build_execution_graph, reachable_nodes_from_entry

    id_to_node, outgoing_edges, _incoming_edges = build_execution_graph(
        [node for node in nodes if isinstance(node, dict)],
        edges,
    )
    entry_node = id_to_node.get(entry)
    if not entry or entry_node is None:
        return ["Pipeline run is missing a valid entry trigger node."]

    if not str(entry_node.get("type") or "").startswith("trigger/"):
        return [f"Entry node '{entry}' is not a trigger node."]

    reachable_ids = reachable_nodes_from_entry(
        entry_node_id=entry,
        id_to_node=id_to_node,
        outgoing_edges=outgoing_edges,
        node_states={},
    )
    if not any(
        not str(id_to_node[node_id].get("type") or "").startswith("trigger/")
        for node_id in reachable_ids
    ):
        return [f"Selected trigger '{entry}' has no downstream executable nodes."]
    return []


def get_pipeline_runtime_context_fields(
    nodes: Any,
    *,
    edges: Any = None,
    entry_node_id: str | None = None,
) -> list[str]:
    if not isinstance(nodes, list):
        return []
    scoped_nodes = _nodes_for_entry_branch(nodes, edges, entry_node_id)

    node_ids = {
        str(node.get("id") or "").strip()
        for node in scoped_nodes
        if isinstance(node, dict) and str(node.get("id") or "").strip()
    }
    placeholders: set[str] = set()
    for node in scoped_nodes:
        if not isinstance(node, dict):
            continue
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        _collect_placeholders(data, placeholders)
        _add_implicit_runtime_fields(node, placeholders, node_ids)

    return sorted(name for name in placeholders if _is_runtime_context_field(name, node_ids))


def get_missing_pipeline_runtime_context_fields(
    nodes: Any,
    context: dict[str, Any] | None,
    *,
    edges: Any = None,
    entry_node_id: str | None = None,
) -> list[str]:
    runtime_fields = get_pipeline_runtime_context_fields(
        nodes,
        edges=edges,
        entry_node_id=entry_node_id,
    )
    available_context = context if isinstance(context, dict) else {}
    return [field for field in runtime_fields if not _has_context_value(available_context.get(field))]


def validate_pipeline_runtime_context(
    nodes: Any,
    context: dict[str, Any] | None,
    *,
    edges: Any = None,
    entry_node_id: str | None = None,
) -> list[str]:
    missing = get_missing_pipeline_runtime_context_fields(
        nodes,
        context,
        edges=edges,
        entry_node_id=entry_node_id,
    )
    if not missing:
        return []
    return [f"Missing required runtime context fields: {', '.join(missing)}."]
