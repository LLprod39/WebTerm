import asyncio as asyncio
import contextlib
import os
from collections.abc import AsyncGenerator
from typing import Any

from google import genai
from loguru import logger

from app.core.llm_anthropic import ClaudeStreamRequest, stream_claude_response
from app.core.llm_budget import BudgetExceededError, get_current_llm_budget_status
from app.core.llm_gemini import GeminiStreamRequest, stream_gemini_response
from app.core.llm_ollama import (
    OllamaStreamRequest,
    build_ollama_request_targets,
    get_ollama_think_value,
    stream_ollama_response,
)
from app.core.llm_openai_compatible import (
    build_chat_completions_request,
    build_openai_request,
    stream_openai_compatible_response,
)
from app.core.llm_provider_keys import apply_managed_llm_keys, load_managed_llm_keys
from app.core.llm_provider_resolution import RuntimeProviderKeys, resolve_stream_provider
from app.core.llm_runtime import (
    _grok_reasoning_effort,
    _is_ollama_connect_error,
    _provider_timeout_seconds,
    _retry_attempts,
)
from app.core.llm_runtime import (
    _is_retryable_error as _is_retryable_error,
)
from app.core.llm_runtime import (
    _is_timeout_error as _is_timeout_error,
)
from app.core.llm_runtime import (
    with_retry as with_retry,
)
from app.core.llm_usage import log_llm_usage as _log_llm_usage
from app.core.model_config import model_manager
from app.core.redacted_logging import redacted_log_text

_provider_instance: "LLMProvider | None" = None


def get_provider() -> "LLMProvider":
    """Return a module-level cached LLMProvider."""
    global _provider_instance
    with contextlib.suppress(Exception):
        model_manager.load_config()
    if _provider_instance is None:
        _provider_instance = LLMProvider()
    return _provider_instance


def reset_provider_cache() -> None:
    """Drop cached provider so changed Settings API keys are picked up."""
    global _provider_instance
    _provider_instance = None


class LLMProvider:
    def __init__(self):
        # Direct LLMProvider() callers are used by agents and tools. Keep them
        # aligned with Settings/.model_config.json, not only get_provider().
        with contextlib.suppress(Exception):
            model_manager.load_config()
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.grok_api_key = os.getenv("GROK_API_KEY")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY") or os.getenv("CODEX_API_KEY")
        self.fair_api_key = os.getenv("FAIR_HYPERION_API_KEY") or os.getenv("FAIR_API_KEY")
        self.ollama_api_key = os.getenv("OLLAMA_API_KEY")

        # Set keys in model manager
        model_manager.set_api_keys(
            gemini_key=self.gemini_api_key,
            grok_key=self.grok_api_key,
            anthropic_key=self.anthropic_api_key,
            openai_key=self.openai_api_key,
            fair_key=self.fair_api_key,
            ollama_key=self.ollama_api_key,
        )

        # Lazy initialization of clients
        self._gemini_client = None
        self._anthropic_client = None

    @staticmethod
    def _get_ollama_base_url() -> str:
        return model_manager._get_ollama_base_url()

    @staticmethod
    def _get_ollama_base_urls() -> list[str]:
        return model_manager._get_ollama_base_urls()

    @staticmethod
    def _get_ollama_cloud_base_url() -> str:
        return model_manager._get_ollama_cloud_base_url()

    @staticmethod
    def _get_ollama_runtime_mode() -> str:
        return model_manager._get_ollama_runtime_mode()

    @staticmethod
    def _get_fair_base_url() -> str:
        return model_manager._get_fair_base_url()

    @staticmethod
    def _get_ollama_think_value() -> Any | None:
        return get_ollama_think_value(model_manager)

    @staticmethod
    def _build_ollama_request_targets(target_model: str) -> list[dict[str, Any]]:
        return build_ollama_request_targets(target_model, model_manager=model_manager)

    def _get_gemini_client(self):
        """Lazy load Gemini client only when enabled"""
        if not model_manager.config.gemini_enabled:
            return None

        if self._gemini_client is None and self.gemini_api_key:
            try:
                self._gemini_client = genai.Client(api_key=self.gemini_api_key)
                logger.info("Configured Gemini client")
            except Exception as e:
                logger.error(f"Failed to configure Gemini: {e}")
                self._gemini_client = None

        return self._gemini_client

    @property
    def gemini_client(self):
        """Property for backward compatibility"""
        return self._get_gemini_client()

    def _get_anthropic_client(self):
        """Lazy load Anthropic client only when enabled"""
        if not model_manager.config.claude_enabled:
            return None
        if self._anthropic_client is None and self.anthropic_api_key:
            try:
                import anthropic

                self._anthropic_client = anthropic.AsyncAnthropic(api_key=self.anthropic_api_key)
                logger.info("Configured Anthropic client")
            except Exception as e:
                logger.error(f"Failed to configure Anthropic: {e}")
                self._anthropic_client = None
        return self._anthropic_client

    async def _load_managed_api_keys(self) -> None:
        apply_managed_llm_keys(self, model_manager, await load_managed_llm_keys())

    def set_api_key(self, model: str, key: str):
        if model == "gemini":
            self.gemini_api_key = key
            model_manager.set_api_keys(gemini_key=key)
            self._gemini_client = None
        elif model == "grok":
            self.grok_api_key = key
            model_manager.set_api_keys(grok_key=key)
        elif model == "claude":
            self.anthropic_api_key = key
            model_manager.set_api_keys(anthropic_key=key)
            self._anthropic_client = None
        elif model == "openai":
            self.openai_api_key = key
            model_manager.set_api_keys(openai_key=key)
        elif model == "fair":
            self.fair_api_key = key
            model_manager.set_api_keys(fair_key=key)
        elif model == "ollama":
            self.ollama_api_key = key
            model_manager.set_api_keys(ollama_key=key)

    async def stream_chat(
        self,
        prompt: str,
        model: str = "auto",
        specific_model: str = None,
        purpose: str = "chat",
        system_prompt: str | None = None,
        json_mode: bool = False,
    ) -> AsyncGenerator[str, None]:
        """
        Stream chat response from the selected model.

        Args:
            prompt: The prompt to send (user message when system_prompt is given)
            model: Provider name (auto/gemini/grok/openai/fair/claude/ollama). «auto» resolves via purpose.
            specific_model: Specific model version to use (overrides config)
            purpose: One of 'chat', 'agent', 'orchestrator' — used when model=='auto'
            system_prompt: Optional system-level instructions. When provided,
                replaces the default generic system message and enables
                provider-level prompt caching (Anthropic cache_control,
                OpenAI automatic prefix caching, Gemini system_instruction).
            json_mode: When True, activates provider-native JSON output mode
                (3.1) so the LLM is constrained to produce valid JSON.
        """

        await self._load_managed_api_keys()

        if model == "auto" or not model:
            model, specific_model = resolve_stream_provider(
                requested_provider=model,
                requested_specific_model=specific_model,
                purpose=purpose,
                model_manager=model_manager,
                keys=RuntimeProviderKeys.from_llm_provider(self),
                ollama_base_url=self._get_ollama_base_url(),
                warn=logger.warning,
            )
            logger.info(f"[{purpose}] using provider: {model}, model: {specific_model or '(default)'}")
        logger.info("Streaming chat from {} with prompt: {}...", model, redacted_log_text(prompt, limit=50))

        # B2: per-user daily token budget pre-flight. Best-effort — never let
        # a budget-service failure break a real LLM call.
        try:
            _budget = get_current_llm_budget_status()
            if _budget.exceeded:
                raise BudgetExceededError(
                    f"Daily LLM token budget exceeded: used {_budget.used_tokens} "
                    f"of {_budget.limit_tokens} tokens in the last 24 h."
                )
        except BudgetExceededError:
            raise
        except Exception as _budget_err:  # noqa: BLE001 — budget check must never block on infra issues
            logger.debug("budget pre-flight skipped: %s", _budget_err)

        if model == "gemini":
            # Check if Gemini is enabled
            if not model_manager.config.gemini_enabled:
                yield "Error: Gemini API disabled. Enable in settings or use CLI agent (ralph/cursor/claude)."
                return

            if not self.gemini_client:
                yield "Error: Gemini API Key not configured."
                return

            target_model = specific_model or model_manager.get_chat_model("gemini")
            logger.info(f"Using Gemini model: {target_model}")
            async for chunk in stream_gemini_response(
                client=self.gemini_client,
                request=GeminiStreamRequest(
                    target_model=target_model,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    json_mode=json_mode,
                ),
                purpose=purpose,
                timeout_seconds=float(_provider_timeout_seconds("gemini")),
                max_attempts=_retry_attempts(),
                usage_logger=_log_llm_usage,
            ):
                yield chunk
            return

        elif model == "grok":
            # Check if Grok is enabled
            if not model_manager.config.grok_enabled:
                yield "Error: Grok API disabled. Enable in settings or use CLI agent (ralph/cursor/claude)."
                return

            if not self.grok_api_key:
                yield "Error: Grok API Key not configured."
                return

            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.grok_api_key}"}
            grok_model = specific_model or model_manager.get_chat_model("grok")
            request = build_chat_completions_request(
                api_url="https://api.x.ai/v1/chat/completions",
                target_model=grok_model,
                prompt=prompt,
                system_prompt=system_prompt,
                json_mode=json_mode,
                temperature=0.7,
            )
            reasoning_effort = _grok_reasoning_effort(grok_model)
            if reasoning_effort:
                request.payload["reasoning_effort"] = reasoning_effort

            async for chunk in stream_openai_compatible_response(
                provider="grok",
                display_name="Grok",
                request=request,
                headers=headers,
                target_model=grok_model,
                prompt=prompt,
                purpose=purpose,
                timeout_seconds=float(_provider_timeout_seconds("grok")),
                max_attempts=_retry_attempts(),
                usage_logger=_log_llm_usage,
                trust_env=True,
            ):
                yield chunk
            return

        elif model == "claude":
            if not model_manager.config.claude_enabled:
                yield "Error: Claude API disabled. Enable in settings."
                return

            client = self._get_anthropic_client()
            if not client:
                yield "Error: Anthropic API Key not configured."
                return

            target_model = specific_model or model_manager.get_chat_model("claude")
            logger.info(f"Using Claude model: {target_model}")
            async for chunk in stream_claude_response(
                client=client,
                request=ClaudeStreamRequest(
                    target_model=target_model,
                    prompt=prompt,
                    system_prompt=system_prompt,
                ),
                purpose=purpose,
                timeout_seconds=float(_provider_timeout_seconds("claude")),
                max_attempts=_retry_attempts(),
                usage_logger=_log_llm_usage,
            ):
                yield chunk
            return

        elif model == "fair":
            if not model_manager.config.fair_enabled:
                yield "Error: FAIR.Hyperion API disabled. Enable in settings."
                return

            if not self.fair_api_key:
                yield "Error: FAIR.Hyperion API Key not configured."
                return

            target_model = specific_model or model_manager.get_chat_model("fair")
            base_url = self._get_fair_base_url()
            request = build_chat_completions_request(
                api_url=f"{base_url}/chat/completions",
                target_model=target_model,
                prompt=prompt,
                system_prompt=system_prompt,
                json_mode=json_mode,
                temperature=0.7,
            )
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.fair_api_key}",
            }
            logger.info("FAIR.Hyperion: model={}, endpoint=chat, api_key=configured", target_model)

            async for chunk in stream_openai_compatible_response(
                provider="fair",
                display_name="FAIR.Hyperion",
                request=request,
                headers=headers,
                target_model=target_model,
                prompt=prompt,
                purpose=purpose,
                timeout_seconds=float(_provider_timeout_seconds("fair")),
                max_attempts=_retry_attempts(),
                usage_logger=_log_llm_usage,
                log_metadata={"base_url": base_url},
            ):
                yield chunk
            return

        elif model == "openai":
            if not model_manager.config.openai_enabled:
                logger.warning("OpenAI: openai_enabled=False, but proceeding because key is present")

            if not self.openai_api_key:
                logger.error("OpenAI: API key not configured (OPENAI_API_KEY / CODEX_API_KEY not set)")
                yield "Error: OpenAI API Key not configured."
                return

            target_model = specific_model or model_manager.get_chat_model("openai")
            request = build_openai_request(
                target_model=target_model,
                prompt=prompt,
                system_prompt=system_prompt,
                json_mode=json_mode,
                reasoning_effort=(model_manager.config.openai_reasoning_effort or "").strip(),
            )
            logger.info(f"OpenAI: model={target_model}, endpoint={request.endpoint_name}, api_key=configured")

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openai_api_key}",
            }
            _timeout_sec = float(_provider_timeout_seconds("openai", endpoint_name=request.endpoint_name))
            logger.debug(f"OpenAI: timeout={_timeout_sec}s")
            async for chunk in stream_openai_compatible_response(
                provider="openai",
                display_name="OpenAI",
                request=request,
                headers=headers,
                target_model=target_model,
                prompt=prompt,
                purpose=purpose,
                timeout_seconds=_timeout_sec,
                max_attempts=_retry_attempts(),
                usage_logger=_log_llm_usage,
            ):
                yield chunk
            return

        elif model == "ollama":
            if not model_manager.config.ollama_enabled:
                yield "Error: Ollama is disabled in settings."
                return

            target_model = specific_model or model_manager.get_chat_model("ollama")
            if not target_model:
                yield "Error: Ollama model is not configured."
                return

            request_targets = self._build_ollama_request_targets(target_model)
            if not request_targets:
                if model_manager._is_ollama_cloud_model(target_model) or self._get_ollama_runtime_mode() == "cloud":
                    yield "Error: Ollama Cloud requires `OLLAMA_API_KEY` and cloud mode enabled in settings."
                else:
                    yield "Error: Ollama runtime is not configured."
                return

            async for chunk in stream_ollama_response(
                request=OllamaStreamRequest(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    json_mode=json_mode,
                    request_targets=request_targets,
                    think_value=self._get_ollama_think_value(),
                ),
                purpose=purpose,
                timeout_seconds=float(_provider_timeout_seconds("ollama")),
                max_attempts=_retry_attempts(),
                usage_logger=_log_llm_usage,
                get_configured_base_url=lambda: model_manager.config.ollama_base_url,
                set_configured_base_url=lambda base_url: setattr(model_manager.config, "ollama_base_url", base_url),
                is_connect_error=_is_ollama_connect_error,
            ):
                yield chunk
            return

        else:
            yield f"Unknown model: {model}"
