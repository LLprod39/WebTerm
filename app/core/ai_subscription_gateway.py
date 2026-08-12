"""Dependency-inverted gateway for subscription CLI execution."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from app.ai_runtime import LLMExecutionContext, ProviderEventV1, ProviderRuntimeError

SubscriptionEventProvider = Callable[..., AsyncIterator[ProviderEventV1]]

_provider: SubscriptionEventProvider | None = None


def register_subscription_event_provider(provider: SubscriptionEventProvider) -> None:
    global _provider
    _provider = provider


async def stream_subscription_events(
    *,
    context: LLMExecutionContext,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system_prompt: str | None,
) -> AsyncIterator[ProviderEventV1]:
    if _provider is None:
        raise ProviderRuntimeError(
            "provider_transport_unavailable",
            "Subscription CLI runtime is not registered",
        )
    async for event in _provider(
        context=context,
        messages=messages,
        tools=tools,
        system_prompt=system_prompt,
    ):
        yield event
