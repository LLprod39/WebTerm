from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.core.llm_anthropic import (
    ClaudeStreamRequest,
    build_claude_stream_kwargs,
    stream_claude_response,
)


class _AsyncTextStream:
    def __init__(self, chunks: list[str]):
        self._chunks = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._chunks)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _Stream:
    def __init__(self, chunks: list[str]):
        self.text_stream = _AsyncTextStream(chunks)


class _StreamContext:
    def __init__(self, outcome: list[str] | Exception):
        self._outcome = outcome

    async def __aenter__(self):
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return _Stream(self._outcome)

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeMessages:
    def __init__(self, outcomes: list[list[str] | Exception]):
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        return _StreamContext(self.outcomes.pop(0))


class _FakeClient:
    def __init__(self, outcomes: list[list[str] | Exception]):
        self.messages = _FakeMessages(outcomes)


class _RetryableProviderError(Exception):
    status_code = 500


def _usage_collector(calls: list[dict[str, Any]]):
    def _log(provider, model_name, input_text, output_text, duration_ms, status="success", **kwargs):
        calls.append(
            {
                "provider": provider,
                "model_name": model_name,
                "input_text": input_text,
                "output_text": output_text,
                "duration_ms": duration_ms,
                "status": status,
                **kwargs,
            }
        )

    return _log


def test_build_claude_stream_kwargs_includes_system_prompt_cache_control():
    kwargs = build_claude_stream_kwargs(
        ClaudeStreamRequest(
            target_model="claude-sonnet-test",
            prompt="Deploy status?",
            system_prompt="Use production facts only.",
        )
    )

    assert kwargs == {
        "model": "claude-sonnet-test",
        "max_tokens": 8192,
        "messages": [{"role": "user", "content": "Deploy status?"}],
        "system": [
            {
                "type": "text",
                "text": "Use production facts only.",
                "cache_control": {"type": "ephemeral"},
            }
        ],
    }


@pytest.mark.asyncio
async def test_stream_claude_response_yields_chunks_and_logs_success():
    usage_calls: list[dict[str, Any]] = []
    client = _FakeClient([["Hel", "lo"]])
    request = ClaudeStreamRequest(
        target_model="claude-sonnet-test",
        prompt="hello",
        system_prompt=None,
    )

    chunks = [
        chunk
        async for chunk in stream_claude_response(
            client=client,
            request=request,
            purpose="chat",
            timeout_seconds=1,
            max_attempts=1,
            usage_logger=_usage_collector(usage_calls),
        )
    ]

    assert chunks == ["Hel", "lo"]
    assert client.messages.calls == [
        {
            "model": "claude-sonnet-test",
            "max_tokens": 8192,
            "messages": [{"role": "user", "content": "hello"}],
        }
    ]
    assert usage_calls == [
        {
            "provider": "claude",
            "model_name": "claude-sonnet-test",
            "input_text": "hello",
            "output_text": "Hello",
            "duration_ms": usage_calls[0]["duration_ms"],
            "status": "success",
            "purpose": "chat",
        }
    ]


@pytest.mark.asyncio
async def test_stream_claude_response_retries_retryable_errors(monkeypatch):
    usage_calls: list[dict[str, Any]] = []
    client = _FakeClient([_RetryableProviderError("temporary"), ["OK"]])

    async def _no_sleep(_delay):
        return None

    monkeypatch.setattr("app.core.llm_anthropic.asyncio.sleep", _no_sleep)

    chunks = [
        chunk
        async for chunk in stream_claude_response(
            client=client,
            request=ClaudeStreamRequest("claude-sonnet-test", "hello", None),
            purpose="chat",
            timeout_seconds=1,
            max_attempts=2,
            usage_logger=_usage_collector(usage_calls),
        )
    ]

    assert chunks == ["[Повтор попытки...]", "OK"]
    assert len(client.messages.calls) == 2
    assert usage_calls[0]["status"] == "success"
    assert usage_calls[0]["output_text"] == "OK"


@pytest.mark.asyncio
async def test_stream_claude_response_logs_timeout_status():
    usage_calls: list[dict[str, Any]] = []
    client = _FakeClient([asyncio.TimeoutError()])

    chunks = [
        chunk
        async for chunk in stream_claude_response(
            client=client,
            request=ClaudeStreamRequest("claude-sonnet-test", "hello", None),
            purpose="chat",
            timeout_seconds=1,
            max_attempts=1,
            usage_logger=_usage_collector(usage_calls),
        )
    ]

    assert chunks == ["Error: Timeout (Claude stream)."]
    assert usage_calls[0]["status"] == "timeout"
    assert usage_calls[0]["provider"] == "claude"
