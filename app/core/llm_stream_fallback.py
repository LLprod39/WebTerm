"""JSON-mode tool-calling fallback for providers without native tool streaming
(F-08a split of llm_tools)."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Any

from loguru import logger

from app.core.llm_tool_helpers import (
    _extract_tool_calls_loose,
    _looks_like_tool_json_leak,
    _parse_json_object,
    normalise_tool_name,
    tools_to_anthropic,
)


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
        base_sys + "\n\nCRITICAL: Reply with ONE valid JSON object only. No markdown.\n"
        'Schema: {"text":"short note","tool_calls":[{"name":"tool_name","arguments":{}}]}\n'
        "Rules: tool names exactly as listed; short text; agent_create needs mode+goal "
        "(no git URL at create); server_ids optional.\n"
        "Tools:\n" + json.dumps(compact_tools, ensure_ascii=False)
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
    # Tell UI immediately that the model is working (Ollama JSON path may stream
    # thinking tokens and/or silent generation before final JSON).
    yield {
        "type": "thinking_status",
        "phase": "thinking",
        "message": "Ждём ответ модели…",
        "reasoning_active": False,
    }
    collected = ""
    chunk_count = 0
    last_hb = 0.0
    saw_thinking = False
    import time as _time

    t0 = _time.monotonic()
    async for chunk in stream_text(prompt=prompt, system_prompt=instruction, purpose=purpose, json_mode=True):
        chunk_count += 1
        # Surface model "thinking" channel to the operator UI (do not mix into JSON body).
        if isinstance(chunk, str) and (chunk.startswith("«THINK»") or chunk.startswith("\x00THINK\x00")):
            think_text = chunk[len("«THINK»") :] if chunk.startswith("«THINK»") else chunk[len("\x00THINK\x00") :]
            if think_text:
                saw_thinking = True
                yield {"type": "thinking_delta", "text": think_text}
            now = _time.monotonic()
            if now - last_hb >= 2.0:
                last_hb = now
                yield {
                    "type": "thinking_status",
                    "phase": "thinking",
                    "message": f"Размышление… {int(now - t0)}с",
                    "reasoning_active": True,
                }
            continue
        collected += chunk
        now = _time.monotonic()
        if chunk_count == 1 or now - last_hb >= 1.5:
            last_hb = now
            yield {
                "type": "thinking_status",
                "phase": "thinking",
                "message": (
                    f"Генерация JSON… {len(collected)} симв."
                    if collected
                    else f"Модель отвечает без thinking… {int(now - t0)}с"
                ),
                "reasoning_active": saw_thinking,
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
