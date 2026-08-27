"""Tool-calling stream orchestration for LLMProvider."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger

from app.ai_runtime import LLMExecutionContext
from app.core.llm_budget import BudgetExceededError, get_current_llm_budget_status
from app.core.llm_provider_resolution import (
    RuntimeProviderKeys,
    apply_execution_context_binding,
    resolve_stream_provider,
)
from app.core.llm_runtime import _is_ollama_connect_error, _provider_timeout_seconds
from app.core.llm_subscription_stream import is_subscription_execution, stream_subscription_tools
from app.core.llm_tools import (
    ollama_model_supports_tools,
    stream_anthropic_tools,
    stream_json_tools_fallback,
    stream_ollama_tools,
    stream_openai_tools,
)
from app.core.llm_usage import log_llm_usage as _log_llm_usage
from app.core.model_config import model_manager


def _json_safe_preview(value: Any, limit: int = 2000) -> str:
    try:
        import json as _json

        return _json.dumps(value, ensure_ascii=False, default=str)[:limit]
    except Exception:  # noqa: BLE001
        return str(value)[:limit]


async def stream_provider_chat_tools(
    provider: Any,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    *,
    model: str = "auto",
    specific_model: str | None = None,
    purpose: str = "orchestrator",
    system_prompt: str | None = None,
    execution_context: LLMExecutionContext | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Stream chat with native tool-calling (Anthropic → OpenAI → JSON fallback).

    Event shapes:
      {"type":"text_delta","text":str}
      {"type":"tool_call","id":str,"name":str,"arguments":dict}
      {"type":"done","usage":dict,"stop_reason":str}
      {"type":"error","code":str,"message":str}
    """
    model, specific_model = apply_execution_context_binding(
        execution_context=execution_context,
        requested_provider=model,
        requested_specific_model=specific_model,
    )

    if is_subscription_execution(execution_context):
        async for event in stream_subscription_tools(
            context=execution_context,
            messages=messages,
            tools=tools,
            system_prompt=system_prompt,
        ):
            yield event
        return

    await provider._load_managed_api_keys()

    model, specific_model = resolve_stream_provider(
        requested_provider=model,
        requested_specific_model=specific_model,
        purpose=purpose,
        model_manager=model_manager,
        keys=RuntimeProviderKeys.from_llm_provider(provider),
        ollama_base_url=provider._get_ollama_base_url(),
        warn=logger.warning,
    )
    logger.info(f"[{purpose}/tools] using provider: {model}, model: {specific_model or '(default)'}")

    try:
        _budget = get_current_llm_budget_status()
        if _budget.exceeded:
            raise BudgetExceededError(
                f"Daily LLM token budget exceeded: used {_budget.used_tokens} "
                f"of {_budget.limit_tokens} tokens in the last 24 h."
            )
    except BudgetExceededError:
        yield {"type": "error", "message": "Daily LLM token budget exceeded"}
        return
    except Exception as _budget_err:  # noqa: BLE001
        logger.debug("budget pre-flight skipped: %s", _budget_err)

    prompt_for_usage = ""
    if messages:
        last = messages[-1]
        content = last.get("content")
        prompt_for_usage = content[:2000] if isinstance(content, str) else _json_safe_preview(messages)[:2000]

    if model == "claude":
        if not model_manager.config.claude_enabled:
            yield {"type": "error", "message": "Claude API disabled"}
            return
        client = provider._get_anthropic_client()
        if not client:
            yield {"type": "error", "message": "Anthropic API Key not configured"}
            return
        target_model = specific_model or model_manager.get_chat_model("claude")
        async for event in stream_anthropic_tools(
            client=client,
            model=target_model,
            messages=messages,
            tools=tools,
            system_prompt=system_prompt,
            purpose=purpose,
            usage_logger=_log_llm_usage,
            prompt_for_usage=prompt_for_usage,
        ):
            yield event
        return

    if model in {"openai", "grok"}:
        if model == "openai":
            if not provider.openai_api_key:
                yield {"type": "error", "message": "OpenAI API Key not configured"}
                return
            api_key = provider.openai_api_key
            api_url = "https://api.openai.com/v1/chat/completions"
            target_model = specific_model or model_manager.get_chat_model("openai")
            provider = "openai"
        else:
            if not provider.grok_api_key:
                yield {"type": "error", "message": "Grok API Key not configured"}
                return
            api_key = provider.grok_api_key
            api_url = "https://api.x.ai/v1/chat/completions"
            target_model = specific_model or model_manager.get_chat_model("grok")
            provider = "grok"
        async for event in stream_openai_tools(
            api_url=api_url,
            api_key=api_key,
            model=target_model,
            messages=messages,
            tools=tools,
            system_prompt=system_prompt,
            purpose=purpose,
            timeout_seconds=float(_provider_timeout_seconds(provider)),
            usage_logger=_log_llm_usage,
            prompt_for_usage=prompt_for_usage,
            provider=provider,
            display_name="OpenAI" if provider == "openai" else "Grok",
            trust_env=provider in {"openai", "grok"},
        ):
            yield event
        return

    # Ollama: prefer native tool-calling when the model exposes the "tools"
    # capability; only fall back to the brittle JSON-in-prompt path otherwise.
    if model == "ollama" and model_manager.config.ollama_enabled:
        target_model = specific_model or model_manager.get_chat_model("ollama")
        request_targets = provider._build_ollama_request_targets(target_model) if target_model else []
        if request_targets:
            first = request_targets[0]
            supports_tools = await ollama_model_supports_tools(first["base_url"], first["model"], first["headers"])
            if supports_tools:
                async for event in stream_ollama_tools(
                    request_targets=request_targets,
                    messages=messages,
                    tools=tools,
                    system_prompt=system_prompt,
                    think_value=provider._get_ollama_think_value(),
                    timeout_seconds=float(_provider_timeout_seconds("ollama")),
                    purpose=purpose,
                    usage_logger=_log_llm_usage,
                    prompt_for_usage=prompt_for_usage,
                    set_configured_base_url=lambda base_url: setattr(model_manager.config, "ollama_base_url", base_url),
                    is_connect_error=_is_ollama_connect_error,
                ):
                    yield event
                return

    # Gemini / Ollama-without-tools / others: JSON tool-call fallback
    async def _text_stream(*, prompt: str, system_prompt: str | None, purpose: str, json_mode: bool):
        async for chunk in provider.stream_chat(
            prompt=prompt,
            model=model,
            specific_model=specific_model,
            purpose=purpose,
            system_prompt=system_prompt,
            json_mode=json_mode,
            execution_context=execution_context,
        ):
            yield chunk

    async for event in stream_json_tools_fallback(
        stream_text=_text_stream,
        messages=messages,
        tools=tools,
        system_prompt=system_prompt,
        purpose=purpose,
    ):
        yield event
