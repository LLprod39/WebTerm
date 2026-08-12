from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.ai_runtime import (
    ExecutionMode,
    LLMExecutionContext,
    ProviderBinding,
    ProviderEventType,
    ProviderEventV1,
    ProviderRuntimeError,
)
from app.core import ai_subscription_gateway
from app.core.llm_provider_stream import stream_provider_chat
from app.core.llm_provider_tools_stream import stream_provider_chat_tools


def _context() -> LLMExecutionContext:
    return LLMExecutionContext(
        actor_user_id=1,
        project_id=None,
        purpose="assistant",
        source_kind="chat_session",
        source_id="1",
        mode=ExecutionMode.INTERACTIVE,
        binding=ProviderBinding("codex_subscription", connection_id=4),
        idempotency_key="turn-1",
    )


class _Provider:
    async def _load_managed_api_keys(self) -> None:
        raise AssertionError("API keys must not be loaded for subscription transport")


@pytest.mark.asyncio
async def test_plain_subscription_stream_never_enters_api_transport(monkeypatch) -> None:
    async def fake_provider(**_kwargs) -> AsyncIterator[ProviderEventV1]:
        yield ProviderEventV1(ProviderEventType.TEXT_DELTA, {"text": "hello"})
        yield ProviderEventV1(ProviderEventType.COMPLETED, {"provider_session_id": "thread-1"})

    monkeypatch.setattr(ai_subscription_gateway, "_provider", fake_provider)
    chunks = [
        chunk
        async for chunk in stream_provider_chat(
            _Provider(),
            "prompt",
            execution_context=_context(),
        )
    ]
    assert chunks == ["hello"]


@pytest.mark.asyncio
async def test_subscription_tool_request_uses_existing_operator_event_shape(monkeypatch) -> None:
    async def fake_provider(**_kwargs) -> AsyncIterator[ProviderEventV1]:
        yield ProviderEventV1(
            ProviderEventType.TOOL_REQUEST,
            {"id": "call-1", "name": "server.list", "arguments": {"limit": 2}},
        )
        yield ProviderEventV1(ProviderEventType.COMPLETED, {"provider_session_id": "thread-1"})

    monkeypatch.setattr(ai_subscription_gateway, "_provider", fake_provider)
    events = [
        event
        async for event in stream_provider_chat_tools(
            _Provider(),
            messages=[{"role": "user", "content": "list"}],
            tools=[{"name": "server.list"}],
            execution_context=_context(),
        )
    ]
    assert events[0] == {
        "type": "tool_call",
        "id": "call-1",
        "name": "server.list",
        "arguments": {"limit": 2},
    }
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_subscription_auth_error_does_not_fall_back(monkeypatch) -> None:
    async def fake_provider(**_kwargs) -> AsyncIterator[ProviderEventV1]:
        yield ProviderEventV1(ProviderEventType.AUTH_REQUIRED, {"authenticated": False})

    monkeypatch.setattr(ai_subscription_gateway, "_provider", fake_provider)
    with pytest.raises(ProviderRuntimeError) as exc_info:
        async for _ in stream_provider_chat(_Provider(), "prompt", execution_context=_context()):
            pass
    assert exc_info.value.code == "provider_auth_required"
