"""Workspace model policy: non-admins cannot choose LLM models."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

AGENT_NODE_TYPES = {
    "agent/llm_query",
    "agent/react",
    "agent/multi",
}


def user_can_select_models(user) -> bool:
    return bool(user and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)))


def workspace_default_agent_model() -> tuple[str, str]:
    """Return (provider, model) from admin settings."""
    try:
        from app.core.model_config import model_manager

        config = model_manager.config
        provider = (
            (getattr(config, "agent_llm_provider", "") or "")
            or (getattr(config, "default_provider", "") or "")
            or (getattr(config, "internal_llm_provider", "") or "")
            or "grok"
        ).strip()
        if provider == "auto":
            provider = (getattr(config, "internal_llm_provider", "") or "grok").strip() or "grok"
        model = (model_manager.get_agent_model(provider) or "").strip()
        if not model:
            model = (model_manager.get_chat_model(provider) or "").strip()
        return provider, model
    except Exception:
        return "grok", "grok-3"


def forced_agent_model_value() -> str:
    """Legacy single-field model string used by AgentConfig.model."""
    provider, model = workspace_default_agent_model()
    return model or provider or "auto"


def sanitize_agent_model_fields(user, data: dict[str, Any] | None) -> dict[str, Any]:
    """Force workspace defaults for non-admin agent payloads."""
    payload = dict(data or {})
    if user_can_select_models(user):
        return payload
    provider, model = workspace_default_agent_model()
    payload["provider"] = "auto"
    payload["model"] = model or forced_agent_model_value()
    # Keep explicit provider empty/auto so runtime uses workspace defaults.
    if "model_preference" in payload:
        payload["model_preference"] = "auto"
    return payload


def sanitize_pipeline_nodes_for_user(user, nodes: list | None) -> list:
    """Force provider/model on agent nodes for non-admin users."""
    if not isinstance(nodes, list):
        return []
    if user_can_select_models(user):
        return nodes

    sanitized: list[Any] = []
    for raw in nodes:
        node = deepcopy(raw) if isinstance(raw, dict) else raw
        if not isinstance(node, dict):
            sanitized.append(node)
            continue
        node_type = str(node.get("type") or node.get("data", {}).get("type") or "")
        data = node.get("data")
        if not isinstance(data, dict):
            data = {}
            node["data"] = data
        effective_type = str(data.get("type") or node_type or "")
        if effective_type in AGENT_NODE_TYPES or node_type in AGENT_NODE_TYPES:
            # Always use workspace default; hide per-user model choice.
            data["provider"] = "auto"
            data["model"] = ""
            # If a concrete model was previously set, clear it so runtime inherits admin default.
            if not data.get("agent_config_id") and not data.get("agent_id"):
                data["model"] = ""
                data["provider"] = "auto"
        sanitized.append(node)
    return sanitized
