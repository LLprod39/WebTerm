from __future__ import annotations

from collections.abc import Callable, Iterable

LLMApiKeyProvider = Callable[[str], str]

_llm_api_key_provider: LLMApiKeyProvider | None = None


def register_llm_api_key_provider(provider: LLMApiKeyProvider | None) -> None:
    """Register the app-level source for UI-managed LLM API keys."""
    global _llm_api_key_provider
    _llm_api_key_provider = provider


def get_managed_llm_api_key(provider: str) -> str:
    if _llm_api_key_provider is None:
        return ""
    return str(_llm_api_key_provider(provider) or "").strip()


def get_managed_llm_api_keys(providers: Iterable[str]) -> dict[str, str]:
    return {provider: get_managed_llm_api_key(provider) for provider in providers}
