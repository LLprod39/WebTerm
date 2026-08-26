from __future__ import annotations

import pytest

from app.ai_runtime import (
    ExecutionMode,
    LLMExecutionContext,
    ProviderBinding,
    ProviderEventType,
    ProviderEventV1,
    ProviderRouteSource,
    ProviderRouteUnavailableError,
    canonicalize_target_id,
    legacy_runtime_provider_id,
    resolve_provider_route,
)


def test_legacy_provider_ids_keep_api_meaning() -> None:
    assert canonicalize_target_id("openai") == "openai_api"
    assert canonicalize_target_id("grok") == "grok_api"
    assert canonicalize_target_id("grok_build") == "grok_subscription"
    assert legacy_runtime_provider_id("grok") == "grok"
    assert legacy_runtime_provider_id("grok_subscription") is None


def test_provider_binding_rejects_connection_and_pool_together() -> None:
    with pytest.raises(ValueError, match="both connection_id and pool_id"):
        ProviderBinding(target_id="codex_subscription", connection_id=1, pool_id=2)


def test_execution_context_can_be_resolved_without_mutating_original() -> None:
    context = LLMExecutionContext(
        actor_user_id=7,
        project_id=3,
        purpose="assistant",
        source_kind="chat_session",
        source_id="11",
        mode=ExecutionMode.INTERACTIVE,
        idempotency_key="turn-12",
    )
    binding = ProviderBinding(target_id="codex", connection_id=5, model_id="gpt-5.4")

    resolved = context.with_binding(binding)

    assert context.binding is None
    assert resolved.binding == binding
    assert resolved.binding.target_id == "codex_subscription"


def test_provider_binding_preserves_model_and_reasoning_selection() -> None:
    binding = ProviderBinding.from_dict(
        {
            "target_id": "codex_subscription",
            "connection_id": 5,
            "model_id": " gpt-5.6-terra ",
            "reasoning_effort": " HIGH ",
        }
    )

    assert binding.model_id == "gpt-5.6-terra"
    assert binding.reasoning_effort == "high"
    assert binding.to_dict()["reasoning_effort"] == "high"


def test_provider_event_v1_has_stable_wire_shape() -> None:
    event = ProviderEventV1(ProviderEventType.TEXT_DELTA, {"text": "hello"})
    assert event.to_dict() == {
        "version": 1,
        "type": "text_delta",
        "payload": {"text": "hello"},
    }


def test_route_precedence_is_deterministic() -> None:
    route = resolve_provider_route(
        explicit=ProviderBinding("grok_subscription", connection_id=4),
        stored=ProviderBinding("codex_subscription", connection_id=3),
        user_default=ProviderBinding("openai_api"),
        workspace_default=ProviderBinding("ollama_local"),
    )

    assert route.source is ProviderRouteSource.EXPLICIT
    assert route.binding.connection_id == 4


def test_denied_selected_route_does_not_fall_back() -> None:
    with pytest.raises(ProviderRouteUnavailableError) as exc_info:
        resolve_provider_route(
            explicit=ProviderBinding("codex_subscription", connection_id=9),
            user_default=ProviderBinding("openai_api"),
            can_use=lambda binding: (binding.connection_id != 9, "connection grant missing"),
        )

    assert exc_info.value.code == "provider_route_unavailable"
    assert exc_info.value.details["source"] == "explicit"
    assert exc_info.value.details["reason"] == "connection grant missing"


def test_missing_route_returns_typed_error() -> None:
    with pytest.raises(ProviderRouteUnavailableError) as exc_info:
        resolve_provider_route()
    assert exc_info.value.to_dict()["code"] == "provider_route_unavailable"
