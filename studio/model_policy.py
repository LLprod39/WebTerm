"""Workspace model policy: non-admins cannot choose LLM models."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from core_ui.ai_model_policy import user_can_manage_ai_routing

AGENT_NODE_TYPES = {
    "agent/llm_query",
    "agent/react",
    "agent/multi",
}


def _sanitize_agent_node_data(data: dict[str, Any]) -> None:
    data["provider"] = "auto"
    data["model"] = ""
    data["provider_binding"] = {}
    if "model_preference" in data:
        data["model_preference"] = "auto"


def user_can_select_models(user) -> bool:
    return user_can_manage_ai_routing(user)


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
            _sanitize_agent_node_data(data)
        sanitized.append(node)
    return sanitized


def sanitize_pipeline_graph_selection_for_user(
    user,
    nodes: list | None,
    selected_node: dict[str, Any] | None,
) -> tuple[list, dict[str, Any] | None]:
    """Sanitize both a draft graph and its separately persisted selected node."""

    sanitized_nodes = sanitize_pipeline_nodes_for_user(user, nodes)
    if not isinstance(selected_node, dict):
        return sanitized_nodes, None
    selected_id = str(selected_node.get("id") or "")
    if selected_id:
        match = next(
            (
                node
                for node in sanitized_nodes
                if isinstance(node, dict) and str(node.get("id") or "") == selected_id
            ),
            None,
        )
        if match is not None:
            return sanitized_nodes, match
    sanitized_selected = sanitize_pipeline_nodes_for_user(user, [selected_node])
    return sanitized_nodes, sanitized_selected[0] if sanitized_selected else None


def sanitize_pipeline_draft_response_for_user(
    user,
    response: dict[str, Any],
    preview_nodes: list | None,
) -> tuple[dict[str, Any], list]:
    """Remove ordinary-user routing choices from every persisted draft graph field."""

    sanitized_nodes = sanitize_pipeline_nodes_for_user(user, preview_nodes)
    if user_can_select_models(user):
        return response, sanitized_nodes

    sanitized_response = deepcopy(response)
    graph_patch = sanitized_response.get("graph_patch")
    if isinstance(graph_patch, dict) and isinstance(graph_patch.get("nodes"), list):
        graph_patch["nodes"] = sanitize_pipeline_nodes_for_user(user, graph_patch["nodes"])

    target_node_id = str(sanitized_response.get("target_node_id") or "")
    target_node = next(
        (
            node
            for node in sanitized_nodes
            if isinstance(node, dict) and str(node.get("id") or "") == target_node_id
        ),
        None,
    )
    target_type = str(target_node.get("type") or "") if isinstance(target_node, dict) else ""
    node_patch = sanitized_response.get("node_patch")
    if target_type in AGENT_NODE_TYPES and isinstance(node_patch, dict):
        _sanitize_agent_node_data(node_patch)
    return sanitized_response, sanitized_nodes
