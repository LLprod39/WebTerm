"""Anthropic native tool-calling stream (F-08a split of llm_tools)."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger

from app.core.llm_tool_helpers import UsageLogger, tools_to_anthropic


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
