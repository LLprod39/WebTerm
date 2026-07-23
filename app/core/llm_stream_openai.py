"""OpenAI-compatible native tool-calling stream (F-08a split of llm_tools)."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger

from app.core.llm_tool_helpers import UsageLogger, _messages_to_openai, tools_to_openai


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
