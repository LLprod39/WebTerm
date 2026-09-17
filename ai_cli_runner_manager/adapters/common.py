"""Shared prompt and event helpers for subscription adapters."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from ai_cli_runner_manager.protocol import RunnerRequestV1
from app.ai_runtime import ProviderEventType, ProviderEventV1

_TOOL_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "tool_calls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    # Codex structured outputs require every object schema to
                    # declare ``additionalProperties: false``. Tool arguments
                    # are intentionally open-ended and vary per WebTerm tool,
                    # so carry them as JSON text here and validate the decoded
                    # object against the server-side allowlist below.
                    "arguments": {"type": "string"},
                },
                "required": ["name", "arguments"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["text", "tool_calls"],
    "additionalProperties": False,
}


def prompt_from_request(request: RunnerRequestV1) -> str:
    """Build text input without duplicating history on a resumed provider session."""
    if request.provider_session_id:
        for message in reversed(request.messages):
            if message.get("role") == "user":
                content = _message_content_text(message.get("content"))
                if content:
                    return _with_tool_protocol(content, request)
    sections: list[str] = []
    if request.system_prompt:
        sections.append(f"System instructions:\n{request.system_prompt}")
    for message in request.messages:
        content = _message_content_text(message.get("content"))
        if not content:
            continue
        role = str(message.get("role") or "user").upper()
        sections.append(f"{role}:\n{content}")
    return _with_tool_protocol("\n\n".join(sections).strip(), request)


def tool_output_schema(request: RunnerRequestV1) -> dict[str, Any] | None:
    if request.output_schema is not None:
        return request.output_schema
    return _TOOL_OUTPUT_SCHEMA if request.tools else None


def tool_response_events(raw: str, request: RunnerRequestV1) -> list[ProviderEventV1]:
    """Translate a constrained CLI JSON response into WebTerm tool events."""
    compact = str(raw or "").strip()
    if request.tools and not compact:
        return [_tool_protocol_error("empty response")]
    parsed = _extract_json_object(compact)
    if parsed is None:
        if request.tools:
            return [_tool_protocol_error("invalid JSON")]
        return [ProviderEventV1(ProviderEventType.TEXT_DELTA, {"text": raw})] if compact else []
    events: list[ProviderEventV1] = []
    text = str(parsed.get("text") or parsed.get("reply") or "")
    if text:
        events.append(ProviderEventV1(ProviderEventType.TEXT_DELTA, {"text": text}))
    allowed_by_norm = _allowed_tool_names(request.tools)
    calls = parsed.get("tool_calls")
    if not isinstance(calls, list):
        return [_tool_protocol_error("missing tool_calls")]
    for call in calls:
        if not isinstance(call, dict):
            return [_tool_protocol_error("invalid tool_calls entry")]
        raw_name = str(call.get("name") or "")
        resolved_name = _resolve_allowed_tool_name(raw_name, allowed_by_norm)
        arguments = _decode_tool_arguments(call.get("arguments"))
        if resolved_name is None:
            return [_tool_protocol_error(f"unknown tool {raw_name or '<empty>'}")]
        if not isinstance(arguments, dict):
            return [_tool_protocol_error(f"invalid arguments for {resolved_name}")]
        events.append(
            ProviderEventV1(
                ProviderEventType.TOOL_REQUEST,
                {
                    "id": str(call.get("id") or f"call_{uuid.uuid4().hex[:12]}"),
                    "name": resolved_name,
                    "arguments": arguments,
                },
            )
        )
    return events


def _tool_protocol_error(detail: str = "") -> ProviderEventV1:
    message = "CLI provider returned an invalid or unauthorized tool request"
    if detail:
        message = f"{message}: {detail}"
    return ProviderEventV1(
        ProviderEventType.ERROR,
        {
            "code": "provider_tool_protocol_invalid",
            "message": message,
            "retryable": False,
        },
    )


def _normalise_tool_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(name or "").strip()).strip("_")
    return cleaned[:64]


def _allowed_tool_names(tools: list[dict[str, Any]]) -> dict[str, str]:
    """Map normalised aliases to the canonical tool name from the request."""
    allowed: dict[str, str] = {}
    for tool in tools:
        function = tool.get("function") if isinstance(tool.get("function"), dict) else tool
        name = str(function.get("name") or tool.get("name") or "")
        if not name:
            continue
        allowed[_normalise_tool_name(name)] = name
        # Accept dotted action_type forms when present on the catalog entry.
        action_type = str(tool.get("action_type") or "")
        if action_type:
            allowed[_normalise_tool_name(action_type)] = name
    return allowed


def _resolve_allowed_tool_name(name: str, allowed_by_norm: dict[str, str]) -> str | None:
    if name in allowed_by_norm.values():
        return name
    return allowed_by_norm.get(_normalise_tool_name(name))


def _decode_tool_arguments(value: Any) -> dict[str, Any] | None:
    """Accept the strict-schema JSON transport and legacy object responses."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _message_content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for block in value:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "")
        if block_type == "text":
            parts.append(str(block.get("text") or ""))
        elif block_type == "tool_result":
            parts.append(f"Tool result for {block.get('tool_use_id')}:\n{str(block.get('content') or '')}")
        elif block_type == "tool_use":
            parts.append(
                f"Tool request {block.get('name')}: {json.dumps(block.get('input') or {}, ensure_ascii=False)}"
            )
    return "\n\n".join(part for part in parts if part).strip()


def _with_tool_protocol(prompt: str, request: RunnerRequestV1) -> str:
    if not request.tools:
        return prompt
    catalog = []
    for tool in request.tools:
        function = tool.get("function") if isinstance(tool.get("function"), dict) else tool
        name = str(function.get("name") or "")
        if not name:
            continue
        catalog.append(
            {
                "name": name,
                "description": str(function.get("description") or "")[:300],
                "parameters": function.get("parameters") or function.get("input_schema") or {"type": "object"},
            }
        )
    instruction = (
        "Use only the WebTerm tools listed below. You cannot execute them yourself. "
        "Encode each tool call's arguments as a JSON object string. "
        "Return exactly one JSON object with schema "
        '{"text":"short user-facing text","tool_calls":[{"name":"exact_name","arguments":"{}"}]}. '
        "Use an empty tool_calls array for a final text answer. No Markdown around JSON.\n"
        f"WebTerm tools: {json.dumps(catalog, ensure_ascii=False, separators=(',', ':'))}"
    )
    if request.target_id == "cursor_subscription":
        names = ", ".join(item["name"] for item in catalog)
        instruction = (
            f"{instruction}\n"
            "Cursor-specific rules: the FINAL assistant/result message MUST be only that JSON object. "
            "Do not put the JSON only in thinking. Do not wrap it in Markdown fences. "
            f"Tool names must match exactly one of: {names}."
        )
    return f"{prompt}\n\n{instruction}".strip()


def _looks_like_tool_protocol(value: dict[str, Any]) -> bool:
    return "tool_calls" in value and ("text" in value or "reply" in value)


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(raw or "").strip(), flags=re.IGNORECASE)
    if not text:
        return None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Prefer the first object that matches the tool protocol when prose wraps JSON.
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            parsed, _end = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and _looks_like_tool_protocol(parsed):
            return parsed

    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def safe_model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="json", by_alias=True)
        return payload if isinstance(payload, dict) else {}
    return {}
