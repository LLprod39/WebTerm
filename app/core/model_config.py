"""
Model Configuration Manager
Manages model selection for different purposes (chat, RAG, agent)
"""
import os
from typing import Dict, List, Optional
from pydantic import BaseModel
from loguru import logger
import httpx
import json


class ModelConfig(BaseModel):
    """Configuration for models"""
    # API providers (optional, disabled by default)
    gemini_enabled: bool = False
    grok_enabled: bool = True  # Fallback for internal calls
    openai_enabled: bool = False
    claude_enabled: bool = False

    # Chat models
    chat_model_gemini: str = "models/gemini-3-flash-preview"
    chat_model_grok: str = "grok-3"
    chat_model_openai: str = "gpt-5-mini"
    chat_model_claude: str = "claude-sonnet-4-6"
    
    # RAG/Embedding models
    rag_model: str = "models/text-embedding-004"  # Gemini embedding
    
    # Agent/ReAct models
    agent_model_gemini: str = "models/gemini-3-flash-preview"
    agent_model_grok: str = "grok-3"
    agent_model_openai: str = "gpt-5-mini"
    
    # Default provider (CLI agent): cursor = Cursor CLI, claude = Claude Code CLI
    # Note: "ralph" is NOT a valid provider - it's an orchestrator mode
    default_provider: str = "cursor"
    
    # Провайдер для ВНУТРЕННИХ вызовов LLM (генерация workflow, анализ задач).
    # Когда default_provider - CLI agent, внутренние вызовы используют этот провайдер.
    # Варианты: "gemini", "grok", "openai", "claude"
    internal_llm_provider: str = "grok"
    
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
    domain_auth_enabled: Optional[bool] = None
    domain_auth_header: Optional[str] = None
    domain_auth_auto_create: Optional[bool] = None
    domain_auth_lowercase_usernames: Optional[bool] = None
    domain_auth_default_profile: Optional[str] = None

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
        self.available_gemini_models: List[str] = []
        self.available_grok_models: List[str] = []
        self.available_openai_models: List[str] = []
        self.available_claude_models: List[str] = []
        self.gemini_api_key: Optional[str] = None
        self.grok_api_key: Optional[str] = None
        self.openai_api_key: Optional[str] = None
        self.anthropic_api_key: Optional[str] = None
    
    def set_api_keys(
        self,
        gemini_key: Optional[str] = None,
        grok_key: Optional[str] = None,
        anthropic_key: Optional[str] = None,
        openai_key: Optional[str] = None,
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

    @staticmethod
    def _extract_model_ids(payload: dict) -> List[str]:
        """Extract model IDs from provider payloads with {data:[{id:...}]} shape."""
        out: List[str] = []
        for item in payload.get("data", []) or []:
            model_id = item.get("id")
            if isinstance(model_id, str) and model_id:
                out.append(model_id)
        return out

    @staticmethod
    def _is_openai_text_model(model_id: str) -> bool:
        """Filter for text/chat-capable OpenAI model IDs."""
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
    
    async def fetch_available_gemini_models(self) -> List[str]:
        """
        Fetch available Gemini models via REST API.
        """
        key = self.gemini_api_key or (os.getenv("GEMINI_API_KEY") or "").strip()
        if key:
            self.gemini_api_key = key
        if not key:
            logger.warning("Gemini API key not set")
            return self._get_default_gemini_models()
        
        try:
            models: List[str] = []
            page_token = ""

            async with httpx.AsyncClient(timeout=20.0) as client:
                while True:
                    params = {"key": key, "pageSize": 200}
                    if page_token:
                        params["pageToken"] = page_token
                    response = await client.get(
                        "https://generativelanguage.googleapis.com/v1beta/models",
                        params=params,
                    )
                    if response.status_code != 200:
                        logger.error(f"Gemini API returned status {response.status_code}: {response.text}")
                        return self._get_default_gemini_models()

                    payload = response.json()
                    for model in payload.get("models", []) or []:
                        name = model.get("name")
                        supported = model.get("supportedGenerationMethods") or []
                        if isinstance(name, str) and name and "generateContent" in supported:
                            models.append(name)

                    page_token = (payload.get("nextPageToken") or "").strip()
                    if not page_token:
                        break

            models = sorted(set(models))
            if not models:
                logger.warning("Gemini API returned empty models list; using defaults")
                return self._get_default_gemini_models()

            self.available_gemini_models = models
            logger.success(f"Fetched {len(models)} Gemini models")
            return models
            
        except Exception as e:
            logger.error(f"Failed to fetch Gemini models: {e}")
            return self._get_default_gemini_models()
    
    async def fetch_available_grok_models(self) -> List[str]:
        """
        Fetch available Grok models from xAI API
        """
        key = self.grok_api_key or (os.getenv("GROK_API_KEY") or "").strip()
        if key:
            self.grok_api_key = key
        if not key:
            logger.warning("Grok API key not set")
            return self._get_default_grok_models()
        
        try:
            async with httpx.AsyncClient() as client:
                for endpoint in ("https://api.x.ai/v1/language-models", "https://api.x.ai/v1/models"):
                    response = await client.get(
                        endpoint,
                        headers={"Authorization": f"Bearer {key}"},
                        timeout=10.0
                    )
                    
                    if response.status_code != 200:
                        logger.warning(f"Grok API returned status {response.status_code} for {endpoint}")
                        continue

                    data = response.json()
                    models = sorted(set(self._extract_model_ids(data)))
                    if not models:
                        continue
                    
                    self.available_grok_models = models
                    logger.success(f"Fetched {len(models)} Grok models from {endpoint}")
                    return models

                logger.error("Grok API returned no model data from supported endpoints")
                return self._get_default_grok_models()
                    
        except Exception as e:
            logger.error(f"Failed to fetch Grok models: {e}")
            return self._get_default_grok_models()

    async def fetch_available_claude_models(self) -> List[str]:
        """Fetch available Claude models from Anthropic API."""
        key = self.anthropic_api_key or (os.getenv("ANTHROPIC_API_KEY") or "").strip()
        if key:
            self.anthropic_api_key = key
        if not key:
            logger.warning("Anthropic API key not set")
            return self._get_default_claude_models()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": key,
                        "anthropic-version": "2023-06-01",
                    },
                )
                if response.status_code != 200:
                    logger.error(f"Anthropic API returned status {response.status_code}: {response.text}")
                    return self._get_default_claude_models()

                payload = response.json()
                models = sorted(
                    set(
                        item.get("id", "")
                        for item in (payload.get("data") or [])
                        if item.get("id")
                    )
                )

                if not models:
                    logger.warning("Anthropic API returned empty model list; using defaults")
                    return self._get_default_claude_models()

                self.available_claude_models = models
                logger.success(f"Fetched {len(models)} Claude models")
                return models
        except Exception as e:
            logger.error(f"Failed to fetch Claude models: {e}")
            return self._get_default_claude_models()

    async def fetch_available_openai_models(self) -> List[str]:
        """
        Fetch available OpenAI models from OpenAI Models API.
        """
        key = self.openai_api_key or (os.getenv("OPENAI_API_KEY") or "").strip() or (os.getenv("CODEX_API_KEY") or "").strip()
        if key:
            self.openai_api_key = key
        if not key:
            logger.warning("OpenAI API key not set")
            return self._get_default_openai_models()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                )

                if response.status_code != 200:
                    logger.error(f"OpenAI API returned status {response.status_code}: {response.text}")
                    return self._get_default_openai_models()

                payload = response.json()
                models = sorted(
                    set(
                        model_id
                        for model_id in self._extract_model_ids(payload)
                        if self._is_openai_text_model(model_id)
                    )
                )

                if not models:
                    logger.warning("OpenAI API returned empty text model list; using defaults")
                    return self._get_default_openai_models()

                self.available_openai_models = models
                logger.success(f"Fetched {len(models)} OpenAI models")
                return models
        except Exception as e:
            logger.error(f"Failed to fetch OpenAI models: {e}")
            return self._get_default_openai_models()
    
    def _get_default_gemini_models(self) -> List[str]:
        """Default Gemini models list (fallback)"""
        return [
            "models/gemini-3-flash-preview",
            "models/gemini-2.5-flash-preview",
        ]
    
    def _get_default_grok_models(self) -> List[str]:
        """Default Grok models list (fallback)"""
        return [
            "grok-3",
            "grok-4-1-fast-non-reasoning",
        ]

    def _get_default_openai_models(self) -> List[str]:
        """Default OpenAI models list (fallback)"""
        return [
            "gpt-5",
            "gpt-5-mini",
            "gpt-5-nano",
        ]
    
    async def refresh_models(self):
        """Refresh available models from both providers"""
        logger.info("Refreshing available models...")
        
        if self.gemini_api_key or (os.getenv("GEMINI_API_KEY") or "").strip():
            await self.fetch_available_gemini_models()
        
        if self.grok_api_key or (os.getenv("GROK_API_KEY") or "").strip():
            await self.fetch_available_grok_models()

        if self.openai_api_key or (os.getenv("OPENAI_API_KEY") or "").strip() or (os.getenv("CODEX_API_KEY") or "").strip():
            await self.fetch_available_openai_models()

        if self.anthropic_api_key or (os.getenv("ANTHROPIC_API_KEY") or "").strip():
            await self.fetch_available_claude_models()
    
    def resolve_purpose(self, purpose: str) -> tuple[str, str]:
        """Return (provider, model_str) for a given purpose: 'chat', 'agent', 'orchestrator'.

        Priority:
        1. Purpose-specific provider/model if both configured
        2. internal_llm_provider + its default chat/agent model
        3. Hard fallback to grok
        """
        c = self.config
        provider_field = f"{purpose}_llm_provider"
        model_field = f"{purpose}_llm_model"
        purpose_provider = (getattr(c, provider_field, "") or "").strip()
        purpose_model = (getattr(c, model_field, "") or "").strip()

        if purpose_provider:
            provider = purpose_provider
        else:
            provider = (c.internal_llm_provider or "grok").strip()

        if purpose_model:
            model_str = purpose_model
        else:
            # Fall back to the per-provider model for this purpose
            if purpose == "agent":
                model_str = self.get_agent_model(provider)
            else:
                model_str = self.get_chat_model(provider)

        return provider, model_str

    def get_chat_model(self, provider: Optional[str] = None) -> str:
        """Get configured chat model for provider."""
        provider = provider or self.config.default_provider
        if provider == "auto":
            provider = self.config.internal_llm_provider or "grok"
        if provider == "gemini":
            return self.config.chat_model_gemini
        if provider == "openai":
            return self.config.chat_model_openai
        if provider == "claude":
            return self.config.chat_model_claude
        return self.config.chat_model_grok

    def get_agent_model(self, provider: Optional[str] = None) -> str:
        """Get configured agent model for provider."""
        provider = provider or self.config.default_provider
        if provider == "auto":
            provider = self.config.internal_llm_provider or "grok"
        if provider == "gemini":
            return self.config.agent_model_gemini
        if provider == "openai":
            return self.config.agent_model_openai
        if provider == "claude":
            return self.config.chat_model_claude
        return self.config.agent_model_grok
    
    def get_rag_model(self) -> str:
        """Get configured RAG/embedding model"""
        return self.config.rag_model
    
    def update_config(self, **kwargs):
        """Update configuration"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                logger.info(f"Updated {key} to {value}")
    
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
                with open(filepath, 'r') as f:
                    data = json.load(f)
                self.config = ModelConfig(**data)
                logger.success(f"Model configuration loaded from {filepath}")
                return True
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
        
        return False
    
    def _get_default_claude_models(self) -> List[str]:
        """Default Anthropic Claude models list"""
        return [
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
        ]

    def get_available_models(self, provider: str) -> List[str]:
        """Get list of available models for provider"""
        if provider == "gemini":
            if not self.available_gemini_models:
                return self._get_default_gemini_models()
            return self.available_gemini_models
        if provider == "openai":
            if not self.available_openai_models:
                return self._get_default_openai_models()
            return self.available_openai_models
        if provider == "claude":
            if not self.available_claude_models:
                return self._get_default_claude_models()
            return self.available_claude_models
        if not self.available_grok_models:
            return self._get_default_grok_models()
        return self.available_grok_models

    def is_provider_enabled(self, provider: str) -> bool:
        """Check if API provider is enabled"""
        if provider == "gemini":
            return self.config.gemini_enabled
        elif provider == "grok":
            return self.config.grok_enabled
        elif provider == "openai":
            return self.config.openai_enabled
        elif provider == "claude":
            return self.config.claude_enabled
        # CLI providers always enabled if binary available
        return True


# Global model manager instance
model_manager = ModelManager()
