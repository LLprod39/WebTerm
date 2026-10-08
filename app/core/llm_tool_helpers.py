"""Shared helpers for native tool-calling streams (F-08a split of llm_tools).

Provider-agnostic: tool-schema conversion, loose tool-call parsing, bounded
tool selection for small local models, and Anthropic-style → provider message
conversion. The per-provider streaming functions live in ``llm_stream_*`` and
import from here.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from typing import Any

UsageLogger = Callable[..., None]

MAX_TOOL_NAME_LEN = 64
_TOOL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def normalise_tool_name(name: str) -> str:
    """Map action_type (may contain dots) to a provider-safe tool name."""
    raw = str(name or "").strip()
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw).strip("_")
    if not cleaned:
        cleaned = "tool"
    return cleaned[:MAX_TOOL_NAME_LEN]


def tools_to_anthropic(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tool in tools:
        name = normalise_tool_name(tool.get("name") or tool.get("action_type") or "")
        if not _TOOL_NAME_RE.match(name):
            continue
        schema = tool.get("input_schema") or tool.get("parameters") or {"type": "object", "properties": {}}
        if not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}}
        if "type" not in schema:
            schema = {**schema, "type": "object"}
        entry: dict[str, Any] = {
            "name": name,
            "description": str(tool.get("description") or tool.get("label") or name)[:1024],
            "input_schema": schema,
        }
        out.append(entry)
    return out


def tools_to_openai(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tool in tools_to_anthropic(tools):
        out.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            }
        )
    return out


def _parse_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    # Strip markdown fences
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    # Tolerate fenced or trailing prose
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        candidate = raw[start : end + 1]
        try:
            data = json.loads(candidate)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            pass
        # Repair common LLM mess: unescaped newlines inside strings, trailing commas
        repaired = re.sub(r",\s*}", "}", candidate)
        repaired = re.sub(r",\s*]", "]", repaired)
        try:
            data = json.loads(repaired)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            pass
    return None


def _extract_tool_calls_loose(text: str) -> list[dict[str, Any]]:
    """Best-effort recovery when model dumps almost-JSON with tool_calls."""
    raw = text or ""
    calls: list[dict[str, Any]] = []
    # Pattern: "name": "agent_create" ... "arguments": { ... }
    for match in re.finditer(
        r'"name"\s*:\s*"([a-zA-Z0-9_.-]+)"\s*,\s*"arguments"\s*:\s*(\{)',
        raw,
    ):
        name = match.group(1)
        brace_start = match.start(2)
        depth = 0
        end = None
        for i, ch in enumerate(raw[brace_start:], start=brace_start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end is None:
            continue
        args_raw = raw[brace_start:end]
        try:
            args = json.loads(args_raw)
        except json.JSONDecodeError:
            args_raw2 = re.sub(r",\s*}", "}", args_raw)
            args_raw2 = re.sub(r",\s*]", "]", args_raw2)
            try:
                args = json.loads(args_raw2)
            except json.JSONDecodeError:
                continue
        if isinstance(args, dict) and name:
            calls.append({"name": name, "arguments": args})
    return calls


def _looks_like_tool_json_leak(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if '"tool_calls"' in t or '"arguments"' in t:
        return True
    return bool(t.startswith("{") and ("agent_create" in t or "operator_" in t or "tool" in t[:80].lower()))


# ---------------------------------------------------------------------------
# Bounded tool selection for small local models
# ---------------------------------------------------------------------------

# Legacy constant kept for imports/tests; catalog is no longer truncated by keywords.
NATIVE_TOOLS_SOFT_LIMIT = 0


def select_tools_for_request(
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]] | None = None,  # noqa: ARG001
    *,
    limit: int | None = None,  # noqa: ARG001
) -> list[dict[str, Any]]:
    """Return the full tool list (no keyword / score-based subsetting).

    Compact descriptions are applied in ``specs_to_tools``. History may still be
    bounded separately via ``bound_messages_for_local``.
    """
    return list(tools or [])


def _is_tool_result_only(msg: dict[str, Any]) -> bool:
    content = msg.get("content")
    if not isinstance(content, list) or not content:
        return False
    return all(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


def bound_messages_for_local(messages: list[dict[str, Any]], *, max_messages: int = 8) -> list[dict[str, Any]]:
    """Keep only the recent tail so small local models don't drown in history.

    qwen3.5:9b stops emitting tool calls once the combined tool catalog + history
    grows large (a fresh turn calls tools reliably; ~18 messages of history breaks
    it). Preserve tool_use/tool_result pairing by dropping a leading orphan
    tool_result block if truncation would start on one.
    """
    if len(messages) <= max_messages:
        return messages
    tail = messages[-max_messages:]
    while tail and _is_tool_result_only(tail[0]):
        tail = tail[1:]
    return tail


def _messages_to_ollama(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Anthropic-style multi-part messages to Ollama /api/chat format.

    Ollama tool calls carry ``arguments`` as an object (not a JSON string) and tool
    results use a ``tool`` role. Matching is positional, so tool_use_id is dropped.
    """
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role") or "user"
        content = msg.get("content")
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        if not isinstance(content, list):
            out.append({"role": role, "content": str(content or "")})
            continue
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                text_parts.append(str(block.get("text") or ""))
            elif btype == "tool_use":
                tool_calls.append(
                    {
                        "function": {
                            "name": block.get("name") or "",
                            "arguments": block.get("input") if isinstance(block.get("input"), dict) else {},
                        }
                    }
                )
            elif btype == "tool_result":
                tool_results.append({"role": "tool", "content": str(block.get("content") or "")})
        if role == "assistant":
            entry: dict[str, Any] = {"role": "assistant", "content": "\n".join(text_parts)}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            out.append(entry)
        elif tool_results and role == "user":
            out.extend(tool_results)
            if text_parts:
                out.append({"role": "user", "content": "\n".join(text_parts)})
        else:
            out.append(
                {
                    "role": role if role in {"user", "system", "assistant"} else "user",
                    "content": "\n".join(text_parts),
                }
            )
    return out


def _messages_to_openai(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Anthropic-style multi-part messages to OpenAI chat format."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role") or "user"
        content = msg.get("content")
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        if not isinstance(content, list):
            out.append({"role": role, "content": str(content or "")})
            continue
        text_parts: list[str] = []
        tool_calls = []
        tool_results = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                text_parts.append(str(block.get("text") or ""))
            elif btype == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": block.get("name") or "",
                            "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
                        },
                    }
                )
            elif btype == "tool_result":
                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id") or "",
                        "content": str(block.get("content") or ""),
                    }
                )
        if role == "assistant":
            entry: dict[str, Any] = {"role": "assistant", "content": "\n".join(text_parts) or None}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            out.append(entry)
        elif tool_results and role == "user":
            out.extend(tool_results)
            if text_parts:
                out.append({"role": "user", "content": "\n".join(text_parts)})
        else:
            out.append(
                {"role": role if role in {"user", "system", "assistant"} else "user", "content": "\n".join(text_parts)}
            )
    return out
