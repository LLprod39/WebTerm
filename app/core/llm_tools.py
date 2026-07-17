"""Native tool-calling stream for the Operator chat loop.

Yields a unified event stream independent of provider:

  {"type": "text_delta", "text": str}
  {"type": "tool_call", "id": str, "name": str, "arguments": dict}
  {"type": "done", "usage": dict, "stop_reason": str}
  {"type": "error", "message": str}
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Any

from loguru import logger

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


async def stream_anthropic_tools(
    *,
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system_prompt: str | None,
    max_tokens: int = 8192,
    purpose: str = "orchestrator",
    usage_logger: UsageLogger | None = None,
    prompt_for_usage: str = "",
) -> AsyncGenerator[dict[str, Any], None]:
    anthropic_tools = tools_to_anthropic(tools)
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
        "tools": anthropic_tools,
    }
    if system_prompt:
        kwargs["system"] = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]
    # Cache tool catalog when large enough to matter
    if len(anthropic_tools) >= 4 and anthropic_tools:
        anthropic_tools[-1] = {**anthropic_tools[-1], "cache_control": {"type": "ephemeral"}}
        kwargs["tools"] = anthropic_tools

    started = time.monotonic()
    text_out = ""
    tool_buffers: dict[int, dict[str, Any]] = {}
    stop_reason = "end_turn"
    usage: dict[str, Any] = {}

    try:
        async with client.messages.stream(**kwargs) as stream:
            async for event in stream:
                etype = getattr(event, "type", None) or ""
                if etype == "content_block_start":
                    block = getattr(event, "content_block", None)
                    index = getattr(event, "index", 0)
                    btype = getattr(block, "type", None) if block is not None else None
                    if btype == "tool_use":
                        tool_buffers[index] = {
                            "id": getattr(block, "id", "") or f"tool_{uuid.uuid4().hex[:12]}",
                            "name": getattr(block, "name", "") or "",
                            "json": "",
                        }
                elif etype == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    dtype = getattr(delta, "type", None) if delta is not None else None
                    index = getattr(event, "index", 0)
                    if dtype == "text_delta":
                        chunk = getattr(delta, "text", "") or ""
                        if chunk:
                            text_out += chunk
                            yield {"type": "text_delta", "text": chunk}
                    elif dtype == "input_json_delta":
                        partial = getattr(delta, "partial_json", "") or ""
                        if index in tool_buffers:
                            tool_buffers[index]["json"] += partial
                elif etype == "message_delta":
                    delta = getattr(event, "delta", None)
                    if delta is not None:
                        stop_reason = getattr(delta, "stop_reason", None) or stop_reason
                    msg_usage = getattr(event, "usage", None)
                    if msg_usage is not None:
                        usage = {
                            "input_tokens": getattr(msg_usage, "input_tokens", 0) or 0,
                            "output_tokens": getattr(msg_usage, "output_tokens", 0) or 0,
                        }
            final = await stream.get_final_message()
            if final is not None:
                stop_reason = getattr(final, "stop_reason", None) or stop_reason
                fu = getattr(final, "usage", None)
                if fu is not None:
                    usage = {
                        "input_tokens": getattr(fu, "input_tokens", 0) or 0,
                        "output_tokens": getattr(fu, "output_tokens", 0) or 0,
                    }
                # Prefer structured content blocks for tool_use completeness
                for block in getattr(final, "content", None) or []:
                    if getattr(block, "type", None) == "tool_use":
                        args = getattr(block, "input", None)
                        if not isinstance(args, dict):
                            args = {}
                        yield {
                            "type": "tool_call",
                            "id": getattr(block, "id", "") or f"tool_{uuid.uuid4().hex[:12]}",
                            "name": getattr(block, "name", "") or "",
                            "arguments": args,
                        }
                    elif getattr(block, "type", None) == "text" and not text_out:
                        # Text already streamed; only fill if empty
                        pass
            elif tool_buffers:
                for buf in tool_buffers.values():
                    try:
                        args = json.loads(buf["json"] or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    if not isinstance(args, dict):
                        args = {}
                    yield {
                        "type": "tool_call",
                        "id": buf["id"],
                        "name": buf["name"],
                        "arguments": args,
                    }
    except Exception as exc:  # noqa: BLE001
        logger.error("Anthropic tool stream failed: {}", exc)
        if usage_logger:
            usage_logger(
                "claude",
                model,
                prompt_for_usage or json.dumps(messages)[:2000],
                text_out,
                int((time.monotonic() - started) * 1000),
                "error",
                purpose=purpose,
            )
        yield {"type": "error", "message": str(exc)}
        return

    if usage_logger:
        usage_logger(
            "claude",
            model,
            prompt_for_usage or json.dumps(messages)[:2000],
            text_out,
            int((time.monotonic() - started) * 1000),
            "success",
            purpose=purpose,
        )
    yield {"type": "done", "usage": usage, "stop_reason": stop_reason or "end_turn"}


async def stream_openai_tools(
    *,
    api_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system_prompt: str | None,
    purpose: str = "orchestrator",
    timeout_seconds: float = 120.0,
    usage_logger: UsageLogger | None = None,
    prompt_for_usage: str = "",
    provider: str = "openai",
) -> AsyncGenerator[dict[str, Any], None]:
    import aiohttp

    openai_tools = tools_to_openai(tools)
    chat_messages: list[dict[str, Any]] = []
    if system_prompt:
        chat_messages.append({"role": "system", "content": system_prompt})
    chat_messages.extend(_messages_to_openai(messages))

    payload: dict[str, Any] = {
        "model": model,
        "messages": chat_messages,
        "stream": True,
        "tools": openai_tools,
        "tool_choice": "auto",
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    started = time.monotonic()
    text_out = ""
    tool_acc: dict[int, dict[str, Any]] = {}
    usage: dict[str, Any] = {}
    finish_reason = "stop"

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.post(api_url, headers=headers, json=payload) as resp,
        ):
                if resp.status >= 400:
                    body = await resp.text()
                    raise RuntimeError(f"{provider} tools HTTP {resp.status}: {body[:400]}")
                async for raw_line in resp.content:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("usage"):
                        u = chunk["usage"]
                        usage = {
                            "input_tokens": u.get("prompt_tokens") or u.get("input_tokens") or 0,
                            "output_tokens": u.get("completion_tokens") or u.get("output_tokens") or 0,
                        }
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    finish_reason = choice.get("finish_reason") or finish_reason
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    if content:
                        text_out += content
                        yield {"type": "text_delta", "text": content}
                    for tc in delta.get("tool_calls") or []:
                        idx = int(tc.get("index") or 0)
                        acc = tool_acc.setdefault(idx, {"id": "", "name": "", "json": ""})
                        if tc.get("id"):
                            acc["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            acc["name"] = fn["name"]
                        if fn.get("arguments"):
                            acc["json"] += fn["arguments"]
    except Exception as exc:  # noqa: BLE001
        logger.error("{} tool stream failed: {}", provider, exc)
        if usage_logger:
            usage_logger(
                provider,
                model,
                prompt_for_usage or json.dumps(messages)[:2000],
                text_out,
                int((time.monotonic() - started) * 1000),
                "error",
                purpose=purpose,
            )
        yield {"type": "error", "message": str(exc)}
        return

    for acc in tool_acc.values():
        try:
            args = json.loads(acc["json"] or "{}")
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        yield {
            "type": "tool_call",
            "id": acc["id"] or f"call_{uuid.uuid4().hex[:12]}",
            "name": acc["name"],
            "arguments": args,
        }

    if usage_logger:
        usage_logger(
            provider,
            model,
            prompt_for_usage or json.dumps(messages)[:2000],
            text_out,
            int((time.monotonic() - started) * 1000),
            "success",
            purpose=purpose,
        )
    stop = "tool_use" if tool_acc else (finish_reason or "end_turn")
    yield {"type": "done", "usage": usage, "stop_reason": stop}


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
            out.append({"role": role if role in {"user", "system", "assistant"} else "user", "content": "\n".join(text_parts)})
    return out


async def stream_json_tools_fallback(
    *,
    stream_text: Callable[..., AsyncGenerator[str, None]],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system_prompt: str | None,
    purpose: str = "orchestrator",
) -> AsyncGenerator[dict[str, Any], None]:
    """JSON-mode fallback for providers without native tool streaming.

    Keep the prompt small: local models (Ollama) hang or stall on huge catalogs.
    """
    catalog = tools_to_anthropic(tools)
    # Prefer high-traffic operator tools first so the head of the list is useful
    priority = (
        "agent_create",
        "agent_run",
        "agents_list",
        "operator_list_servers",
        "operator_run_command",
        "operator_server_forecasts",
        "operator_fleet_status",
        "operator_list_alerts",
        "operator_server_metrics",
        "operator_metric_series",
    )
    by_name = {str(t.get("name") or ""): t for t in catalog}
    ordered: list[dict[str, Any]] = []
    for name in priority:
        if name in by_name:
            ordered.append(by_name.pop(name))
    ordered.extend(by_name.values())

    compact_tools = []
    for t in ordered[:18]:
        schema = t.get("input_schema") if isinstance(t.get("input_schema"), dict) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        compact_tools.append(
            {
                "name": t.get("name"),
                "desc": str(t.get("description") or "")[:100],
                "req": required[:6],
            }
        )

    # Short system — full OPERATOR_SYSTEM_PROMPT + tools blows local models
    base_sys = (system_prompt or "You are a helpful operator assistant.").strip()
    if len(base_sys) > 1800:
        base_sys = base_sys[:1800] + "\n…"
    instruction = (
        base_sys
        + "\n\nCRITICAL: Reply with ONE valid JSON object only. No markdown.\n"
        'Schema: {"text":"short note","tool_calls":[{"name":"tool_name","arguments":{}}]}\n'
        "Rules: tool names exactly as listed; short text; agent_create needs mode+goal "
        "(no git URL at create); server_ids optional.\n"
        "Tools:\n"
        + json.dumps(compact_tools, ensure_ascii=False)
    )
    # Flatten recent turns only; truncate heavy tool dumps
    user_bits: list[str] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if isinstance(content, str):
            user_bits.append(f"{role}: {content[:1200]}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    user_bits.append(f"{role}: {str(block.get('text') or '')[:1200]}")
                elif isinstance(block, dict) and block.get("type") == "tool_result":
                    user_bits.append(
                        f"tool_result({block.get('tool_use_id')}): {str(block.get('content') or '')[:800]}"
                    )
                elif isinstance(block, dict) and block.get("type") == "tool_use":
                    user_bits.append(
                        f"tool_use:{block.get('name')} args={json.dumps(block.get('input') or {}, ensure_ascii=False)[:400]}"
                    )
    prompt = "\n".join(user_bits[-12:]) or "Hello"
    # Tell UI immediately that the model is working (Ollama JSON path has no mid-stream tokens)
    yield {
        "type": "thinking_status",
        "phase": "thinking",
        "message": "Модель думает…",
    }
    collected = ""
    chunk_count = 0
    last_hb = 0.0
    import time as _time

    t0 = _time.monotonic()
    async for chunk in stream_text(prompt=prompt, system_prompt=instruction, purpose=purpose, json_mode=True):
        chunk_count += 1
        # Ignore thinking stream (sentinels) — only final JSON content matters
        if isinstance(chunk, str) and (
            chunk.startswith("«THINK»") or chunk.startswith("\x00THINK\x00")
        ):
            now = _time.monotonic()
            if now - last_hb >= 1.5:
                last_hb = now
                yield {
                    "type": "thinking_status",
                    "phase": "thinking",
                    "message": f"думает… {int(now - t0)}с",
                }
            continue
        collected += chunk
        now = _time.monotonic()
        if chunk_count == 1 or now - last_hb >= 1.5:
            last_hb = now
            yield {
                "type": "thinking_status",
                "phase": "thinking",
                "message": f"генерация… {len(collected)} симв.",
            }
        # Surface provider/connectivity errors immediately instead of empty bubble
        if chunk.startswith("Error:") or chunk.startswith("Error from") or chunk.startswith("Error calling"):
            yield {"type": "error", "message": chunk}
            yield {"type": "done", "usage": {}, "stop_reason": "error"}
            return
    data = _parse_json_object(collected) or {}
    text = str(data.get("text") or data.get("reply") or data.get("message") or "")
    # Some models wrap tools under "tools" or return bare prose
    raw_calls = data.get("tool_calls")
    if raw_calls is None and isinstance(data.get("tools"), list):
        raw_calls = data.get("tools")
    if not isinstance(raw_calls, list):
        raw_calls = []

    if not data or (not raw_calls and _looks_like_tool_json_leak(collected)):
        loose = _extract_tool_calls_loose(collected)
        if loose:
            logger.warning("JSON tool fallback: recovered {} tool call(s) from messy output", len(loose))
            raw_calls = loose
            if not data:
                data = {"text": "", "tool_calls": loose}

    if not data and not raw_calls:
        stripped = (collected or "").strip()
        if stripped.startswith("Error:") or ("Ollama" in stripped and "не" in stripped.lower()):
            yield {"type": "error", "message": stripped[:500]}
            yield {"type": "done", "usage": {}, "stop_reason": "error"}
            return
        if stripped:
            # Never dump raw tool JSON into the chat transcript
            if _looks_like_tool_json_leak(stripped):
                logger.warning("JSON tool fallback: dropped unparseable tool-shaped leak ({} chars)", len(stripped))
                yield {
                    "type": "text_delta",
                    "text": "Не удалось разобрать вызов инструмента. Повтори запрос короче.",
                }
                yield {"type": "done", "usage": {}, "stop_reason": "end_turn"}
                return
            logger.warning("JSON tool fallback: non-JSON reply, using raw text ({} chars)", len(stripped))
            yield {"type": "text_delta", "text": stripped[:4000]}
            yield {"type": "done", "usage": {}, "stop_reason": "end_turn"}
            return
        yield {
            "type": "error",
            "message": (
                "Локальная модель вернула пустой ответ. "
                "Проверь Ollama (ollama serve), URL в настройках и что backend достучится до хоста."
            ),
        }
        yield {"type": "done", "usage": {}, "stop_reason": "error"}
        return

    # Human text only if not a JSON leak
    if text and not _looks_like_tool_json_leak(text):
        yield {"type": "text_delta", "text": text[:2000]}
    elif raw_calls and not text:
        pass
    elif text and _looks_like_tool_json_leak(text) and raw_calls:
        # Model put tool JSON into "text" field — ignore text, keep tools
        pass
    elif text and _looks_like_tool_json_leak(text) and not raw_calls:
        yield {
            "type": "text_delta",
            "text": "Не удалось разобрать ответ модели. Повтори запрос.",
        }

    emitted = 0
    for call in raw_calls:
        if not isinstance(call, dict):
            continue
        name = str(call.get("name") or call.get("tool") or "")
        args = call.get("arguments") if isinstance(call.get("arguments"), dict) else call.get("args")
        if not isinstance(args, dict):
            # Sometimes arguments is a JSON string
            if isinstance(call.get("arguments"), str):
                try:
                    args = json.loads(call["arguments"])
                except json.JSONDecodeError:
                    args = {}
            else:
                args = {}
        if not name:
            continue
        # Normalize dotted names models invent (agent.create → agent_create stays; resolve later)
        name = normalise_tool_name(name.replace(".", "_"))
        yield {
            "type": "tool_call",
            "id": str(call.get("id") or f"call_{uuid.uuid4().hex[:12]}"),
            "name": name,
            "arguments": args,
        }
        emitted += 1
    yield {
        "type": "done",
        "usage": {},
        "stop_reason": "tool_use" if emitted else "end_turn",
    }
