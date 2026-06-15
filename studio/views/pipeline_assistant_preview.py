"""
Pure preview and risk helpers for Studio pipeline assistant responses.
"""

import json
import re

from studio.execution_policy import build_execution_policy_decisions


def _clone_json_snapshot(value):
    return json.loads(json.dumps(value))


def _assistant_safe_id(raw_value: str, *, prefix: str, used_ids: set[str]) -> str:
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", str(raw_value or "").strip().lower()).strip("_")
    if not base:
        base = prefix
    if not re.match(r"^[a-zA-Z_]", base):
        base = f"{prefix}_{base}"
    base = base[:48].strip("_") or prefix
    candidate = base
    counter = 2
    while candidate in used_ids:
        candidate = f"{base}_{counter}"
        counter += 1
    used_ids.add(candidate)
    return candidate


def _assistant_safe_edge_id(source: str, target: str, source_handle: str, used_edge_ids: set[str]) -> str:
    raw = f"edge_{source}_{target}_{source_handle or 'out'}"
    return _assistant_safe_id(raw, prefix="edge", used_ids=used_edge_ids)


def _assistant_allowed_source_handles(node_type: str) -> set[str]:
    if node_type == "logic/condition":
        return {"true", "false"}
    if node_type == "logic/human_approval":
        return {"approved", "rejected", "timeout"}
    if node_type == "logic/telegram_input":
        return {"received", "timeout"}
    if node_type == "logic/wait":
        return {"done", "out"}
    if node_type in {"logic/parallel", "logic/merge"} or node_type.startswith("trigger/"):
        return {"out"}
    if node_type.startswith("agent/") or node_type.startswith("ops/") or node_type.startswith("output/"):
        return {"success", "error", "out"}
    return {"out"}


def _assistant_default_source_handle(node_type: str) -> str:
    if node_type == "logic/condition":
        return "true"
    if node_type == "logic/human_approval":
        return "approved"
    if node_type == "logic/telegram_input":
        return "received"
    if node_type == "logic/wait":
        return "done"
    return "out"


def _assistant_normalize_source_handle(raw_handle: object, *, source_type: str) -> str:
    value = str(raw_handle or "").strip()
    allowed = _assistant_allowed_source_handles(source_type)
    if value in allowed:
        return value
    return _assistant_default_source_handle(source_type)


def assistant_patch_summary(response: dict) -> str:
    graph_patch = response.get("graph_patch") if isinstance(response.get("graph_patch"), dict) else {}
    added = len(graph_patch.get("nodes") or [])
    linked = len(graph_patch.get("edges") or [])
    updated = len(graph_patch.get("update_nodes") or [])
    removed = len(graph_patch.get("remove_node_ids") or []) + len(graph_patch.get("remove_edge_ids") or [])
    if response.get("node_patch"):
        updated += 1
    parts = []
    if added:
        parts.append(f"{added} node(s) added")
    if linked:
        parts.append(f"{linked} edge(s) added")
    if updated:
        parts.append(f"{updated} node update(s)")
    if removed:
        parts.append(f"{removed} removal(s)")
    return ", ".join(parts) if parts else "No graph changes proposed"


def apply_pipeline_assistant_patch(nodes: list, edges: list, response: dict) -> tuple[list[dict], list[dict]]:
    preview_nodes = _clone_json_snapshot(nodes if isinstance(nodes, list) else [])
    preview_edges = _clone_json_snapshot(edges if isinstance(edges, list) else [])
    graph_patch = response.get("graph_patch") if isinstance(response.get("graph_patch"), dict) else {}

    node_map = {str(node.get("id") or ""): node for node in preview_nodes if isinstance(node, dict)}
    edge_ids = {str(edge.get("id") or "") for edge in preview_edges if isinstance(edge, dict) and edge.get("id")}

    target_node_id = str(response.get("target_node_id") or "").strip()
    node_patch = response.get("node_patch")
    if target_node_id and isinstance(node_patch, dict) and target_node_id in node_map:
        data = node_map[target_node_id].get("data")
        if not isinstance(data, dict):
            data = {}
        node_map[target_node_id]["data"] = {**data, **_clone_json_snapshot(node_patch)}

    remove_node_ids = {
        str(item).strip()
        for item in (graph_patch.get("remove_node_ids") or [])
        if str(item).strip()
    }
    remove_edge_ids = {
        str(item).strip()
        for item in (graph_patch.get("remove_edge_ids") or [])
        if str(item).strip()
    }
    if remove_node_ids:
        preview_nodes = [node for node in preview_nodes if str(node.get("id") or "") not in remove_node_ids]
        node_map = {str(node.get("id") or ""): node for node in preview_nodes if isinstance(node, dict)}
    if remove_edge_ids or remove_node_ids:
        preview_edges = [
            edge
            for edge in preview_edges
            if str(edge.get("id") or "") not in remove_edge_ids
            and str(edge.get("source") or "") not in remove_node_ids
            and str(edge.get("target") or "") not in remove_node_ids
        ]
        edge_ids = {str(edge.get("id") or "") for edge in preview_edges if isinstance(edge, dict) and edge.get("id")}

    for update in graph_patch.get("update_nodes") or []:
        if not isinstance(update, dict):
            continue
        node_id = str(update.get("node_id") or "").strip()
        patch_data = update.get("data")
        if not node_id or not isinstance(patch_data, dict) or node_id not in node_map:
            continue
        data = node_map[node_id].get("data")
        if not isinstance(data, dict):
            data = {}
        node_map[node_id]["data"] = {**data, **_clone_json_snapshot(patch_data)}

    anchor_node_id = str(graph_patch.get("anchor_node_id") or target_node_id or "").strip()
    anchor_node = node_map.get(anchor_node_id) if anchor_node_id else None
    if not anchor_node and preview_nodes:
        anchor_node = max(
            preview_nodes,
            key=lambda node: float((node.get("position") or {}).get("x") or 0) if isinstance(node, dict) else 0,
        )
    anchor_position = anchor_node.get("position") if isinstance(anchor_node, dict) else {}
    if not isinstance(anchor_position, dict):
        anchor_position = {}
    anchor_x = float(anchor_position.get("x") or 0)
    anchor_y = float(anchor_position.get("y") or 0)

    used_node_ids = {str(node.get("id") or "") for node in preview_nodes if isinstance(node, dict)}
    ref_to_node_id: dict[str, str] = {}
    raw_new_nodes = graph_patch.get("nodes") or []
    for index, item in enumerate(raw_new_nodes):
        if not isinstance(item, dict):
            continue
        ref = str(item.get("ref") or "").strip()
        node_type = str(item.get("type") or "").strip()
        if not ref or not node_type:
            continue
        node_id = _assistant_safe_id(ref, prefix="node", used_ids=used_node_ids)
        ref_to_node_id[ref] = node_id
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        data = _clone_json_snapshot(data)
        label = str(item.get("label") or "").strip()
        if label and not str(data.get("label") or "").strip():
            data["label"] = label
        x_offset = item.get("x_offset")
        y_offset = item.get("y_offset")
        x = anchor_x + (float(x_offset) if isinstance(x_offset, (int, float)) else (260 * (index + 1 if anchor_node else index)))
        y = anchor_y + (float(y_offset) if isinstance(y_offset, (int, float)) else (90 * index))
        preview_nodes.append(
            {
                "id": node_id,
                "type": node_type,
                "position": {"x": x, "y": y},
                "data": data,
            }
        )
        node_map[node_id] = preview_nodes[-1]

    for item in graph_patch.get("edges") or []:
        if not isinstance(item, dict):
            continue
        source = ref_to_node_id.get(str(item.get("source") or "").strip(), str(item.get("source") or "").strip())
        target = ref_to_node_id.get(str(item.get("target") or "").strip(), str(item.get("target") or "").strip())
        if not source or not target:
            continue
        source_node = node_map.get(source)
        source_type = str(source_node.get("type") or "") if isinstance(source_node, dict) else ""
        source_handle = _assistant_normalize_source_handle(item.get("source_handle"), source_type=source_type)
        edge = {
            "id": _assistant_safe_edge_id(source, target, source_handle, edge_ids),
            "source": source,
            "target": target,
            "sourceHandle": source_handle,
        }
        target_handle = str(item.get("target_handle") or "").strip()
        label = str(item.get("label") or "").strip()
        if target_handle:
            edge["targetHandle"] = target_handle
        if label:
            edge["label"] = label
        preview_edges.append(edge)

    return preview_nodes, preview_edges


def pipeline_assistant_risk(nodes: list, edges: list | None = None) -> dict:
    items = [
        decision.to_risk_item()
        for decision in build_execution_policy_decisions(
            nodes=nodes if isinstance(nodes, list) else [],
            edges=edges if isinstance(edges, list) else None,
        )
    ]
    if any(str(item.get("level") or "") == "dangerous" for item in items):
        level = "dangerous"
    elif items:
        level = "review"
    else:
        level = "safe"
    return {"level": level, "items": items}


def compact_node_summary(node: dict) -> dict:
    data = node.get("data") if isinstance(node, dict) else {}
    if not isinstance(data, dict):
        data = {}
    label = str(data.get("label") or "").strip()
    return {
        "id": str(node.get("id") or ""),
        "type": str(node.get("type") or ""),
        "label": label or None,
    }


def compact_selected_node(node: dict) -> dict:
    data = node.get("data") if isinstance(node, dict) else {}
    if not isinstance(data, dict):
        data = {}
    return {
        "id": str(node.get("id") or ""),
        "type": str(node.get("type") or ""),
        "position": node.get("position") or {},
        "data": data,
    }
