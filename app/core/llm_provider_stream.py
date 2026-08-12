"""Plain stream_chat orchestration for LLMProvider."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger

from app.ai_runtime import LLMExecutionContext, ProviderRuntimeError
from app.core.llm_anthropic import ClaudeStreamRequest, stream_claude_response
from app.core.llm_budget import BudgetExceededError, get_current_llm_budget_status
from app.core.llm_gemini import GeminiStreamRequest, stream_gemini_response
from app.core.llm_ollama import OllamaStreamRequest, stream_ollama_response
from app.core.llm_openai_compatible import (
    build_chat_completions_request,
    build_openai_request,
    stream_openai_compatible_response,
)
from app.core.llm_provider_resolution import (
    RuntimeProviderKeys,
    apply_execution_context_binding,
    resolve_stream_provider,
)
from app.core.llm_runtime import (
    _grok_reasoning_effort,
    _is_ollama_connect_error,
    _provider_timeout_seconds,
    _retry_attempts,
)
from app.core.llm_subscription_stream import is_subscription_execution, stream_subscription_text
from app.core.llm_usage import log_llm_usage as _log_llm_usage
from app.core.model_config import model_manager


async def stream_provider_chat(
    provider: Any,
    prompt: str,
    model: str = "auto",
    specific_model: str = None,
    purpose: str = "chat",
    system_prompt: str | None = None,
    json_mode: bool = False,
    execution_context: LLMExecutionContext | None = None,
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

    model, specific_model = apply_execution_context_binding(
        execution_context=execution_context,
        requested_provider=model,
        requested_specific_model=specific_model,
    )

    if is_subscription_execution(execution_context):
        async for chunk in stream_subscription_text(
            context=execution_context,
            prompt=prompt,
            system_prompt=system_prompt,
        ):
            yield chunk
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
    logger.info(f"[{purpose}] using provider: {model}, model: {specific_model or '(default)'}")
    # Prompts are intentionally never logged, even after redaction: pilot logs
    # may be retained for weeks and redaction cannot prove semantic privacy.
    logger.info(
        "Streaming chat provider={} model={} prompt_length={} system_prompt_present={}",
        model,
        specific_model or "(default)",
        len(prompt),
        bool(system_prompt),
    )

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
            raise ProviderRuntimeError("provider_disabled", "Gemini API is disabled")

        if not provider.gemini_client:
            raise ProviderRuntimeError("provider_auth_required", "Gemini API key is not configured")

        target_model = specific_model or model_manager.get_chat_model("gemini")
        logger.info(f"Using Gemini model: {target_model}")
        async for chunk in stream_gemini_response(
            client=provider.gemini_client,
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
            raise ProviderRuntimeError("provider_disabled", "Grok API is disabled")

        if not provider.grok_api_key:
            raise ProviderRuntimeError("provider_auth_required", "Grok API key is not configured")

        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {provider.grok_api_key}"}
        grok_model = specific_model or model_manager.get_chat_model("grok")
        request = build_chat_completions_request(
            api_url="https://api.x.ai/v1/chat/completions",
            target_model=grok_model,
            prompt=prompt,
            system_prompt=system_prompt,
            json_mode=json_mode,
            temperature=0.7,
        )
        reasoning_effort = _grok_reasoning_effort(grok_model, purpose=purpose)
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
            raise ProviderRuntimeError("provider_disabled", "Claude API is disabled")

        client = provider._get_anthropic_client()
        if not client:
            raise ProviderRuntimeError("provider_auth_required", "Anthropic API key is not configured")

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

    elif model == "openai":
        if not model_manager.config.openai_enabled:
            raise ProviderRuntimeError("provider_disabled", "OpenAI API is disabled")

        if not provider.openai_api_key:
            logger.error("OpenAI: API key not configured (OPENAI_API_KEY / CODEX_API_KEY not set)")
            raise ProviderRuntimeError("provider_auth_required", "OpenAI API key is not configured")

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
            "Authorization": f"Bearer {provider.openai_api_key}",
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
            raise ProviderRuntimeError("provider_disabled", "Ollama is disabled")

        target_model = specific_model or model_manager.get_chat_model("ollama")
        if not target_model:
            raise ProviderRuntimeError("provider_model_unconfigured", "Ollama model is not configured")

        request_targets = provider._build_ollama_request_targets(target_model)
        if not request_targets:
            if model_manager._is_ollama_cloud_model(target_model) or provider._get_ollama_runtime_mode() == "cloud":
                message = "Ollama Cloud credentials or cloud mode are not configured"
            else:
                message = "Ollama runtime is not configured"
            raise ProviderRuntimeError("provider_transport_unavailable", message)

        async for chunk in stream_ollama_response(
            request=OllamaStreamRequest(
                prompt=prompt,
                system_prompt=system_prompt,
                json_mode=json_mode,
                request_targets=request_targets,
                think_value=provider._get_ollama_think_value(),
            ),
            purpose=purpose,
            timeout_seconds=float(_provider_timeout_seconds("ollama")),
            max_attempts=_retry_attempts(),
            usage_logger=_log_llm_usage,
            get_configured_base_url=lambda: model_manager.config.ollama_base_url,
            set_configured_base_url=lambda base_url: setattr(model_manager.config, "ollama_base_url", base_url),
            is_connect_error=_is_ollama_connect_error,
        ):
            # Keep «THINK» markers in the stream. Consumers (operator JSON tools path)
            # convert them to thinking_delta for the UI; plain chat callers may ignore.
            yield chunk
        return

    else:
        raise ProviderRuntimeError("provider_target_unknown", f"Unknown model target: {model}")
