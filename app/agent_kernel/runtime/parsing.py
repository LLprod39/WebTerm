"""
Shared response-parsing utilities for agent engines.

Both AgentEngine and MultiAgentEngine use the same ReAct-style
THOUGHT / ACTION protocol.  This module provides a single canonical
implementation so bug fixes apply everywhere.

Also accepts an optional **JSON action** form (provider-agnostic JSON mode)
as an alternate to free-text ``ACTION: tool {...}``. Text parsing remains
the fallback when JSON is absent or invalid.
"""

from __future__ import annotations

import json
import re
from typing import Any

_ACTION_NAME_RE = re.compile(r"ACTION:\s*([\w_]+)\s*", re.DOTALL)
_THOUGHT_RE = re.compile(r"THOUGHT:\s*(.+?)(?=ACTION:|$)", re.DOTALL)

# Keys accepted for tool name in JSON action objects.
_TOOL_KEYS = ("tool", "action", "name", "tool_name")
_ARGS_KEYS = ("args", "arguments", "parameters", "input", "params")
_THOUGHT_KEYS = ("thinking", "thought", "reason", "reasoning")


def parse_action(response: str) -> tuple[str | None, dict]:
    """Надёжный парсинг ACTION: tool_name {...}.

    Использует json.JSONDecoder.raw_decode вместо regex {.*?},
    чтобы корректно обрабатывать многострочные JSON-объекты с отступами.
    """
    name_match = _ACTION_NAME_RE.search(response)
    if not name_match:
        return None, {}

    action_name = name_match.group(1).strip()
    json_start = name_match.end()

    # Пропускаем пробелы до '{'
    while json_start < len(response) and response[json_start] in " \t\n\r":
        json_start += 1

    if json_start >= len(response) or response[json_start] != "{":
        return action_name, {}

    try:
        decoder = json.JSONDecoder()
        action_args, _ = decoder.raw_decode(response, json_start)
        if isinstance(action_args, dict):
            return action_name, action_args
    except json.JSONDecodeError:
        pass

    return action_name, {}


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Try to parse a top-level JSON object from model text (optional fences)."""
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    # Prefer first {...} slice when prose wraps JSON.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = cleaned[start : end + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        try:
            decoder = json.JSONDecoder()
            data, _ = decoder.raw_decode(cleaned, start)
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def parse_json_action(response: str) -> tuple[str, str | None, dict] | None:
    """Parse a JSON action object if present.

    Accepted shapes (examples)::

        {"tool": "ssh_execute", "args": {"command": "uptime"}, "thinking": "..."}
        {"action": "ssh_execute", "arguments": {...}}
        {"tool": "done", "final_text": "..."}  # tool with empty args ok

    Returns ``(thought, tool_name, args)`` or ``None`` if not a valid JSON action.
    """
    data = _extract_json_object(response)
    if not data:
        return None

    tool_name: str | None = None
    for key in _TOOL_KEYS:
        raw = data.get(key)
        if isinstance(raw, str) and raw.strip():
            tool_name = raw.strip()
            break
    if not tool_name:
        return None
    # Reject pure plan arrays disguised as objects without a tool.
    if tool_name.lower() in {"thought", "thinking"}:
        return None

    args: dict[str, Any] = {}
    for key in _ARGS_KEYS:
        raw_args = data.get(key)
        if isinstance(raw_args, dict):
            args = dict(raw_args)
            break
    # Allow top-level non-meta keys as args when no args object present.
    if not args:
        reserved = (
            set(_TOOL_KEYS)
            | set(_ARGS_KEYS)
            | set(_THOUGHT_KEYS)
            | {
                "final_text",
                "finalText",
                "mode",
                "execution_mode",
            }
        )
        leftover = {k: v for k, v in data.items() if k not in reserved}
        # Only promote simple leftover maps; avoid swallowing nested plans.
        if (
            leftover
            and all(not isinstance(v, (dict, list)) or k == "options" for k, v in leftover.items())
            and any(k in leftover for k in ("command", "server", "path", "query", "question", "final_text"))
        ):
            args = dict(leftover)

    thought = ""
    for key in _THOUGHT_KEYS:
        raw_t = data.get(key)
        if isinstance(raw_t, str) and raw_t.strip():
            thought = raw_t.strip()
            break

    # done / final_text convenience
    if (
        tool_name == "done"
        and "final_text" in data
        and "final_text" not in args
        and isinstance(data.get("final_text"), str)
    ):
        args = {**args, "final_text": data["final_text"]}

    return thought, tool_name, args


def parse_response(response: str) -> tuple[str, str | None, dict]:
    """Extract THOUGHT and ACTION from LLM response.

    Order:
      1. Classic ``ACTION: tool {json}`` text form (preferred when present).
      2. Top-level JSON object with tool/action + args (JSON mode alternate).
      3. Thought-only final answer (no action).
    """
    # Prefer classic ACTION line when both styles appear — keeps legacy tests
    # and stronger models stable.
    text_action_name, text_action_args = parse_action(response)
    if text_action_name is not None:
        thought = ""
        thought_match = _THOUGHT_RE.search(response)
        if thought_match:
            thought = thought_match.group(1).strip()
        else:
            thought = response.split("ACTION:")[0].strip() if "ACTION:" in response else response.strip()
        return thought, text_action_name, text_action_args

    json_parsed = parse_json_action(response)
    if json_parsed is not None:
        thought, action_name, action_args = json_parsed
        if not thought:
            # Fall back to any prose before the JSON object.
            stripped = (response or "").strip()
            brace = stripped.find("{")
            if brace > 0:
                thought = stripped[:brace].strip()
        return thought, action_name, action_args

    thought = ""
    thought_match = _THOUGHT_RE.search(response)
    if thought_match:
        thought = thought_match.group(1).strip()
    else:
        thought = response.split("ACTION:")[0].strip() if "ACTION:" in response else (response or "").strip()
    return thought, None, {}
