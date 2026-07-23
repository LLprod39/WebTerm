from __future__ import annotations

import pytest

from app.core.llm_openai_compatible import (
    OpenAICompatibleRequest,
    build_openai_request,
    stream_openai_compatible_response,
)


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
