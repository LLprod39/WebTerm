from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.ai_runtime import LLMExecutionContext, ProviderRouteUnavailableError, ProviderRuntimeError
from app.ai_runtime.targets import canonicalize_target_id, legacy_runtime_provider_id

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
        return _resolve_runtime_target(requested_provider), requested_specific_model

    preferred, purpose_model = model_manager.resolve_purpose(purpose)
    specific_model = requested_specific_model or purpose_model

    runtime_provider = _resolve_runtime_target(preferred)
    if is_runtime_provider_enabled(
        runtime_provider,
        config=model_manager.config,
        keys=keys,
        ollama_base_url=ollama_base_url,
    ):
        return runtime_provider, specific_model

    raise ProviderRouteUnavailableError(
        "Selected provider is disabled or unconfigured",
        details={"purpose": purpose, "target_id": canonicalize_target_id(preferred)},
    )


def apply_execution_context_binding(
    *,
    execution_context: LLMExecutionContext | None,
    requested_provider: str | None,
    requested_specific_model: str | None,
) -> tuple[str | None, str | None]:
    """Apply the already-resolved binding without selecting another route."""
    if execution_context is None or execution_context.binding is None:
        return requested_provider, requested_specific_model
    binding = execution_context.binding
    return binding.target_id, binding.model_id or requested_specific_model


def _resolve_runtime_target(target_id: str) -> str:
    """Resolve old/API target IDs and reject subscription-to-API crossover."""
    try:
        canonical_target = canonicalize_target_id(target_id)
    except ValueError:
        # Preserve the existing unsupported-provider error path for internal
        # adapters not represented by the generative provider registry.
        return target_id

    runtime_provider = legacy_runtime_provider_id(canonical_target)
    if runtime_provider is None:
        raise ProviderRuntimeError(
            "provider_transport_unavailable",
            "Subscription target requires the isolated CLI runner transport",
            details={"target_id": canonical_target},
        )
    return runtime_provider
