from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from typing import Any

import aiohttp
from loguru import logger

from app.core.llm_http_errors import provider_http_error
from app.core.llm_runtime import (
    RETRY_BACKOFF,
    _is_retryable_error,
    _is_timeout_error,
)
from app.core.redacted_logging import redacted_log_text

UsageLogger = Callable[..., None]


@dataclass(frozen=True)
class OpenAICompatibleRequest:
    endpoint_name: str
    api_url: str
    payload: dict[str, Any]


def build_chat_completions_request(
    *,
    api_url: str,
    target_model: str,
    prompt: str,
    system_prompt: str | None,
    json_mode: bool,
    temperature: float | None = None,
) -> OpenAICompatibleRequest:
    payload: dict[str, Any] = {
        "model": target_model,
        "messages": [
            {"role": "system", "content": system_prompt or "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        "stream": True,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    return OpenAICompatibleRequest(endpoint_name="chat", api_url=api_url, payload=payload)


def build_openai_request(
    *,
    target_model: str,
    prompt: str,
    system_prompt: str | None,
    json_mode: bool,
    reasoning_effort: str,
) -> OpenAICompatibleRequest:
    model_lower = target_model.lower()
    use_responses_api = model_lower.startswith("gpt-5") or (
        "codex" in model_lower and any(model_lower.startswith(p) for p in ("gpt-4", "o1", "o3", "o4"))
    )
    legacy_completions = (
        not use_responses_api
        and any(kw in model_lower for kw in ("instruct", "davinci", "babbage", "curie", "ada"))
        and not model_lower.startswith("gpt-4")
    )

    if use_responses_api:
        payload: dict[str, Any] = {
            "model": target_model,
            "instructions": system_prompt or "You are a helpful assistant.",
            "input": prompt,
            "stream": True,
        }
        if json_mode:
            payload["text"] = {"format": {"type": "json_object"}}
            if "json" not in prompt.lower():
                payload["input"] = f"{prompt}\n\nReturn the answer as a valid JSON object."
        if reasoning_effort in {"none", "low", "medium", "high"}:
            payload["reasoning"] = {"effort": reasoning_effort}
            logger.debug(f"OpenAI Responses: reasoning.effort={reasoning_effort}")
        return OpenAICompatibleRequest(
            endpoint_name="responses",
            api_url="https://api.openai.com/v1/responses",
            payload=payload,
        )

    if legacy_completions:
        return OpenAICompatibleRequest(
            endpoint_name="completions",
            api_url="https://api.openai.com/v1/completions",
            payload={
                "model": target_model,
                "prompt": f"You are a helpful assistant.\n\n{prompt}",
                "stream": True,
                "max_tokens": 2048,
            },
        )

    return build_chat_completions_request(
        api_url="https://api.openai.com/v1/chat/completions",
        target_model=target_model,
        prompt=prompt,
        system_prompt=system_prompt,
        json_mode=json_mode,
    )


async def stream_openai_compatible_response(
    *,
    provider: str,
    display_name: str,
    request: OpenAICompatibleRequest,
    headers: dict[str, str],
    target_model: str,
    prompt: str,
    purpose: str,
    timeout_seconds: float,
    max_attempts: int,
    usage_logger: UsageLogger,
    log_metadata: dict[str, Any] | None = None,
    trust_env: bool = False,
) -> AsyncGenerator[str, None]:
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    started_at = time.monotonic()

    for attempt in range(max_attempts):
        logger.debug(f"{display_name}: attempt {attempt + 1}/{max_attempts} -> POST {request.api_url}")
        try:
            async with (
                aiohttp.ClientSession(timeout=timeout, trust_env=trust_env) as session,
                session.post(request.api_url, headers=headers, json=request.payload) as response,
            ):
                logger.debug(f"{display_name}: HTTP status={response.status}")
                if response.status == 200:
                    output = ""
                    chunks = 0
                    async for content in _iter_openai_compatible_content(
                        response.content,
                        endpoint_name=request.endpoint_name,
                        display_name=display_name,
                    ):
                        output += content
                        chunks += 1
                        yield content

                    logger.debug(f"{display_name}: stream done, chunks={chunks}, chars={len(output)}")
                    _log_usage(
                        usage_logger,
                        provider=provider,
                        target_model=target_model,
                        prompt=prompt,
                        output=output,
                        started_at=started_at,
                        purpose=purpose,
                        metadata=log_metadata,
                    )
                    return

                provider_error = provider_http_error(
                    provider=provider,
                    display_name=display_name,
                    status=response.status,
                    body=await response.text(),
                )
                is_retryable = provider_error.retryable
                logger.error(
                    "{}: HTTP error {}, code={}, retryable={}",
                    display_name,
                    response.status,
                    provider_error.code,
                    is_retryable,
                )
                if is_retryable and attempt < max_attempts - 1:
                    yield "[Повтор попытки...]"
                    await asyncio.sleep(RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)])
                    continue

                _log_usage(
                    usage_logger,
                    provider=provider,
                    target_model=target_model,
                    prompt=prompt,
                    output="",
                    started_at=started_at,
                    status="error",
                    purpose=purpose,
                    metadata=log_metadata,
                )
                yield f"Error from {display_name} API: {provider_error.message}"
                return
        except Exception as exc:
            err_retryable = _is_retryable_error(exc) and attempt < max_attempts - 1
            logger.error(
                "{}: exception attempt={}/{} type={} retryable={}",
                display_name,
                attempt + 1,
                max_attempts,
                type(exc).__name__,
                err_retryable,
            )
            if err_retryable:
                yield "[Повтор попытки...]"
                await asyncio.sleep(RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)])
                continue

            _log_usage(
                usage_logger,
                provider=provider,
                target_model=target_model,
                prompt=prompt,
                output="",
                started_at=started_at,
                status="timeout" if _is_timeout_error(exc) else "error",
                purpose=purpose,
                metadata=log_metadata,
            )
            if _is_timeout_error(exc):
                yield f"Error: Timeout ({display_name} stream)."
            else:
                yield f"Error calling {display_name}: Provider transport is temporarily unavailable. Try again later."
            return


async def _iter_openai_compatible_content(
    byte_stream: Any,
    *,
    endpoint_name: str,
    display_name: str,
) -> AsyncGenerator[str, None]:
    async for line_bytes in byte_stream:
        line = line_bytes.decode("utf-8").strip()
        if not line or line.startswith("event:") or not line.startswith("data: "):
            continue
        chunk_str = line[6:]
        if chunk_str == "[DONE]":
            break
        try:
            chunk_json = json.loads(chunk_str)
        except json.JSONDecodeError as exc:
            logger.warning(
                "{}: stream JSON decode skipped: {} | raw={}",
                display_name,
                exc,
                redacted_log_text(chunk_str, limit=120),
            )
            continue

        content, done = _extract_content(chunk_json, endpoint_name=endpoint_name)
        if done:
            break
        if content:
            yield content


def _extract_content(chunk_json: dict[str, Any], *, endpoint_name: str) -> tuple[str, bool]:
    if endpoint_name == "responses":
        event_type = chunk_json.get("type", "")
        if event_type == "response.output_text.delta":
            return str(chunk_json.get("delta", "") or ""), False
        if event_type == "response.completed":
            return "", True
        return "", False
    if endpoint_name == "completions":
        return str(chunk_json.get("choices", [{}])[0].get("text", "") or ""), False
    return str(chunk_json.get("choices", [{}])[0].get("delta", {}).get("content", "") or ""), False


def _log_usage(
    usage_logger: UsageLogger,
    *,
    provider: str,
    target_model: str,
    prompt: str,
    output: str,
    started_at: float,
    status: str = "success",
    purpose: str,
    metadata: dict[str, Any] | None,
) -> None:
    usage_logger(
        provider,
        target_model,
        prompt,
        output,
        int((time.monotonic() - started_at) * 1000),
        status,
        purpose=purpose,
        metadata=metadata,
    )
