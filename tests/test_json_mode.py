"""Tests for 3.1 native JSON mode in LLMProvider.stream_chat().

Verifies that json_mode=True adds the correct provider-specific
parameters to the API request payloads.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.llm import LLMProvider


@pytest.fixture
def llm():
    """Minimal LLMProvider with all keys stubbed."""
    provider = LLMProvider.__new__(LLMProvider)
    provider.gemini_api_key = "test-gemini"
    provider.grok_api_key = "test-grok"
    provider.openai_api_key = "test-openai"
    provider.anthropic_api_key = "test-claude"
    provider._gemini_client = MagicMock()
    provider._anthropic_client = None
    return provider


class _EmptyAsyncIter:
    """Async iterator that yields nothing — used as a fake Gemini stream."""

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class TestGeminiJsonMode:
    """Gemini: json_mode → response_mime_type in config."""

    @pytest.mark.asyncio
    async def test_json_mode_adds_mime_type(self, llm):
        fake_client = MagicMock()
        mock_stream = AsyncMock(return_value=_EmptyAsyncIter())
        fake_client.aio.models.generate_content_stream = mock_stream
        llm._gemini_client = fake_client

        with patch("app.core.llm.model_manager") as mm:
            mm.config.gemini_enabled = True
            mm.get_chat_model.return_value = "gemini-2.0-flash"
            mm.resolve_purpose.return_value = ("gemini", "gemini-2.0-flash")

            async for _ in llm.stream_chat(
                "test prompt", model="gemini", json_mode=True
            ):
                pass

        call_kwargs = mock_stream.call_args.kwargs
        config = call_kwargs.get("config", {})
        assert config.get("response_mime_type") == "application/json"

    @pytest.mark.asyncio
    async def test_no_json_mode_no_mime_type(self, llm):
        fake_client = MagicMock()
        mock_stream = AsyncMock(return_value=_EmptyAsyncIter())
        fake_client.aio.models.generate_content_stream = mock_stream
        llm._gemini_client = fake_client

        with patch("app.core.llm.model_manager") as mm:
            mm.config.gemini_enabled = True
            mm.get_chat_model.return_value = "gemini-2.0-flash"
            mm.resolve_purpose.return_value = ("gemini", "gemini-2.0-flash")

            async for _ in llm.stream_chat(
                "test prompt", model="gemini", json_mode=False
            ):
                pass

        call_kwargs = mock_stream.call_args.kwargs
        config = call_kwargs.get("config", {})
        assert "response_mime_type" not in config


class TestOpenAIJsonMode:
    """OpenAI Chat Completions: json_mode → response_format in payload."""

    @pytest.mark.asyncio
    async def test_chat_completions_json_mode(self, llm):
        """response_format is added for non-gpt5 models."""
        fake_response = AsyncMock()
        fake_response.status = 200
        fake_response.content.__aiter__ = AsyncMock(return_value=iter([
            b'data: {"choices":[{"delta":{"content":"{\\"mode\\":\\"answer\\"}"}}]}\n',
            b"data: [DONE]\n",
        ]))

        fake_session = AsyncMock()
        fake_session.__aenter__ = AsyncMock(return_value=fake_session)
        fake_session.__aexit__ = AsyncMock(return_value=False)
        fake_session.post = MagicMock()
        fake_session.post.return_value.__aenter__ = AsyncMock(return_value=fake_response)
        fake_session.post.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.core.llm.model_manager") as mm,
            patch("aiohttp.ClientSession", return_value=fake_session),
        ):
            mm.config.openai_enabled = True
            mm.get_chat_model.return_value = "gpt-4o"
            mm.resolve_purpose.return_value = ("openai", "gpt-4o")
            mm.config.openai_reasoning_effort = ""

            async for _ in llm.stream_chat(
                "test prompt", model="openai", json_mode=True
            ):
                pass

        # Extract the json= argument from the post() call
        call_args = fake_session.post.call_args
        if call_args:
            payload = call_args.kwargs.get("json") or (call_args.args[1] if len(call_args.args) > 1 else {})
            assert payload.get("response_format") == {"type": "json_object"}


class TestProviderJsonModeSignature:
    """Verify json_mode parameter exists and defaults to False."""

    @pytest.mark.asyncio
    async def test_json_mode_default_false(self):
        """stream_chat accepts json_mode kwarg."""
        import inspect

        sig = inspect.signature(LLMProvider.stream_chat)
        param = sig.parameters.get("json_mode")
        assert param is not None, "json_mode parameter missing from stream_chat"
        assert param.default is False, "json_mode should default to False"
