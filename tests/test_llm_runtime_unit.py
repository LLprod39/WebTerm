import asyncio

import pytest
from django.test import override_settings

from app.core.llm import LLMProvider, _is_timeout_error, _provider_timeout_seconds
from app.core.model_config import ModelManager, model_manager


def test_is_timeout_error_detects_timeout_variants():
    assert _is_timeout_error(asyncio.TimeoutError())
    assert _is_timeout_error(TimeoutError("timed out"))
    assert not _is_timeout_error(RuntimeError("boom"))


@override_settings(
    LLM_GROK_STREAM_TIMEOUT_SECONDS=77,
    LLM_OPENAI_RESPONSES_TIMEOUT_SECONDS=222,
    LLM_OLLAMA_STREAM_TIMEOUT_SECONDS=333,
)
def test_provider_timeout_seconds_uses_django_settings():
    assert _provider_timeout_seconds("grok") == 77
    assert _provider_timeout_seconds("openai", endpoint_name="responses") == 222
    assert _provider_timeout_seconds("ollama") == 333


@pytest.mark.asyncio
async def test_gemini_stream_chat_returns_timeout_message(monkeypatch):
    provider = LLMProvider()
    provider.gemini_api_key = "test-key"
    provider._gemini_client = object()

    monkeypatch.setattr(model_manager.config, "gemini_enabled", True)
    monkeypatch.setattr(model_manager, "get_chat_model", lambda _provider: "gemini-test")
    monkeypatch.setattr("app.core.llm._log_llm_usage", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.core.llm._provider_timeout_seconds", lambda provider_name, **kwargs: 1)

    async def _raise_timeout(awaitable, timeout=None):
        if asyncio.iscoroutine(awaitable):
            awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr("app.core.llm.asyncio.wait_for", _raise_timeout)

    chunks = [chunk async for chunk in provider.stream_chat("hello", model="gemini")]

    assert chunks == ["Error: Timeout (Gemini stream)."]


@pytest.mark.asyncio
async def test_ollama_stream_chat_yields_local_response(monkeypatch):
    provider = LLMProvider()

    monkeypatch.setattr(model_manager.config, "ollama_enabled", True)
    monkeypatch.setattr(model_manager.config, "ollama_base_url", "http://127.0.0.1:11434")
    monkeypatch.setattr(model_manager, "get_chat_model", lambda _provider: "llama3.2:latest")
    monkeypatch.setattr("app.core.llm._log_llm_usage", lambda *args, **kwargs: None)

    class FakeContent:
        async def iter_any(self):
            for chunk in (
                b'{"message":{"content":"Hel"},"done":false}\n',
                b'{"message":{"content":"lo"},"done":false}\n',
                b'{"done":true}\n',
            ):
                yield chunk

    class FakeResponse:
        status = 200
        content = FakeContent()

        async def text(self):
            return ""

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers=None, json=None):
            assert url == "http://127.0.0.1:11434/api/chat"
            assert json["model"] == "llama3.2:latest"
            return FakeResponse()

    monkeypatch.setattr("aiohttp.ClientSession", FakeSession)
    monkeypatch.setattr("aiohttp.ClientTimeout", lambda total: object())

    chunks = [chunk async for chunk in provider.stream_chat("hello", model="ollama")]

    assert chunks == ["Hel", "lo"]


@pytest.mark.asyncio
async def test_ollama_stream_chat_falls_back_to_next_base_url(monkeypatch):
    provider = LLMProvider()

    monkeypatch.setattr(model_manager.config, "ollama_enabled", True)
    monkeypatch.setattr(model_manager.config, "ollama_base_url", "http://127.0.0.1:11434")
    monkeypatch.setattr(model_manager.config, "ollama_runtime_mode", "auto")
    monkeypatch.setattr(model_manager, "get_chat_model", lambda _provider: "glm-4.7-flash:latest")
    monkeypatch.setattr(model_manager, "_get_ollama_base_urls", lambda: [
        "http://127.0.0.1:11434",
        "http://10.255.255.254:11434",
    ])
    monkeypatch.setattr("app.core.llm._log_llm_usage", lambda *args, **kwargs: None)

    calls = []

    class FailingResponse:
        async def __aenter__(self):
            raise OSError("Cannot connect to host 127.0.0.1:11434")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeContent:
        async def iter_any(self):
            for chunk in (
                b'{"message":{"content":"WSL "},"done":false}\n',
                b'{"message":{"content":"OK"},"done":false}\n',
                b'{"done":true}\n',
            ):
                yield chunk

    class SuccessResponse:
        status = 200
        content = FakeContent()

        async def text(self):
            return ""

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers=None, json=None):
            calls.append(url)
            if url.startswith("http://127.0.0.1:11434"):
                return FailingResponse()
            return SuccessResponse()

    monkeypatch.setattr("aiohttp.ClientSession", FakeSession)
    monkeypatch.setattr("aiohttp.ClientTimeout", lambda total: object())

    chunks = [chunk async for chunk in provider.stream_chat("hello", model="ollama")]

    assert calls == [
        "http://127.0.0.1:11434/api/chat",
        "http://10.255.255.254:11434/api/chat",
    ]
    assert chunks == ["WSL ", "OK"]
    assert model_manager.config.ollama_base_url == "http://10.255.255.254:11434"


@pytest.mark.asyncio
async def test_fetch_available_ollama_models_uses_wsl_fallback(monkeypatch):
    manager = ModelManager()
    manager.config.ollama_enabled = True
    manager.config.ollama_base_url = "http://127.0.0.1:11434"
    monkeypatch.setattr(manager, "_get_ollama_base_urls", lambda: [
        "http://127.0.0.1:11434",
        "http://10.255.255.254:11434",
    ])

    class FakeResponse:
        def __init__(self, status_code, payload=None, text=""):
            self.status_code = status_code
            self._payload = payload or {}
            self.text = text

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            if url == "http://127.0.0.1:11434/api/tags":
                raise OSError("Connection refused")
            return FakeResponse(
                200,
                {
                    "models": [
                        {"name": "glm-4.7-flash:latest"},
                        {"model": "qwen2.5-coder:7b"},
                    ]
                },
            )

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)

    models = await manager.fetch_available_ollama_models()

    assert models == ["glm-4.7-flash:latest", "qwen2.5-coder:7b"]
    assert manager.config.ollama_base_url == "http://10.255.255.254:11434"


@pytest.mark.asyncio
async def test_fetch_available_ollama_models_merges_cloud_catalog(monkeypatch):
    manager = ModelManager()
    manager.config.ollama_base_url = "http://127.0.0.1:11434"
    manager.config.ollama_cloud_enabled = True
    manager.config.ollama_cloud_base_url = "https://ollama.com"
    monkeypatch.setattr(manager, "_get_ollama_base_urls", lambda: ["http://127.0.0.1:11434"])
    monkeypatch.setenv("OLLAMA_API_KEY", "cloud-key")

    class FakeResponse:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self._payload = payload or {}

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            if url == "http://127.0.0.1:11434/api/tags":
                return FakeResponse(200, {"models": [{"name": "llama3.2:latest"}]})
            assert url == "https://ollama.com/api/tags"
            assert headers == {"Authorization": "Bearer cloud-key"}
            return FakeResponse(200, {"models": [{"name": "gpt-oss:120b"}]})

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)

    models = await manager.fetch_available_ollama_models()

    assert models == ["llama3.2:latest", "gpt-oss:120b (cloud)"]
    assert manager.available_ollama_local_models == ["llama3.2:latest"]
    assert manager.available_ollama_cloud_models == ["gpt-oss:120b (cloud)"]


@pytest.mark.asyncio
async def test_ollama_stream_chat_cloud_uses_api_key_and_disables_thinking(monkeypatch):
    provider = LLMProvider()

    monkeypatch.setattr(model_manager.config, "ollama_enabled", True)
    monkeypatch.setattr(model_manager.config, "ollama_runtime_mode", "cloud")
    monkeypatch.setattr(model_manager.config, "ollama_cloud_enabled", True)
    monkeypatch.setattr(model_manager.config, "ollama_cloud_base_url", "https://ollama.com")
    monkeypatch.setattr(model_manager.config, "ollama_think_mode", "off")
    monkeypatch.setenv("OLLAMA_API_KEY", "cloud-key")
    monkeypatch.setattr(model_manager, "get_chat_model", lambda _provider: "gpt-oss:120b (cloud)")
    monkeypatch.setattr("app.core.llm._log_llm_usage", lambda *args, **kwargs: None)

    class FakeContent:
        async def iter_any(self):
            for chunk in (
                b'{"message":{"content":"Cloud "},"done":false}\n',
                b'{"message":{"content":"OK"},"done":false}\n',
                b'{"done":true}\n',
            ):
                yield chunk

    class FakeResponse:
        status = 200
        content = FakeContent()

        async def text(self):
            return ""

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers=None, json=None):
            assert url == "https://ollama.com/api/chat"
            assert headers == {
                "Content-Type": "application/json",
                "Authorization": "Bearer cloud-key",
            }
            assert json["model"] == "gpt-oss:120b"
            assert json["think"] is False
            return FakeResponse()

    monkeypatch.setattr("aiohttp.ClientSession", FakeSession)
    monkeypatch.setattr("aiohttp.ClientTimeout", lambda total: object())

    chunks = [chunk async for chunk in provider.stream_chat("hello", model="ollama")]

    assert chunks == ["Cloud ", "OK"]
