from __future__ import annotations

import re
from typing import Any

from studio.services.pipeline_template_text import _text

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_RUNTIME_PLACEHOLDER_NAMES = {"approve_url", "reject_url"}
_MONITORING_RUNTIME_PLACEHOLDER_NAMES = {
    "alert_id",
    "alert_source",
    "alert_severity",
    "alert_type",
    "service_name",
}
_OPERATIONAL_PLACEHOLDER_FIELDS = {
    "arguments",
    "packages",
    "path",
    "service",
    "url",
    "preflight_commands",
    "verification_commands",
}


def _replace_bound_placeholders(value: Any, bindings: dict[str, str]) -> Any:
    if isinstance(value, str):
        return _PLACEHOLDER_RE.sub(lambda match: bindings.get(match.group(1), match.group(0)), value)
    if isinstance(value, list):
        return [_replace_bound_placeholders(item, bindings) for item in value]
    if isinstance(value, dict):
        return {key: _replace_bound_placeholders(item, bindings) for key, item in value.items()}
    return value


def _find_placeholders(value: Any) -> set[str]:
    if isinstance(value, str):
        return set(_PLACEHOLDER_RE.findall(value))
    if isinstance(value, list):
        result: set[str] = set()
        for item in value:
            result.update(_find_placeholders(item))
        return result
    if isinstance(value, dict):
        result: set[str] = set()
        for item in value.values():
            result.update(_find_placeholders(item))
        return result
    return set()


def _trigger_runtime_placeholders(template: dict[str, Any]) -> set[str]:
    placeholders: set[str] = set()
    for node in template.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node_type = node.get("type")
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        if node_type == "trigger/webhook":
            payload_map = data.get("webhook_payload_map")
            if isinstance(payload_map, dict):
                placeholders.update(_text(key) for key in payload_map if _text(key))
        elif node_type == "trigger/monitoring":
            placeholders.update(_MONITORING_RUNTIME_PLACEHOLDER_NAMES)
    return placeholders


def _is_runtime_placeholder(name: str, webhook_placeholders: set[str]) -> bool:
    return (
        name in _RUNTIME_PLACEHOLDER_NAMES
        or name in webhook_placeholders
        or name.endswith("_output")
        or name.endswith("_error")
    )


def _unresolved_operational_placeholders(
    template: dict[str, Any],
    *,
    bindings: dict[str, str],
) -> tuple[list[str], list[str]]:
    trigger_placeholders = _trigger_runtime_placeholders(template)
    missing: set[str] = set()
    runtime: set[str] = set()
    for node in template.get("nodes", []):
        if not isinstance(node, dict) or not isinstance(node.get("data"), dict):
            continue
        data = node["data"]
        for field in _OPERATIONAL_PLACEHOLDER_FIELDS:
            if field not in data:
                continue
            for placeholder in _find_placeholders(data[field]):
                if placeholder in bindings:
                    continue
                if _is_runtime_placeholder(placeholder, trigger_placeholders):
                    runtime.add(placeholder)
                else:
                    missing.add(placeholder)
    return sorted(missing), sorted(runtime)
