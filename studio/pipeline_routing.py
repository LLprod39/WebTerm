from __future__ import annotations

from collections import defaultdict, deque
from typing import Any


def build_execution_graph(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, list[dict[str, Any]]],
    dict[str, list[dict[str, Any]]],
]:
    id_to_node = {str(node.get("id") or ""): node for node in nodes if str(node.get("id") or "").strip()}
    outgoing_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    incoming_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges or []:
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        if source in id_to_node and target in id_to_node:
            outgoing_edges[source].append(edge)
            incoming_edges[target].append(edge)
    return id_to_node, outgoing_edges, incoming_edges


def graph_edge_handle(edge: dict[str, Any]) -> str:
    return str(edge.get("sourceHandle") or "").strip() or "out"


def possible_routing_ports(node_type: str) -> set[str]:
    if node_type.startswith("trigger/"):
        return {"out"}
    if node_type == "logic/condition":
        return {"true", "false"}
    if node_type == "logic/parallel":
        return {"out"}
    if node_type == "logic/merge":
        return {"out"}
    if node_type == "logic/wait":
        return {"done", "out"}
    if node_type == "logic/human_approval":
        return {"approved", "rejected", "timeout"}
    if node_type == "logic/telegram_input":
        return {"received", "timeout"}
    if node_type.startswith("agent/") or node_type.startswith("output/") or node_type.startswith("ops/"):
        return {"success", "error", "out"}
    return {"out"}


def routing_ports_for_state(node_type: str, state: dict[str, Any] | None) -> set[str]:
    if isinstance(state, dict):
        raw = state.get("routing_ports")
        if isinstance(raw, list) and raw:
            return {str(item).strip() for item in raw if str(item).strip()}
    return possible_routing_ports(node_type)


def result_routing_ports(node: dict[str, Any], result: dict[str, Any]) -> list[str]:
    node_type = str(node.get("type") or "")
    status = str(result.get("status") or "")
    if status == "stopped":
        return []
    if node_type == "logic/condition":
        return ["true"] if bool(result.get("passed")) else ["false"]
    if node_type == "logic/parallel":
        return ["out"]
    if node_type == "logic/merge":
        return ["out"]
    if node_type == "logic/wait":
        return ["done", "out"] if status == "completed" else []
    if node_type == "logic/human_approval":
        decision = str(result.get("decision") or "").strip()
        return [decision] if decision in {"approved", "rejected", "timeout"} else []
    if node_type == "logic/telegram_input":
        decision = str(result.get("decision") or "").strip()
        return [decision] if decision in {"received", "timeout"} else []
    if node_type.startswith("agent/") or node_type.startswith("output/") or node_type.startswith("ops/"):
        if status == "completed":
            return ["success", "out"]
        if status == "failed":
            return ["error"]
        return []
    return ["out"] if status == "completed" else []


def serialize_routing_state(
    *,
    entry_node_id: str,
    activated_nodes: set[str],
    completed_nodes: set[str],
    queued_nodes: set[str],
    pending_merges: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    serialized_merges: dict[str, dict[str, Any]] = {}
    for node_id, item in pending_merges.items():
        serialized_merges[node_id] = {
            "mode": str(item.get("mode") or "all"),
            "arrived_sources": sorted(str(source) for source in (item.get("arrived_sources") or set())),
            "possible_sources": sorted(str(source) for source in (item.get("possible_sources") or set())),
            "released": bool(item.get("released")),
        }
    return {
        "entry_node_id": str(entry_node_id or ""),
        "activated_nodes": sorted(activated_nodes),
        "completed_nodes": sorted(completed_nodes),
        "queued_nodes": sorted(queued_nodes),
        "pending_merges": serialized_merges,
    }


def reachable_nodes_from_entry(
    *,
    entry_node_id: str,
    id_to_node: dict[str, dict[str, Any]],
    outgoing_edges: dict[str, list[dict[str, Any]]],
    node_states: dict[str, dict[str, Any]],
) -> set[str]:
    if not entry_node_id or entry_node_id not in id_to_node:
        return set()
    visited: set[str] = set()
    queue: deque[str] = deque([entry_node_id])
    while queue:
        node_id = queue.popleft()
        if node_id in visited:
            continue
        visited.add(node_id)
        node_type = str(id_to_node[node_id].get("type") or "")
        allowed_ports = routing_ports_for_state(node_type, node_states.get(node_id))
        for edge in outgoing_edges.get(node_id, []):
            if graph_edge_handle(edge) not in allowed_ports:
                continue
            target = str(edge.get("target") or "")
            if target and target not in visited:
                queue.append(target)
    return visited


def possible_merge_sources(
    *,
    merge_node_id: str,
    entry_node_id: str,
    id_to_node: dict[str, dict[str, Any]],
    incoming_edges: dict[str, list[dict[str, Any]]],
    outgoing_edges: dict[str, list[dict[str, Any]]],
    node_states: dict[str, dict[str, Any]],
) -> set[str]:
    reachable = reachable_nodes_from_entry(
        entry_node_id=entry_node_id,
        id_to_node=id_to_node,
        outgoing_edges=outgoing_edges,
        node_states=node_states,
    )
    possible: set[str] = set()
    for edge in incoming_edges.get(merge_node_id, []):
        source = str(edge.get("source") or "")
        if not source or source not in reachable or source not in id_to_node:
            continue
        source_type = str(id_to_node[source].get("type") or "")
        allowed_ports = routing_ports_for_state(source_type, node_states.get(source))
        if graph_edge_handle(edge) in allowed_ports:
            possible.add(source)
    return possible


async def route_from_node(
    *,
    source_node_id: str,
    routing_ports: set[str],
    entry_node_id: str,
    id_to_node: dict[str, dict[str, Any]],
    outgoing_edges: dict[str, list[dict[str, Any]]],
    incoming_edges: dict[str, list[dict[str, Any]]],
    node_states: dict[str, dict[str, Any]],
    ready_queue: deque[str],
    ready_nodes: set[str],
    activated_nodes: set[str],
    completed_nodes: set[str],
    pending_merges: dict[str, dict[str, Any]],
) -> None:
    source_id = str(source_node_id or "").strip()
    if not source_id:
        return
    activated_nodes.add(source_id)

    for edge in outgoing_edges.get(source_id, []):
        if graph_edge_handle(edge) not in routing_ports:
            continue

        target_id = str(edge.get("target") or "").strip()
        target_node = id_to_node.get(target_id)
        if not target_id or target_node is None:
            continue

        target_type = str(target_node.get("type") or "")
        activated_nodes.add(target_id)

        if target_type == "logic/merge":
            merge_state = pending_merges.setdefault(
                target_id,
                {
                    "mode": str((target_node.get("data") or {}).get("mode") or "all").strip().lower() or "all",
                    "arrived_sources": set(),
                    "possible_sources": set(),
                    "released": False,
                },
            )
            if merge_state["mode"] not in {"all", "any"}:
                merge_state["mode"] = "all"
            merge_state.setdefault("arrived_sources", set()).add(source_id)
            merge_state["possible_sources"] = possible_merge_sources(
                merge_node_id=target_id,
                entry_node_id=entry_node_id,
                id_to_node=id_to_node,
                incoming_edges=incoming_edges,
                outgoing_edges=outgoing_edges,
                node_states=node_states,
            )
            if merge_state.get("released") or target_id in completed_nodes or target_id in ready_nodes:
                continue

            arrived_sources = set(merge_state.get("arrived_sources") or set())
            possible_sources = set(merge_state.get("possible_sources") or set())
            should_release = False
            if merge_state["mode"] == "any":
                should_release = bool(arrived_sources)
            else:
                should_release = bool(possible_sources) and arrived_sources >= possible_sources

            if should_release:
                merge_state["released"] = True
                ready_queue.append(target_id)
                ready_nodes.add(target_id)
            continue

        if target_id in completed_nodes or target_id in ready_nodes:
            continue
        ready_queue.append(target_id)
        ready_nodes.add(target_id)
