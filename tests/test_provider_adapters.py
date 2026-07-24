from __future__ import annotations

from types import SimpleNamespace

from app.core.provider_adapters import DEFAULT_PROVIDER_ORDER, build_provider_adapters


def test_provider_adapters_keep_api_key_aliases_and_status_details():
    adapters = build_provider_adapters()
    config = SimpleNamespace(openai_enabled=True)

    def key_lookup(provider: str, *env_names: str) -> str:
        assert env_names
        return {"openai": "codex-key"}.get(provider, "")

    def binary_lookup(_provider: str) -> bool:
        return False

    openai = adapters["openai"]
    assert openai.is_enabled(config, binary_lookup) is True
    assert openai.is_configured(config, key_lookup, binary_lookup) is True
    assert openai.status_details(config, key_lookup, binary_lookup) == {
        "api_key_set": True,
        "api_key_name": "OPENAI_API_KEY/CODEX_API_KEY",
    }


def test_provider_adapters_keep_cli_binary_policy():
    adapters = build_provider_adapters()
    config = SimpleNamespace()

    def key_lookup(provider: str, *env_names: str) -> str:
        return "anthropic-key" if provider == "claude" and env_names == ("ANTHROPIC_API_KEY",) else ""

    assert adapters["claude"].is_enabled(config, lambda _provider: False) is False
    assert adapters["claude"].is_configured(config, key_lookup, lambda _provider: False) is False
    assert adapters["claude"].is_enabled(config, lambda _provider: True) is True
    assert adapters["claude"].is_configured(config, key_lookup, lambda _provider: True) is True


def test_provider_fallback_order_is_explicit_policy():
    assert DEFAULT_PROVIDER_ORDER == ("openai", "grok", "gemini", "ollama", "ralph", "cursor", "claude")
