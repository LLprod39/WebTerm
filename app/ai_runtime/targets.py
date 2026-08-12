"""Canonical provider target identifiers and legacy compatibility mapping."""

from __future__ import annotations

from enum import StrEnum


class ProviderTarget(StrEnum):
    OPENAI_API = "openai_api"
    GROK_API = "grok_api"
    CLAUDE_API = "claude_api"
    GEMINI_API = "gemini_api"
    OLLAMA_LOCAL = "ollama_local"
    CODEX_SUBSCRIPTION = "codex_subscription"
    GROK_SUBSCRIPTION = "grok_subscription"


CANONICAL_PROVIDER_TARGETS = frozenset(target.value for target in ProviderTarget)
SUBSCRIPTION_PROVIDER_TARGETS = frozenset(
    {ProviderTarget.CODEX_SUBSCRIPTION.value, ProviderTarget.GROK_SUBSCRIPTION.value}
)

# Existing public IDs remain accepted at input boundaries. They never change
# meaning: ``grok`` is still the xAI API, while Grok Build is a distinct target.
LEGACY_PROVIDER_TARGET_ALIASES: dict[str, str] = {
    "openai": ProviderTarget.OPENAI_API,
    "grok": ProviderTarget.GROK_API,
    "claude": ProviderTarget.CLAUDE_API,
    "anthropic": ProviderTarget.CLAUDE_API,
    "gemini": ProviderTarget.GEMINI_API,
    "ollama": ProviderTarget.OLLAMA_LOCAL,
    "codex": ProviderTarget.CODEX_SUBSCRIPTION,
    "codex_cli": ProviderTarget.CODEX_SUBSCRIPTION,
    "grok_cli": ProviderTarget.GROK_SUBSCRIPTION,
    "grok_build": ProviderTarget.GROK_SUBSCRIPTION,
}

_LEGACY_RUNTIME_PROVIDER_IDS: dict[str, str] = {
    ProviderTarget.OPENAI_API: "openai",
    ProviderTarget.GROK_API: "grok",
    ProviderTarget.CLAUDE_API: "claude",
    ProviderTarget.GEMINI_API: "gemini",
    ProviderTarget.OLLAMA_LOCAL: "ollama",
}


def canonicalize_target_id(value: str | ProviderTarget) -> str:
    """Return a canonical target ID or raise a stable validation error."""
    normalized = str(value).strip().lower()
    normalized = LEGACY_PROVIDER_TARGET_ALIASES.get(normalized, normalized)
    if normalized not in CANONICAL_PROVIDER_TARGETS:
        allowed = ", ".join(sorted(CANONICAL_PROVIDER_TARGETS))
        raise ValueError(f"Unknown provider target '{value}'. Expected one of: {allowed}")
    return normalized


def legacy_runtime_provider_id(value: str | ProviderTarget) -> str | None:
    """Map API/local targets to the current provider stream implementation.

    Subscription targets deliberately return ``None``. They must be handled by
    an isolated CLI adapter and must never be converted into provider API calls.
    """
    return _LEGACY_RUNTIME_PROVIDER_IDS.get(canonicalize_target_id(value))


def is_subscription_target(value: str | ProviderTarget) -> bool:
    return canonicalize_target_id(value) in SUBSCRIPTION_PROVIDER_TARGETS
