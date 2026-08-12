"""Translate subscription-runner events into the legacy LLM stream contracts."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from app.ai_runtime import LLMExecutionContext, ProviderEventType, ProviderRuntimeError, is_subscription_target
from app.core.ai_subscription_gateway import stream_subscription_events


def is_subscription_execution(context: LLMExecutionContext | None) -> bool:
    return bool(context and context.binding and is_subscription_target(context.binding.target_id))


def _runtime_error(event_type: ProviderEventType, payload: dict[str, Any]) -> ProviderRuntimeError | None:
    if event_type is ProviderEventType.AUTH_REQUIRED:
        return ProviderRuntimeError("provider_auth_required", "Provider authentication is required")
    if event_type is ProviderEventType.LIMIT:
        return ProviderRuntimeError("provider_limit_reached", "Provider subscription limit is reached")
    if event_type is ProviderEventType.CANCELLED:
        return ProviderRuntimeError("provider_cancelled", "Provider invocation was cancelled")
    if event_type is ProviderEventType.ERROR:
        return ProviderRuntimeError(
            str(payload.get("code") or "provider_error"),
            str(payload.get("message") or "Provider runtime failed"),
            retryable=bool(payload.get("retryable")),
        )
    return None


async def stream_subscription_text(
    *,
    context: LLMExecutionContext,
    prompt: str,
    system_prompt: str | None,
) -> AsyncGenerator[str, None]:
    async for event in stream_subscription_events(
        context=context,
        messages=[{"role": "user", "content": prompt}],
        tools=[],
        system_prompt=system_prompt,
    ):
        if event.type is ProviderEventType.TEXT_DELTA:
            yield str(event.payload.get("text") or "")
        elif event.type is ProviderEventType.REASONING_DELTA:
            yield f"«THINK»{event.payload.get('text') or ''}"
        else:
            runtime_error = _runtime_error(event.type, event.payload)
            if runtime_error is not None:
                raise runtime_error


def _tool_error(event_type: ProviderEventType, payload: dict[str, Any]) -> dict[str, Any] | None:
    codes = {
        ProviderEventType.CANCELLED: ("provider_cancelled", "Provider invocation cancelled"),
        ProviderEventType.AUTH_REQUIRED: ("provider_auth_required", "Provider authentication required"),
        ProviderEventType.LIMIT: ("provider_limit_reached", "Provider limit reached"),
    }
    if event_type in codes:
        code, message = codes[event_type]
        return {"type": "error", "code": code, "message": message}
    if event_type is ProviderEventType.ERROR:
        return {
            "type": "error",
            "code": str(payload.get("code") or "provider_error"),
            "message": str(payload.get("message") or "Provider runtime failed"),
        }
    return None


async def stream_subscription_tools(
    *,
    context: LLMExecutionContext,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system_prompt: str | None,
) -> AsyncGenerator[dict[str, Any], None]:
    usage: dict[str, Any] = {}
    async for event in stream_subscription_events(
        context=context,
        messages=messages,
        tools=tools,
        system_prompt=system_prompt,
    ):
        if event.type is ProviderEventType.TEXT_DELTA:
            yield {"type": "text_delta", "text": str(event.payload.get("text") or "")}
        elif event.type is ProviderEventType.TOOL_REQUEST:
            yield {
                "type": "tool_call",
                "id": str(event.payload.get("id") or ""),
                "name": str(event.payload.get("name") or ""),
                "arguments": event.payload.get("arguments") or {},
            }
        elif event.type is ProviderEventType.USAGE:
            usage = event.payload
        elif event.type is ProviderEventType.COMPLETED:
            yield {
                "type": "done",
                "usage": usage,
                "stop_reason": "stop",
                "provider_session_id": str(event.payload.get("provider_session_id") or ""),
                "binding_snapshot": event.payload.get("binding_snapshot") or {},
            }
        else:
            error = _tool_error(event.type, event.payload)
            if error is not None:
                yield error
