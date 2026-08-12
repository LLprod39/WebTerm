from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ai_runtime import (
    ExecutionMode,
    LLMExecutionContext,
    ProviderBinding,
    ProviderRouteUnavailableError,
    ProviderRuntimeError,
)
from app.core.llm_provider_resolution import (
    RuntimeProviderKeys,
    apply_execution_context_binding,
    resolve_stream_provider,
)


class _ModelManager:
    def __init__(self, provider: str, model: str, config: SimpleNamespace):
        self._provider = provider
        self._model = model
        self.config = config

    def resolve_purpose(self, purpose: str) -> tuple[str, str]:
        assert purpose == "agent"
        return self._provider, self._model


def test_resolve_stream_provider_rejects_preferred_provider_when_disabled():
    manager = _ModelManager(
        "openai",
        "gpt-test",
        SimpleNamespace(
            openai_enabled=False,
            claude_enabled=False,
            grok_enabled=False,
            gemini_enabled=False,
            ollama_enabled=False,
        ),
    )
    keys = RuntimeProviderKeys(openai="openai-key")

    with pytest.raises(ProviderRouteUnavailableError):
        resolve_stream_provider(
            requested_provider="auto",
            requested_specific_model=None,
            purpose="agent",
            model_manager=manager,
            keys=keys,
            ollama_base_url="http://127.0.0.1:11434",
        )


def test_resolve_stream_provider_does_not_fall_back_to_another_provider():
    manager = _ModelManager(
        "claude",
        "claude-test",
        SimpleNamespace(
            openai_enabled=True,
            claude_enabled=False,
            grok_enabled=True,
            gemini_enabled=False,
            ollama_enabled=True,
        ),
    )
    keys = RuntimeProviderKeys(openai="openai-key", grok="grok-key")

    with pytest.raises(ProviderRouteUnavailableError) as exc_info:
        resolve_stream_provider(
            requested_provider="",
            requested_specific_model="manual-model",
            purpose="agent",
            model_manager=manager,
            keys=keys,
            ollama_base_url="http://127.0.0.1:11434",
        )

    assert exc_info.value.details["target_id"] == "claude_api"


def test_resolve_stream_provider_returns_requested_provider_unchanged():
    manager = _ModelManager("openai", "gpt-test", SimpleNamespace())

    provider, model = resolve_stream_provider(
        requested_provider="gemini",
        requested_specific_model="gemini-test",
        purpose="agent",
        model_manager=manager,
        keys=RuntimeProviderKeys(),
        ollama_base_url="",
    )

    assert provider == "gemini"
    assert model == "gemini-test"


def test_resolve_stream_provider_accepts_canonical_api_target():
    manager = _ModelManager("openai", "gpt-test", SimpleNamespace())
    provider, model = resolve_stream_provider(
        requested_provider="openai_api",
        requested_specific_model="gpt-explicit",
        purpose="agent",
        model_manager=manager,
        keys=RuntimeProviderKeys(),
        ollama_base_url="",
    )
    assert (provider, model) == ("openai", "gpt-explicit")


def test_subscription_target_never_crosses_into_api_transport():
    manager = _ModelManager("openai", "gpt-test", SimpleNamespace())
    with pytest.raises(ProviderRuntimeError) as exc_info:
        resolve_stream_provider(
            requested_provider="codex_subscription",
            requested_specific_model=None,
            purpose="agent",
            model_manager=manager,
            keys=RuntimeProviderKeys(openai="api-key"),
            ollama_base_url="",
        )
    assert exc_info.value.code == "provider_transport_unavailable"


def test_execution_context_binding_overrides_legacy_model_arguments():
    context = LLMExecutionContext(
        actor_user_id=1,
        project_id=None,
        purpose="assistant",
        source_kind="chat_session",
        source_id="4",
        mode=ExecutionMode.INTERACTIVE,
        binding=ProviderBinding("grok_subscription", connection_id=7, model_id="grok-code-fast"),
    )
    provider, model = apply_execution_context_binding(
        execution_context=context,
        requested_provider="openai",
        requested_specific_model="gpt-old",
    )
    assert (provider, model) == ("grok_subscription", "grok-code-fast")
