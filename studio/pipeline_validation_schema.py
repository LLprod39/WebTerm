from __future__ import annotations

import json
import re
from typing import Any

PLACEHOLDER_RE = re.compile(r"^\{[A-Za-z_][A-Za-z0-9_]*\}$")


def parse_json_object_text(raw: Any, *, field_name: str, errors: list[str], node_id: str) -> dict[str, Any] | None:
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


def mcp_arguments_from_node_data(data: dict[str, Any], *, errors: list[str], node_id: str) -> dict[str, Any] | None:
    if "arguments_text" in data:
        parsed = parse_json_object_text(
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


def validate_mcp_arguments_schema(
    data: dict[str, Any],
    arguments: dict[str, Any],
    *,
    errors: list[str],
    node_id: str,
) -> None:
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
