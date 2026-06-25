from __future__ import annotations

import pytest

from app.core import model_refresh
from app.core.model_config import ModelManager


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_fetch_available_gemini_models_handles_pagination_and_filters_generate_content(monkeypatch):
    manager = ModelManager()
    manager.gemini_api_key = "gemini-key"
    calls: list[dict] = []
    responses = [
        _FakeResponse(
            200,
            {
                "models": [
                    {"name": "models/gemini-z", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/embed", "supportedGenerationMethods": ["embedContent"]},
                ],
                "nextPageToken": "next",
            },
        ),
        _FakeResponse(
            200,
            {
                "models": [
                    {"name": "models/gemini-a", "supportedGenerationMethods": ["generateContent"]},
                ],
            },
        ),
    ]

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None, headers=None, timeout=None):
            calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
            return responses.pop(0)

    monkeypatch.setattr("app.core.model_refresh.httpx.AsyncClient", FakeAsyncClient)

    models = await model_refresh.fetch_available_gemini_models(manager)

    assert models == ["models/gemini-a", "models/gemini-z"]
    assert manager.available_gemini_models == models
    assert [call["params"].get("pageToken") for call in calls] == [None, "next"]


@pytest.mark.asyncio
async def test_fetch_available_openai_models_filters_non_text_models(monkeypatch):
    manager = ModelManager()
    manager.openai_api_key = "openai-key"

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            assert url == "https://api.openai.com/v1/models"
            assert headers == {"Authorization": "Bearer openai-key"}
            return _FakeResponse(
                200,
                {
                    "data": [
                        {"id": "gpt-5-mini"},
                        {"id": "text-embedding-3-large"},
                        {"id": "dall-e-3"},
                        {"id": "o4-mini"},
                    ]
                },
            )

    monkeypatch.setattr("app.core.model_refresh.httpx.AsyncClient", FakeAsyncClient)

    models = await model_refresh.fetch_available_openai_models(manager)

    assert models == ["gpt-5-mini", "o4-mini"]
    assert manager.available_openai_models == models


@pytest.mark.asyncio
async def test_fetch_available_grok_models_accepts_xai_env_and_language_models_payload(monkeypatch):
    manager = ModelManager()
    calls: list[dict] = []

    async def fake_managed_key(_provider: str) -> str:
        return ""

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None, timeout=None):
            calls.append({"url": url, "headers": headers, "timeout": timeout})
            assert url == "https://api.x.ai/v1/language-models"
            assert headers == {"Authorization": "Bearer xai-key"}
            return _FakeResponse(
                200,
                {
                    "models": [
                        {"id": "grok-4.3"},
                        {"id": "grok-4.3-mini"},
                    ]
                },
            )

    monkeypatch.setattr(manager, "_aget_managed_llm_api_key", fake_managed_key)
    monkeypatch.setenv("XAI_API_KEY", "xai-key")
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    monkeypatch.setattr("app.core.model_refresh.httpx.AsyncClient", FakeAsyncClient)

    models = await model_refresh.fetch_available_grok_models(manager)

    assert models == ["grok-4.3", "grok-4.3-mini"]
    assert manager.grok_api_key == "xai-key"
    assert manager.available_grok_models == models
    assert len(calls) == 1
