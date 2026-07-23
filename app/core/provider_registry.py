"""
Provider Registry - централизованное управление всеми AI провайдерами
"""

import os
import shutil
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.llm_secrets import get_managed_llm_api_key
from app.core.model_config import model_manager
from app.core.provider_adapters import DEFAULT_PROVIDER_ORDER, ProviderAdapter, build_provider_adapters


class ProviderRegistry:
    """
    Реестр всех провайдеров с возможностью включения/отключения
    """

    DEFAULT_ADAPTERS = build_provider_adapters()
    PROVIDERS = {provider_id: adapter.spec.compatibility_payload() for provider_id, adapter in DEFAULT_ADAPTERS.items()}

    def __init__(self, adapters: dict[str, ProviderAdapter] | None = None):
        self._cache = {}
        self._adapters = adapters or build_provider_adapters()

    def is_enabled(self, provider: str) -> bool:
        """
        Проверка, включен ли провайдер

        API провайдеры: проверяем config.{provider}_enabled
        CLI провайдеры: всегда enabled если binary доступен
        """
        adapter = self._adapters.get(provider)
        if adapter is None:
            return False

        return adapter.is_enabled(model_manager.config, self.is_binary_available)

    def is_configured(self, provider: str) -> bool:
        """Проверка, настроен ли провайдер (API key или binary)"""
        adapter = self._adapters.get(provider)
        if adapter is None:
            return False

        return adapter.is_configured(model_manager.config, self._get_api_key, self.is_binary_available)

    @staticmethod
    def _get_api_key(provider: str, *env_names: str) -> str:
        try:
            managed_key = get_managed_llm_api_key(provider)
            if managed_key:
                return managed_key
        except Exception as exc:
            logger.debug("Managed LLM API key lookup skipped for %s: %s", provider, exc)
        for env_name in env_names:
            value = os.getenv(env_name, "").strip()
            if value:
                return value
        return ""

    def is_binary_available(self, provider: str) -> bool:
        """Проверка доступности бинарника CLI"""
        adapter = self._adapters.get(provider)
        if adapter is None:
            return False

        binary = adapter.spec.requires_binary

        if not binary:
            return True  # Нет требования к binary

        # Кэширование результата
        cache_key = f"binary_{binary}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Проверяем через переменную окружения или shutil.which
        env_var = f"{provider.upper()}_CLI_PATH"
        env_path = os.getenv(env_var, "").strip()

        if env_path and Path(env_path).exists():
            self._cache[cache_key] = True
            return True

        # Проверяем через which
        result = shutil.which(binary) is not None
        self._cache[cache_key] = result
        return result

    def get_available_providers(self) -> list[dict[str, Any]]:
        """Получить список enabled и configured провайдеров"""
        available = []

        for provider_id, adapter in self._adapters.items():
            spec = adapter.spec
            enabled = self.is_enabled(provider_id)
            configured = self.is_configured(provider_id)

            if enabled and configured:
                available.append(
                    {
                        "id": provider_id,
                        "name": spec.name,
                        "type": spec.provider_type,
                        "enabled": enabled,
                        "configured": configured,
                    }
                )

        return available

    def get_all_providers(self) -> list[dict[str, Any]]:
        """Получить список всех провайдеров с статусами"""
        providers = []

        for provider_id, adapter in self._adapters.items():
            spec = adapter.spec
            enabled = self.is_enabled(provider_id)
            configured = self.is_configured(provider_id)

            status = "ready" if (enabled and configured) else "disabled" if not enabled else "not_configured"

            providers.append(
                {
                    "id": provider_id,
                    "name": spec.name,
                    "type": spec.provider_type,
                    "status": status,
                    "enabled": enabled,
                    "configured": configured,
                    "requires_key": spec.requires_key,
                    "requires_binary": spec.requires_binary,
                    "optional": spec.optional,
                }
            )

        return providers

    def get_provider_status(self, provider: str) -> dict[str, Any]:
        """Получить детальный статус провайдера"""
        adapter = self._adapters.get(provider)
        if adapter is None:
            return {"error": "Unknown provider"}

        enabled = self.is_enabled(provider)
        configured = self.is_configured(provider)

        result = {
            "id": provider,
            "name": adapter.spec.name,
            "type": adapter.spec.provider_type,
            "enabled": enabled,
            "configured": configured,
            "status": "ready" if (enabled and configured) else "not_ready",
        }

        result.update(adapter.status_details(model_manager.config, self._get_api_key, self.is_binary_available))

        return result

    def get_default_provider(self) -> str | None:
        """Получить провайдер по умолчанию"""
        default = model_manager.config.default_provider

        # Проверяем что default провайдер доступен
        if self.is_enabled(default) and self.is_configured(default):
            return default

        # Fallback: первый доступный API/CLI провайдер
        for provider in DEFAULT_PROVIDER_ORDER:
            if self.is_enabled(provider) and self.is_configured(provider):
                logger.warning(f"Default provider {default} not available, using {provider}")
                return provider

        logger.error("No providers available!")
        return None

    def clear_cache(self):
        """Очистить кэш проверок"""
        self._cache = {}


# Global registry instance
_provider_registry = None


def get_provider_registry() -> ProviderRegistry:
    """Get or create global provider registry instance"""
    global _provider_registry
    if _provider_registry is None:
        _provider_registry = ProviderRegistry()
    return _provider_registry


def set_provider_registry(registry: ProviderRegistry | None) -> None:
    """Install an explicit provider registry for tests or host-managed runtimes."""
    global _provider_registry
    _provider_registry = registry


def reset_provider_registry() -> None:
    """Reset the cached provider registry so the next access creates a fresh instance."""
    set_provider_registry(None)
