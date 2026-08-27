from __future__ import annotations

import pytest
from loguru import logger

from app.core.llm_openai_compatible import (
    OpenAICompatibleRequest,
    build_openai_request,
    stream_openai_compatible_response,
)
from app.core.llm_http_errors import provider_http_error
from app.core.llm_stream_openai import stream_openai_tools


class _AsyncByteStream:
    def __init__(self, chunks: list[bytes]):
        self._chunks = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._chunks)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeResponse:
    def __init__(self, status: int, chunks: list[bytes] | None = None, text: str = ""):
        self.status = status
        self.content = _AsyncByteStream(chunks or [])
        self._text = text

    async def text(self) -> str:
        return self._text


class _ResponseContext:
    def __init__(self, response: _FakeResponse):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse], calls: list[dict]):
        self._responses = responses
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def post(self, url, headers=None, json=None):
        self._calls.append({"url": url, "headers": headers, "json": json})
        return _ResponseContext(self._responses.pop(0))


def test_build_openai_request_uses_responses_json_mode_and_reasoning_hint():
    request = build_openai_request(
        target_model="gpt-5-nano",
        prompt="summarize this",
        system_prompt="Be exact.",
        json_mode=True,
        reasoning_effort="low",
    )

    assert request.endpoint_name == "responses"
    assert request.api_url == "https://api.openai.com/v1/responses"
    assert request.payload["instructions"] == "Be exact."
    assert request.payload["text"] == {"format": {"type": "json_object"}}
    assert "valid JSON object" in request.payload["input"]
    assert request.payload["reasoning"] == {"effort": "low"}


@pytest.mark.asyncio
async def test_stream_openai_compatible_response_retries_and_logs_usage(monkeypatch):
    calls: list[dict] = []
    session_kwargs: list[dict] = []
    usage_calls: list[dict] = []
    responses = [
        _FakeResponse(500, text="temporary failure"),
        _FakeResponse(
            200,
            chunks=[
                b"event: message\n",
                b'data: {"choices":[{"delta":{"content":"Hel"}}]}\n',
                b'data: {"choices":[{"delta":{"content":"lo"}}]}\n',
                b"data: [DONE]\n",
            ],
        ),
    ]

    def _session_factory(**kwargs):
        session_kwargs.append(kwargs)
        return _FakeSession(responses, calls)

    monkeypatch.setattr("app.core.llm_openai_compatible.aiohttp.ClientSession", _session_factory)

    async def _no_sleep(_delay):
        return None

    monkeypatch.setattr("app.core.llm_openai_compatible.asyncio.sleep", _no_sleep)

    def _usage_logger(provider, model_name, input_text, output_text, duration_ms, status="success", **kwargs):
        usage_calls.append(
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

    chunks = [
        chunk
        async for chunk in stream_openai_compatible_response(
            provider="custom",
            display_name="Custom OpenAI-compatible API",
            request=OpenAICompatibleRequest(
                endpoint_name="chat",
                api_url="https://llm.example/chat/completions",
                payload={"model": "custom-model", "stream": True},
            ),
            headers={"Authorization": "Bearer test"},
            target_model="custom-model",
            prompt="hello",
            purpose="chat",
            timeout_seconds=1,
            max_attempts=2,
            usage_logger=_usage_logger,
            log_metadata={"base_url": "https://llm.example"},
            trust_env=True,
        )
    ]

    assert chunks == ["[Повтор попытки...]", "Hel", "lo"]
    assert [kwargs["trust_env"] for kwargs in session_kwargs] == [True, True]
    assert [call["url"] for call in calls] == [
        "https://llm.example/chat/completions",
        "https://llm.example/chat/completions",
    ]
    assert usage_calls == [
        {
            "provider": "custom",
            "model_name": "custom-model",
            "input_text": "hello",
            "output_text": "Hello",
            "duration_ms": usage_calls[0]["duration_ms"],
            "status": "success",
            "purpose": "chat",
            "metadata": {"base_url": "https://llm.example"},
        }
    ]


@pytest.mark.asyncio
async def test_stream_openai_compatible_response_parses_responses_api(monkeypatch):
    calls: list[dict] = []
    usage_calls: list[dict] = []
    responses = [
        _FakeResponse(
            200,
            chunks=[
                b'data: {"type":"response.output_text.delta","delta":"{\\"ok\\":"}\n',
                b'data: {"type":"response.output_text.delta","delta":"true}"}\n',
                b'data: {"type":"response.completed"}\n',
            ],
        )
    ]

    monkeypatch.setattr(
        "app.core.llm_openai_compatible.aiohttp.ClientSession",
        lambda **_kwargs: _FakeSession(responses, calls),
    )

    def _usage_logger(*args, **kwargs):
        usage_calls.append({"args": args, "kwargs": kwargs})

    chunks = [
        chunk
        async for chunk in stream_openai_compatible_response(
            provider="openai",
            display_name="OpenAI",
            request=OpenAICompatibleRequest(
                endpoint_name="responses",
                api_url="https://api.openai.com/v1/responses",
                payload={"model": "gpt-5-nano", "stream": True},
            ),
            headers={"Authorization": "Bearer test"},
            target_model="gpt-5-nano",
            prompt="json",
            purpose="chat",
            timeout_seconds=1,
            max_attempts=1,
            usage_logger=_usage_logger,
        )
    ]

    assert chunks == ['{"ok":', "true}"]
    assert usage_calls[0]["args"][0:4] == ("openai", "gpt-5-nano", "json", '{"ok":true}')


@pytest.mark.asyncio
async def test_provider_quota_response_is_classified_without_exposing_raw_body(monkeypatch):
    sensitive_body = (
        '{"code":"permission-denied","error":"Your team team-sensitive-id has either used all available '
        'credits or reached its monthly spending limit."}'
    )
    responses = [_FakeResponse(403, text=sensitive_body)]
    monkeypatch.setattr(
        "app.core.llm_openai_compatible.aiohttp.ClientSession",
        lambda **_kwargs: _FakeSession(responses, []),
    )

    log_messages: list[str] = []
    sink_id = logger.add(lambda message: log_messages.append(str(message)), format="{message}")
    try:
        chunks = [
            chunk
            async for chunk in stream_openai_compatible_response(
                provider="grok",
                display_name="Grok",
                request=OpenAICompatibleRequest(
                    endpoint_name="chat",
                    api_url="https://api.x.ai/v1/chat/completions",
                    payload={"model": "grok-3", "stream": True},
                ),
                headers={"Authorization": "Bearer test"},
                target_model="grok-3",
                prompt="hello",
                purpose="chat",
                timeout_seconds=1,
                max_attempts=1,
                usage_logger=lambda *_args, **_kwargs: None,
            )
        ]
    finally:
        logger.remove(sink_id)

    assert chunks == [
        "Error from Grok API: Grok quota or spending limit is exhausted. Contact the platform administrator."
    ]
    assert "team-sensitive-id" not in "".join(chunks)
    assert "team-sensitive-id" not in "".join(log_messages)


def test_transient_429_quota_is_retryable_but_billing_quota_is_not():
    rate_limit = provider_http_error(
        provider="grok",
        display_name="Grok",
        status=429,
        body='{"code":"resource_exhausted","error":"Request quota exceeded per minute"}',
    )
    billing_limit = provider_http_error(
        provider="openai",
        display_name="OpenAI",
        status=429,
        body='{"code":"insufficient_quota","error":"Monthly quota exhausted"}',
    )

    assert rate_limit.code == "provider_rate_limited"
    assert rate_limit.retryable is True
    assert billing_limit.code == "provider_quota_exceeded"
    assert billing_limit.retryable is False


@pytest.mark.asyncio
async def test_plain_stream_sanitizes_transport_exception_and_logs(monkeypatch):
    marker = "plain-transport-secret-marker"
    monkeypatch.setattr(
        "app.core.llm_openai_compatible.aiohttp.ClientSession",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError(marker)),
    )
    log_messages: list[str] = []
    sink_id = logger.add(lambda message: log_messages.append(str(message)), format="{message}")
    try:
        chunks = [
            chunk
            async for chunk in stream_openai_compatible_response(
                provider="grok",
                display_name="Grok",
                request=OpenAICompatibleRequest(
                    endpoint_name="chat",
                    api_url="https://api.x.ai/v1/chat/completions",
                    payload={"model": "grok-3", "stream": True},
                ),
                headers={"Authorization": "Bearer test"},
                target_model="grok-3",
                prompt="hello",
                purpose="chat",
                timeout_seconds=1,
                max_attempts=1,
                usage_logger=lambda *_args, **_kwargs: None,
            )
        ]
    finally:
        logger.remove(sink_id)

    assert chunks == ["Error calling Grok: Provider transport is temporarily unavailable. Try again later."]
    assert marker not in "".join(chunks)
    assert marker not in "".join(log_messages)


@pytest.mark.asyncio
async def test_tool_stream_emits_typed_quota_error_without_provider_body(monkeypatch):
    sensitive_body = '{"error":"team-sensitive-id used all available credits"}'
    responses = [_FakeResponse(403, text=sensitive_body)]
    monkeypatch.setattr(
        "aiohttp.ClientSession",
        lambda **_kwargs: _FakeSession(responses, []),
    )

    events = [
        event
        async for event in stream_openai_tools(
            api_url="https://api.x.ai/v1/chat/completions",
            api_key="test",
            model="grok-3",
            messages=[{"role": "user", "content": "hello"}],
            tools=[],
            system_prompt=None,
            provider="grok",
        )
    ]

    assert events == [
        {
            "type": "error",
            "code": "provider_quota_exceeded",
            "message": "Grok quota or spending limit is exhausted. Contact the platform administrator.",
        }
    ]
    assert "team-sensitive-id" not in str(events)


@pytest.mark.asyncio
async def test_tool_stream_sanitizes_transport_exception_and_logs(monkeypatch):
    marker = "transport-secret-marker"
    monkeypatch.setattr("aiohttp.ClientSession", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError(marker)))
    log_messages: list[str] = []
    sink_id = logger.add(lambda message: log_messages.append(str(message)), format="{message}")
    try:
        events = [
            event
            async for event in stream_openai_tools(
                api_url="https://api.x.ai/v1/chat/completions",
                api_key="test",
                model="grok-3",
                messages=[{"role": "user", "content": "hello"}],
                tools=[],
                system_prompt=None,
                provider="grok",
            )
        ]
    finally:
        logger.remove(sink_id)

    assert events == [
        {
            "type": "error",
            "code": "provider_transport_unavailable",
            "message": "Grok is temporarily unavailable. Try again later.",
        }
    ]
    assert marker not in str(events)
    assert marker not in "".join(log_messages)
