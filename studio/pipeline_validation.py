from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from plugin_marketplace.services.install_service import enabled_plugin_ids_for_user

from .execution_policy import validate_execution_policy_guardrails
from .models import CURRENT_PIPELINE_GRAPH_VERSION

# Compatibility re-export: ``KNOWN_NODE_TYPES`` is imported from this module by
# callers/tests even though it is not referenced locally.  The explicit ``as``
# alias marks it as an intentional re-export so ruff's F401 keeps it.
from .node_manifest import KNOWN_NODE_TYPES as KNOWN_NODE_TYPES
from .node_manifest import TRIGGER_NODE_TYPES, allowed_source_handles, runtime_known_node_types
from .pipeline_validation_references import validate_node_references


def _normalized_handle(raw: Any) -> str:
    value = str(raw or "").strip()
    return value or "out"


def _allowed_outgoing_handles(node_type: str) -> set[str]:
    return set(allowed_source_handles(node_type))


def _is_active_manual_trigger(node: dict[str, Any]) -> bool:
    if str(node.get("type") or "") != "trigger/manual":
        return False
    data = node.get("data")
    if not isinstance(data, dict):
        return True
    return bool(data.get("is_active", True))


def _validate_graph_structure(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    known_node_types: frozenset[str],
) -> tuple[list[str], dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    errors: list[str] = []
    node_ids: list[str] = []
    id_to_node: dict[str, dict[str, Any]] = {}

    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"Node #{index + 1} must be an object.")
            continue

        node_id = str(node.get("id") or "").strip()
        node_type = str(node.get("type") or "").strip()
        if not node_id:
            errors.append(f"Node #{index + 1} is missing an id.")
            continue
        if node_id in id_to_node:
            errors.append(f"Duplicate node id '{node_id}'.")
            continue
        if node_type not in known_node_types:
            errors.append(f"Node '{node_id}' uses an unknown type '{node_type}'.")

        position = node.get("position")
        if position is not None and not isinstance(position, dict):
            errors.append(f"Node '{node_id}' position must be an object.")
        if node.get("data") is not None and not isinstance(node.get("data"), dict):
            errors.append(f"Node '{node_id}' data must be an object.")

        node_ids.append(node_id)
        id_to_node[node_id] = node

    if not isinstance(edges, list):
        return [*errors, "Pipeline edges must be a list."], {}, {}, {}

    outgoing_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    incoming_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    edge_ids: set[str] = set()
    children: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = defaultdict(int)

    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"Edge #{index + 1} must be an object.")
            continue

        edge_id = str(edge.get("id") or "").strip()
        if edge_id:
            if edge_id in edge_ids:
                errors.append(f"Duplicate edge id '{edge_id}'.")
            edge_ids.add(edge_id)

        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        if not source or not target:
            errors.append(f"Edge #{index + 1} must define both source and target.")
            continue
        if source not in id_to_node:
            errors.append(f"Edge #{index + 1} references missing source node '{source}'.")
            continue
        if target not in id_to_node:
            errors.append(f"Edge #{index + 1} references missing target node '{target}'.")
            continue

        outgoing_edges[source].append(edge)
        incoming_edges[target].append(edge)
        children[source].append(target)
        in_degree[target] += 1

    if errors:
        return errors, id_to_node, outgoing_edges, incoming_edges

    queue: deque[str] = deque(node_id for node_id in node_ids if in_degree[node_id] == 0)
    processed: list[str] = []
    while queue:
        node_id = queue.popleft()
        processed.append(node_id)
        for child in children[node_id]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    if len(processed) != len(node_ids):
        blocked = sorted(set(node_ids) - set(processed))
        preview = ", ".join(blocked[:5])
        errors.append(f"Pipeline graph contains a cycle or unreachable loop involving: {preview}.")

    return errors, id_to_node, outgoing_edges, incoming_edges


def _validate_graph_contract(
    *,
    nodes: list[dict[str, Any]],
    id_to_node: dict[str, dict[str, Any]],
    outgoing_edges: dict[str, list[dict[str, Any]]],
    incoming_edges: dict[str, list[dict[str, Any]]],
    require_manual_trigger: bool,
) -> list[str]:
    errors: list[str] = []
    trigger_nodes = [node for node in nodes if str(node.get("type") or "") in TRIGGER_NODE_TYPES]
    if not trigger_nodes:
        errors.append("Pipeline must include at least one trigger node.")
        return errors

    if require_manual_trigger and not any(_is_active_manual_trigger(node) for node in trigger_nodes):
        errors.append("Manual runs require at least one active manual trigger node.")

    for node_id, node in id_to_node.items():
        node_type = str(node.get("type") or "")
        incoming = incoming_edges.get(node_id, [])
        outgoing = outgoing_edges.get(node_id, [])

        if node_type in TRIGGER_NODE_TYPES and incoming:
            errors.append(f"Trigger node '{node_id}' must be a graph entry point and cannot have incoming edges.")

        if node_type == "logic/merge":
            if len(incoming) < 1:
                errors.append(f"Merge node '{node_id}' requires at least one incoming edge.")
        elif len(incoming) > 1:
            errors.append(
                f"Node '{node_id}' has {len(incoming)} incoming edges. Use an explicit merge node for branch joins."
            )

        allowed_handles = _allowed_outgoing_handles(node_type)
        for edge in outgoing:
            edge_handle = _normalized_handle(edge.get("sourceHandle"))
            if edge_handle not in allowed_handles:
                edge_label = str(edge.get("id") or "") or f"{node_id}->{str(edge.get('target') or '')}"
                errors.append(
                    f"Edge '{edge_label}' uses sourceHandle "
                    f"'{edge_handle}' which is invalid for node '{node_id}' ({node_type}). "
                    f"Allowed: {', '.join(sorted(allowed_handles))}."
                )

    reachable: set[str] = set()
    queue: deque[str] = deque(str(node.get("id") or "") for node in trigger_nodes)
    while queue:
        node_id = queue.popleft()
        if not node_id or node_id in reachable:
            continue
        reachable.add(node_id)
        for edge in outgoing_edges.get(node_id, []):
            target = str(edge.get("target") or "")
            if target and target not in reachable:
                queue.append(target)

    unreachable = sorted(node_id for node_id in id_to_node if node_id not in reachable)
    if unreachable:
        preview = ", ".join(unreachable[:5])
        errors.append(f"Nodes are unreachable from every trigger: {preview}.")

    return errors


def _runtime_known_node_types_for_owner(owner) -> frozenset[str]:
    if not getattr(owner, "pk", None):
        return runtime_known_node_types(set())
    try:
        return runtime_known_node_types(enabled_plugin_ids_for_user(owner))
    except Exception:
        return runtime_known_node_types(set())


def validate_pipeline_definition(
    *,
    nodes: Any,
    edges: Any,
    owner,
    graph_version: Any = CURRENT_PIPELINE_GRAPH_VERSION,
    require_manual_trigger: bool = False,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(nodes, list):
        return ["Pipeline nodes must be a list."]
    if not isinstance(edges, list):
        return ["Pipeline edges must be a list."]

    try:
        normalized_graph_version = int(graph_version)
    except (TypeError, ValueError):
        return ["Pipeline graph_version must be an integer."]
    if normalized_graph_version != CURRENT_PIPELINE_GRAPH_VERSION:
        return [
            (
                f"Pipeline graph_version={normalized_graph_version} is not supported. "
                f"Resave or recreate the pipeline as V{CURRENT_PIPELINE_GRAPH_VERSION}."
            )
        ]

    known_node_types = _runtime_known_node_types_for_owner(owner)
    structure_errors, id_to_node, outgoing_edges, incoming_edges = _validate_graph_structure(
        nodes, edges, known_node_types
    )
    errors.extend(structure_errors)
    if errors:
        return errors

    errors.extend(
        _validate_graph_contract(
            nodes=nodes,
            id_to_node=id_to_node,
            outgoing_edges=outgoing_edges,
            incoming_edges=incoming_edges,
            require_manual_trigger=require_manual_trigger,
        )
    )
    errors.extend(
        validate_execution_policy_guardrails(
            nodes=nodes,
            id_to_node=id_to_node,
            incoming_edges=incoming_edges,
        )
    )

    for node in nodes:
        if isinstance(node, dict):
            validate_node_references(node, owner, errors)

    return errors


def ensure_json_object(value: Any, *, label: str) -> tuple[dict[str, Any] | None, str | None]:
    if value in (None, ""):
        return {}, None
    if not isinstance(value, dict):
        return None, f"{label} must be a JSON object"
    return dict(value), None
