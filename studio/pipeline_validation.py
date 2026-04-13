from __future__ import annotations

import json
from collections import defaultdict, deque
from typing import Any

try:
    from croniter import croniter
except ModuleNotFoundError:  # pragma: no cover - optional dependency in local mini env
    croniter = None

from servers.models import Server

from .models import AgentConfig, MCPServerPool, CURRENT_PIPELINE_GRAPH_VERSION
from .skill_registry import normalise_skill_slugs, resolve_skills

TRIGGER_NODE_TYPES = {
    "trigger/manual",
    "trigger/webhook",
    "trigger/schedule",
    "trigger/monitoring",
}
KNOWN_NODE_TYPES = {
    *TRIGGER_NODE_TYPES,
    "agent/react",
    "agent/multi",
    "agent/ssh_cmd",
    "agent/llm_query",
    "agent/mcp_call",
    "logic/condition",
    "logic/parallel",
    "logic/merge",
    "logic/wait",
    "logic/human_approval",
    "logic/telegram_input",
    "output/report",
    "output/webhook",
    "output/email",
    "output/telegram",
}


def _owner_can_use_mcp(owner) -> bool:
    return bool(owner and getattr(owner, "is_staff", False))


def _looks_like_five_field_cron(value: str) -> bool:
    return len([part for part in value.split() if part]) == 5


def _collect_int_ids(raw: Any, *, field_name: str, errors: list[str], node_id: str) -> list[int]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        errors.append(f"Node '{node_id}' field '{field_name}' must be a list of ids.")
        return []

    ids: list[int] = []
    for item in raw:
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            errors.append(f"Node '{node_id}' field '{field_name}' contains an invalid id: {item!r}.")
    return ids


def _collect_optional_int(raw: Any, *, field_name: str, errors: list[str], node_id: str) -> int | None:
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        errors.append(f"Node '{node_id}' field '{field_name}' must be an integer id.")
        return None


def _parse_json_object_text(raw: Any, *, field_name: str, errors: list[str], node_id: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        errors.append(f"Node '{node_id}' field '{field_name}' contains invalid JSON: {exc}.")
        return None
    if not isinstance(parsed, dict):
        errors.append(f"Node '{node_id}' field '{field_name}' must be a JSON object.")
        return None
    return parsed


def _validate_node_references(node: dict[str, Any], owner, errors: list[str]) -> None:
    node_id = str(node.get("id") or "").strip() or "<unknown>"
    node_type = str(node.get("type") or "").strip()
    data = node.get("data") if isinstance(node.get("data"), dict) else {}

    if "webhook_payload_map_text" in data:
        _parse_json_object_text(
            data.get("webhook_payload_map_text"),
            field_name="webhook_payload_map_text",
            errors=errors,
            node_id=node_id,
        )

    if "arguments_text" in data:
        _parse_json_object_text(
            data.get("arguments_text"),
            field_name="arguments_text",
            errors=errors,
            node_id=node_id,
        )

    if node_type == "trigger/webhook":
        payload_map = data.get("webhook_payload_map", {})
        if payload_map not in (None, "") and not isinstance(payload_map, dict):
            errors.append(f"Node '{node_id}' webhook_payload_map must be a JSON object.")

    if node_type == "trigger/schedule":
        cron_expression = str(data.get("cron_expression") or "").strip()
        if cron_expression:
            if croniter is None:
                if not _looks_like_five_field_cron(cron_expression):
                    errors.append(
                        f"Node '{node_id}' cron expression must contain 5 fields (minute hour day month weekday)."
                    )
            else:
                try:
                    croniter(cron_expression)
                except Exception as exc:
                    errors.append(f"Node '{node_id}' has an invalid cron expression: {exc}.")

    if node_type == "trigger/monitoring":
        monitoring_filters = data.get("monitoring_filters")
        if not isinstance(monitoring_filters, dict):
            monitoring_filters = {}

        def _monitoring_value(field_name: str):
            return monitoring_filters.get(field_name, data.get(field_name))

        server_ids = _collect_int_ids(
            _monitoring_value("server_ids"),
            field_name="server_ids",
            errors=errors,
            node_id=node_id,
        )
        if server_ids:
            accessible = set(Server.objects.filter(user=owner, id__in=server_ids).values_list("id", flat=True))
            missing = [sid for sid in server_ids if sid not in accessible]
            if missing:
                errors.append(f"Node '{node_id}' references inaccessible servers: {missing}.")

        for field_name in ("severities", "alert_types", "container_names"):
            raw = _monitoring_value(field_name)
            if raw in (None, ""):
                continue
            if not isinstance(raw, list) or any(not str(item or "").strip() for item in raw):
                errors.append(f"Node '{node_id}' field '{field_name}' must be a list of non-empty strings.")

    skill_slugs = normalise_skill_slugs(data.get("skill_slugs"))
    if skill_slugs:
        _skills, skill_errors = resolve_skills(skill_slugs)
        errors.extend(f"Node '{node_id}' skill error: {item}" for item in skill_errors)

    if node_type in {"agent/react", "agent/multi"}:
        server_ids = _collect_int_ids(data.get("server_ids"), field_name="server_ids", errors=errors, node_id=node_id)
        if server_ids:
            accessible = set(Server.objects.filter(user=owner, id__in=server_ids).values_list("id", flat=True))
            missing = [sid for sid in server_ids if sid not in accessible]
            if missing:
                errors.append(f"Node '{node_id}' references inaccessible servers: {missing}.")

        agent_config_id = _collect_optional_int(
            data.get("agent_config_id"),
            field_name="agent_config_id",
            errors=errors,
            node_id=node_id,
        )
        agent_config = None
        if agent_config_id is not None:
            agent_config = AgentConfig.objects.filter(owner=owner, id=agent_config_id).prefetch_related("mcp_servers").first()
            if agent_config is None:
                errors.append(f"Node '{node_id}' references an inaccessible agent config: {agent_config_id}.")
            elif not _owner_can_use_mcp(owner) and agent_config.mcp_servers.exists():
                errors.append(f"Node '{node_id}' references an agent config with MCP servers, but MCP is admin-only.")

        mcp_server_ids = _collect_int_ids(
            data.get("mcp_server_ids"),
            field_name="mcp_server_ids",
            errors=errors,
            node_id=node_id,
        )
        if mcp_server_ids:
            if not _owner_can_use_mcp(owner):
                errors.append(f"Node '{node_id}' attaches MCP servers, but MCP is admin-only.")
            accessible = set(MCPServerPool.objects.filter(owner=owner, id__in=mcp_server_ids).values_list("id", flat=True))
            missing = [mid for mid in mcp_server_ids if mid not in accessible]
            if missing:
                errors.append(f"Node '{node_id}' references inaccessible MCP servers: {missing}.")

    if node_type == "agent/ssh_cmd":
        server_id = _collect_optional_int(data.get("server_id"), field_name="server_id", errors=errors, node_id=node_id)
        if server_id is not None and not Server.objects.filter(user=owner, id=server_id).exists():
            errors.append(f"Node '{node_id}' references an inaccessible server: {server_id}.")

    if node_type == "agent/mcp_call":
        mcp_server_id = _collect_optional_int(
            data.get("mcp_server_id"),
            field_name="mcp_server_id",
            errors=errors,
            node_id=node_id,
        )
        if mcp_server_id is not None:
            if not _owner_can_use_mcp(owner):
                errors.append(f"Node '{node_id}' uses an MCP call, but MCP is admin-only.")
            if not MCPServerPool.objects.filter(owner=owner, id=mcp_server_id).exists():
                errors.append(f"Node '{node_id}' references an inaccessible MCP server: {mcp_server_id}.")


def _normalized_handle(raw: Any) -> str:
    value = str(raw or "").strip()
    return value or "out"


def _allowed_outgoing_handles(node_type: str) -> set[str]:
    if node_type == "logic/condition":
        return {"true", "false"}
    if node_type == "logic/human_approval":
        return {"approved", "rejected", "timeout"}
    if node_type == "logic/telegram_input":
        return {"received", "timeout"}
    if node_type == "logic/wait":
        return {"done", "out"}
    if node_type in {"logic/parallel", "logic/merge"} or node_type in TRIGGER_NODE_TYPES:
        return {"out"}
    if node_type.startswith("agent/") or node_type.startswith("output/"):
        return {"success", "error", "out"}
    return {"out"}


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
        if node_type not in KNOWN_NODE_TYPES:
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

    structure_errors, id_to_node, outgoing_edges, incoming_edges = _validate_graph_structure(nodes, edges)
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

    for node in nodes:
        if isinstance(node, dict):
            _validate_node_references(node, owner, errors)

    return errors


def ensure_json_object(value: Any, *, label: str) -> tuple[dict[str, Any] | None, str | None]:
    if value in (None, ""):
        return {}, None
    if not isinstance(value, dict):
        return None, f"{label} must be a JSON object"
    return dict(value), None
