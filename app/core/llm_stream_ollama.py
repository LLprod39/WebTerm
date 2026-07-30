"""Ollama native tool-calling stream + capability probe (F-08a split of llm_tools).

For models with the ``tools`` capability. Base-URL failover is handled here.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Any

from loguru import logger

from app.core.llm_tool_helpers import (
    UsageLogger,
    _messages_to_ollama,
    bound_messages_for_local,
    select_tools_for_request,
    tools_to_openai,
)

_OLLAMA_TOOLS_CAPABILITY: dict[str, bool] = {}


async def ollama_model_supports_tools(base_url: str, model: str, headers: dict[str, Any] | None = None) -> bool:
    """Best-effort check (cached) whether an Ollama model exposes the ``tools`` capability.

    Falls back to optimistic True on any error so a transient probe failure never
    downgrades a capable model to the brittle JSON path.
    """
    key = f"{base_url}::{model}"
    cached = _OLLAMA_TOOLS_CAPABILITY.get(key)
    if cached is not None:
        return cached
    import aiohttp

    try:
        timeout = aiohttp.ClientTimeout(total=6)
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.post(f"{base_url}/api/show", headers=dict(headers or {}), json={"model": model}) as resp,
        ):
            if resp.status == 200:
                data = await resp.json()
                caps = data.get("capabilities") or []
                supported = "tools" in caps
                _OLLAMA_TOOLS_CAPABILITY[key] = supported
                return supported
    except Exception as exc:  # noqa: BLE001
        logger.debug("ollama capability probe failed for {}: {}", model, exc)
    _OLLAMA_TOOLS_CAPABILITY[key] = True
    return True


async def stream_ollama_tools(
    *,
    request_targets: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system_prompt: str | None,
    think_value: Any | None = None,
    timeout_seconds: float = 120.0,
    purpose: str = "orchestrator",
    usage_logger: UsageLogger | None = None,
    prompt_for_usage: str = "",
    set_configured_base_url: Callable[[str], None] | None = None,
    is_connect_error: Callable[[Exception], bool] | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Native Ollama tool-calling stream with base-URL failover.

    Reads message.content -> text_delta, message.thinking -> thinking_delta, and
    message.tool_calls -> tool_call. Yields the same unified events as the other
    provider tool streams.
    """
    import aiohttp

    # Bound catalog + history so small local models stay accurate
    # (see select_tools_for_request / bound_messages_for_local).
    bounded = bound_messages_for_local(messages)
    ollama_tools = tools_to_openai(select_tools_for_request(tools, bounded))
    chat_messages: list[dict[str, Any]] = []
    if system_prompt:
        chat_messages.append({"role": "system", "content": system_prompt})
    chat_messages.extend(_messages_to_ollama(bounded))

    payload: dict[str, Any] = {
        "messages": chat_messages,
        "stream": True,
        "tools": ollama_tools,
        # num_ctx MUST be large: the operator system prompt + tool schemas alone run
        # ~4000 tokens, filling Ollama's default 4096 context. Once any history is
        # added the prompt overflows, output truncates (done_reason=length) and the
        # model "thinks" then emits nothing — the classic empty-second-message bug.
        # num_predict=-1 removes the output cap entirely: thinking tokens no longer
        # eat the answer budget, so long tool-calling turns and multi-step tasks are
        # never truncated to empty. The model stops naturally; the request timeout is
        # the real upper bound.
        "options": {"temperature": 0.3, "num_ctx": 16384, "num_predict": -1},
    }
    # NB: Ollama's qwen3 tool grammar 500s ("XML syntax error … <function> closed by
    # </parameter>") when thinking is explicitly disabled. Never send think:false with
    # tools — omit the param instead so the model keeps its default reasoning.
    if think_value not in (None, False, "off"):
        payload["think"] = think_value

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    started = time.monotonic()
    last_error: Exception | None = None

    for base_index, target in enumerate(request_targets):
        base_url = target["base_url"]
        headers = dict(target["headers"])
        payload["model"] = target["model"]
        text_out = ""
        tool_calls_acc: list[dict[str, Any]] = []
        usage: dict[str, Any] = {}
        stop_reason = "end_turn"
        try:
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.post(f"{base_url}/api/chat", headers=headers, json=payload) as resp,
            ):
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"Ollama tools HTTP {resp.status}: {body[:300]}")
                async for raw_line in resp.content:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = chunk.get("message") or {}
                    thinking = msg.get("thinking") or ""
                    if thinking:
                        yield {"type": "thinking_delta", "text": thinking}
                    content = msg.get("content") or ""
                    if content:
                        text_out += content
                        yield {"type": "text_delta", "text": content}
                    for tc in msg.get("tool_calls") or []:
                        fn = tc.get("function") or {}
                        name = str(fn.get("name") or "")
                        args = fn.get("arguments")
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}
                        if not isinstance(args, dict):
                            args = {}
                        if name:
                            tool_calls_acc.append({"name": name, "arguments": args})
                    if chunk.get("done"):
                        stop_reason = chunk.get("done_reason") or stop_reason
                        usage = {
                            "input_tokens": int(chunk.get("prompt_eval_count") or 0),
                            "output_tokens": int(chunk.get("eval_count") or 0),
                        }
                        break
            if target["kind"] == "local" and set_configured_base_url:
                set_configured_base_url(base_url)
                try:
                    from app.core.ollama_config import remember_ollama_url

                    remember_ollama_url(base_url)
                except Exception as persist_exc:  # noqa: BLE001
                    logger.debug("Ollama URL persistence skipped: {}", persist_exc)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            has_next = base_index < len(request_targets) - 1
            if target["kind"] == "local" and is_connect_error and is_connect_error(exc) and has_next:
                logger.warning("Ollama tools connect failed via {}: {}. Trying next base URL.", base_url, exc)
                continue
            logger.error("Ollama tool stream failed: {}", exc)
            if usage_logger:
                usage_logger(
                    "ollama",
                    payload["model"],
                    prompt_for_usage or "",
                    text_out,
                    int((time.monotonic() - started) * 1000),
                    "error",
                    purpose=purpose,
                )
            yield {"type": "error", "message": f"Error calling Ollama: {exc}"}
            return

        for call in tool_calls_acc:
            yield {
                "type": "tool_call",
                "id": f"call_{uuid.uuid4().hex[:12]}",
                "name": call["name"],
                "arguments": call["arguments"],
            }
        if usage_logger:
            usage_logger(
                "ollama",
                payload["model"],
                prompt_for_usage or "",
                text_out,
                int((time.monotonic() - started) * 1000),
                "success",
                purpose=purpose,
            )
        yield {
            "type": "done",
            "usage": usage,
            "stop_reason": "tool_use" if tool_calls_acc else (stop_reason or "end_turn"),
        }
        return

    if last_error is not None:
        yield {"type": "error", "message": f"Ollama недоступен из backend: {last_error}"}
        yield {"type": "done", "usage": {}, "stop_reason": "error"}
