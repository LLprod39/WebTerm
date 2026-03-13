import asyncio

import pytest
from django.test import override_settings

from app.core.llm import LLMProvider, _is_timeout_error, _provider_timeout_seconds
from app.core.model_config import model_manager


def test_is_timeout_error_detects_timeout_variants():
    assert _is_timeout_error(asyncio.TimeoutError())
    assert _is_timeout_error(TimeoutError("timed out"))
    assert not _is_timeout_error(RuntimeError("boom"))


@override_settings(
    LLM_GROK_STREAM_TIMEOUT_SECONDS=77,
    LLM_OPENAI_RESPONSES_TIMEOUT_SECONDS=222,
)
def test_provider_timeout_seconds_uses_django_settings():
    assert _provider_timeout_seconds("grok") == 77
    assert _provider_timeout_seconds("openai", endpoint_name="responses") == 222


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
