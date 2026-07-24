from __future__ import annotations

from typing import Any

from studio.services.pipeline_assistant_graph_refs import (
    _canonical_node_type,
    _default_source_handle,
    _edge_from_placeholder_node,
    _edge_path_exists,
    _humanize_ref,
    _infer_structural_node_type,
    _normalize_source_handle,
    _resolve_graph_ref,
    _warn,
)


def _append_ai_node(
    nodes: list[dict[str, Any]],
    new_node_types: dict[str, str],
    *,
    ref: str,
    node_type: str,
    label: str | None = None,
    data: dict[str, Any] | None = None,
    x_offset: float | None = None,
    y_offset: float | None = None,
) -> None:
    if ref in new_node_types:
        return
    nodes.append(
        {
            "ref": ref,
            "type": node_type,
            "data": data or {},
            "label": label or _humanize_ref(ref),
            "x_offset": x_offset,
            "y_offset": y_offset,
        }
    )
    new_node_types[ref] = node_type


def _ensure_ai_node_instructions(
    *,
    node_type: str,
    data: dict[str, Any],
    label: str,
    task_hint: str,
    warnings: list[str] | None,
) -> dict[str, Any]:
    if node_type not in {"agent/react", "agent/multi", "agent/llm_query"}:
        return data

    next_data = dict(data)
    node_label = label.strip() or "AI step"
    hint = task_hint.strip()
    short_hint = hint[:700] if hint else "the operator request and previous pipeline outputs"

    if node_type == "agent/llm_query":
        if not str(next_data.get("system_prompt") or "").strip():
            next_data["system_prompt"] = (
                "You are a concise DevOps automation analyst. Read the pipeline context and prior node outputs, "
                "avoid unsafe assumptions, and return a short actionable result with risks and next steps."
            )
            _warn(warnings, f"AI node '{node_label}' was missing system_prompt; a safe default was added.")
        if not str(next_data.get("prompt") or "").strip():
            next_data["prompt"] = (
                f"Task: {node_label}\n"
                f"Operator request: {short_hint}\n\n"
                "Use previous node outputs from the pipeline context. Produce:\n"
                "1. Brief conclusion.\n"
                "2. Important findings or missing data.\n"
                "3. Recommended next action.\n"
                "Keep the answer compact and suitable for Telegram/report output."
            )
            _warn(warnings, f"AI node '{node_label}' was missing prompt; a working prompt was added.")
        return next_data

    if not str(next_data.get("goal") or "").strip():
        next_data["goal"] = (
            f"{node_label}. Handle this automation task from the operator request: {short_hint}. "
            "Use only configured servers/tools, verify observations, and return a concise operational result."
        )
        _warn(warnings, f"AI node '{node_label}' was missing goal; a working goal was added.")
    if not str(next_data.get("system_prompt") or "").strip():
        next_data["system_prompt"] = (
            "You are a careful DevOps agent inside WebTerm. Prefer read-only diagnostics first, "
            "avoid destructive commands without explicit approval, summarize evidence, and make every action auditable."
        )
        _warn(warnings, f"AI node '{node_label}' was missing system_prompt; a safe default was added.")
    if not str(next_data.get("instructions") or "").strip():
        next_data["instructions"] = (
            "1. Read prior pipeline outputs and the operator request.\n"
            "2. Decide the smallest safe diagnostic action.\n"
            "3. If server access is configured, inspect logs/status without destructive changes.\n"
            "4. If information is missing, state exactly what is missing.\n"
            "5. Return a short result, evidence, and next action."
        )
        _warn(warnings, f"AI node '{node_label}' was missing instructions; working instructions were added.")
    if not str(next_data.get("expected_output") or "").strip():
        next_data["expected_output"] = (
            "Short operational summary with status, evidence, risks, and recommended next action."
        )
    return next_data


def _append_ai_edge(
    edges: list[dict[str, Any]],
    seen_edges: set[tuple[str, str, str, str]],
    *,
    source: str,
    target: str,
    source_handle: str,
    target_handle: str = "",
    label: str | None = None,
    warnings: list[str] | None = None,
    reason: str | None = None,
) -> bool:
    if not source or not target or source == target:
        return False
    edge_key = (source, target, source_handle, target_handle)
    if edge_key in seen_edges:
        _warn(warnings, f"Duplicate AI edge '{source}->{target}' was dropped.")
        return False
    if _edge_path_exists(edges, start=target, goal=source):
        _warn(warnings, f"AI edge '{source}->{target}' would create a cycle and was dropped.")
        return False
    seen_edges.add(edge_key)
    edges.append(
        {
            "source": source,
            "target": target,
            "label": label,
            "source_handle": source_handle,
            "target_handle": target_handle or None,
        }
    )
    if reason:
        _warn(warnings, f"AI graph repair added edge '{source}->{target}' ({reason}).")
    return True


def _sanitize_graph_patch(
    raw_graph_patch: object,
    *,
    fallback_anchor: str | None = None,
    known_node_types: dict[str, str] | None = None,
    known_edges: list[dict[str, Any]] | None = None,
    task_hint: str = "",
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(raw_graph_patch, dict):
        return {
            "anchor_node_id": fallback_anchor,
            "nodes": [],
            "edges": [],
            "update_nodes": [],
            "remove_node_ids": [],
            "remove_edge_ids": [],
        }

    raw_nodes = raw_graph_patch.get("nodes")
    raw_edges = raw_graph_patch.get("edges")
    if not isinstance(raw_nodes, list):
        raw_nodes = []
    if not isinstance(raw_edges, list):
        raw_edges = []

    nodes: list[dict[str, Any]] = []
    dropped_refs: set[str] = set()
    new_node_types: dict[str, str] = {}
    inferred_edges: list[dict[str, Any]] = []
    for item in raw_nodes[:24]:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("ref") or item.get("id") or "").strip()
        if not ref:
            continue
        node_type = _canonical_node_type(item.get("type"), ref=ref, warnings=warnings)
        if node_type is None:
            dropped_refs.add(ref)
            edge = _edge_from_placeholder_node(item)
            if edge is not None:
                inferred_edges.append(edge)
            continue
        raw_data = item.get("data")
        label = str(item.get("label") or "").strip()
        data = raw_data if isinstance(raw_data, dict) else {}
        data = _ensure_ai_node_instructions(
            node_type=node_type,
            data=data,
            label=label or _humanize_ref(ref),
            task_hint=task_hint,
            warnings=warnings,
        )
        try:
            x_offset = float(item["x_offset"]) if item.get("x_offset") not in (None, "") else None
        except (TypeError, ValueError):
            x_offset = None
        try:
            y_offset = float(item["y_offset"]) if item.get("y_offset") not in (None, "") else None
        except (TypeError, ValueError):
            y_offset = None
        _append_ai_node(
            nodes,
            new_node_types,
            ref=ref,
            node_type=node_type,
            data=data,
            label=label or None,
            x_offset=x_offset,
            y_offset=y_offset,
        )

    edges: list[dict[str, Any]] = []
    source_type_lookup = {**(known_node_types or {}), **new_node_types}
    known_graph_refs = set(source_type_lookup)
    raw_remove_edge_ids = raw_graph_patch.get("remove_edge_ids")
    if not isinstance(raw_remove_edge_ids, list):
        raw_remove_edge_ids = []
    remove_edge_ids = [str(item).strip() for item in raw_remove_edge_ids[:48] if str(item).strip()]
    known_incoming_edges: dict[str, list[dict[str, Any]]] = {}
    for edge in known_edges or []:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        if source and target:
            known_incoming_edges.setdefault(target, []).append(edge)

    for item in [*raw_edges, *inferred_edges][:48]:
        if not isinstance(item, dict):
            continue
        for endpoint in ("source", "target"):
            raw_ref = str(item.get(endpoint) or "").strip()
            if not raw_ref or raw_ref in known_graph_refs or raw_ref in dropped_refs:
                continue
            if _resolve_graph_ref(raw_ref, known_graph_refs):
                continue
            inferred_type = _infer_structural_node_type(raw_ref)
            if not inferred_type:
                continue
            _append_ai_node(
                nodes,
                new_node_types,
                ref=raw_ref,
                node_type=inferred_type,
                label=_humanize_ref(raw_ref),
            )
            source_type_lookup[raw_ref] = inferred_type
            known_graph_refs.add(raw_ref)
            _warn(warnings, f"AI referenced missing structural node '{raw_ref}', created '{inferred_type}'.")

    seen_edges: set[tuple[str, str, str, str]] = set()
    for item in [*raw_edges, *inferred_edges][:48]:
        if not isinstance(item, dict):
            continue
        raw_source = str(item.get("source") or "").strip()
        raw_target = str(item.get("target") or "").strip()
        source = _resolve_graph_ref(raw_source, known_graph_refs) or raw_source
        target = _resolve_graph_ref(raw_target, known_graph_refs) or raw_target
        if not source or not target:
            continue
        if raw_source in dropped_refs or raw_target in dropped_refs or source in dropped_refs or target in dropped_refs:
            _warn(warnings, f"AI edge '{raw_source}->{raw_target}' referenced a dropped node and was dropped.")
            continue
        if source not in known_graph_refs or target not in known_graph_refs:
            _warn(warnings, f"AI edge '{raw_source}->{raw_target}' referenced a missing node and was dropped.")
            continue
        if source != raw_source or target != raw_target:
            _warn(warnings, f"AI edge '{raw_source}->{raw_target}' was rewired to '{source}->{target}'.")
        source_type = source_type_lookup.get(source, "")
        source_handle = _normalize_source_handle(
            item.get("source_handle"),
            source=source,
            source_type=source_type,
            warnings=warnings,
        )
        target_handle = str(item.get("target_handle") or "").strip() or ""
        _append_ai_edge(
            edges,
            seen_edges,
            source=source,
            target=target,
            source_handle=source_handle,
            target_handle=target_handle,
            label=str(item.get("label") or "").strip() or None,
            warnings=warnings,
        )

    def _add_repair_edge(source: str, target: str, reason: str) -> None:
        if not source or not target or source == target:
            return
        if source not in known_graph_refs or target not in known_graph_refs:
            return
        source_handle = _default_source_handle(source_type_lookup.get(source, ""))
        _append_ai_edge(
            edges,
            seen_edges,
            source=source,
            target=target,
            source_handle=source_handle,
            warnings=warnings,
            reason=reason,
        )

    anchor_node_id = str(raw_graph_patch.get("anchor_node_id") or "").strip() or fallback_anchor
    anchor_node_id = _resolve_graph_ref(anchor_node_id or "", known_graph_refs) or anchor_node_id
    if anchor_node_id not in known_graph_refs:
        anchor_node_id = None

    def _incoming_targets() -> set[str]:
        return {str(edge.get("target") or "") for edge in edges if str(edge.get("target") or "")}

    def _outgoing_sources() -> set[str]:
        return {str(edge.get("source") or "") for edge in edges if str(edge.get("source") or "")}

    # Auto-inject trigger/webhook if the combined graph (existing + new) has no trigger nodes.
    # This prevents the "Pipeline must include at least one trigger node" error for AI drafts
    # that forgot to add a trigger (common with Telegram bot patterns).
    existing_has_trigger = any(v.startswith("trigger/") for v in (known_node_types or {}).values())
    new_has_trigger = any(v.startswith("trigger/") for v in new_node_types.values())
    if not existing_has_trigger and not new_has_trigger and nodes:
        auto_trigger_ref = "auto_webhook_trigger"
        _append_ai_node(
            nodes,
            new_node_types,
            ref=auto_trigger_ref,
            node_type="trigger/webhook",
            label="Webhook / Telegram Trigger",
            data={"is_active": True},
            x_offset=0,
            y_offset=0,
        )
        source_type_lookup[auto_trigger_ref] = "trigger/webhook"
        known_graph_refs.add(auto_trigger_ref)
        _warn(
            warnings,
            "AI draft had no trigger node; a trigger/webhook was automatically added. "
            "Configure it with your Telegram webhook URL or replace with the appropriate trigger type.",
        )

    new_refs = [str(node.get("ref") or "") for node in nodes if str(node.get("ref") or "")]
    new_triggers = [ref for ref in new_refs if source_type_lookup.get(ref, "").startswith("trigger/")]
    incoming_targets = _incoming_targets()
    root_new_refs = [
        ref
        for ref in new_refs
        if ref not in incoming_targets and not source_type_lookup.get(ref, "").startswith("trigger/")
    ]

    if root_new_refs:
        start_ref = new_triggers[0] if new_triggers else anchor_node_id
        parallel_root = next((ref for ref in root_new_refs if source_type_lookup.get(ref) == "logic/parallel"), None)
        if start_ref and parallel_root:
            _add_repair_edge(start_ref, parallel_root, "connect new branch root")
            for ref in root_new_refs:
                if ref != parallel_root:
                    _add_repair_edge(parallel_root, ref, "connect parallel fan-out")
        elif start_ref:
            for ref in root_new_refs:
                _add_repair_edge(start_ref, ref, "connect unreachable new node")

    incoming_targets = _incoming_targets()
    outgoing_sources = _outgoing_sources()
    merge_refs = [ref for ref in new_refs if source_type_lookup.get(ref) == "logic/merge"]
    output_refs = [ref for ref in new_refs if source_type_lookup.get(ref, "").startswith("output/")]
    branch_leaf_refs = [
        ref
        for ref in new_refs
        if ref not in outgoing_sources
        and source_type_lookup.get(ref) not in {"logic/merge"}
        and not source_type_lookup.get(ref, "").startswith(("trigger/", "output/"))
    ]
    for merge_ref in merge_refs:
        existing_merge_sources = {
            str(edge.get("source") or "") for edge in edges if str(edge.get("target") or "") == merge_ref
        }
        for leaf_ref in branch_leaf_refs[:4]:
            if leaf_ref not in existing_merge_sources:
                _add_repair_edge(leaf_ref, merge_ref, "feed merge from new branch leaf")

    incoming_targets = _incoming_targets()
    outgoing_sources = _outgoing_sources()
    for output_ref in output_refs:
        if output_ref in incoming_targets:
            continue
        source_ref = next((ref for ref in merge_refs if ref in outgoing_sources or ref in incoming_targets), None)
        if not source_ref:
            source_ref = next((ref for ref in branch_leaf_refs if ref != output_ref), None)
        if source_ref:
            _add_repair_edge(source_ref, output_ref, "connect output from repaired branch")

    def _existing_edge_source_handle(edge: dict[str, Any]) -> str:
        source = str(edge.get("source") or "").strip()
        source_type = source_type_lookup.get(source, "")
        return _normalize_source_handle(
            edge.get("sourceHandle") or edge.get("source_handle"),
            source=source,
            source_type=source_type,
            warnings=warnings,
        )

    for target in list(known_graph_refs):
        target_type = source_type_lookup.get(target, "")
        if target_type == "logic/merge":
            continue
        existing_incoming = [
            edge
            for edge in known_incoming_edges.get(target, [])
            if str(edge.get("id") or "").strip() not in set(remove_edge_ids)
        ]
        new_incoming = [edge for edge in edges if str(edge.get("target") or "") == target]
        if not existing_incoming or not new_incoming:
            continue

        merge_ref_base = f"{target}_ai_merge"
        merge_ref = merge_ref_base
        counter = 2
        while merge_ref in known_graph_refs:
            merge_ref = f"{merge_ref_base}_{counter}"
            counter += 1
        _append_ai_node(
            nodes,
            new_node_types,
            ref=merge_ref,
            node_type="logic/merge",
            label=f"Merge before {_humanize_ref(target)}",
        )
        source_type_lookup[merge_ref] = "logic/merge"
        known_graph_refs.add(merge_ref)

        for edge in existing_incoming:
            edge_id = str(edge.get("id") or "").strip()
            source = str(edge.get("source") or "").strip()
            if edge_id:
                remove_edge_ids.append(edge_id)
            else:
                _warn(warnings, f"Existing edge '{source}->{target}' has no id and could not be removed cleanly.")
            if source in known_graph_refs:
                _append_ai_edge(
                    edges,
                    seen_edges,
                    source=source,
                    target=merge_ref,
                    source_handle=_existing_edge_source_handle(edge),
                    warnings=warnings,
                    reason="preserve existing branch before shared target",
                )

        for edge in new_incoming:
            edge["target"] = merge_ref
            edge["target_handle"] = None

        _add_repair_edge(merge_ref, target, "insert explicit merge before shared target")
        _warn(
            warnings,
            f"AI graph repair inserted merge '{merge_ref}' before '{target}' to avoid multiple incoming edges.",
        )

    raw_update_nodes = raw_graph_patch.get("update_nodes")
    if not isinstance(raw_update_nodes, list):
        raw_update_nodes = []
    update_nodes: list[dict[str, Any]] = []
    for item in raw_update_nodes[:24]:
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("node_id") or "").strip()
        raw_data = item.get("data")
        if not node_id or not isinstance(raw_data, dict):
            continue
        update_nodes.append({"node_id": node_id, "data": raw_data})

    raw_remove_node_ids = raw_graph_patch.get("remove_node_ids")
    if not isinstance(raw_remove_node_ids, list):
        raw_remove_node_ids = []
    remove_node_ids = [str(item).strip() for item in raw_remove_node_ids[:24] if str(item).strip()]

    return {
        "anchor_node_id": anchor_node_id,
        "nodes": nodes,
        "edges": edges,
        "update_nodes": update_nodes,
        "remove_node_ids": remove_node_ids,
        "remove_edge_ids": list(dict.fromkeys(remove_edge_ids)),
    }
