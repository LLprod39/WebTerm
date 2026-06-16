from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from typing import Any

from .cron_schedule import validate_cron_expression
from .execution_policy import validate_execution_policy_guardrails
from .models import CURRENT_PIPELINE_GRAPH_VERSION, AgentConfig, MCPServerPool
from .node_manifest import KNOWN_NODE_TYPES, OPS_NODE_TYPES, TRIGGER_NODE_TYPES, allowed_source_handles
from .services import get_owned_server_id_set, has_owned_server
from .skill_registry import normalise_skill_slugs, resolve_skills

PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._:@~/-]{0,127}$")
PLACEHOLDER_RE = re.compile(r"^\{[A-Za-z_][A-Za-z0-9_]*\}$")
SUDO_POLICY_VALUES = {"inherit", "disabled", "ask", "approved"}


def _owner_can_use_mcp(owner) -> bool:
    return bool(owner and getattr(owner, "is_staff", False))


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


def _validate_owned_optional_server(data: dict[str, Any], owner, errors: list[str], node_id: str) -> None:
    server_id = _collect_optional_int(data.get("server_id"), field_name="server_id", errors=errors, node_id=node_id)
    if server_id is not None and not has_owned_server(owner, server_id):
        errors.append(f"Node '{node_id}' references an inaccessible server: {server_id}.")


def _validate_choice(
    data: dict[str, Any],
    *,
    field_name: str,
    allowed: set[str],
    errors: list[str],
    node_id: str,
    required: bool = False,
) -> None:
    value = str(data.get(field_name) or "").strip().lower()
    if not value:
        if required:
            errors.append(f"Node '{node_id}' field '{field_name}' is required.")
        return
    if value not in allowed:
        errors.append(f"Node '{node_id}' field '{field_name}' must be one of: {', '.join(sorted(allowed))}.")


def _validate_optional_int_list(data: dict[str, Any], *, field_name: str, errors: list[str], node_id: str) -> None:
    raw = data.get(field_name)
    if raw in (None, ""):
        return
    if not isinstance(raw, list):
        errors.append(f"Node '{node_id}' field '{field_name}' must be a list of integers.")
        return
    for item in raw:
        try:
            int(item)
        except (TypeError, ValueError):
            errors.append(f"Node '{node_id}' field '{field_name}' contains an invalid integer: {item!r}.")


def _validate_optional_int_range(
    data: dict[str, Any],
    *,
    field_name: str,
    min_value: int,
    max_value: int,
    errors: list[str],
    node_id: str,
) -> None:
    raw = data.get(field_name)
    if raw in (None, ""):
        return
    try:
        value = int(raw)
    except (TypeError, ValueError):
        errors.append(f"Node '{node_id}' field '{field_name}' must be an integer.")
        return
    if value < min_value or value > max_value:
        errors.append(f"Node '{node_id}' field '{field_name}' must be between {min_value} and {max_value}.")


def _validate_package_names(data: dict[str, Any], *, field_name: str, errors: list[str], node_id: str, required: bool = False) -> None:
    raw = data.get(field_name)
    if raw in (None, ""):
        if required:
            errors.append(f"Node '{node_id}' field '{field_name}' is required.")
        return
    source_items = raw if isinstance(raw, list) else [raw]
    items: list[str] = []
    for item in source_items:
        items.extend(part for part in re.split(r"[\s,]+", str(item or "")) if part)
    packages = [str(item or "").strip() for item in items if str(item or "").strip()]
    if required and not packages:
        errors.append(f"Node '{node_id}' field '{field_name}' is required.")
        return
    invalid = [package for package in packages if not PLACEHOLDER_RE.fullmatch(package) and not PACKAGE_NAME_RE.fullmatch(package)]
    if invalid:
        errors.append(f"Node '{node_id}' field '{field_name}' contains invalid package names: {invalid}.")


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


def _is_template_placeholder(value: Any) -> bool:
    return isinstance(value, str) and bool(PLACEHOLDER_RE.fullmatch(value.strip()))


def _has_schema_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _mcp_arguments_from_node_data(data: dict[str, Any], *, errors: list[str], node_id: str) -> dict[str, Any] | None:
    if "arguments_text" in data:
        parsed = _parse_json_object_text(
            data.get("arguments_text"),
            field_name="arguments_text",
            errors=errors,
            node_id=node_id,
        )
        if parsed is not None:
            return parsed

    raw_arguments = data.get("arguments")
    if raw_arguments in (None, ""):
        return {}
    if isinstance(raw_arguments, dict):
        return raw_arguments
    errors.append(f"Node '{node_id}' field 'arguments' must be a JSON object.")
    return None


def _schema_type_matches(value: Any, expected_type: str) -> bool:
    if _is_template_placeholder(value):
        return True
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return True
        if isinstance(value, str):
            try:
                int(value)
                return True
            except ValueError:
                return False
        return False
    if expected_type == "number":
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return True
        if isinstance(value, str):
            try:
                float(value)
                return True
            except ValueError:
                return False
        return False
    if expected_type == "boolean":
        if isinstance(value, bool):
            return True
        return isinstance(value, str) and value.strip().lower() in {"true", "false", "1", "0", "yes", "no"}
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    return True


def _validate_mcp_arguments_schema(data: dict[str, Any], arguments: dict[str, Any], *, errors: list[str], node_id: str) -> None:
    schema = data.get("input_schema")
    if not isinstance(schema, dict):
        return
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return
    required = schema.get("required") or []
    if isinstance(required, list):
        for field_name in required:
            field = str(field_name)
            if not _has_schema_value(arguments.get(field)):
                errors.append(f"Node '{node_id}' MCP argument '{field}' is required by input_schema.")

    for field_name, property_schema in properties.items():
        if not isinstance(property_schema, dict) or field_name not in arguments:
            continue
        value = arguments.get(field_name)
        if not _has_schema_value(value):
            continue
        enum_values = property_schema.get("enum")
        if isinstance(enum_values, list) and enum_values and not _is_template_placeholder(value):
            allowed = [str(item) for item in enum_values]
            if str(value) not in allowed:
                errors.append(f"Node '{node_id}' MCP argument '{field_name}' must be one of: {', '.join(allowed)}.")
                continue
        expected_type = property_schema.get("type")
        if isinstance(expected_type, list):
            allowed_types = [str(item) for item in expected_type]
        elif isinstance(expected_type, str):
            allowed_types = [expected_type]
        else:
            allowed_types = []
        if allowed_types and not any(_schema_type_matches(value, item) for item in allowed_types):
            errors.append(f"Node '{node_id}' MCP argument '{field_name}' must match schema type: {' or '.join(allowed_types)}.")


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

    if node_type == "trigger/webhook":
        payload_map = data.get("webhook_payload_map", {})
        if payload_map not in (None, "") and not isinstance(payload_map, dict):
            errors.append(f"Node '{node_id}' webhook_payload_map must be a JSON object.")

    if node_type == "trigger/schedule":
        cron_expression = str(data.get("cron_expression") or "").strip()
        if cron_expression:
            is_valid, error = validate_cron_expression(cron_expression)
            if not is_valid:
                errors.append(f"Node '{node_id}' has an invalid cron expression: {error}.")

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
            accessible = get_owned_server_id_set(owner, server_ids)
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
        sudo_policy = data.get("sudo_policy")
        if sudo_policy not in (None, "") and str(sudo_policy) not in SUDO_POLICY_VALUES:
            errors.append(f"Node '{node_id}' field 'sudo_policy' must be one of: inherit, disabled, ask, approved.")

        server_ids = _collect_int_ids(data.get("server_ids"), field_name="server_ids", errors=errors, node_id=node_id)
        if server_ids:
            accessible = get_owned_server_id_set(owner, server_ids)
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
        sudo_policy = data.get("sudo_policy")
        if sudo_policy not in (None, "") and str(sudo_policy) not in {"disabled", "ask", "approved"}:
            errors.append(f"Node '{node_id}' field 'sudo_policy' must be one of: disabled, ask, approved.")
        _validate_owned_optional_server(data, owner, errors, node_id)

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
        mcp_arguments = _mcp_arguments_from_node_data(data, errors=errors, node_id=node_id)
        if mcp_arguments is not None:
            _validate_mcp_arguments_schema(data, mcp_arguments, errors=errors, node_id=node_id)

    if node_type in {"ops/server_snapshot", "ops/log_query", "ops/file_action", "ops/package_action", "ops/disk_cleanup", "ops/backup_restore_check", "ops/service_action", "ops/docker_action", "ops/process_action"}:
        _validate_owned_optional_server(data, owner, errors, node_id)

    if node_type == "ops/server_snapshot":
        allowed_sections = {"overview", "services", "processes", "docker", "logs", "disk", "network", "packages"}
        raw_sections = data.get("sections")
        if raw_sections not in (None, ""):
            if not isinstance(raw_sections, list) or any(str(item or "").strip().lower() not in allowed_sections for item in raw_sections):
                errors.append(f"Node '{node_id}' field 'sections' must be a list of known server snapshot sections.")

    if node_type == "ops/log_query":
        _validate_choice(
            data,
            field_name="source",
            allowed={"journal", "service", "docker", "syslog", "messages", "auth", "nginx_error", "nginx_access", "apache_error", "apache_access"},
            errors=errors,
            node_id=node_id,
            required=False,
        )
        _validate_optional_int_range(data, field_name="lines", min_value=20, max_value=240, errors=errors, node_id=node_id)

    if node_type == "ops/file_action":
        _validate_choice(
            data,
            field_name="action",
            allowed={"read", "write"},
            errors=errors,
            node_id=node_id,
            required=False,
        )
        if not str(data.get("path") or "").strip():
            errors.append(f"Node '{node_id}' field 'path' is required.")
        _validate_optional_int_range(data, field_name="max_bytes", min_value=1024, max_value=1048576, errors=errors, node_id=node_id)

    if node_type == "ops/package_action":
        _validate_choice(
            data,
            field_name="action",
            allowed={"list_updates", "install", "update", "remove"},
            errors=errors,
            node_id=node_id,
            required=False,
        )
        package_action = str(data.get("action") or "list_updates").strip().lower()
        _validate_package_names(
            data,
            field_name="packages",
            errors=errors,
            node_id=node_id,
            required=package_action in {"install", "update", "remove"},
        )

    if node_type == "ops/disk_cleanup":
        _validate_choice(
            data,
            field_name="action",
            allowed={"inspect", "journal_vacuum", "tmp_cleanup"},
            errors=errors,
            node_id=node_id,
            required=False,
        )
        _validate_optional_int_range(data, field_name="min_age_days", min_value=1, max_value=365, errors=errors, node_id=node_id)
        _validate_optional_int_range(data, field_name="max_entries", min_value=1, max_value=500, errors=errors, node_id=node_id)
        _validate_optional_int_range(data, field_name="vacuum_time_days", min_value=1, max_value=365, errors=errors, node_id=node_id)
        _validate_optional_int_range(data, field_name="vacuum_size_mb", min_value=64, max_value=102400, errors=errors, node_id=node_id)

    if node_type == "ops/backup_restore_check":
        _validate_choice(
            data,
            field_name="action",
            allowed={"inspect", "verify_latest"},
            errors=errors,
            node_id=node_id,
            required=False,
        )
        if not str(data.get("path") or "").strip():
            errors.append(f"Node '{node_id}' field 'path' is required.")
        _validate_optional_int_range(data, field_name="max_depth", min_value=1, max_value=5, errors=errors, node_id=node_id)
        _validate_optional_int_range(data, field_name="max_files", min_value=1, max_value=100, errors=errors, node_id=node_id)
        _validate_optional_int_range(data, field_name="max_age_hours", min_value=1, max_value=8760, errors=errors, node_id=node_id)

    if node_type == "ops/service_action":
        _validate_choice(
            data,
            field_name="action",
            allowed={"start", "stop", "restart", "reload"},
            errors=errors,
            node_id=node_id,
            required=True,
        )

    if node_type == "ops/docker_action":
        _validate_choice(
            data,
            field_name="action",
            allowed={"start", "stop", "restart"},
            errors=errors,
            node_id=node_id,
            required=True,
        )

    if node_type == "ops/process_action":
        _validate_choice(
            data,
            field_name="action",
            allowed={"terminate", "kill_force"},
            errors=errors,
            node_id=node_id,
            required=True,
        )

    if node_type == "ops/http_check":
        method = str(data.get("method") or "GET").strip().upper()
        if method not in {"GET", "HEAD"}:
            errors.append(f"Node '{node_id}' field 'method' must be GET or HEAD.")
        _validate_optional_int_list(data, field_name="expected_status", errors=errors, node_id=node_id)

    if node_type == "ops/alert_update":
        _validate_choice(
            data,
            field_name="action",
            allowed={"resolve"},
            errors=errors,
            node_id=node_id,
            required=False,
        )

    if node_type == "logic/condition":
        check_type = str(data.get("check_type") or "").strip()
        if check_type in {"contains", "not_contains"} and not str(data.get("check_value") or "").strip():
            errors.append(f"Node '{node_id}' field 'check_value' is required for {check_type}.")

    if node_type == "output/webhook":
        _validate_optional_int_range(
            data,
            field_name="timeout_seconds",
            min_value=1,
            max_value=120,
            errors=errors,
            node_id=node_id,
        )
        for field_name in ("headers", "extra_payload"):
            raw = data.get(field_name)
            if raw not in (None, "") and not isinstance(raw, dict):
                errors.append(f"Node '{node_id}' field '{field_name}' must be a JSON object.")


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
    errors.extend(
        validate_execution_policy_guardrails(
            nodes=nodes,
            id_to_node=id_to_node,
            incoming_edges=incoming_edges,
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
