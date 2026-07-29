"""Write-only managed credentials for Studio pipeline nodes."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from core_ui.managed_secrets import get_studio_pipeline_secrets, set_studio_pipeline_secrets

PIPELINE_NODE_SECRET_FIELDS = (
    "bot_token",
    "tg_bot_token",
    "telegram_bot_token",
    "smtp_password",
)

PIPELINE_RUN_PUBLIC_NODE_STATE_FIELDS = frozenset(
    {
        "agent_run_id",
        "decision",
        "error",
        "finished_at",
        "output",
        "passed",
        "routing_ports",
        "started_at",
        "status",
    }
)

_RUNTIME_TOKEN_QUERY_RE = re.compile(
    r"(?i)([?&](?:approval_token|token)=)[^&\s\"'<>]+",
)


def _configured_key(secret_key: str) -> str:
    return f"{secret_key}_configured"


def _clear_key(secret_key: str) -> str:
    return f"{secret_key}_clear"


def _secret_text(value: Any) -> str:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return ""
    return str(value).strip()


def prepare_pipeline_nodes_for_storage(
    nodes: Any,
    *,
    existing_secrets: dict[str, dict[str, str]] | None = None,
) -> tuple[Any, dict[str, dict[str, str]]]:
    """Strip credentials from graph JSON and produce the next encrypted envelope."""
    if not isinstance(nodes, list):
        return deepcopy(nodes), dict(existing_secrets or {})

    existing = deepcopy(existing_secrets or {})
    next_secrets: dict[str, dict[str, str]] = {}
    safe_nodes: list[Any] = []

    for raw_node in nodes:
        if not isinstance(raw_node, dict):
            safe_nodes.append(deepcopy(raw_node))
            continue
        node = deepcopy(raw_node)
        node_id = str(node.get("id") or "").strip()
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        data = dict(data)
        node_secrets = dict(existing.get(node_id) or {}) if node_id else {}

        for secret_key in PIPELINE_NODE_SECRET_FIELDS:
            clear_requested = data.pop(_clear_key(secret_key), False) is True
            supplied = secret_key in data
            supplied_value = _secret_text(data.pop(secret_key, None)) if supplied else ""
            if clear_requested:
                node_secrets.pop(secret_key, None)
            elif supplied_value:
                node_secrets[secret_key] = supplied_value

            marker = _configured_key(secret_key)
            if _secret_text(node_secrets.get(secret_key)):
                data[marker] = True
            else:
                data.pop(marker, None)

        node["data"] = data
        safe_nodes.append(node)
        if node_id and node_secrets:
            next_secrets[node_id] = node_secrets

    return safe_nodes, next_secrets


def secure_pipeline_nodes_for_storage(pipeline_id: int | None, nodes: Any) -> tuple[Any, dict[str, dict[str, str]]]:
    existing = get_studio_pipeline_secrets(pipeline_id) if pipeline_id else {}
    return prepare_pipeline_nodes_for_storage(nodes, existing_secrets=existing)


def persist_pipeline_secrets(pipeline_id: int, secrets_by_node: dict[str, dict[str, str]]) -> None:
    set_studio_pipeline_secrets(pipeline_id, secrets_by_node)


def hydrate_pipeline_node_data(pipeline_id: int, node_id: str, node_data: Any) -> dict[str, Any]:
    """Resolve credentials only for the node about to execute."""
    hydrated = dict(node_data) if isinstance(node_data, dict) else {}
    managed = get_studio_pipeline_secrets(pipeline_id).get(str(node_id or ""), {})
    for secret_key in PIPELINE_NODE_SECRET_FIELDS:
        value = _secret_text(managed.get(secret_key))
        if value:
            hydrated[secret_key] = value
    return hydrated


def get_pipeline_node_secret(pipeline_id: int, node_id: str, *keys: str) -> str:
    managed = get_studio_pipeline_secrets(pipeline_id).get(str(node_id or ""), {})
    for key in keys:
        value = _secret_text(managed.get(str(key)))
        if value:
            return value
    return ""


def redact_pipeline_nodes(nodes: Any) -> Any:
    """Defensive output/prompt scrub for current and legacy graph snapshots."""
    if not isinstance(nodes, list):
        return redact_pipeline_secret_values(nodes)
    return [redact_pipeline_secret_values(node) for node in nodes]


def _redact_runtime_token_text(value: str) -> str:
    return _RUNTIME_TOKEN_QUERY_RE.sub(r"\1[REDACTED]", value)


def _serialize_public_node_state_value(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_runtime_token_text(value)
    if isinstance(value, dict):
        return {str(key): _serialize_public_node_state_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_public_node_state_value(item) for item in value]
    return value


def serialize_pipeline_node_state(state: Any) -> dict[str, Any]:
    """Return the explicit public contract for one persisted node state."""
    if not isinstance(state, dict):
        return {}
    return {
        key: _serialize_public_node_state_value(state[key])
        for key in PIPELINE_RUN_PUBLIC_NODE_STATE_FIELDS
        if key in state
    }


def serialize_pipeline_node_states(node_states: Any) -> dict[str, dict[str, Any]]:
    """Return node states without runtime-only credentials or delivery links."""
    if not isinstance(node_states, dict):
        return {}
    return {
        str(node_id): serialize_pipeline_node_state(state)
        for node_id, state in node_states.items()
        if isinstance(state, dict)
    }


def redact_pipeline_secret_values(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {
            str(key): redact_pipeline_secret_values(item)
            for key, item in value.items()
            if str(key) not in PIPELINE_NODE_SECRET_FIELDS
            and str(key) not in {_clear_key(secret_key) for secret_key in PIPELINE_NODE_SECRET_FIELDS}
        }
        for secret_key in PIPELINE_NODE_SECRET_FIELDS:
            if _secret_text(value.get(secret_key)):
                redacted[_configured_key(secret_key)] = True
        return redacted
    if isinstance(value, list):
        return [redact_pipeline_secret_values(item) for item in value]
    if isinstance(value, tuple):
        return [redact_pipeline_secret_values(item) for item in value]
    if isinstance(value, str):
        return _redact_runtime_token_text(value)
    return value
