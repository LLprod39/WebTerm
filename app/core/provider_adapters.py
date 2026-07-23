from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ApiKeyLookup = Callable[..., str]
BinaryLookup = Callable[[str], bool]


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    provider_type: str
    name: str
    enabled_by_default: bool = False
    enabled_field: str | None = None
    requires_key: str | None = None
    key_env_names: tuple[str, ...] = ()
    requires_binary: str | None = None
    check_method: str = "api"
    optional: bool = False

    def compatibility_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.provider_type,
            "name": self.name,
            "enabled_by_default": self.enabled_by_default,
            "check_method": self.check_method,
        }
        if self.requires_key:
            payload["requires_key"] = self.requires_key
        if self.requires_binary:
            payload["requires_binary"] = self.requires_binary
        if self.optional:
            payload["optional"] = True
        return payload


class ProviderAdapter:
    def __init__(self, spec: ProviderSpec):
        self.spec = spec

    def is_enabled(self, config: Any, binary_lookup: BinaryLookup) -> bool:
        if self.spec.provider_type == "cli":
            return self.spec.requires_binary is None or binary_lookup(self.spec.id)
        if self.spec.enabled_field:
            return bool(getattr(config, self.spec.enabled_field, False))
        return False

    def is_configured(self, config: Any, key_lookup: ApiKeyLookup, binary_lookup: BinaryLookup) -> bool:
        if self.spec.requires_key and not key_lookup(self.spec.id, *self.spec.key_env_names):
            return False
        return not (self.spec.requires_binary and not binary_lookup(self.spec.id))

    def status_details(
        self,
        config: Any,
        key_lookup: ApiKeyLookup,
        binary_lookup: BinaryLookup,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.spec.requires_key:
            result["api_key_set"] = bool(key_lookup(self.spec.id, *self.spec.key_env_names))
            result["api_key_name"] = self._api_key_display_name()

        if self.spec.requires_binary:
            result["binary_name"] = self.spec.requires_binary
            result["binary_available"] = binary_lookup(self.spec.id)
            if result["binary_available"]:
                result["binary_path"] = _binary_path(self.spec.id, self.spec.requires_binary)

        return result

    def _api_key_display_name(self) -> str:
        if self.spec.id == "openai":
            return "OPENAI_API_KEY/CODEX_API_KEY"
        return self.spec.requires_key or ""


class OllamaProviderAdapter(ProviderAdapter):
    def is_configured(self, config: Any, key_lookup: ApiKeyLookup, binary_lookup: BinaryLookup) -> bool:
        base_url = _ollama_base_url(config)
        cloud_enabled = bool(getattr(config, "ollama_cloud_enabled", False))
        cloud_api_key = bool(key_lookup("ollama", "OLLAMA_API_KEY"))
        return bool(base_url) or (cloud_enabled and cloud_api_key)

    def status_details(
        self,
        config: Any,
        key_lookup: ApiKeyLookup,
        binary_lookup: BinaryLookup,
    ) -> dict[str, Any]:
        return {
            "base_url": _ollama_base_url(config),
            "runtime_mode": getattr(config, "ollama_runtime_mode", "auto") or "auto",
            "cloud_enabled": bool(getattr(config, "ollama_cloud_enabled", False)),
            "cloud_api_key_set": bool(key_lookup("ollama", "OLLAMA_API_KEY")),
            "cloud_base_url": _ollama_cloud_base_url(config),
            "think_mode": getattr(config, "ollama_think_mode", "") or "",
        }


def _binary_path(provider_id: str, binary: str) -> str | None:
    env_path = os.getenv(f"{provider_id.upper()}_CLI_PATH")
    return env_path or shutil.which(binary)


def _ollama_base_url(config: Any) -> str:
    return (
        (getattr(config, "ollama_base_url", "") or "").strip()
        or os.getenv("OLLAMA_BASE_URL", "").strip()
        or "http://127.0.0.1:11434"
    )


def _ollama_cloud_base_url(config: Any) -> str:
    return (
        getattr(config, "ollama_cloud_base_url", "").strip()
        or os.getenv("OLLAMA_CLOUD_BASE_URL", "").strip()
        or "https://ollama.com"
    )


DEFAULT_PROVIDER_ORDER = ("openai", "grok", "gemini", "ollama", "ralph", "cursor", "claude")

PROVIDER_SPECS: dict[str, ProviderSpec] = {
    "gemini": ProviderSpec(
        id="gemini",
        provider_type="api",
        name="Google Gemini",
        enabled_field="gemini_enabled",
        requires_key="GEMINI_API_KEY",
        key_env_names=("GEMINI_API_KEY",),
    ),
    "grok": ProviderSpec(
        id="grok",
        provider_type="api",
        name="xAI Grok",
        enabled_by_default=True,
        enabled_field="grok_enabled",
        requires_key="GROK_API_KEY or XAI_API_KEY",
        key_env_names=("GROK_API_KEY", "XAI_API_KEY"),
    ),
    "openai": ProviderSpec(
        id="openai",
        provider_type="api",
        name="OpenAI API",
        enabled_field="openai_enabled",
        requires_key="OPENAI_API_KEY",
        key_env_names=("OPENAI_API_KEY", "CODEX_API_KEY"),
    ),
    "ollama": ProviderSpec(
        id="ollama",
        provider_type="api",
        name="Ollama",
        enabled_field="ollama_enabled",
        check_method="http",
    ),
    "cursor": ProviderSpec(
        id="cursor",
        provider_type="cli",
        name="Cursor CLI",
        enabled_by_default=True,
        requires_key="CURSOR_API_KEY",
        key_env_names=("CURSOR_API_KEY",),
        requires_binary="agent",
        check_method="binary",
    ),
    "claude": ProviderSpec(
        id="claude",
        provider_type="cli",
        name="Claude Code CLI",
        enabled_by_default=True,
        requires_key="ANTHROPIC_API_KEY",
        key_env_names=("ANTHROPIC_API_KEY",),
        requires_binary="claude",
        check_method="binary",
    ),
    "ralph": ProviderSpec(
        id="ralph",
        provider_type="cli",
        name="Ralph Orchestrator",
        enabled_by_default=True,
        requires_binary="ralph",
        check_method="binary",
        optional=True,
    ),
}


def build_provider_adapters() -> dict[str, ProviderAdapter]:
    adapters: dict[str, ProviderAdapter] = {}
    for provider_id, spec in PROVIDER_SPECS.items():
        if provider_id == "ollama":
            adapters[provider_id] = OllamaProviderAdapter(spec)
        else:
            adapters[provider_id] = ProviderAdapter(spec)
    return adapters
