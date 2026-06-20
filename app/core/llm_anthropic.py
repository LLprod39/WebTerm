from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.core.llm_runtime import RETRY_BACKOFF, _is_retryable_error, _is_timeout_error

UsageLogger = Callable[..., None]


@dataclass(frozen=True)
class ClaudeStreamRequest:
    target_model: str
    prompt: str
    system_prompt: str | None
    max_tokens: int = 8192


def build_claude_stream_kwargs(request: ClaudeStreamRequest) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": request.target_model,
        "max_tokens": request.max_tokens,
        "messages": [{"role": "user", "content": request.prompt}],
    }
    if request.system_prompt:
        kwargs["system"] = [
            {
                "type": "text",
                "text": request.system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]
    return kwargs


async def stream_claude_response(
    *,
    client: Any,
    request: ClaudeStreamRequest,
    purpose: str,
    timeout_seconds: float,
    max_attempts: int,
    usage_logger: UsageLogger,
) -> AsyncGenerator[str, None]:
    started_at = time.monotonic()

    for attempt in range(max_attempts):
        try:
            output = ""
            async with asyncio.timeout(timeout_seconds):
                async with client.messages.stream(**build_claude_stream_kwargs(request)) as stream:
                    async for text in stream.text_stream:
                        output += text
                        yield text
            _log_usage(
                usage_logger,
                request=request,
                output=output,
                started_at=started_at,
                purpose=purpose,
            )
            return
        except Exception as exc:
            if _is_retryable_error(exc) and attempt < max_attempts - 1:
                yield "[Повтор попытки...]"
                await asyncio.sleep(RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)])
                continue

            logger.error(f"Claude Error: {exc}")
            _log_usage(
                usage_logger,
                request=request,
                output="",
                started_at=started_at,
                status="timeout" if _is_timeout_error(exc) else "error",
                purpose=purpose,
            )
            if _is_timeout_error(exc):
                yield "Error: Timeout (Claude stream)."
            else:
                yield f"Error calling Claude: {str(exc)}"
            return


def _log_usage(
    usage_logger: UsageLogger,
    *,
    request: ClaudeStreamRequest,
    output: str,
    started_at: float,
    purpose: str,
    status: str = "success",
) -> None:
    usage_logger(
        "claude",
        request.target_model,
        request.prompt,
        output,
        int((time.monotonic() - started_at) * 1000),
        status,
        purpose=purpose,
    )
