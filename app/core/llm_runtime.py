from __future__ import annotations

import asyncio
import os

from django.conf import settings as django_settings
from loguru import logger

GEMINI_STREAM_TIMEOUT = 90
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


def _setting_str(name: str, default: str = "") -> str:
    try:
        raw = getattr(django_settings, name, None)
    except Exception:
        raw = None
    if raw in (None, ""):
        raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return str(raw).strip()


def _retry_attempts() -> int:
    return _setting_int("LLM_MAX_RETRY_ATTEMPTS", 3, minimum=1)


def _provider_timeout_seconds(provider: str, *, endpoint_name: str | None = None) -> int:
    if provider == "gemini":
        return _setting_int("LLM_GEMINI_STREAM_TIMEOUT_SECONDS", GEMINI_STREAM_TIMEOUT, minimum=1)
    if provider == "grok":
        return _setting_int("LLM_GROK_STREAM_TIMEOUT_SECONDS", 3600, minimum=1)
    if provider == "claude":
        return _setting_int("LLM_CLAUDE_STREAM_TIMEOUT_SECONDS", 120, minimum=1)
    if provider == "ollama":
        # Operator tools can hang on huge prompts; fail faster so the UI recovers
        return _setting_int("LLM_OLLAMA_STREAM_TIMEOUT_SECONDS", 120, minimum=1)
    if provider == "openai" and endpoint_name == "responses":
        return _setting_int("LLM_OPENAI_RESPONSES_TIMEOUT_SECONDS", 300, minimum=1)
    if provider == "openai":
        return _setting_int("LLM_OPENAI_STREAM_TIMEOUT_SECONDS", 90, minimum=1)
    if provider == "fair":
        return _setting_int("LLM_FAIR_STREAM_TIMEOUT_SECONDS", 120, minimum=1)
    return _setting_int("LLM_PROVIDER_TIMEOUT_SECONDS", 90, minimum=1)


def _grok_reasoning_effort(model: str, *, purpose: str = "") -> str | None:
    normalized_model = (model or "").strip().lower()
    if not normalized_model.startswith("grok-4.3"):
        return None

    default = "medium" if (purpose or "").strip().lower() == "orchestrator" else "none"
    value = _setting_str("LLM_GROK_REASONING_EFFORT", default).lower()
    if value in {"", "default", "auto"}:
        return None
    if value in {"none", "low", "medium", "high"}:
        return value

    logger.warning("Invalid LLM_GROK_REASONING_EFFORT=%r; using 'none'", value)
    return "none"


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


def _is_retryable_error(e: Exception) -> bool:
    if _is_timeout_error(e):
        return True
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
