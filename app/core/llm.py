"""LLM provider facade: keys, clients, and stream entrypoints.

F-08a: stream orchestration lives in ``llm_provider_stream`` and
``llm_provider_tools_stream``. This module keeps provider lifecycle and
thin ``stream_chat`` / ``stream_chat_tools`` wrappers.
"""

import asyncio as asyncio
import contextlib
import os
from collections.abc import AsyncGenerator
from typing import Any

from google import genai
from loguru import logger

from app.core.llm_ollama import (
    build_ollama_request_targets,
    get_ollama_think_value,
)
from app.core.llm_provider_keys import apply_managed_llm_keys, load_managed_llm_keys
from app.core.llm_runtime import (
    _is_retryable_error as _is_retryable_error,
)
from app.core.llm_runtime import (
    _is_timeout_error as _is_timeout_error,
)
from app.core.llm_runtime import (
    _provider_timeout_seconds as _provider_timeout_seconds,
)
from app.core.llm_runtime import (
    with_retry as with_retry,
)
from app.core.llm_usage import log_llm_usage as _log_llm_usage  # noqa: F401 — public re-export for tests
from app.core.model_config import model_manager

_provider_instance: "LLMProvider | None" = None

# Ollama streams model reasoning ("thinking") fragments prefixed with this
# sentinel so the operator chat can turn them into reasoning events. Every other
# consumer (agents, final reports, orchestrator) must drop them from answer text —
# otherwise the raw thinking leaks into the output as «THINK»-littered prose.
_THINK_SENTINELS = ("«THINK»", "\x00THINK\x00")


def is_thinking_chunk(chunk: object) -> bool:
    """True if a stream_chat chunk is a model-thinking fragment, not answer text."""
    return isinstance(chunk, str) and chunk.startswith(_THINK_SENTINELS)


def get_provider() -> "LLMProvider":
    """Return a module-level cached LLMProvider."""
    global _provider_instance
    with contextlib.suppress(Exception):
        model_manager.load_config()
    if _provider_instance is None:
        _provider_instance = LLMProvider()
    return _provider_instance


def reset_provider_cache() -> None:
    """Drop cached provider so changed Settings API keys are picked up."""
    global _provider_instance
    _provider_instance = None


class LLMProvider:
    def __init__(self):
        # Direct LLMProvider() callers are used by agents and tools. Keep them
        # aligned with Settings/.model_config.json, not only get_provider().
        with contextlib.suppress(Exception):
            model_manager.load_config()
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.grok_api_key = os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY") or os.getenv("CODEX_API_KEY")
        self.ollama_api_key = os.getenv("OLLAMA_API_KEY")

        # Set keys in model manager
        model_manager.set_api_keys(
            gemini_key=self.gemini_api_key,
            grok_key=self.grok_api_key,
            anthropic_key=self.anthropic_api_key,
            openai_key=self.openai_api_key,
            ollama_key=self.ollama_api_key,
        )

        # Lazy initialization of clients
        self._gemini_client = None
        self._anthropic_client = None

    @staticmethod
    def _get_ollama_base_url() -> str:
        return model_manager._get_ollama_base_url()

    @staticmethod
    def _get_ollama_base_urls() -> list[str]:
        return model_manager._get_ollama_base_urls()

    @staticmethod
    def _get_ollama_cloud_base_url() -> str:
        return model_manager._get_ollama_cloud_base_url()

    @staticmethod
    def _get_ollama_runtime_mode() -> str:
        return model_manager._get_ollama_runtime_mode()

    @staticmethod
    def _get_ollama_think_value() -> Any | None:
        return get_ollama_think_value(model_manager)

    @staticmethod
    def _build_ollama_request_targets(target_model: str) -> list[dict[str, Any]]:
        return build_ollama_request_targets(target_model, model_manager=model_manager)

    def _get_gemini_client(self):
        """Lazy load Gemini client only when enabled"""
        if not model_manager.config.gemini_enabled:
            return None

        if self._gemini_client is None and self.gemini_api_key:
            try:
                self._gemini_client = genai.Client(api_key=self.gemini_api_key)
                logger.info("Configured Gemini client")
            except Exception as e:
                logger.error(f"Failed to configure Gemini: {e}")
                self._gemini_client = None

        return self._gemini_client

    @property
    def gemini_client(self):
        """Property for backward compatibility"""
        return self._get_gemini_client()

    def _get_anthropic_client(self):
        """Lazy load Anthropic client only when enabled"""
        if not model_manager.config.claude_enabled:
            return None
        if self._anthropic_client is None and self.anthropic_api_key:
            try:
                import anthropic

                self._anthropic_client = anthropic.AsyncAnthropic(api_key=self.anthropic_api_key)
                logger.info("Configured Anthropic client")
            except Exception as e:
                logger.error(f"Failed to configure Anthropic: {e}")
                self._anthropic_client = None
        return self._anthropic_client

    async def _load_managed_api_keys(self) -> None:
        apply_managed_llm_keys(self, model_manager, await load_managed_llm_keys())

    def set_api_key(self, model: str, key: str):
        if model == "gemini":
            self.gemini_api_key = key
            model_manager.set_api_keys(gemini_key=key)
            self._gemini_client = None
        elif model == "grok":
            self.grok_api_key = key
            model_manager.set_api_keys(grok_key=key)
        elif model == "claude":
            self.anthropic_api_key = key
            model_manager.set_api_keys(anthropic_key=key)
            self._anthropic_client = None
        elif model == "openai":
            self.openai_api_key = key
            model_manager.set_api_keys(openai_key=key)
        elif model == "ollama":
            self.ollama_api_key = key
            model_manager.set_api_keys(ollama_key=key)

    async def stream_chat(
        self,
        prompt: str,
        model: str = "auto",
        specific_model: str = None,
        purpose: str = "chat",
        system_prompt: str | None = None,
        json_mode: bool = False,
    ) -> AsyncGenerator[str, None]:
        """Stream chat response from the selected model (see llm_provider_stream)."""
        from app.core.llm_provider_stream import stream_provider_chat

        stream = stream_provider_chat(
            self,
            prompt=prompt,
            model=model,
            specific_model=specific_model,
            purpose=purpose,
            system_prompt=system_prompt,
            json_mode=json_mode,
        )
        async with contextlib.aclosing(stream):
            async for chunk in stream:
                yield chunk

    async def stream_chat_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str = "auto",
        specific_model: str | None = None,
        purpose: str = "orchestrator",
        system_prompt: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream chat with native tool-calling (see llm_provider_tools_stream)."""
        from app.core.llm_provider_tools_stream import stream_provider_chat_tools

        stream = stream_provider_chat_tools(
            self,
            messages=messages,
            tools=tools,
            model=model,
            specific_model=specific_model,
            purpose=purpose,
            system_prompt=system_prompt,
        )
        async with contextlib.aclosing(stream):
            async for event in stream:
                yield event


def json_safe_preview(value: Any, limit: int = 2000) -> str:
    try:
        import json as _json

        return _json.dumps(value, ensure_ascii=False, default=str)[:limit]
    except Exception:  # noqa: BLE001
        return str(value)[:limit]
