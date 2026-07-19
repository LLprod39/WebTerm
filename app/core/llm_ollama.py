from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from typing import Any

import aiohttp
from loguru import logger

from app.core.llm_runtime import RETRY_BACKOFF, _is_retryable_error, _is_timeout_error
from app.core.redacted_logging import redacted_log_text

UsageLogger = Callable[..., None]
ConnectErrorPredicate = Callable[[Exception], bool]


@dataclass(frozen=True)
class OllamaStreamRequest:
    prompt: str
    system_prompt: str | None
    json_mode: bool
    request_targets: list[dict[str, Any]]
    think_value: Any | None = None


def get_ollama_think_value(model_manager: Any) -> Any | None:
    # Per-turn override from Operator chat "thinking mode" toggle
    try:
        from core_ui.services.operator_turn_runtime import operator_thinking_mode

        override = operator_thinking_mode.get()
        if override == "off":
            return False
        if override == "on":
            return True
        if override in {"low", "medium", "high"}:
            return override
    except Exception:  # noqa: BLE001
        pass

    think_mode = model_manager._get_ollama_think_mode()
    if think_mode == "off":
        return False
    if think_mode == "on":
        return True
    if think_mode in {"low", "medium", "high"}:
        return think_mode
    return None


def build_ollama_request_targets(target_model: str, *, model_manager: Any) -> list[dict[str, Any]]:
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


def build_ollama_payload(request: OllamaStreamRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": request.request_targets[0]["model"],
        "messages": [
            {"role": "system", "content": request.system_prompt or "You are a helpful assistant."},
            {"role": "user", "content": request.prompt},
        ],
        "stream": True,
        # Keep local replies bounded — long tool JSON should not run forever
        "options": {
            "num_predict": 1024 if request.json_mode else 2048,
            "temperature": 0.2 if request.json_mode else 0.5,
            # Large context: operator/agent system prompts run several thousand tokens
            # and overflow Ollama's default 4096 window, truncating the reply to empty.
            "num_ctx": 16384,
        },
    }
    if request.json_mode:
        payload["format"] = "json"
    if request.think_value is not None:
        payload["think"] = request.think_value
    # Always disable deep thinking for tool JSON — it stalls chat UX
    if request.json_mode and request.think_value is None:
        payload["think"] = False
    return payload


async def stream_ollama_response(
    *,
    request: OllamaStreamRequest,
    purpose: str,
    timeout_seconds: float,
    max_attempts: int,
    usage_logger: UsageLogger,
    get_configured_base_url: Callable[[], str],
    set_configured_base_url: Callable[[str], None],
    is_connect_error: ConnectErrorPredicate,
) -> AsyncGenerator[str, None]:
    payload = build_ollama_payload(request)
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    started_at = time.monotonic()
    last_error: Exception | None = None

    for base_index, request_target in enumerate(request.request_targets):
        base_url = request_target["base_url"]
        headers = dict(request_target["headers"])
        payload["model"] = request_target["model"]
        for attempt in range(max_attempts):
            try:
                async with (
                    aiohttp.ClientSession(timeout=timeout) as session,
                    session.post(f"{base_url}/api/chat", headers=headers, json=payload) as response,
                ):
                    if response.status == 200:
                        output = ""
                        async for content in _iter_ollama_content(response.content):
                            output += content
                            yield content

                        if request_target["kind"] == "local" and base_url != get_configured_base_url():
                            logger.warning(
                                f"Ollama chat fallback: configured={get_configured_base_url() or 'unset'} -> using {base_url}"
                            )
                        if request_target["kind"] == "local":
                            set_configured_base_url(base_url)
                            try:
                                from app.core.ollama_config import remember_ollama_url

                                remember_ollama_url(base_url)
                            except Exception:
                                pass
                        _log_usage(
                            usage_logger,
                            payload=payload,
                            request=request,
                            output=output,
                            started_at=started_at,
                            purpose=purpose,
                            request_target=request_target,
                        )
                        return

                    error_text = redacted_log_text(await response.text())
                    is_retryable = response.status == 429 or (500 <= response.status < 600)
                    if is_retryable and attempt < max_attempts - 1:
                        yield "[Повтор попытки...]"
                        await asyncio.sleep(RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)])
                        continue

                    _log_usage(
                        usage_logger,
                        payload=payload,
                        request=request,
                        output="",
                        started_at=started_at,
                        status="error",
                        purpose=purpose,
                        request_target=request_target,
                    )
                    if request_target["kind"] == "cloud":
                        yield f"Error from Ollama Cloud API: {response.status} - {error_text}"
                    else:
                        yield f"Error from Ollama API: {response.status} - {error_text}"
                    return
            except Exception as exc:
                last_error = exc
                has_next_base_url = base_index < len(request.request_targets) - 1
                if request_target["kind"] == "local" and is_connect_error(exc) and has_next_base_url:
                    logger.warning(f"Ollama connect failed via {base_url}: {exc}. Trying next base URL.")
                    break

                if _is_retryable_error(exc) and attempt < max_attempts - 1:
                    yield "[Повтор попытки...]"
                    await asyncio.sleep(RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)])
                    continue

                logger.error(f"Ollama Error: {exc}")
                _log_usage(
                    usage_logger,
                    payload=payload,
                    request=request,
                    output="",
                    started_at=started_at,
                    status="timeout" if _is_timeout_error(exc) else "error",
                    purpose=purpose,
                    request_target=request_target,
                )
                if _is_timeout_error(exc):
                    yield "Error: Timeout (Ollama stream)."
                elif request_target["kind"] == "local" and is_connect_error(exc) and len(request.request_targets) > 1:
                    yield (
                        "Error: Ollama недоступен по localhost из backend runtime. "
                        "Проверь, что Ollama слушает Windows host не только на 127.0.0.1."
                    )
                elif request_target["kind"] == "cloud":
                    yield f"Error calling Ollama Cloud: {str(exc)}"
                else:
                    yield f"Error calling Ollama: {str(exc)}"
                return

    if last_error is not None:
        logger.error(f"Ollama Error after trying all base URLs: {last_error}")
        usage_logger(
            "ollama",
            payload["model"],
            request.prompt,
            "",
            int((time.monotonic() - started_at) * 1000),
            "timeout" if _is_timeout_error(last_error) else "error",
            purpose=purpose,
            metadata={
                "request_targets": [target["base_url"] for target in request.request_targets],
                "think": payload.get("think"),
            },
        )
        if _is_timeout_error(last_error):
            yield "Error: Timeout (Ollama stream)."
        elif any(target["kind"] == "cloud" for target in request.request_targets):
            yield "Error: Ollama Cloud не ответил по настроенному API endpoint."
        else:
            yield (
                "Error: Ollama не доступен из backend. "
                "Сервис запущен, но runtime не может достучаться до него по всем известным адресам."
            )
        return


async def _iter_ollama_content(byte_stream: Any) -> AsyncGenerator[str, None]:
    """Yield assistant content strings. Thinking fragments are prefixed with a sentinel."""
    pending = ""
    async for chunk_bytes in byte_stream.iter_any():
        pending += chunk_bytes.decode("utf-8")
        stop_stream = False
        while "\n" in pending:
            raw_line, pending = pending.split("\n", 1)
            content, thinking, done = _extract_ollama_content_line(raw_line)
            # Use printable sentinel — never NUL (\x00), Postgres rejects it in JSON logs
            if thinking:
                yield f"«THINK»{thinking}"
            if content:
                yield content
            if done:
                stop_stream = True
                break
        if stop_stream:
            break

    if pending.strip():
        content, thinking, _done = _extract_ollama_content_line(pending, trailing=True)
        if thinking:
            yield f"«THINK»{thinking}"
        if content:
            yield content


def _extract_ollama_content_line(raw_line: str, *, trailing: bool = False) -> tuple[str, str, bool]:
    line = raw_line.strip()
    if not line:
        return "", "", False
    try:
        chunk_json = json.loads(line)
    except json.JSONDecodeError:
        if trailing:
            logger.debug("Ollama: trailing stream fragment ignored: {}", redacted_log_text(line, limit=160))
        else:
            logger.debug(f"Ollama: failed to parse stream line: {line[:160]}")
        return "", "", False
    msg = chunk_json.get("message") or {}
    content = msg.get("content") or ""
    thinking = msg.get("thinking") or ""
    # Some builds put partial think on the root
    if not thinking and isinstance(chunk_json.get("thinking"), str):
        thinking = chunk_json.get("thinking") or ""
    return content, thinking, bool(chunk_json.get("done"))


def _log_usage(
    usage_logger: UsageLogger,
    *,
    payload: dict[str, Any],
    request: OllamaStreamRequest,
    output: str,
    started_at: float,
    purpose: str,
    request_target: dict[str, Any],
    status: str = "success",
) -> None:
    usage_logger(
        "ollama",
        payload["model"],
        request.prompt,
        output,
        int((time.monotonic() - started_at) * 1000),
        status,
        purpose=purpose,
        metadata={
            "base_url": request_target["base_url"],
            "request_targets": [target["base_url"] for target in request.request_targets],
            "source": request_target["kind"],
            "think": payload.get("think"),
        },
    )
