"""
Provider Registry - централизованное управление всеми AI провайдерами
"""
import os
import shutil
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.model_config import model_manager


class ProviderRegistry:
    """
    Реестр всех провайдеров с возможностью включения/отключения
    """

    PROVIDERS = {
        "gemini": {
            "type": "api",
            "name": "Google Gemini",
            "enabled_by_default": False,
            "requires_key": "GEMINI_API_KEY",
            "check_method": "api"
        },
        "grok": {
            "type": "api",
            "name": "xAI Grok",
            "enabled_by_default": True,  # Fallback для внутренних вызовов
            "requires_key": "GROK_API_KEY",
            "check_method": "api"
        },
        "openai": {
            "type": "api",
            "name": "OpenAI API",
            "enabled_by_default": False,
            "requires_key": "OPENAI_API_KEY",
            "check_method": "api"
        },
        "ollama": {
            "type": "api",
            "name": "Ollama",
            "enabled_by_default": False,
            "check_method": "http"
        },
        "cursor": {
            "type": "cli",
            "name": "Cursor CLI",
            "enabled_by_default": True,
            "requires_key": "CURSOR_API_KEY",
            "requires_binary": "agent",
            "check_method": "binary"
        },
        "claude": {
            "type": "cli",
            "name": "Claude Code CLI",
            "enabled_by_default": True,
            "requires_key": "ANTHROPIC_API_KEY",
            "requires_binary": "claude",
            "check_method": "binary"
        },
        "ralph": {
            "type": "cli",
            "name": "Ralph Orchestrator",
            "enabled_by_default": True,  # По умолчанию для DevOps
            "requires_binary": "ralph",
            "check_method": "binary",
            "optional": True  # Опциональный
        }
    }

    def __init__(self):
        self._cache = {}

    def is_enabled(self, provider: str) -> bool:
        """
        Проверка, включен ли провайдер

        API провайдеры: проверяем config.{provider}_enabled
        CLI провайдеры: всегда enabled если binary доступен
        """
        if provider not in self.PROVIDERS:
            return False

        info = self.PROVIDERS[provider]

        # API провайдеры - проверяем config
        if info["type"] == "api":
            if provider == "gemini":
                return model_manager.config.gemini_enabled
            elif provider == "grok":
                return model_manager.config.grok_enabled
            elif provider == "openai":
                return model_manager.config.openai_enabled
            elif provider == "ollama":
                return model_manager.config.ollama_enabled

        # CLI провайдеры - проверяем наличие binary
        elif info["type"] == "cli":
            return self.is_binary_available(provider)

        return False

    def is_configured(self, provider: str) -> bool:
        """Проверка, настроен ли провайдер (API key или binary)"""
        if provider not in self.PROVIDERS:
            return False

        info = self.PROVIDERS[provider]

        # Проверяем API key
        if info.get("requires_key"):
            if provider == "openai":
                key = os.getenv("OPENAI_API_KEY", "").strip() or os.getenv("CODEX_API_KEY", "").strip()
            else:
                key = os.getenv(info["requires_key"], "").strip()
            if not key:
                return False

        if provider == "ollama":
            base_url = (
                (model_manager.config.ollama_base_url or "").strip()
                or os.getenv("OLLAMA_BASE_URL", "").strip()
                or "http://127.0.0.1:11434"
            )
            cloud_enabled = bool(getattr(model_manager.config, "ollama_cloud_enabled", False))
            cloud_api_key = bool((os.getenv("OLLAMA_API_KEY") or "").strip())
            return bool(base_url) or (cloud_enabled and cloud_api_key)

        # Проверяем binary
        return not (info.get("requires_binary") and not self.is_binary_available(provider))

    def is_binary_available(self, provider: str) -> bool:
        """Проверка доступности бинарника CLI"""
        if provider not in self.PROVIDERS:
            return False

        info = self.PROVIDERS[provider]
        binary = info.get("requires_binary")

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

        for provider_id, info in self.PROVIDERS.items():
            enabled = self.is_enabled(provider_id)
            configured = self.is_configured(provider_id)

            if enabled and configured:
                available.append({
                    "id": provider_id,
                    "name": info["name"],
                    "type": info["type"],
                    "enabled": enabled,
                    "configured": configured
                })

        return available

    def get_all_providers(self) -> list[dict[str, Any]]:
        """Получить список всех провайдеров с статусами"""
        providers = []

        for provider_id, info in self.PROVIDERS.items():
            enabled = self.is_enabled(provider_id)
            configured = self.is_configured(provider_id)

            status = "ready" if (enabled and configured) else \
                    "disabled" if not enabled else \
                    "not_configured"

            providers.append({
                "id": provider_id,
                "name": info["name"],
                "type": info["type"],
                "status": status,
                "enabled": enabled,
                "configured": configured,
                "requires_key": info.get("requires_key"),
                "requires_binary": info.get("requires_binary"),
                "optional": info.get("optional", False)
            })

        return providers

    def get_provider_status(self, provider: str) -> dict[str, Any]:
        """Получить детальный статус провайдера"""
        if provider not in self.PROVIDERS:
            return {"error": "Unknown provider"}

        info = self.PROVIDERS[provider]
        enabled = self.is_enabled(provider)
        configured = self.is_configured(provider)

        result = {
            "id": provider,
            "name": info["name"],
            "type": info["type"],
            "enabled": enabled,
            "configured": configured,
            "status": "ready" if (enabled and configured) else "not_ready"
        }

        # Детали конфигурации
        if info.get("requires_key"):
            key_name = info["requires_key"]
            if provider == "openai":
                result["api_key_set"] = bool(os.getenv("OPENAI_API_KEY", "").strip() or os.getenv("CODEX_API_KEY", "").strip())
                result["api_key_name"] = "OPENAI_API_KEY/CODEX_API_KEY"
            else:
                result["api_key_set"] = bool(os.getenv(key_name, "").strip())
                result["api_key_name"] = key_name

        if provider == "ollama":
            result["base_url"] = (
                (model_manager.config.ollama_base_url or "").strip()
                or os.getenv("OLLAMA_BASE_URL", "").strip()
                or "http://127.0.0.1:11434"
            )
            result["runtime_mode"] = getattr(model_manager.config, "ollama_runtime_mode", "auto") or "auto"
            result["cloud_enabled"] = bool(getattr(model_manager.config, "ollama_cloud_enabled", False))
            result["cloud_api_key_set"] = bool((os.getenv("OLLAMA_API_KEY") or "").strip())
            result["cloud_base_url"] = (
                getattr(model_manager.config, "ollama_cloud_base_url", "").strip()
                or os.getenv("OLLAMA_CLOUD_BASE_URL", "").strip()
                or "https://ollama.com"
            )
            result["think_mode"] = getattr(model_manager.config, "ollama_think_mode", "") or ""

        if info.get("requires_binary"):
            binary = info["requires_binary"]
            result["binary_name"] = binary
            result["binary_available"] = self.is_binary_available(provider)

            # Путь к binary если найден
            if result["binary_available"]:
                env_var = f"{provider.upper()}_CLI_PATH"
                env_path = os.getenv(env_var)
                if env_path:
                    result["binary_path"] = env_path
                else:
                    result["binary_path"] = shutil.which(binary)

        return result

    def get_default_provider(self) -> str | None:
        """Получить провайдер по умолчанию"""
        default = model_manager.config.default_provider

        # Проверяем что default провайдер доступен
        if self.is_enabled(default) and self.is_configured(default):
            return default

        # Fallback: первый доступный CLI провайдер
        for provider in ["ralph", "cursor", "claude"]:
            if self.is_enabled(provider) and self.is_configured(provider):
                logger.warning(f"Default provider {default} not available, using {provider}")
                return provider

        # Fallback: Grok для внутренних вызовов
        if self.is_enabled("grok") and self.is_configured("grok"):
            logger.warning("No CLI provider available, using Grok")
            return "grok"

        if self.is_enabled("openai") and self.is_configured("openai"):
            logger.warning("No CLI provider available, using OpenAI")
            return "openai"

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
