from __future__ import annotations

from types import SimpleNamespace

from app.core.llm_provider_resolution import RuntimeProviderKeys, resolve_stream_provider


class _ModelManager:
    def __init__(self, provider: str, model: str, config: SimpleNamespace):
        self._provider = provider
        self._model = model
        self.config = config

    def resolve_purpose(self, purpose: str) -> tuple[str, str]:
        assert purpose == "agent"
        return self._provider, self._model


def test_resolve_stream_provider_uses_preferred_key_even_when_disabled():
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

    provider, model = resolve_stream_provider(
        requested_provider="auto",
        requested_specific_model=None,
        purpose="agent",
        model_manager=manager,
        keys=keys,
        ollama_base_url="http://127.0.0.1:11434",
    )

    assert provider == "openai"
    assert model == "gpt-test"


def test_resolve_stream_provider_falls_back_to_first_enabled_provider():
    warnings: list[str] = []
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

    provider, model = resolve_stream_provider(
        requested_provider="",
        requested_specific_model="manual-model",
        purpose="agent",
        model_manager=manager,
        keys=keys,
        ollama_base_url="http://127.0.0.1:11434",
        warn=warnings.append,
    )

    assert provider == "openai"
    assert model == "manual-model"
    assert warnings == ["[agent] provider 'claude' is disabled/unconfigured, falling back to 'openai'"]


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
