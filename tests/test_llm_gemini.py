from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.core.llm_gemini import (
    GeminiStreamRequest,
    build_gemini_stream_kwargs,
    stream_gemini_response,
)


class _Chunk:
    def __init__(self, text: str | None):
        self.text = text


class _AsyncChunkStream:
    def __init__(self, chunks: list[str | None]):
        self._chunks = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return _Chunk(next(self._chunks))
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeModels:
    def __init__(self, outcomes: list[list[str | None] | Exception]):
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    async def generate_content_stream(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return _AsyncChunkStream(outcome)


class _FakeClient:
    def __init__(self, outcomes: list[list[str | None] | Exception]):
        self.aio = type("Aio", (), {"models": _FakeModels(outcomes)})()


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


def test_build_gemini_stream_kwargs_includes_system_instruction_and_json_mode():
    kwargs = build_gemini_stream_kwargs(
        GeminiStreamRequest(
            target_model="models/gemini-test",
            prompt="Return status",
            system_prompt="Use production facts only.",
            json_mode=True,
        )
    )

    assert kwargs == {
        "model": "models/gemini-test",
        "contents": "Return status",
        "config": {
            "system_instruction": "Use production facts only.",
            "response_mime_type": "application/json",
        },
    }


@pytest.mark.asyncio
async def test_stream_gemini_response_yields_chunks_and_logs_success():
    usage_calls: list[dict[str, Any]] = []
    client = _FakeClient([["Hel", None, "lo"]])

    chunks = [
        chunk
        async for chunk in stream_gemini_response(
            client=client,
            request=GeminiStreamRequest("models/gemini-test", "hello", None),
            purpose="chat",
            timeout_seconds=1,
            max_attempts=1,
            usage_logger=_usage_collector(usage_calls),
        )
    ]

    assert chunks == ["Hel", "lo"]
    assert client.aio.models.calls == [
        {
            "model": "models/gemini-test",
            "contents": "hello",
        }
    ]
    assert usage_calls == [
        {
            "provider": "gemini",
            "model_name": "models/gemini-test",
            "input_text": "hello",
            "output_text": "Hello",
            "duration_ms": usage_calls[0]["duration_ms"],
            "status": "success",
            "purpose": "chat",
        }
    ]


@pytest.mark.asyncio
async def test_stream_gemini_response_retries_retryable_errors(monkeypatch):
    usage_calls: list[dict[str, Any]] = []
    client = _FakeClient([_RetryableProviderError("temporary"), ["OK"]])

    async def _no_sleep(_delay):
        return None

    monkeypatch.setattr("app.core.llm_gemini.asyncio.sleep", _no_sleep)

    chunks = [
        chunk
        async for chunk in stream_gemini_response(
            client=client,
            request=GeminiStreamRequest("models/gemini-test", "hello", None),
            purpose="chat",
            timeout_seconds=1,
            max_attempts=2,
            usage_logger=_usage_collector(usage_calls),
        )
    ]

    assert chunks == ["[Повтор попытки...]", "OK"]
    assert len(client.aio.models.calls) == 2
    assert usage_calls[0]["status"] == "success"
    assert usage_calls[0]["output_text"] == "OK"


@pytest.mark.asyncio
async def test_stream_gemini_response_logs_timeout_status():
    usage_calls: list[dict[str, Any]] = []
    client = _FakeClient([asyncio.TimeoutError()])

    chunks = [
        chunk
        async for chunk in stream_gemini_response(
            client=client,
            request=GeminiStreamRequest("models/gemini-test", "hello", None),
            purpose="chat",
            timeout_seconds=1,
            max_attempts=1,
            usage_logger=_usage_collector(usage_calls),
        )
    ]

    assert chunks == ["Error: Timeout (Gemini stream)."]
    assert usage_calls[0]["status"] == "timeout"
    assert usage_calls[0]["provider"] == "gemini"
