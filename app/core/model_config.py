"""
Model Configuration Manager
Manages model selection for different purposes (chat, RAG, agent)
"""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
from loguru import logger
from pydantic import BaseModel

OLLAMA_CLOUD_MODEL_SUFFIX = " (cloud)"
OLLAMA_RUNTIME_MODES = {"auto", "local", "cloud"}
OLLAMA_THINK_MODES = {"", "off", "on", "low", "medium", "high"}


class ModelConfig(BaseModel):
    """Configuration for models"""
    # API providers (optional, disabled by default)
    gemini_enabled: bool = False
    grok_enabled: bool = True  # Fallback for internal calls
    openai_enabled: bool = False
    claude_enabled: bool = False
    ollama_enabled: bool = False

    # Chat models
    chat_model_gemini: str = "models/gemini-3-flash-preview"
    chat_model_grok: str = "grok-3"
    chat_model_openai: str = "gpt-5-mini"
    chat_model_claude: str = "claude-sonnet-4-6"
    chat_model_ollama: str = ""

    # RAG/Embedding models
    rag_model: str = "models/text-embedding-004"  # Gemini embedding

    # Agent/ReAct models
    agent_model_gemini: str = "models/gemini-3-flash-preview"
    agent_model_grok: str = "grok-3"
    agent_model_openai: str = "gpt-5-mini"
    agent_model_ollama: str = ""

    # Default provider (CLI agent): cursor = Cursor CLI, claude = Claude Code CLI
    # Note: "ralph" is NOT a valid provider - it's an orchestrator mode
    default_provider: str = "cursor"

    # Провайдер для ВНУТРЕННИХ вызовов LLM (генерация workflow, анализ задач).
    # Когда default_provider - CLI agent, внутренние вызовы используют этот провайдер.
    # Варианты: "gemini", "grok", "openai", "claude", "ollama"
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
    domain_auth_enabled: bool | None = None
    domain_auth_header: str | None = None
    domain_auth_auto_create: bool | None = None
    domain_auth_lowercase_usernames: bool | None = None
    domain_auth_default_profile: str | None = None

    # Ollama runtime
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
        self.available_claude_models: list[str] = []
        self.available_ollama_models: list[str] = []
        self.available_ollama_local_models: list[str] = []
        self.available_ollama_cloud_models: list[str] = []
        self.gemini_api_key: str | None = None
        self.grok_api_key: str | None = None
        self.openai_api_key: str | None = None
        self.anthropic_api_key: str | None = None

    def set_api_keys(
        self,
        gemini_key: str | None = None,
        grok_key: str | None = None,
        anthropic_key: str | None = None,
        openai_key: str | None = None,
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
    def _extract_model_ids(payload: dict) -> list[str]:
        """Extract model IDs from provider payloads with {data:[{id:...}]} shape."""
        out: list[str] = []
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

    @staticmethod
    def _normalize_ollama_base_url(raw: str | None = None) -> str:
        value = (
            (raw or "").strip()
            or (os.getenv("OLLAMA_BASE_URL") or "").strip()
            or "http://127.0.0.1:11434"
        ).rstrip("/")
        if "://" not in value:
            value = f"http://{value}"
        return value.rstrip("/")

    @staticmethod
    def _normalize_ollama_cloud_base_url(raw: str | None = None) -> str:
        value = (
            (raw or "").strip()
            or (os.getenv("OLLAMA_CLOUD_BASE_URL") or "").strip()
            or "https://ollama.com"
        ).rstrip("/")
        if "://" not in value:
            value = f"https://{value}"
        return value.rstrip("/")

    @staticmethod
    def _normalize_ollama_runtime_mode(raw: str | None = None) -> str:
        value = (raw or "").strip().lower()
        if value in OLLAMA_RUNTIME_MODES:
            return value
        return "auto"

    @staticmethod
    def _normalize_ollama_think_mode(raw: str | None = None) -> str:
        value = (raw or "").strip().lower()
        if value in OLLAMA_THINK_MODES:
            return value
        return ""

    @staticmethod
    def _get_ollama_api_key() -> str:
        return (os.getenv("OLLAMA_API_KEY") or "").strip()

    @staticmethod
    def _encode_ollama_cloud_model(model_id: str) -> str:
        model_id = (model_id or "").strip()
        if not model_id:
            return ""
        if model_id.endswith(OLLAMA_CLOUD_MODEL_SUFFIX):
            return model_id
        return f"{model_id}{OLLAMA_CLOUD_MODEL_SUFFIX}"

    @staticmethod
    def _is_ollama_cloud_model(model_id: str | None) -> bool:
        return (model_id or "").strip().endswith(OLLAMA_CLOUD_MODEL_SUFFIX)

    @staticmethod
    def _decode_ollama_cloud_model(model_id: str | None) -> str:
        value = (model_id or "").strip()
        if value.endswith(OLLAMA_CLOUD_MODEL_SUFFIX):
            return value[: -len(OLLAMA_CLOUD_MODEL_SUFFIX)].rstrip()
        return value

    @staticmethod
    def _is_wsl_runtime() -> bool:
        if os.getenv("WSL_DISTRO_NAME") or os.getenv("WSL_INTEROP"):
            return True
        for proc_file in ("/proc/sys/kernel/osrelease", "/proc/version"):
            try:
                if "microsoft" in Path(proc_file).read_text(encoding="utf-8", errors="ignore").lower():
                    return True
            except OSError:
                continue
        return False

    @staticmethod
    def _replace_ollama_host(base_url: str, host: str) -> str:
        parsed = urlsplit(base_url)
        scheme = parsed.scheme or "http"
        port = parsed.port or 11434
        auth = ""
        if parsed.username:
            auth = parsed.username
            if parsed.password:
                auth = f"{auth}:{parsed.password}"
            auth = f"{auth}@"
        path = parsed.path or ""
        return urlunsplit((scheme, f"{auth}{host}:{port}", path, parsed.query, parsed.fragment)).rstrip("/")

    def _get_ollama_base_url(self) -> str:
        return self._normalize_ollama_base_url(self.config.ollama_base_url)

    def _get_ollama_cloud_base_url(self) -> str:
        return self._normalize_ollama_cloud_base_url(self.config.ollama_cloud_base_url)

    def _get_ollama_runtime_mode(self) -> str:
        return self._normalize_ollama_runtime_mode(self.config.ollama_runtime_mode)

    def _get_ollama_think_mode(self) -> str:
        return self._normalize_ollama_think_mode(self.config.ollama_think_mode)

    def _get_ollama_base_urls(self) -> list[str]:
        primary = self._get_ollama_base_url()
        urls: list[str] = [primary]
        parsed = urlsplit(primary)
        host = (parsed.hostname or "").strip().lower()

        if host not in {"127.0.0.1", "localhost", "::1"} or not self._is_wsl_runtime():
            return urls

        fallback_hosts: list[str] = ["host.docker.internal", "host.containers.internal"]
        try:
            for line in Path("/etc/resolv.conf").read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("nameserver "):
                    candidate = (line.split(maxsplit=1)[1] or "").strip()
                    if candidate:
                        fallback_hosts.append(candidate)
                    break
        except OSError:
            pass
        try:
            for line in Path("/proc/net/route").read_text(encoding="utf-8", errors="ignore").splitlines()[1:]:
                parts = line.split()
                if len(parts) < 3 or parts[1] != "00000000":
                    continue
                gateway_hex = parts[2]
                if len(gateway_hex) != 8:
                    continue
                octets = [str(int(gateway_hex[i:i + 2], 16)) for i in range(0, 8, 2)]
                fallback_hosts.append(".".join(reversed(octets)))
                break
        except OSError:
            pass

        seen_hosts: set[str] = set()
        for fallback_host in fallback_hosts:
            normalized_host = fallback_host.strip().lower()
            if not normalized_host or normalized_host in seen_hosts:
                continue
            seen_hosts.add(normalized_host)
            candidate_url = self._replace_ollama_host(primary, fallback_host.strip())
            if candidate_url not in urls:
                urls.append(candidate_url)
        return urls

    @staticmethod
    def _extract_ollama_model_names(payload: dict, *, cloud: bool = False) -> list[str]:
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
                normalized = ModelManager._encode_ollama_cloud_model(normalized)
            if normalized in seen:
                continue
            seen.add(normalized)
            models.append(normalized)

        return models

    def _combine_ollama_models(self, local_models: list[str], cloud_models: list[str]) -> list[str]:
        ordered_sources = (
            [cloud_models, local_models]
            if self._get_ollama_runtime_mode() == "cloud"
            else [local_models, cloud_models]
        )
        seen: set[str] = set()
        combined: list[str] = []

        for source_models in ordered_sources:
            for model_id in source_models:
                if model_id in seen:
                    continue
                seen.add(model_id)
                combined.append(model_id)

        return combined

    async def fetch_available_gemini_models(self) -> list[str]:
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
            models: list[str] = []
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

    async def fetch_available_grok_models(self) -> list[str]:
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

    async def fetch_available_claude_models(self) -> list[str]:
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
                    {
                        item.get("id", "")
                        for item in (payload.get("data") or [])
                        if item.get("id")
                    }
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

    async def fetch_available_openai_models(self) -> list[str]:
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
                    {
                        model_id
                        for model_id in self._extract_model_ids(payload)
                        if self._is_openai_text_model(model_id)
                    }
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

    async def fetch_available_ollama_models(self) -> list[str]:
        """Fetch Ollama models from local runtime and optional ollama.com cloud catalog."""
        local_models: list[str] = []
        cloud_models: list[str] = []
        errors: list[str] = []

        for base_url in self._get_ollama_base_urls():
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(f"{base_url}/api/tags")

                if response.status_code != 200:
                    errors.append(f"local {base_url} -> HTTP {response.status_code}")
                    continue

                local_models = self._extract_ollama_model_names(response.json())
                self.available_ollama_local_models = local_models
                if base_url != self.config.ollama_base_url:
                    logger.warning(
                        f"Ollama base URL fallback: configured={self.config.ollama_base_url or 'unset'} -> using {base_url}"
                    )
                self.config.ollama_base_url = base_url
                logger.success(f"Fetched {len(local_models)} local Ollama models from {base_url}")
                break
            except Exception as e:
                errors.append(f"local {base_url} -> {e}")

        if not local_models:
            self.available_ollama_local_models = []

        if self.config.ollama_cloud_enabled:
            api_key = self._get_ollama_api_key()
            if not api_key:
                errors.append("cloud https://ollama.com -> OLLAMA_API_KEY is not configured")
            else:
                cloud_base_url = self._get_ollama_cloud_base_url()
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        response = await client.get(
                            f"{cloud_base_url}/api/tags",
                            headers={"Authorization": f"Bearer {api_key}"},
                        )

                    if response.status_code != 200:
                        errors.append(f"cloud {cloud_base_url} -> HTTP {response.status_code}")
                    else:
                        cloud_models = self._extract_ollama_model_names(response.json(), cloud=True)
                        self.available_ollama_cloud_models = cloud_models
                        logger.success(f"Fetched {len(cloud_models)} Ollama cloud models from {cloud_base_url}")
                except Exception as e:
                    errors.append(f"cloud {cloud_base_url} -> {e}")
        else:
            self.available_ollama_cloud_models = []

        combined_models = self._combine_ollama_models(local_models, cloud_models)
        self.available_ollama_models = combined_models
        if combined_models:
            return combined_models

        logger.error(f"Failed to fetch Ollama models. Tried: {'; '.join(errors)}")
        return self._get_default_ollama_models()

    def _get_default_gemini_models(self) -> list[str]:
        """Default Gemini models list (fallback)"""
        return [
            "models/gemini-3-flash-preview",
            "models/gemini-2.5-flash-preview",
        ]

    def _get_default_grok_models(self) -> list[str]:
        """Default Grok models list (fallback)"""
        return [
            "grok-3",
            "grok-4-1-fast-non-reasoning",
        ]

    def _get_default_openai_models(self) -> list[str]:
        """Default OpenAI models list (fallback)"""
        return [
            "gpt-5",
            "gpt-5-mini",
            "gpt-5-nano",
        ]

    def _get_default_ollama_models(self) -> list[str]:
        """Ollama models are local-install specific; default to no cached models."""
        return []

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
        provider = provider or self.config.default_provider
        if provider == "auto":
            provider = self.config.internal_llm_provider or "grok"
        if provider == "gemini":
            return self.config.chat_model_gemini
        if provider == "openai":
            return self.config.chat_model_openai
        if provider == "claude":
            return self.config.chat_model_claude
        if provider == "ollama":
            return self.config.chat_model_ollama or self._get_first_available_ollama_model()
        return self.config.chat_model_grok

    def get_agent_model(self, provider: str | None = None) -> str:
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
        if provider == "ollama":
            return (
                self.config.agent_model_ollama
                or self.config.chat_model_ollama
                or self._get_first_available_ollama_model()
            )
        return self.config.agent_model_grok

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
        return [
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
        ]

    def get_available_models(self, provider: str) -> list[str]:
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
        if provider == "ollama":
            if not self.available_ollama_models:
                return self._get_default_ollama_models()
            return self.available_ollama_models
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
        elif provider == "ollama":
            return self.config.ollama_enabled
        # CLI providers always enabled if binary available
        return True


# Global model manager instance
model_manager = ModelManager()
