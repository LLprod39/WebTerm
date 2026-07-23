from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

RUNTIME_FALLBACK_ORDER = ("openai", "claude", "grok", "gemini", "ollama")
RUNTIME_ENABLED_FIELDS = {
    "gemini": "gemini_enabled",
    "grok": "grok_enabled",
    "claude": "claude_enabled",
    "openai": "openai_enabled",
}


@dataclass(frozen=True)
class RuntimeProviderKeys:
    gemini: str = ""
    grok: str = ""
    claude: str = ""
    openai: str = ""

    @classmethod
    def from_llm_provider(cls, provider: Any) -> RuntimeProviderKeys:
        return cls(
            gemini=(getattr(provider, "gemini_api_key", "") or "").strip(),
            grok=(getattr(provider, "grok_api_key", "") or "").strip(),
            claude=(getattr(provider, "anthropic_api_key", "") or "").strip(),
            openai=(getattr(provider, "openai_api_key", "") or "").strip(),
        )

    def has_key(self, provider: str) -> bool:
        return bool(getattr(self, provider, ""))


def is_runtime_provider_enabled(
    provider: str,
    *,
    config: Any,
    keys: RuntimeProviderKeys,
    ollama_base_url: str,
) -> bool:
    if provider == "ollama":
        return bool(getattr(config, "ollama_enabled", False) and ollama_base_url)

    enabled_field = RUNTIME_ENABLED_FIELDS.get(provider)
    return bool(enabled_field and getattr(config, enabled_field, False) and keys.has_key(provider))


def resolve_stream_provider(
    *,
    requested_provider: str | None,
    requested_specific_model: str | None,
    purpose: str,
    model_manager: Any,
    keys: RuntimeProviderKeys,
    ollama_base_url: str,
    warn: Callable[[str], None] | None = None,
) -> tuple[str, str | None]:
    if requested_provider and requested_provider != "auto":
        return requested_provider, requested_specific_model

    preferred, purpose_model = model_manager.resolve_purpose(purpose)
    specific_model = requested_specific_model or purpose_model

    if keys.has_key(preferred) or is_runtime_provider_enabled(
        preferred,
        config=model_manager.config,
        keys=keys,
        ollama_base_url=ollama_base_url,
    ):
        return preferred, specific_model

    for candidate in RUNTIME_FALLBACK_ORDER:
        if is_runtime_provider_enabled(
            candidate,
            config=model_manager.config,
            keys=keys,
            ollama_base_url=ollama_base_url,
        ):
            if warn is not None:
                warn(f"[{purpose}] provider '{preferred}' is disabled/unconfigured, falling back to '{candidate}'")
            return candidate, specific_model

    return preferred, specific_model
