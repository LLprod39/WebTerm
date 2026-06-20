from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.core.llm_runtime import RETRY_BACKOFF, _is_retryable_error

UsageLogger = Callable[..., None]


@dataclass(frozen=True)
class GeminiStreamRequest:
    target_model: str
    prompt: str
    system_prompt: str | None
    json_mode: bool = False


def build_gemini_stream_kwargs(request: GeminiStreamRequest) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": request.target_model,
        "contents": request.prompt,
    }
    config: dict[str, Any] = {}
    if request.system_prompt:
        config["system_instruction"] = request.system_prompt
    if request.json_mode:
        config["response_mime_type"] = "application/json"
    if config:
        kwargs["config"] = config
    return kwargs


async def stream_gemini_response(
    *,
    client: Any,
    request: GeminiStreamRequest,
    purpose: str,
    timeout_seconds: float,
    max_attempts: int,
    usage_logger: UsageLogger,
) -> AsyncGenerator[str, None]:
    started_at = time.monotonic()

    for attempt in range(max_attempts):
        try:
            chunks = await asyncio.wait_for(
                _consume_gemini_stream(client, request),
                timeout=timeout_seconds,
            )
            output = ""
            for chunk in chunks:
                output += chunk
                yield chunk
            _log_usage(
                usage_logger,
                request=request,
                output=output,
                started_at=started_at,
                purpose=purpose,
            )
            return
        except asyncio.TimeoutError:
            logger.error("Gemini stream timeout")
            _log_usage(
                usage_logger,
                request=request,
                output="",
                started_at=started_at,
                status="timeout",
                purpose=purpose,
            )
            yield "Error: Timeout (Gemini stream)."
            return
        except Exception as exc:
            if _is_retryable_error(exc) and attempt < max_attempts - 1:
                yield "[Повтор попытки...]"
                await asyncio.sleep(RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)])
                continue

            logger.error(f"Gemini Error: {exc}")
            _log_usage(
                usage_logger,
                request=request,
                output="",
                started_at=started_at,
                status="error",
                purpose=purpose,
            )
            yield f"Error calling Gemini: {str(exc)}"
            return


async def _consume_gemini_stream(client: Any, request: GeminiStreamRequest) -> list[str]:
    output: list[str] = []
    stream = await client.aio.models.generate_content_stream(**build_gemini_stream_kwargs(request))
    async for chunk in stream:
        text = getattr(chunk, "text", None)
        if text:
            output.append(text)
    return output


def _log_usage(
    usage_logger: UsageLogger,
    *,
    request: GeminiStreamRequest,
    output: str,
    started_at: float,
    purpose: str,
    status: str = "success",
) -> None:
    usage_logger(
        "gemini",
        request.target_model,
        request.prompt,
        output,
        int((time.monotonic() - started_at) * 1000),
        status,
        purpose=purpose,
    )
