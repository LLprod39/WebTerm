"""Tool registry bridge: AssistantActionSpec → LLM tools → execution."""

from __future__ import annotations

import json
from typing import Any

from app.assistant_actions import (
    AssistantActionContext,
    AssistantActionError,
    get_action_spec,
    list_action_specs,
)
from app.core.llm_tools import normalise_tool_name
from app.egress_redaction import payload_preview, redact_egress_payload
from core_ui.access import feature_allowed_for_user


def _redacted_result(payload: Any) -> Any:
    redacted, _report, _hashes = redact_egress_payload(payload if isinstance(payload, dict) else {"result": payload})
    return redacted


def specs_to_tools(user) -> list[dict[str, Any]]:
    """Build LLM tool list from registered action specs the user may access."""
    tools: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for spec in list_action_specs():
        if not feature_allowed_for_user(user, spec.required_feature):
            continue
        name = normalise_tool_name(spec.action_type)
        if name in seen_names:
            # Disambiguate collisions (rare)
            name = normalise_tool_name(f"{spec.action_type}_{spec.required_feature}")
        seen_names.add(name)
        schema = dict(spec.input_schema or {})
        if "type" not in schema:
            schema = {"type": "object", "properties": schema.get("properties") or {}, **{k: v for k, v in schema.items() if k != "properties"}}
            if "properties" not in schema:
                schema["properties"] = {}
            schema.setdefault("type", "object")
        risk_note = f" [risk={spec.risk}]"
        if spec.requires_confirmation:
            risk_note += " [requires_confirmation]"
        tools.append(
            {
                "name": name,
                "action_type": spec.action_type,
                "description": f"{spec.description}{risk_note}",
                "label": spec.label,
                "risk": spec.risk,
                "requires_confirmation": spec.requires_confirmation,
                "required_feature": spec.required_feature,
                "input_schema": schema,
            }
        )
    from core_ui.services.operator_policy import filter_tools_for_policy

    return filter_tools_for_policy(user, tools)


def resolve_action_type(tool_name: str, tools: list[dict[str, Any]] | None = None) -> str | None:
    name = normalise_tool_name(tool_name)
    if tools:
        for tool in tools:
            if normalise_tool_name(tool.get("name") or "") == name:
                return str(tool.get("action_type") or tool.get("name") or "")
            if normalise_tool_name(tool.get("action_type") or "") == name:
                return str(tool.get("action_type") or "")
    # Fallback: reverse common mapping dots→underscores by registry scan
    for spec in list_action_specs():
        if normalise_tool_name(spec.action_type) == name:
            return spec.action_type
    return None


def is_read_tool(action_type: str) -> bool:
    spec = get_action_spec(action_type)
    if spec is None:
        return False
    return spec.risk == "read" and not spec.requires_confirmation


def execute_tool(
    *,
    user,
    action_type: str,
    arguments: dict[str, Any],
    request=None,
    source: str = "operator_chat",
) -> dict[str, Any]:
    """Run a tool handler immediately (read tools / already confirmed mutates)."""
    spec = get_action_spec(action_type)
    if spec is None or spec.handler is None:
        return {"ok": False, "error": f"Unknown tool: {action_type}"}
    if not feature_allowed_for_user(user, spec.required_feature):
        return {"ok": False, "error": f"Feature access required: {spec.required_feature}"}
    try:
        result = spec.handler(
            AssistantActionContext(
                user=user,
                input_payload=dict(arguments or {}),
                request=request,
                source=source,
            )
        )
    except AssistantActionError as exc:
        return {"ok": False, "error": exc.message, "details": exc.details, "status": exc.status}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc) or "Tool execution failed"}
    if not isinstance(result, dict):
        result = {"result": result}
    safe = _redacted_result(result)
    preview = payload_preview(safe) if not isinstance(safe, dict) else safe
    return {"ok": True, "result": preview if isinstance(preview, dict) else safe}


def truncate_tool_result(result: dict[str, Any], *, max_chars: int = 6000) -> str:
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "…[truncated]"
