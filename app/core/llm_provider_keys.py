from __future__ import annotations

from typing import Any

from loguru import logger

from app.core.llm_secrets import get_managed_llm_api_keys

LLM_KEY_PROVIDERS = ("gemini", "grok", "openai", "claude", "ollama")


async def load_managed_llm_keys() -> dict[str, str]:
    try:
        from asgiref.sync import sync_to_async

        def _read_keys() -> dict[str, str]:
            return get_managed_llm_api_keys(LLM_KEY_PROVIDERS)

        return await sync_to_async(_read_keys, thread_sensitive=True)()
    except Exception as exc:
        logger.debug("Managed LLM API keys unavailable: %s", exc)
        return {}


def apply_managed_llm_keys(provider: Any, model_manager: Any, keys: dict[str, str]) -> None:
    gemini_key = (keys.get("gemini") or "").strip()
    if gemini_key and gemini_key != provider.gemini_api_key:
        provider.gemini_api_key = gemini_key
        provider._gemini_client = None

    grok_key = (keys.get("grok") or "").strip()
    if grok_key:
        provider.grok_api_key = grok_key

    openai_key = (keys.get("openai") or "").strip()
    if openai_key:
        provider.openai_api_key = openai_key

    ollama_key = (keys.get("ollama") or "").strip()
    if ollama_key:
        provider.ollama_api_key = ollama_key

    claude_key = (keys.get("claude") or "").strip()
    if claude_key and claude_key != provider.anthropic_api_key:
        provider.anthropic_api_key = claude_key
        provider._anthropic_client = None

    model_manager.set_api_keys(
        gemini_key=gemini_key or None,
        grok_key=grok_key or None,
        anthropic_key=claude_key or None,
        openai_key=openai_key or None,
        ollama_key=ollama_key or None,
    )
