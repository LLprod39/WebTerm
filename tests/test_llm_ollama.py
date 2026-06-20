from __future__ import annotations

from typing import Any

import pytest

from app.core.llm_ollama import (
    OllamaStreamRequest,
    build_ollama_payload,
    build_ollama_request_targets,
    stream_ollama_response,
)


class _FakeConfig:
    ollama_cloud_enabled = True


class _FakeModelManager:
    config = _FakeConfig()

    def _decode_ollama_cloud_model(self, model_id: str) -> str:
        return model_id.replace(" (cloud)", "")

    def _get_ollama_runtime_mode(self) -> str:
        return "cloud"

    def _is_ollama_cloud_model(self, model_id: str) -> bool:
        return model_id.endswith(" (cloud)")

    def _get_ollama_api_key(self) -> str:
        return "cloud-key"

    def _get_ollama_cloud_base_url(self) -> str:
        return "https://ollama.com"

    def _get_ollama_base_urls(self) -> list[str]:
        return ["http://127.0.0.1:11434"]


class _FakeContent:
    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks

    async def iter_any(self):
        for chunk in self._chunks:
            yield chunk


class _FakeResponse:
    def __init__(self, status: int, chunks: list[bytes] | None = None, text: str = ""):
        self.status = status
        self.content = _FakeContent(chunks or [])
        self._text = text

    async def text(self) -> str:
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FailingResponse:
    def __init__(self, exc: Exception):
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self, responses: list[Any], calls: list[dict[str, Any]], **_kwargs):
        self._responses = responses
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def post(self, url, headers=None, json=None):
        self._calls.append({"url": url, "headers": headers, "json": dict(json or {})})
        return self._responses.pop(0)


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


def test_build_ollama_request_targets_cloud_decodes_model_and_adds_auth_header():
    targets = build_ollama_request_targets(
        "gpt-oss:120b (cloud)",
        model_manager=_FakeModelManager(),
    )

    assert targets == [
        {
            "kind": "cloud",
            "base_url": "https://ollama.com",
            "headers": {
                "Content-Type": "application/json",
                "Authorization": "Bearer cloud-key",
            },
            "model": "gpt-oss:120b",
        }
    ]


def test_build_ollama_payload_includes_json_mode_and_thinking_flag():
    payload = build_ollama_payload(
        OllamaStreamRequest(
            prompt="hello",
            system_prompt=None,
            json_mode=True,
            request_targets=[
                {
                    "kind": "local",
                    "base_url": "http://127.0.0.1:11434",
                    "headers": {"Content-Type": "application/json"},
                    "model": "llama3.2",
                }
            ],
            think_value=False,
        )
    )

    assert payload == {
        "model": "llama3.2",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "hello"},
        ],
        "stream": True,
        "format": "json",
        "think": False,
    }


@pytest.mark.asyncio
async def test_stream_ollama_response_retries_http_errors_and_logs_success(monkeypatch):
    calls: list[dict[str, Any]] = []
    usage_calls: list[dict[str, Any]] = []
    base_updates: list[str] = []
    responses = [
        _FakeResponse(500, text="temporary"),
        _FakeResponse(
            200,
            chunks=[
                b'{"message":{"content":"Hel"},"done":false}\n',
                b'{"message":{"content":"lo"},"done":false}\n',
                b'{"done":true}\n',
            ],
        ),
    ]

    monkeypatch.setattr(
        "app.core.llm_ollama.aiohttp.ClientSession",
        lambda **kwargs: _FakeSession(responses, calls, **kwargs),
    )

    async def _no_sleep(_delay):
        return None

    monkeypatch.setattr("app.core.llm_ollama.asyncio.sleep", _no_sleep)

    chunks = [
        chunk
        async for chunk in stream_ollama_response(
            request=OllamaStreamRequest(
                prompt="hello",
                system_prompt="Be brief.",
                json_mode=False,
                request_targets=[
                    {
                        "kind": "local",
                        "base_url": "http://127.0.0.1:11434",
                        "headers": {"Content-Type": "application/json"},
                        "model": "llama3.2",
                    }
                ],
            ),
            purpose="chat",
            timeout_seconds=1,
            max_attempts=2,
            usage_logger=_usage_collector(usage_calls),
            get_configured_base_url=lambda: "http://127.0.0.1:11434",
            set_configured_base_url=base_updates.append,
            is_connect_error=lambda _exc: False,
        )
    ]

    assert chunks == ["[Повтор попытки...]", "Hel", "lo"]
    assert [call["url"] for call in calls] == [
        "http://127.0.0.1:11434/api/chat",
        "http://127.0.0.1:11434/api/chat",
    ]
    assert base_updates == ["http://127.0.0.1:11434"]
    assert usage_calls[0]["provider"] == "ollama"
    assert usage_calls[0]["model_name"] == "llama3.2"
    assert usage_calls[0]["output_text"] == "Hello"
    assert usage_calls[0]["metadata"]["base_url"] == "http://127.0.0.1:11434"


@pytest.mark.asyncio
async def test_stream_ollama_response_falls_back_to_next_local_base_url(monkeypatch):
    calls: list[dict[str, Any]] = []
    usage_calls: list[dict[str, Any]] = []
    base_updates: list[str] = []
    responses = [
        _FailingResponse(OSError("Cannot connect to host 127.0.0.1:11434")),
        _FakeResponse(
            200,
            chunks=[
                b'{"message":{"content":"WSL "},"done":false}\n',
                b'{"message":{"content":"OK"},"done":false}\n',
                b'{"done":true}\n',
            ],
        ),
    ]

    monkeypatch.setattr(
        "app.core.llm_ollama.aiohttp.ClientSession",
        lambda **kwargs: _FakeSession(responses, calls, **kwargs),
    )

    chunks = [
        chunk
        async for chunk in stream_ollama_response(
            request=OllamaStreamRequest(
                prompt="hello",
                system_prompt=None,
                json_mode=False,
                request_targets=[
                    {
                        "kind": "local",
                        "base_url": "http://127.0.0.1:11434",
                        "headers": {"Content-Type": "application/json"},
                        "model": "glm-4.7",
                    },
                    {
                        "kind": "local",
                        "base_url": "http://10.255.255.254:11434",
                        "headers": {"Content-Type": "application/json"},
                        "model": "glm-4.7",
                    },
                ],
            ),
            purpose="chat",
            timeout_seconds=1,
            max_attempts=1,
            usage_logger=_usage_collector(usage_calls),
            get_configured_base_url=lambda: "http://127.0.0.1:11434",
            set_configured_base_url=base_updates.append,
            is_connect_error=lambda exc: isinstance(exc, OSError),
        )
    ]

    assert chunks == ["WSL ", "OK"]
    assert [call["url"] for call in calls] == [
        "http://127.0.0.1:11434/api/chat",
        "http://10.255.255.254:11434/api/chat",
    ]
    assert base_updates == ["http://10.255.255.254:11434"]
    assert usage_calls[0]["output_text"] == "WSL OK"
