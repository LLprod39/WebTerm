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


# Keys models commonly emit that should map onto the canonical schema key.
_ARG_KEY_ALIASES = {
    "cmd": "command",
    "shell": "command",
    "command_line": "command",
    "commandline": "command",
    "host": "server",
    "hostname": "server",
    "server_name": "server",
    "target": "server",
    "servers": "server_ids",
    "server_names": "server_ids",
    "hosts": "server_ids",
    "dry": "dry_run",
    "check": "check_mode",
    "checkmode": "check_mode",
}


def _coerce_server_id(user, value: Any) -> int | None:
    """Best-effort resolve a server reference (id, numeric string, or name) to an id."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, dict):
        if value.get("id") is not None:
            try:
                return int(value["id"])
            except (TypeError, ValueError):
                return None
        value = value.get("name") or value.get("hostname") or ""
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s.isdigit():
            return int(s)
        from servers.views.server_helpers import _accessible_servers_queryset

        qs = _accessible_servers_queryset(user)
        row = qs.filter(name__iexact=s).first() or qs.filter(name__icontains=s).first()
        return int(row.id) if row else None
    return None


def normalize_tool_arguments(user, action_type: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Coerce loose model arguments onto the canonical tool schema.

    Tolerates key aliases (cmd→command, host→server, …), resolves server
    names/numeric strings to ids, and coerces id lists. Never touches free-text
    fields like ``command``. Best-effort: unresolved values are left as-is so the
    tool handler can still surface a precise error.
    """
    if not isinstance(arguments, dict):
        return {}
    args: dict[str, Any] = {}
    for key, value in arguments.items():
        canonical = _ARG_KEY_ALIASES.get(str(key), str(key))
        # Do not clobber an explicit canonical key with an alias duplicate.
        if canonical in args and canonical != key:
            continue
        args[canonical] = value

    # A single "server" reference collapses into server_id (or a q hint for lookups).
    if "server" in args and "server_id" not in args:
        raw = args.pop("server")
        sid = _coerce_server_id(user, raw)
        if sid is not None:
            args["server_id"] = sid
        elif isinstance(raw, (str, int)):
            args.setdefault("q", str(raw))

    if "server_id" in args:
        sid = _coerce_server_id(user, args["server_id"])
        if sid is not None:
            args["server_id"] = sid

    if isinstance(args.get("server_ids"), list):
        resolved: list[int] = []
        for item in args["server_ids"]:
            sid = _coerce_server_id(user, item)
            if sid is not None and sid not in resolved:
                resolved.append(sid)
        if resolved:
            args["server_ids"] = resolved

    return args


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
    """Serialize tool result for the model; keep name_index when truncating large inventories."""
    # Prefer a stable order so critical lookup fields survive truncation.
    if isinstance(result, dict):
        payload = result.get("result") if isinstance(result.get("result"), dict) else result
        if isinstance(payload, dict) and (
            "name_index" in payload or payload.get("ui_table") is False
        ):
            preferred_keys = (
                "ok",
                "found",
                "query",
                "server_id",
                "server_name",
                "match",
                "reply_hint",
                "name_index",
                "count",
                "status_counts",
                "note",
                "error",
                "ui_table",
                "match_count",
                "matches",
                "servers",
            )
            ordered: dict[str, Any] = {}
            for key in preferred_keys:
                if key in payload:
                    ordered[key] = payload[key]
            for key, value in payload.items():
                if key not in ordered:
                    ordered[key] = value
            if result is not payload and "result" in result:
                wrapped = {**result, "result": ordered}
                text = json.dumps(wrapped, ensure_ascii=False, default=str)
            else:
                text = json.dumps(ordered, ensure_ascii=False, default=str)
            if len(text) <= max_chars:
                return text
            # Drop bulky arrays first, keep name_index / match
            slim = {
                k: v
                for k, v in ordered.items()
                if k not in {"servers", "matches", "sample_names", "alerts", "agents"}
            }
            slim_text = json.dumps(
                {**result, "result": slim} if result is not payload and "result" in result else slim,
                ensure_ascii=False,
                default=str,
            )
            if len(slim_text) <= max_chars:
                return slim_text + "…[rows omitted]"
            return slim_text[: max_chars - 20] + "…[truncated]"

    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "…[truncated]"
