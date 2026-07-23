from __future__ import annotations

import re
from typing import Any

from .cron_schedule import validate_cron_expression
from .models import AgentConfig, MCPServerPool
from .pipeline_validation_schema import (
    PLACEHOLDER_RE,
)
from .pipeline_validation_schema import (
    mcp_arguments_from_node_data as _mcp_arguments_from_node_data,
)
from .pipeline_validation_schema import (
    parse_json_object_text as _parse_json_object_text,
)
from .pipeline_validation_schema import (
    validate_mcp_arguments_schema as _validate_mcp_arguments_schema,
)
from .services import get_owned_server_id_set, has_owned_server
from .skill_registry import normalise_skill_slugs, resolve_skills

PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._:@~/-]{0,127}$")
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


def _validate_package_names(
    data: dict[str, Any], *, field_name: str, errors: list[str], node_id: str, required: bool = False
) -> None:
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
    invalid = [
        package
        for package in packages
        if not PLACEHOLDER_RE.fullmatch(package) and not PACKAGE_NAME_RE.fullmatch(package)
    ]
    if invalid:
        errors.append(f"Node '{node_id}' field '{field_name}' contains invalid package names: {invalid}.")


def validate_node_references(node: dict[str, Any], owner, errors: list[str]) -> None:
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
            agent_config = (
                AgentConfig.objects.filter(owner=owner, id=agent_config_id).prefetch_related("mcp_servers").first()
            )
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
            accessible = set(
                MCPServerPool.objects.filter(owner=owner, id__in=mcp_server_ids).values_list("id", flat=True)
            )
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

    if node_type in {
        "ops/server_snapshot",
        "ops/log_query",
        "ops/file_action",
        "ops/package_action",
        "ops/disk_cleanup",
        "ops/backup_restore_check",
        "ops/service_action",
        "ops/docker_action",
        "ops/process_action",
    }:
        _validate_owned_optional_server(data, owner, errors, node_id)

    if node_type == "ops/server_snapshot":
        allowed_sections = {"overview", "services", "processes", "docker", "logs", "disk", "network", "packages"}
        raw_sections = data.get("sections")
        if raw_sections not in (None, "") and (
            not isinstance(raw_sections, list)
            or any(str(item or "").strip().lower() not in allowed_sections for item in raw_sections)
        ):
            errors.append(f"Node '{node_id}' field 'sections' must be a list of known server snapshot sections.")

    if node_type == "ops/log_query":
        _validate_choice(
            data,
            field_name="source",
            allowed={
                "journal",
                "service",
                "docker",
                "syslog",
                "messages",
                "auth",
                "nginx_error",
                "nginx_access",
                "apache_error",
                "apache_access",
            },
            errors=errors,
            node_id=node_id,
            required=False,
        )
        _validate_optional_int_range(
            data, field_name="lines", min_value=20, max_value=240, errors=errors, node_id=node_id
        )

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
        _validate_optional_int_range(
            data, field_name="max_bytes", min_value=1024, max_value=1048576, errors=errors, node_id=node_id
        )

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
        _validate_optional_int_range(
            data, field_name="min_age_days", min_value=1, max_value=365, errors=errors, node_id=node_id
        )
        _validate_optional_int_range(
            data, field_name="max_entries", min_value=1, max_value=500, errors=errors, node_id=node_id
        )
        _validate_optional_int_range(
            data, field_name="vacuum_time_days", min_value=1, max_value=365, errors=errors, node_id=node_id
        )
        _validate_optional_int_range(
            data, field_name="vacuum_size_mb", min_value=64, max_value=102400, errors=errors, node_id=node_id
        )

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
        _validate_optional_int_range(
            data, field_name="max_depth", min_value=1, max_value=5, errors=errors, node_id=node_id
        )
        _validate_optional_int_range(
            data, field_name="max_files", min_value=1, max_value=100, errors=errors, node_id=node_id
        )
        _validate_optional_int_range(
            data, field_name="max_age_hours", min_value=1, max_value=8760, errors=errors, node_id=node_id
        )

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
