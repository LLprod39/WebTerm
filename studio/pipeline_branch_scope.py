from __future__ import annotations

from studio.pipeline_routing import build_execution_graph, reachable_nodes_from_entry


def entry_branch_node_ids(pipeline, entry_node_id: str | None) -> set[str] | None:
    entry = str(entry_node_id or "").strip()
    if not entry:
        return None
    nodes = [node for node in (pipeline.nodes or []) if isinstance(node, dict)]
    id_to_node, outgoing_edges, _incoming_edges = build_execution_graph(nodes, pipeline.edges or [])
    return reachable_nodes_from_entry(
        entry_node_id=entry,
        id_to_node=id_to_node,
        outgoing_edges=outgoing_edges,
        node_states={},
    )
