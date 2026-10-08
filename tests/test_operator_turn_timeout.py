"""Operator turn timeout resolution and failed-turn progress."""

from __future__ import annotations

from core_ui.services.operator_turn_runtime import (
    OPERATOR_TURN_TIMEOUT_LOCAL_SECONDS,
    OPERATOR_TURN_TIMEOUT_SECONDS,
    _summarize_failed_turn_progress,
    resolve_operator_turn_timeout_seconds,
)


def test_resolve_timeout_local_ollama_default():
    assert (
        resolve_operator_turn_timeout_seconds(provider_binding={"provider": "ollama"})
        == OPERATOR_TURN_TIMEOUT_LOCAL_SECONDS
    )


def test_resolve_timeout_cloud_default():
    assert (
        resolve_operator_turn_timeout_seconds(provider_binding={"provider": "openai"})
        == OPERATOR_TURN_TIMEOUT_SECONDS
    )


def test_resolve_timeout_env_override(monkeypatch):
    monkeypatch.setenv("OPERATOR_TURN_TIMEOUT_SECONDS", "240")
    assert resolve_operator_turn_timeout_seconds(provider_binding={"provider": "openai"}) == 240.0


def test_summarize_failed_turn_progress_includes_tools():
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "name": "operator_resolve_server", "input": {"q": "prom-01"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "content": '{"ok": true, "server_id": 17}'},
            ],
        },
    ]
    text = _summarize_failed_turn_progress(messages)
    assert "operator.resolve_server" in text
    assert "prom-01" in text
    assert "продолжи" in text.casefold()
