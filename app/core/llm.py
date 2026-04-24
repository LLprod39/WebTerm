import asyncio
import contextlib
import os
import time
from collections.abc import AsyncGenerator
from typing import Any

from django.conf import settings as django_settings
from google import genai
from loguru import logger

from app.core.model_config import model_manager

# Таймаут для стрима Gemini (сек), экспоненциальная задержка при retry
GEMINI_STREAM_TIMEOUT = 90  # в диапазоне 60–120 сек
RETRY_BACKOFF = [1, 2, 4]


def _setting_int(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        raw = getattr(django_settings, name, None)
    except Exception:
        raw = None
    if raw in (None, ""):
        raw = os.getenv(name)
    try:
        value = int(raw if raw not in (None, "") else default)
    except (TypeError, ValueError):
        value = default
    return max(value, minimum)


def _retry_attempts() -> int:
    return _setting_int("LLM_MAX_RETRY_ATTEMPTS", 3, minimum=1)


def _provider_timeout_seconds(provider: str, *, endpoint_name: str | None = None) -> int:
    if provider == "gemini":
        return _setting_int("LLM_GEMINI_STREAM_TIMEOUT_SECONDS", GEMINI_STREAM_TIMEOUT, minimum=1)
    if provider == "grok":
        return _setting_int("LLM_GROK_STREAM_TIMEOUT_SECONDS", 60, minimum=1)
    if provider == "claude":
        return _setting_int("LLM_CLAUDE_STREAM_TIMEOUT_SECONDS", 120, minimum=1)
    if provider == "ollama":
        return _setting_int("LLM_OLLAMA_STREAM_TIMEOUT_SECONDS", 300, minimum=1)
    if provider == "openai" and endpoint_name == "responses":
        return _setting_int("LLM_OPENAI_RESPONSES_TIMEOUT_SECONDS", 300, minimum=1)
    if provider == "openai":
        return _setting_int("LLM_OPENAI_STREAM_TIMEOUT_SECONDS", 90, minimum=1)
    return _setting_int("LLM_PROVIDER_TIMEOUT_SECONDS", 90, minimum=1)


def _is_timeout_error(e: Exception) -> bool:
    if isinstance(e, (TimeoutError, asyncio.TimeoutError)):
        return True
    s = str(e).lower()
    return "timeout" in s or "timed out" in s


def _is_ollama_connect_error(e: Exception) -> bool:
    try:
        import aiohttp

        if isinstance(e, (aiohttp.ClientConnectorError, aiohttp.ClientOSError, aiohttp.ClientConnectionError)):
            return True
    except ImportError:
        pass
    if isinstance(e, (ConnectionError, OSError)):
        return True
    s = str(e).lower()
    return "cannot connect to host" in s or "failed to connect" in s or "connection refused" in s


def _log_llm_usage(
    provider: str,
    model_name: str,
    input_text: str,
    output_text: str,
    duration_ms: int,
    status: str = "success",
    *,
    purpose: str = "",
    metadata: dict[str, Any] | None = None,
):
    """Log LLM API usage for monitoring. Never raises — errors are silently logged.

    Safe to call from both sync and async contexts.
    """
    try:
        from core_ui.audit import get_audit_context

        captured_audit_ctx = get_audit_context()
    except Exception:
        captured_audit_ctx = {}

    def _do_log():
        try:
            from core_ui.activity import log_llm_activity
            from core_ui.audit import audit_context, get_audit_context, maybe_apply_log_retention, should_log_llm
            from core_ui.models import LLMUsageLog

            with audit_context(**captured_audit_ctx):
                if not should_log_llm():
                    return

                maybe_apply_log_retention()
                audit_ctx = get_audit_context()
                LLMUsageLog.objects.create(
                    provider=provider,
                    model_name=model_name,
                    user_id=audit_ctx.get("user_id"),
                    input_tokens=len(input_text) // 4,
                    output_tokens=len(output_text) // 4,
                    duration_ms=duration_ms,
                    status=status,
                )
                log_llm_activity(
                    provider=provider,
                    model_name=model_name,
                    prompt=input_text,
                    response=output_text,
                    duration_ms=duration_ms,
                    status=status,
                    purpose=purpose,
                    metadata=metadata,
                )
        except Exception as e:
            logger.debug(f"Failed to log LLM usage: {e}")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Detached background logging must not inherit asgiref's thread-sensitive
        # executor context, otherwise later ASGI requests can fail with a broken
        # CurrentThreadExecutor after this task outlives the originating request.
        loop.run_in_executor(None, _do_log)
        return

    _do_log()


def _is_retryable_error(e: Exception) -> bool:
    """Проверка на 429 (rate limit), 5xx или таймаут — повторять с backoff."""
    if _is_timeout_error(e):
        return True
    # aiohttp таймауты
    try:
        import aiohttp
        if isinstance(e, (aiohttp.ServerTimeoutError, aiohttp.ClientConnectorError)):
            return True
    except ImportError:
        pass
    s = str(e).lower()
    if "timeout" in s or "timed out" in s:
        return True
    code = getattr(e, "status_code", None) or getattr(e, "code", None)
    if code is not None:
        if code == 429:
            return True
        if isinstance(code, int) and 500 <= code < 600:
            return True
    if "429" in s or "resource exhausted" in s or "rate" in s:
        return True
    return bool("503" in s or "502" in s or "500" in s or "internal" in s)


async def with_retry(coro, max_attempts: int = 3):
    """
    Обёртка с retry при 429/5xx.
    Экспоненциальная задержка: 1с, 2с, 4с.
    После max_attempts — пробрасывает ошибку.
    coro: корутина или callable, возвращающий корутину.
    """
    last_err = None
    for attempt in range(max_attempts):
        try:
            awaitable = coro() if callable(coro) and not asyncio.iscoroutine(coro) else coro
            return await awaitable
        except Exception as e:
            last_err = e
            if not _is_retryable_error(e) or attempt >= max_attempts - 1:
                raise
            delay = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
            logger.warning(f"Retryable error (attempt {attempt + 1}/{max_attempts}): {e}, sleep {delay}s")
            await asyncio.sleep(delay)
    if last_err is not None:
        raise last_err


# ---------------------------------------------------------------------------
# Singleton accessor (P1-7).
# ---------------------------------------------------------------------------
_provider_instance: "LLMProvider | None" = None


def get_provider() -> "LLMProvider":
    """Return a module-level cached LLMProvider.

    Avoids re-reading env variables and re-initializing model_manager keys
    on every call.  Safe across async tasks (GIL protects simple attribute
    assignment; LLMProvider already lazy-inits API clients).
    """
    global _provider_instance
    with contextlib.suppress(Exception):
        model_manager.load_config()
    if _provider_instance is None:
        _provider_instance = LLMProvider()
    return _provider_instance


class LLMProvider:
    def __init__(self):
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.grok_api_key = os.getenv("GROK_API_KEY")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY") or os.getenv("CODEX_API_KEY")

        # Set keys in model manager
        model_manager.set_api_keys(
            self.gemini_api_key,
            self.grok_api_key,
            self.anthropic_api_key,
            self.openai_api_key,
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
    def _get_ollama_think_value() -> Any | None:
        think_mode = model_manager._get_ollama_think_mode()
        if think_mode == "off":
            return False
        if think_mode == "on":
            return True
        if think_mode in {"low", "medium", "high"}:
            return think_mode
        return None

    @staticmethod
    def _build_ollama_request_targets(target_model: str) -> list[dict[str, Any]]:
        normalized_model = model_manager._decode_ollama_cloud_model(target_model)
        runtime_mode = model_manager._get_ollama_runtime_mode()
        explicit_cloud_model = model_manager._is_ollama_cloud_model(target_model)

        if explicit_cloud_model or runtime_mode == "cloud":
            api_key = model_manager._get_ollama_api_key()
            if not model_manager.config.ollama_cloud_enabled or not api_key:
                return []
            return [
                {
                    "kind": "cloud",
                    "base_url": model_manager._get_ollama_cloud_base_url(),
                    "headers": {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                    },
                    "model": normalized_model,
                }
            ]

        return [
            {
                "kind": "local",
                "base_url": base_url,
                "headers": {"Content-Type": "application/json"},
                "model": normalized_model,
            }
            for base_url in model_manager._get_ollama_base_urls()
        ]

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
            model: Provider name (auto/gemini/grok/openai/claude/ollama). «auto» resolves via purpose.
            specific_model: Specific model version to use (overrides config)
            purpose: One of 'chat', 'agent', 'orchestrator' — used when model=='auto'
            system_prompt: Optional system-level instructions. When provided,
                replaces the default generic system message and enables
                provider-level prompt caching (Anthropic cache_control,
                OpenAI automatic prefix caching, Gemini system_instruction).
            json_mode: When True, activates provider-native JSON output mode
                (3.1) so the LLM is constrained to produce valid JSON.
        """
        def _has_key(p: str) -> bool:
            """Провайдер доступен по ключу (без учёта глобального *_enabled)."""
            if p == "grok":
                return bool(self.grok_api_key)
            if p == "gemini":
                return bool(self.gemini_api_key)
            if p == "claude":
                return bool(self.anthropic_api_key)
            if p == "openai":
                return bool(self.openai_api_key)
            if p == "ollama":
                return False
            return False

        def _enabled(p: str) -> bool:
            if p == "grok":
                return model_manager.config.grok_enabled and bool(self.grok_api_key)
            if p == "gemini":
                return model_manager.config.gemini_enabled and bool(self.gemini_api_key)
            if p == "claude":
                return model_manager.config.claude_enabled and bool(self.anthropic_api_key)
            if p == "openai":
                return model_manager.config.openai_enabled and bool(self.openai_api_key)
            if p == "ollama":
                return model_manager.config.ollama_enabled and bool(self._get_ollama_base_url())
            return False

        if model == "auto" or not model:
            # Resolve provider + model via purpose-based config
            preferred, purpose_model = model_manager.resolve_purpose(purpose)
            if not specific_model:
                specific_model = purpose_model

            # Явный выбор в конфиге + есть ключ — используем провайдер даже без глобального *_enabled
            if _has_key(preferred) or _enabled(preferred):
                model = preferred
            else:
                # Fallback: pick first enabled provider
                for candidate in ("openai", "claude", "grok", "gemini", "ollama"):
                    if _enabled(candidate):
                        model = candidate
                        logger.warning(
                            f"[{purpose}] provider '{preferred}' is disabled/unconfigured, "
                            f"falling back to '{model}'"
                        )
                        break
                else:
                    model = preferred
            logger.info(f"[{purpose}] using provider: {model}, model: {specific_model or '(default)'}")
        logger.info(f"Streaming chat from {model} with prompt: {prompt[:50]}...")

        # B2: per-user daily token budget pre-flight. Best-effort — never let
        # a budget-service failure break a real LLM call (lazy import + try).
        try:
            from core_ui.audit import get_audit_context
            from core_ui.services.llm_budget import (
                BudgetExceededError,
                get_user_daily_budget_status,
            )

            _budget_user_id = (get_audit_context() or {}).get("user_id")
            if _budget_user_id:
                _budget = get_user_daily_budget_status(int(_budget_user_id))
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
            max_attempts = _retry_attempts()
            timeout_seconds = _provider_timeout_seconds("gemini")
            _t0 = time.monotonic()

            for attempt in range(max_attempts):
                try:
                    async def consume():
                        out = []
                        # generate_content_stream возвращает корутину; нужен await перед async for
                        _gemini_kwargs: dict[str, Any] = {
                            "model": target_model,
                            "contents": prompt,
                        }
                        _gemini_config: dict[str, Any] = {}
                        if system_prompt:
                            _gemini_config["system_instruction"] = system_prompt
                        # 3.1: JSON mode — Gemini native structured output.
                        if json_mode:
                            _gemini_config["response_mime_type"] = "application/json"
                        if _gemini_config:
                            _gemini_kwargs["config"] = _gemini_config
                        stream = await self.gemini_client.aio.models.generate_content_stream(
                            **_gemini_kwargs
                        )
                        async for chunk in stream:
                            if chunk.text:
                                out.append(chunk.text)
                        return out

                    chunks = await asyncio.wait_for(consume(), timeout=timeout_seconds)
                    _output = ""
                    for c in chunks:
                        _output += c
                        yield c
                    _log_llm_usage(
                        "gemini",
                        target_model,
                        prompt,
                        _output,
                        int((time.monotonic() - _t0) * 1000),
                        purpose=purpose,
                    )
                    return
                except asyncio.TimeoutError:
                    logger.error("Gemini stream timeout")
                    _log_llm_usage(
                        "gemini",
                        target_model,
                        prompt,
                        "",
                        int((time.monotonic() - _t0) * 1000),
                        "timeout",
                        purpose=purpose,
                    )
                    yield "Error: Timeout (Gemini stream)."
                    return
                except Exception as e:
                    if _is_retryable_error(e) and attempt < max_attempts - 1:
                        yield "[Повтор попытки...]"
                        delay = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"Gemini Error: {e}")
                        _log_llm_usage(
                            "gemini",
                            target_model,
                            prompt,
                            "",
                            int((time.monotonic() - _t0) * 1000),
                            "error",
                            purpose=purpose,
                        )
                        yield f"Error calling Gemini: {str(e)}"
                        return

        elif model == "grok":
            # Check if Grok is enabled
            if not model_manager.config.grok_enabled:
                yield "Error: Grok API disabled. Enable in settings or use CLI agent (ralph/cursor/claude)."
                return

            if not self.grok_api_key:
                yield "Error: Grok API Key not configured."
                return

            import json

            import aiohttp

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.grok_api_key}"
            }
            grok_model = specific_model or model_manager.get_chat_model("grok")
            data: dict[str, Any] = {
                "messages": [
                    {"role": "system", "content": system_prompt or "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                "model": grok_model,
                "stream": True,
                "temperature": 0.7,
            }
            # 3.1: JSON mode — Grok uses OpenAI-compatible response_format.
            if json_mode:
                data["response_format"] = {"type": "json_object"}
            timeout = aiohttp.ClientTimeout(total=float(_provider_timeout_seconds("grok")))
            max_attempts = _retry_attempts()
            _t0 = time.monotonic()

            for attempt in range(max_attempts):
                try:
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.post("https://api.x.ai/v1/chat/completions", headers=headers, json=data) as response:
                            if response.status == 200:
                                _output = ""
                                async for line_bytes in response.content:
                                    line = line_bytes.decode('utf-8').strip()
                                    if line.startswith("data: "):
                                        chunk_str = line[6:]
                                        if chunk_str == "[DONE]":
                                            break
                                        try:
                                            chunk_json = json.loads(chunk_str)
                                            content = chunk_json.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                            if content:
                                                _output += content
                                                yield content
                                        except json.JSONDecodeError:
                                            continue
                                _log_llm_usage(
                                    "grok",
                                    grok_model,
                                    prompt,
                                    _output,
                                    int((time.monotonic() - _t0) * 1000),
                                    purpose=purpose,
                                )
                                return
                            error_text = await response.text()
                            is_retryable = response.status == 429 or (500 <= response.status < 600)
                            if is_retryable and attempt < max_attempts - 1:
                                yield "[Повтор попытки...]"
                                delay = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                                await asyncio.sleep(delay)
                            else:
                                _log_llm_usage(
                                    "grok",
                                    grok_model,
                                    prompt,
                                    "",
                                    int((time.monotonic() - _t0) * 1000),
                                    "error",
                                    purpose=purpose,
                                )
                                yield f"Error from Grok API: {response.status} - {error_text}"
                                return
                except Exception as e:
                    err_retryable = _is_retryable_error(e) and attempt < max_attempts - 1
                    if err_retryable:
                        yield "[Повтор попытки...]"
                        delay = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"Grok Error: {e}")
                        _log_llm_usage(
                            "grok",
                            grok_model,
                            prompt,
                            "",
                            int((time.monotonic() - _t0) * 1000),
                            "timeout" if _is_timeout_error(e) else "error",
                            purpose=purpose,
                        )
                        if _is_timeout_error(e):
                            yield "Error: Timeout (Grok stream)."
                        else:
                            yield f"Error calling Grok: {str(e)}"
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
            max_attempts = _retry_attempts()
            timeout_seconds = _provider_timeout_seconds("claude")
            _t0 = time.monotonic()

            for attempt in range(max_attempts):
                try:
                    _output = ""
                    _claude_kwargs: dict[str, Any] = {
                        "model": target_model,
                        "max_tokens": 8192,
                        "messages": [{"role": "user", "content": prompt}],
                    }
                    if system_prompt:
                        _claude_kwargs["system"] = [
                            {
                                "type": "text",
                                "text": system_prompt,
                                "cache_control": {"type": "ephemeral"},
                            }
                        ]
                    async with asyncio.timeout(timeout_seconds):
                        async with client.messages.stream(
                            **_claude_kwargs,
                        ) as stream:
                            async for text in stream.text_stream:
                                _output += text
                                yield text
                    _log_llm_usage(
                        "claude",
                        target_model,
                        prompt,
                        _output,
                        int((time.monotonic() - _t0) * 1000),
                        purpose=purpose,
                    )
                    return
                except Exception as e:
                    if _is_retryable_error(e) and attempt < max_attempts - 1:
                        yield "[Повтор попытки...]"
                        delay = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"Claude Error: {e}")
                        _log_llm_usage(
                            "claude",
                            target_model,
                            prompt,
                            "",
                            int((time.monotonic() - _t0) * 1000),
                            "timeout" if _is_timeout_error(e) else "error",
                            purpose=purpose,
                        )
                        if _is_timeout_error(e):
                            yield "Error: Timeout (Claude stream)."
                        else:
                            yield f"Error calling Claude: {str(e)}"
                        return

        elif model == "openai":
            if not model_manager.config.openai_enabled:
                logger.warning("OpenAI: openai_enabled=False, but proceeding because key is present")

            if not self.openai_api_key:
                logger.error("OpenAI: API key not configured (OPENAI_API_KEY / CODEX_API_KEY not set)")
                yield "Error: OpenAI API Key not configured."
                return

            import json

            import aiohttp

            target_model = specific_model or model_manager.get_chat_model("openai")
            key_preview = self.openai_api_key[:8] + "..." if self.openai_api_key else "—"

            # Определяем эндпоинт:
            # - gpt-5.x (все модели нового поколения) → Responses API (/v1/responses)
            # - gpt-4+/o1/o3 + "codex" → тоже Responses API
            # - старые codex/instruct/davinci → Legacy Completions (/v1/completions)
            # - остальное → Chat Completions (/v1/chat/completions)
            _model_lower = target_model.lower()
            _USE_RESPONSES_API = (
                _model_lower.startswith("gpt-5")
                or (
                    "codex" in _model_lower
                    and any(_model_lower.startswith(p) for p in ("gpt-4", "o1", "o3", "o4"))
                )
            )
            _LEGACY_COMPLETIONS = (
                not _USE_RESPONSES_API
                and any(kw in _model_lower for kw in ("instruct", "davinci", "babbage", "curie", "ada"))
                and not _model_lower.startswith("gpt-4")
            )

            if _USE_RESPONSES_API:
                endpoint_name = "responses"
                api_url = "https://api.openai.com/v1/responses"
                request_data: dict = {
                    "model": target_model,
                    "instructions": system_prompt or "You are a helpful assistant.",
                    "input": prompt,
                    "stream": True,
                }
                # 3.1: JSON mode — Responses API uses text.format.
                if json_mode:
                    request_data["text"] = {"format": {"type": "json_object"}}
                # Передаём reasoning.effort если задан
                # "none" — отключить мышление полностью, "low"/"medium"/"high" — уровень
                # "" — не передавать (модель решает сама)
                _reasoning_effort = (model_manager.config.openai_reasoning_effort or "").strip()
                if _reasoning_effort in ("none", "low", "medium", "high"):
                    request_data["reasoning"] = {"effort": _reasoning_effort}
                    logger.debug(f"OpenAI Responses: reasoning.effort={_reasoning_effort}")
            elif _LEGACY_COMPLETIONS:
                endpoint_name = "completions"
                api_url = "https://api.openai.com/v1/completions"
                request_data = {
                    "model": target_model,
                    "prompt": f"You are a helpful assistant.\n\n{prompt}",
                    "stream": True,
                    "max_tokens": 2048,
                }
            else:
                endpoint_name = "chat"
                api_url = "https://api.openai.com/v1/chat/completions"
                request_data = {
                    "model": target_model,
                    "messages": [
                        {"role": "system", "content": system_prompt or "You are a helpful assistant."},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": True,
                }
                # 3.1: JSON mode — Chat Completions uses response_format.
                if json_mode:
                    request_data["response_format"] = {"type": "json_object"}

            logger.info(f"OpenAI: model={target_model}, endpoint={endpoint_name}, key_prefix={key_preview}")

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openai_api_key}",
            }
            # Responses API (reasoning-модели gpt-5.x) могут думать несколько минут
            _timeout_sec = float(_provider_timeout_seconds("openai", endpoint_name=endpoint_name))
            timeout = aiohttp.ClientTimeout(total=_timeout_sec)
            logger.debug(f"OpenAI: timeout={_timeout_sec}s")
            max_attempts = _retry_attempts()
            _t0 = time.monotonic()

            for attempt in range(max_attempts):
                logger.debug(f"OpenAI: attempt {attempt + 1}/{max_attempts} → POST {api_url}")
                try:
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.post(api_url, headers=headers, json=request_data) as response:
                            logger.debug(f"OpenAI: HTTP status={response.status}")
                            if response.status == 200:
                                _output = ""
                                _chunks = 0
                                async for line_bytes in response.content:
                                    line = line_bytes.decode("utf-8").strip()
                                    if not line or line.startswith("event:"):
                                        # SSE event-type lines (Responses API) — пропускаем
                                        continue
                                    if not line.startswith("data: "):
                                        continue
                                    chunk_str = line[6:]
                                    if chunk_str == "[DONE]":
                                        logger.debug(f"OpenAI: stream done, chunks={_chunks}, chars={len(_output)}")
                                        break
                                    try:
                                        chunk_json = json.loads(chunk_str)
                                    except json.JSONDecodeError as je:
                                        logger.warning(f"OpenAI: JSON decode error: {je} | raw={chunk_str[:120]}")
                                        continue

                                    if endpoint_name == "responses":
                                        # Responses API: event type = response.output_text.delta → {"delta":"..."}
                                        event_type = chunk_json.get("type", "")
                                        if event_type == "response.output_text.delta":
                                            content = chunk_json.get("delta", "")
                                        elif event_type == "response.completed":
                                            logger.debug(f"OpenAI Responses: completed, chunks={_chunks}, chars={len(_output)}")
                                            break
                                        else:
                                            continue
                                    elif endpoint_name == "completions":
                                        content = chunk_json.get("choices", [{}])[0].get("text", "")
                                    else:
                                        content = chunk_json.get("choices", [{}])[0].get("delta", {}).get("content", "")

                                    if content:
                                        _chunks += 1
                                        _output += content
                                        yield content

                                _log_llm_usage(
                                    "openai",
                                    target_model,
                                    prompt,
                                    _output,
                                    int((time.monotonic() - _t0) * 1000),
                                    purpose=purpose,
                                )
                                return

                            error_text = await response.text()
                            is_retryable = response.status == 429 or (500 <= response.status < 600)
                            logger.error(f"OpenAI: HTTP error {response.status}, retryable={is_retryable}, body={error_text[:500]}")
                            if is_retryable and attempt < max_attempts - 1:
                                yield "[Повтор попытки...]"
                                delay = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                                await asyncio.sleep(delay)
                            else:
                                _log_llm_usage(
                                    "openai",
                                    target_model,
                                    prompt,
                                    "",
                                    int((time.monotonic() - _t0) * 1000),
                                    "error",
                                    purpose=purpose,
                                )
                                yield f"Error from OpenAI API: {response.status} - {error_text}"
                                return
                except Exception as e:
                    err_retryable = _is_retryable_error(e) and attempt < max_attempts - 1
                    logger.error(f"OpenAI: exception attempt={attempt + 1}: {type(e).__name__}: {e}", exc_info=True)
                    if err_retryable:
                        yield "[Повтор попытки...]"
                        delay = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                        await asyncio.sleep(delay)
                    else:
                        _log_llm_usage(
                            "openai",
                            target_model,
                            prompt,
                            "",
                            int((time.monotonic() - _t0) * 1000),
                            "timeout" if _is_timeout_error(e) else "error",
                            purpose=purpose,
                        )
                        if _is_timeout_error(e):
                            yield "Error: Timeout (OpenAI stream)."
                        else:
                            yield f"Error calling OpenAI: {str(e)}"
                        return

        elif model == "ollama":
            if not model_manager.config.ollama_enabled:
                yield "Error: Ollama is disabled in settings."
                return

            import json

            import aiohttp

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

            payload: dict[str, Any] = {
                "model": request_targets[0]["model"],
                "messages": [
                    {"role": "system", "content": system_prompt or "You are a helpful assistant."},
                    {"role": "user", "content": prompt},
                ],
                "stream": True,
            }
            # 3.1: JSON mode — Ollama uses format field.
            if json_mode:
                payload["format"] = "json"
            think_value = self._get_ollama_think_value()
            if think_value is not None:
                payload["think"] = think_value
            timeout = aiohttp.ClientTimeout(total=float(_provider_timeout_seconds("ollama")))
            max_attempts = _retry_attempts()
            _t0 = time.monotonic()
            last_error = None

            for base_index, request_target in enumerate(request_targets):
                base_url = request_target["base_url"]
                headers = dict(request_target["headers"])
                payload["model"] = request_target["model"]
                for attempt in range(max_attempts):
                    try:
                        async with aiohttp.ClientSession(timeout=timeout) as session:
                            async with session.post(f"{base_url}/api/chat", headers=headers, json=payload) as response:
                                if response.status == 200:
                                    _output = ""
                                    pending = ""
                                    async for chunk_bytes in response.content.iter_any():
                                        pending += chunk_bytes.decode("utf-8")
                                        while "\n" in pending:
                                            raw_line, pending = pending.split("\n", 1)
                                            line = raw_line.strip()
                                            if not line:
                                                continue
                                            try:
                                                chunk_json = json.loads(line)
                                            except json.JSONDecodeError:
                                                logger.debug(f"Ollama: failed to parse stream line: {line[:160]}")
                                                continue
                                            content = ((chunk_json.get("message") or {}).get("content") or "")
                                            if content:
                                                _output += content
                                                yield content
                                            if chunk_json.get("done"):
                                                break
                                        else:
                                            continue
                                        break

                                    if pending.strip():
                                        try:
                                            chunk_json = json.loads(pending.strip())
                                            content = ((chunk_json.get("message") or {}).get("content") or "")
                                            if content:
                                                _output += content
                                                yield content
                                        except json.JSONDecodeError:
                                            logger.debug(f"Ollama: trailing stream fragment ignored: {pending[:160]}")

                                    if request_target["kind"] == "local" and base_url != model_manager.config.ollama_base_url:
                                        logger.warning(
                                            f"Ollama chat fallback: configured={model_manager.config.ollama_base_url or 'unset'} -> using {base_url}"
                                        )
                                    if request_target["kind"] == "local":
                                        model_manager.config.ollama_base_url = base_url
                                    _log_llm_usage(
                                        "ollama",
                                        payload["model"],
                                        prompt,
                                        _output,
                                        int((time.monotonic() - _t0) * 1000),
                                        purpose=purpose,
                                        metadata={
                                            "base_url": base_url,
                                            "request_targets": [target["base_url"] for target in request_targets],
                                            "source": request_target["kind"],
                                            "think": payload.get("think"),
                                        },
                                    )
                                    return

                                error_text = await response.text()
                                is_retryable = response.status == 429 or (500 <= response.status < 600)
                                if is_retryable and attempt < max_attempts - 1:
                                    yield "[Повтор попытки...]"
                                    delay = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                                    await asyncio.sleep(delay)
                                else:
                                    _log_llm_usage(
                                        "ollama",
                                        payload["model"],
                                        prompt,
                                        "",
                                        int((time.monotonic() - _t0) * 1000),
                                        "error",
                                        purpose=purpose,
                                        metadata={
                                            "base_url": base_url,
                                            "request_targets": [target["base_url"] for target in request_targets],
                                            "source": request_target["kind"],
                                            "think": payload.get("think"),
                                        },
                                    )
                                    if request_target["kind"] == "cloud":
                                        yield f"Error from Ollama Cloud API: {response.status} - {error_text}"
                                    else:
                                        yield f"Error from Ollama API: {response.status} - {error_text}"
                                    return
                    except Exception as e:
                        last_error = e
                        has_next_base_url = base_index < len(request_targets) - 1
                        if request_target["kind"] == "local" and _is_ollama_connect_error(e) and has_next_base_url:
                            logger.warning(
                                f"Ollama connect failed via {base_url}: {e}. Trying next base URL."
                            )
                            break

                        err_retryable = _is_retryable_error(e) and attempt < max_attempts - 1
                        if err_retryable:
                            yield "[Повтор попытки...]"
                            delay = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                            await asyncio.sleep(delay)
                        else:
                            logger.error(f"Ollama Error: {e}")
                            _log_llm_usage(
                                "ollama",
                                payload["model"],
                                prompt,
                                "",
                                int((time.monotonic() - _t0) * 1000),
                                "timeout" if _is_timeout_error(e) else "error",
                                purpose=purpose,
                                metadata={
                                    "base_url": base_url,
                                    "request_targets": [target["base_url"] for target in request_targets],
                                    "source": request_target["kind"],
                                    "think": payload.get("think"),
                                },
                            )
                            if _is_timeout_error(e):
                                yield "Error: Timeout (Ollama stream)."
                            elif request_target["kind"] == "local" and _is_ollama_connect_error(e) and len(request_targets) > 1:
                                yield (
                                    "Error: Ollama недоступен по localhost из backend runtime. "
                                    "Проверь, что Ollama слушает Windows host не только на 127.0.0.1."
                                )
                            elif request_target["kind"] == "cloud":
                                yield f"Error calling Ollama Cloud: {str(e)}"
                            else:
                                yield f"Error calling Ollama: {str(e)}"
                            return

            if last_error is not None:
                logger.error(f"Ollama Error after trying all base URLs: {last_error}")
                _log_llm_usage(
                    "ollama",
                    payload["model"],
                    prompt,
                    "",
                    int((time.monotonic() - _t0) * 1000),
                    "timeout" if _is_timeout_error(last_error) else "error",
                    purpose=purpose,
                    metadata={
                        "request_targets": [target["base_url"] for target in request_targets],
                        "think": payload.get("think"),
                    },
                )
                if _is_timeout_error(last_error):
                    yield "Error: Timeout (Ollama stream)."
                elif any(target["kind"] == "cloud" for target in request_targets):
                    yield "Error: Ollama Cloud не ответил по настроенному API endpoint."
                else:
                    yield (
                        "Error: Ollama не доступен из backend. "
                        "Сервис запущен, но runtime не может достучаться до него по всем известным адресам."
                    )
                return

        else:
            yield f"Unknown model: {model}"
