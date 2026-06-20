"""
Model Configuration Manager
Manages model selection for different purposes (chat, RAG, agent)
"""
import json
import os

from loguru import logger
from pydantic import BaseModel

from app.core import model_refresh
from app.core.llm_secrets import get_managed_llm_api_key
from app.core.model_catalog import (
    get_provider_agent_model,
    get_provider_chat_model,
    get_provider_default_models,
    is_config_provider_enabled,
    provider_model_spec,
)
from app.core.ollama_config import (
    decode_ollama_cloud_model,
    encode_ollama_cloud_model,
    get_ollama_base_urls,
    is_ollama_cloud_model,
    normalize_ollama_base_url,
    normalize_ollama_cloud_base_url,
    normalize_ollama_runtime_mode,
    normalize_ollama_think_mode,
)
from app.core.redacted_logging import redacted_config_value


class ModelConfig(BaseModel):
    """Configuration for models"""
    # API providers (optional, disabled by default)
    gemini_enabled: bool = False
    grok_enabled: bool = True  # Fallback for internal calls
    openai_enabled: bool = False
    fair_enabled: bool = True
    claude_enabled: bool = False
    ollama_enabled: bool = False

    # Chat models
    chat_model_gemini: str = "models/gemini-3-flash-preview"
    chat_model_grok: str = "grok-3"
    chat_model_openai: str = "gpt-5-mini"
    chat_model_fair: str = "qwen3:14b"
    chat_model_claude: str = "claude-sonnet-4-6"
    chat_model_ollama: str = ""

    # RAG/Embedding models
    rag_model: str = "models/text-embedding-004"  # Gemini embedding

    # Agent/ReAct models
    agent_model_gemini: str = "models/gemini-3-flash-preview"
    agent_model_grok: str = "grok-3"
    agent_model_openai: str = "gpt-5-mini"
    agent_model_fair: str = "fair-spark"
    agent_model_ollama: str = ""

    # Default provider for internal chat/agent routing.
    # Note: "ralph" is NOT a valid provider - it's an orchestrator mode
    default_provider: str = "fair"

    # Провайдер для ВНУТРЕННИХ вызовов LLM (генерация workflow, анализ задач).
    # Когда default_provider - CLI agent, внутренние вызовы используют этот провайдер.
    # Варианты: "gemini", "grok", "openai", "fair", "claude", "ollama"
    internal_llm_provider: str = "fair"

    # Default orchestrator mode: react | ralph_internal | ralph_cli
    default_orchestrator_mode: str = "ralph_internal"

    # Ralph settings
    ralph_max_iterations: int = 20
    ralph_completion_promise: str = "COMPLETE"

    # Папка по умолчанию для сохранения файлов агента (код, артефакты workflow).
    # Относительный путь внутри AGENT_PROJECTS_DIR или пусто = не задано.
    default_agent_output_path: str = ""

    # Режим Cursor CLI в чате при выборе «Авто»: ask — только ответы, agent — агент с правкой файлов.
    cursor_chat_mode: str = "ask"
    # Sandbox для Cursor CLI: пусто = не передавать, "enabled" | "disabled".
    cursor_sandbox: str = ""
    # В headless/чате автоматически одобрять MCP (--approve-mcps).
    cursor_approve_mcps: bool = False

    # OpenAI Responses API: reasoning effort — "low" | "medium" | "high" | "" (не передавать)
    # "low" — быстро, "high" — глубокое мышление, "" — по умолчанию модели
    openai_reasoning_effort: str = "low"

    # Purpose-based LLM configuration (provider + specific model per use-case)
    # Empty string means "inherit from internal_llm_provider / default chat model"
    chat_llm_provider: str = ""
    chat_llm_model: str = ""
    agent_llm_provider: str = ""
    agent_llm_model: str = ""
    orchestrator_llm_provider: str = ""
    orchestrator_llm_model: str = ""

    # Domain SSO settings (None => use Django settings/.env fallback)
    domain_auth_enabled: bool | None = None
    domain_auth_header: str | None = None
    domain_auth_auto_create: bool | None = None
    domain_auth_lowercase_usernames: bool | None = None
    domain_auth_default_profile: str | None = None

    # Ollama runtime
    fair_base_url: str = "https://fair-hyperion.dev.k8s.erg.kz/api/hyperion/openai/v1"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_runtime_mode: str = "auto"
    ollama_cloud_enabled: bool = False
    ollama_cloud_base_url: str = "https://ollama.com"
    ollama_think_mode: str = ""

    # Audit logging configuration
    log_terminal_commands: bool = True
    log_ai_assistant: bool = True
    log_agent_runs: bool = True
    log_pipeline_runs: bool = True
    log_auth_events: bool = True
    log_server_changes: bool = True
    log_settings_changes: bool = True
    log_file_operations: bool = False
    log_mcp_calls: bool = True
    log_http_requests: bool = True
    retention_days: int = 90
    export_format: str = "json"



class ModelManager:
    """Manages available models and configurations"""

    def __init__(self):
        self.config = ModelConfig()
        self.available_gemini_models: list[str] = []
        self.available_grok_models: list[str] = []
        self.available_openai_models: list[str] = []
        self.available_fair_models: list[str] = []
        self.available_claude_models: list[str] = []
        self.available_ollama_models: list[str] = []
        self.available_ollama_local_models: list[str] = []
        self.available_ollama_cloud_models: list[str] = []
        self.gemini_api_key: str | None = None
        self.grok_api_key: str | None = None
        self.openai_api_key: str | None = None
        self.fair_api_key: str | None = None
        self.ollama_api_key: str | None = None
        self.anthropic_api_key: str | None = None

    def set_api_keys(
        self,
        gemini_key: str | None = None,
        grok_key: str | None = None,
        anthropic_key: str | None = None,
        openai_key: str | None = None,
        fair_key: str | None = None,
        ollama_key: str | None = None,
    ):
        """Set API keys"""
        if gemini_key:
            self.gemini_api_key = gemini_key
        if grok_key:
            self.grok_api_key = grok_key
        if anthropic_key:
            self.anthropic_api_key = anthropic_key
        if openai_key:
            self.openai_api_key = openai_key
        if fair_key:
            self.fair_api_key = fair_key
        if ollama_key:
            self.ollama_api_key = ollama_key

    def _get_ollama_api_key(self) -> str:
        return (self.ollama_api_key or "").strip() or (os.getenv("OLLAMA_API_KEY") or "").strip()

    @staticmethod
    def _normalize_fair_base_url(raw: str | None = None) -> str:
        value = (
            (raw or "").strip()
            or (os.getenv("FAIR_HYPERION_BASE_URL") or "").strip()
            or "https://fair-hyperion.dev.k8s.erg.kz/api/hyperion/openai/v1"
        ).rstrip("/")
        if "://" not in value:
            value = f"https://{value}"
        return value.rstrip("/")

    def _get_fair_base_url(self) -> str:
        return self._normalize_fair_base_url(self.config.fair_base_url)

    @staticmethod
    def _get_fair_api_key() -> str:
        return (
            (os.getenv("FAIR_HYPERION_API_KEY") or "").strip()
            or (os.getenv("FAIR_API_KEY") or "").strip()
        )

    @staticmethod
    def _get_managed_llm_api_key(provider: str) -> str:
        try:
            return get_managed_llm_api_key(provider)
        except Exception as exc:
            logger.debug(f"Managed LLM API key lookup skipped for {provider}: {exc}")
            return ""

    @classmethod
    async def _aget_managed_llm_api_key(cls, provider: str) -> str:
        try:
            from asgiref.sync import sync_to_async

            return await sync_to_async(cls._get_managed_llm_api_key, thread_sensitive=True)(provider)
        except Exception as exc:
            logger.debug(f"Async managed LLM API key lookup skipped for {provider}: {exc}")
            return ""

    @staticmethod
    def _encode_ollama_cloud_model(model_id: str) -> str:
        return encode_ollama_cloud_model(model_id)

    @staticmethod
    def _is_ollama_cloud_model(model_id: str | None) -> bool:
        return is_ollama_cloud_model(model_id)

    @staticmethod
    def _decode_ollama_cloud_model(model_id: str | None) -> str:
        return decode_ollama_cloud_model(model_id)

    def _get_ollama_base_url(self) -> str:
        return normalize_ollama_base_url(self.config.ollama_base_url)

    def _get_ollama_cloud_base_url(self) -> str:
        return normalize_ollama_cloud_base_url(self.config.ollama_cloud_base_url)

    def _get_ollama_runtime_mode(self) -> str:
        return normalize_ollama_runtime_mode(self.config.ollama_runtime_mode)

    def _get_ollama_think_mode(self) -> str:
        return normalize_ollama_think_mode(self.config.ollama_think_mode)

    def _get_ollama_base_urls(self) -> list[str]:
        return get_ollama_base_urls(self._get_ollama_base_url())

    async def fetch_available_gemini_models(self) -> list[str]:
        return await model_refresh.fetch_available_gemini_models(self)

    async def fetch_available_grok_models(self) -> list[str]:
        return await model_refresh.fetch_available_grok_models(self)

    async def fetch_available_claude_models(self) -> list[str]:
        return await model_refresh.fetch_available_claude_models(self)

    async def fetch_available_openai_models(self) -> list[str]:
        return await model_refresh.fetch_available_openai_models(self)

    async def fetch_available_fair_models(self) -> list[str]:
        return await model_refresh.fetch_available_fair_models(self)

    async def fetch_available_ollama_models(self) -> list[str]:
        return await model_refresh.fetch_available_ollama_models(self)

    def _get_default_gemini_models(self) -> list[str]:
        """Default Gemini models list (fallback)"""
        return get_provider_default_models("gemini")

    def _get_default_grok_models(self) -> list[str]:
        """Default Grok models list (fallback)"""
        return get_provider_default_models("grok")

    def _get_default_openai_models(self) -> list[str]:
        """Default OpenAI models list (fallback)"""
        return get_provider_default_models("openai")

    def _get_default_fair_models(self) -> list[str]:
        """Default FAIR.Hyperion models list (fallback)."""
        return get_provider_default_models("fair")

    def _get_default_ollama_models(self) -> list[str]:
        """Ollama models are local-install specific; default to no cached models."""
        return get_provider_default_models("ollama")

    async def refresh_models(self):
        """Refresh available models from both providers"""
        logger.info("Refreshing available models...")

        if self.gemini_api_key or (os.getenv("GEMINI_API_KEY") or "").strip() or await self._aget_managed_llm_api_key("gemini"):
            await self.fetch_available_gemini_models()

        if self.grok_api_key or (os.getenv("GROK_API_KEY") or "").strip() or await self._aget_managed_llm_api_key("grok"):
            await self.fetch_available_grok_models()

        if (
            self.openai_api_key
            or (os.getenv("OPENAI_API_KEY") or "").strip()
            or (os.getenv("CODEX_API_KEY") or "").strip()
            or await self._aget_managed_llm_api_key("openai")
        ):
            await self.fetch_available_openai_models()

        if self.fair_api_key or self._get_fair_api_key() or await self._aget_managed_llm_api_key("fair"):
            await self.fetch_available_fair_models()

        if self.anthropic_api_key or (os.getenv("ANTHROPIC_API_KEY") or "").strip() or await self._aget_managed_llm_api_key("claude"):
            await self.fetch_available_claude_models()

        if self.config.ollama_enabled:
            await self.fetch_available_ollama_models()

    def resolve_purpose(self, purpose: str) -> tuple[str, str]:
        """Return (provider, model_str) for a given purpose: 'chat', 'agent', 'orchestrator'.

        Priority:
        1. Purpose-specific provider/model if both configured
        2. internal_llm_provider + its default chat/agent model
        3. Hard fallback to grok
        """
        c = self.config
        purpose_aliases = {
            "ops": "agent",
            "opsexecutor": "agent",
            "opsplan": "orchestrator",
            "opsreplan": "orchestrator",
            "opssummary": "chat",
            "opsguard": "chat",
            "opsmemory": "chat",
            # Terminal AI purposes (F1-8): cheap/fast tier by default.
            # ``terminal_planning`` chooses mode/commands — small JSON task;
            # ``memory_extraction`` compacts a run into facts/issues JSON.
            # Both route to the "chat" bucket so admins can point them at a
            # lite model (gpt-5-mini / gemini-flash / claude-haiku) via
            # ``chat_llm_provider`` / ``chat_llm_model`` without affecting
            # agent-level ReAct calls.
            "terminal_planning": "chat",
            "memory_extraction": "chat",
            # A4: expanded per-purpose routing for terminal AI sub-calls.
            # All of these are small, focused tasks and do not need the
            # flagship agent model — route them to the chat bucket.
            "terminal_step_decision": "chat",   # 1-shot "next / stop" JSON
            "terminal_recovery": "chat",         # retry/skip/ask after error
            "terminal_report": "chat",           # short run summary
            "terminal_answer": "chat",           # pure knowledge answer
            "terminal_explain": "chat",          # A6: explain command output
        }
        normalized_purpose = purpose_aliases.get(purpose, purpose)

        provider_field = f"{normalized_purpose}_llm_provider"
        model_field = f"{normalized_purpose}_llm_model"
        purpose_provider = (getattr(c, provider_field, "") or "").strip()
        purpose_model = (getattr(c, model_field, "") or "").strip()

        provider = purpose_provider or (c.internal_llm_provider or "grok").strip()

        if purpose_model:
            model_str = purpose_model
        else:
            # Fall back to the per-provider model for this purpose
            if normalized_purpose == "agent":
                model_str = self.get_agent_model(provider)
            else:
                model_str = self.get_chat_model(provider)

        return provider, model_str

    def get_chat_model(self, provider: str | None = None) -> str:
        """Get configured chat model for provider."""
        normalized_provider = self._normalize_model_provider(provider)
        fallback = self._get_first_available_ollama_model() if normalized_provider == "ollama" else ""
        return get_provider_chat_model(self.config, normalized_provider, empty_fallback=fallback)

    def get_agent_model(self, provider: str | None = None) -> str:
        """Get configured agent model for provider."""
        normalized_provider = self._normalize_model_provider(provider)
        fallback = self._get_first_available_ollama_model() if normalized_provider == "ollama" else ""
        return get_provider_agent_model(self.config, normalized_provider, empty_fallback=fallback)

    def _normalize_model_provider(self, provider: str | None = None) -> str:
        normalized = (provider or self.config.default_provider or "grok").strip()
        if normalized == "auto":
            normalized = (self.config.internal_llm_provider or "grok").strip()
        return provider_model_spec(normalized).provider

    def _get_first_available_ollama_model(self) -> str:
        runtime_mode = self._get_ollama_runtime_mode()
        if runtime_mode == "cloud" and self.available_ollama_cloud_models:
            return self.available_ollama_cloud_models[0]
        if self.available_ollama_local_models:
            return self.available_ollama_local_models[0]
        if self.available_ollama_cloud_models:
            return self.available_ollama_cloud_models[0]
        return self.available_ollama_models[0] if self.available_ollama_models else ""

    def get_rag_model(self) -> str:
        """Get configured RAG/embedding model"""
        return self.config.rag_model

    def update_config(self, **kwargs):
        """Update configuration"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                logger.info("Updated {} to {}", key, redacted_config_value(key, value))

    def save_config(self, filepath: str = ".model_config.json"):
        """Save configuration to file"""
        try:
            with open(filepath, 'w') as f:
                json.dump(self.config.model_dump(), f, indent=2)
            logger.success(f"Model configuration saved to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def load_config(self, filepath: str = ".model_config.json"):
        """Load configuration from file"""
        try:
            if os.path.exists(filepath):
                with open(filepath) as f:
                    data = json.load(f)
                self.config = ModelConfig(**data)
                logger.success(f"Model configuration loaded from {filepath}")
                return True
        except Exception as e:
            logger.error(f"Failed to load config: {e}")

        return False

    def _get_default_claude_models(self) -> list[str]:
        """Default Anthropic Claude models list"""
        return get_provider_default_models("claude")

    def get_available_models(self, provider: str) -> list[str]:
        """Get list of available models for provider"""
        spec = provider_model_spec(provider)
        models = list(getattr(self, spec.available_models_attr, []) or [])
        return models or get_provider_default_models(spec.provider)

    def is_provider_enabled(self, provider: str) -> bool:
        """Check if API provider is enabled"""
        return is_config_provider_enabled(self.config, provider)


# Global model manager instance
model_manager = ModelManager()
