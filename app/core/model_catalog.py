from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.ollama_config import encode_ollama_cloud_model

DEFAULT_GEMINI_MODELS = [
    "models/gemini-3-flash-preview",
    "models/gemini-2.5-flash-preview",
]

DEFAULT_GROK_MODELS = [
    "grok-3",
    "grok-4-1-fast-non-reasoning",
]

DEFAULT_OPENAI_MODELS = [
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
]

DEFAULT_OLLAMA_MODELS: list[str] = []

DEFAULT_CLAUDE_MODELS = [
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
]


@dataclass(frozen=True)
class ProviderModelSpec:
    provider: str
    chat_model_field: str
    agent_model_fields: tuple[str, ...]
    available_models_attr: str
    default_models: tuple[str, ...]
    enabled_field: str | None = None

    def chat_model(self, config: Any, *, empty_fallback: str = "") -> str:
        value = str(getattr(config, self.chat_model_field, "") or "")
        return value or empty_fallback

    def agent_model(self, config: Any, *, empty_fallback: str = "") -> str:
        for field in self.agent_model_fields:
            value = str(getattr(config, field, "") or "")
            if value:
                return value
        return empty_fallback


PROVIDER_MODEL_SPECS: dict[str, ProviderModelSpec] = {
    "gemini": ProviderModelSpec(
        provider="gemini",
        chat_model_field="chat_model_gemini",
        agent_model_fields=("agent_model_gemini",),
        available_models_attr="available_gemini_models",
        default_models=tuple(DEFAULT_GEMINI_MODELS),
        enabled_field="gemini_enabled",
    ),
    "grok": ProviderModelSpec(
        provider="grok",
        chat_model_field="chat_model_grok",
        agent_model_fields=("agent_model_grok",),
        available_models_attr="available_grok_models",
        default_models=tuple(DEFAULT_GROK_MODELS),
        enabled_field="grok_enabled",
    ),
    "openai": ProviderModelSpec(
        provider="openai",
        chat_model_field="chat_model_openai",
        agent_model_fields=("agent_model_openai",),
        available_models_attr="available_openai_models",
        default_models=tuple(DEFAULT_OPENAI_MODELS),
        enabled_field="openai_enabled",
    ),
    "claude": ProviderModelSpec(
        provider="claude",
        chat_model_field="chat_model_claude",
        agent_model_fields=("chat_model_claude",),
        available_models_attr="available_claude_models",
        default_models=tuple(DEFAULT_CLAUDE_MODELS),
        enabled_field="claude_enabled",
    ),
    "ollama": ProviderModelSpec(
        provider="ollama",
        chat_model_field="chat_model_ollama",
        agent_model_fields=("agent_model_ollama", "chat_model_ollama"),
        available_models_attr="available_ollama_models",
        default_models=tuple(DEFAULT_OLLAMA_MODELS),
        enabled_field="ollama_enabled",
    ),
}


def provider_model_spec(provider: str | None) -> ProviderModelSpec:
    return PROVIDER_MODEL_SPECS.get((provider or "").strip(), PROVIDER_MODEL_SPECS["grok"])


def get_provider_chat_model(config: Any, provider: str | None, *, empty_fallback: str = "") -> str:
    return provider_model_spec(provider).chat_model(config, empty_fallback=empty_fallback)


def get_provider_agent_model(config: Any, provider: str | None, *, empty_fallback: str = "") -> str:
    return provider_model_spec(provider).agent_model(config, empty_fallback=empty_fallback)


def get_provider_default_models(provider: str | None) -> list[str]:
    return list(provider_model_spec(provider).default_models)


def is_config_provider_enabled(config: Any, provider: str | None) -> bool:
    spec = PROVIDER_MODEL_SPECS.get((provider or "").strip())
    if spec is None:
        return True
    enabled_field = spec.enabled_field
    if not enabled_field:
        return True
    return bool(getattr(config, enabled_field, False))


def extract_model_ids(payload: dict) -> list[str]:
    out: list[str] = []
    for item in [*(payload.get("data", []) or []), *(payload.get("models", []) or [])]:
        model_id = item.get("id")
        if isinstance(model_id, str) and model_id:
            out.append(model_id)
    return out


def is_openai_text_model(model_id: str) -> bool:
    mid = (model_id or "").lower()
    if not mid:
        return False

    blocked_prefixes = (
        "text-embedding",
        "omni-moderation",
        "whisper",
        "tts",
        "dall-e",
        "gpt-image",
        "sora",
    )
    if mid.startswith(blocked_prefixes):
        return False

    return (
        mid.startswith("gpt-")
        or mid.startswith("gpt-oss")
        or mid.startswith("codex-")
        or mid.startswith("o1")
        or mid.startswith("o3")
        or mid.startswith("o4")
        or mid.startswith("o5")
    )


def extract_ollama_model_names(payload: dict, *, cloud: bool = False) -> list[str]:
    seen: set[str] = set()
    models: list[str] = []

    for item in payload.get("models", []) or []:
        model_id = item.get("name") or item.get("model")
        if not isinstance(model_id, str):
            continue
        normalized = model_id.strip()
        if not normalized:
            continue
        if cloud:
            normalized = encode_ollama_cloud_model(normalized)
        if normalized in seen:
            continue
        seen.add(normalized)
        models.append(normalized)

    return models


def combine_ollama_models(
    local_models: list[str],
    cloud_models: list[str],
    *,
    prefer_cloud: bool = False,
) -> list[str]:
    ordered_sources = [cloud_models, local_models] if prefer_cloud else [local_models, cloud_models]
    seen: set[str] = set()
    combined: list[str] = []

    for source_models in ordered_sources:
        for model_id in source_models:
            if model_id in seen:
                continue
            seen.add(model_id)
            combined.append(model_id)

    return combined
