"""Tests for auxiliary/utility model roles and settings wiring."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from django.contrib.auth.models import User

from app.core import aux_model_roles as roles
from app.core.model_config import ModelConfig, model_manager


@pytest.fixture
def aux_config(monkeypatch):
    cfg = ModelConfig(
        aux_llm_enabled=True,
        aux_llm_provider="openai_compatible",
        aux_llm_model="local-model",
        aux_llm_base_url="http://127.0.0.1:1234",
        aux_llm_timeout_seconds=5,
        aux_role_verifier_enabled=True,
        aux_role_intent_enabled=True,
        aux_role_summarizer_enabled=True,
        aux_role_safety_enabled=True,
    )
    monkeypatch.setattr(roles, "_config", lambda: cfg)
    return cfg


def test_aux_is_ready_requires_provider_model_and_base(aux_config):
    assert roles.aux_is_ready(aux_config) is True
    aux_config.aux_llm_model = ""
    assert roles.aux_is_ready(aux_config) is False


def test_heuristic_intent_chitchat_and_host():
    hi = roles.heuristic_intent("Привет")
    assert hi.kind == "chitchat"
    assert hi.needs_ssh is False
    host = roles.heuristic_intent("глянь что с @grafana-01")
    assert host.needs_ssh is True


@pytest.mark.asyncio
async def test_classify_intent_falls_back_on_json_error(aux_config, monkeypatch):
    async def boom(**kwargs):
        return {"not": "valid for our schema"}, "aux"

    # Force parse path: return non-dict-looking via _call_aux_json None
    async def fail_call(**kwargs):
        return None, "fallback"

    monkeypatch.setattr(roles, "_call_aux_json", fail_call)
    result = await roles.classify_intent("Привет")
    assert result.source == "heuristic"
    assert result.kind == "chitchat"


@pytest.mark.asyncio
async def test_classify_intent_uses_aux_and_keeps_heuristic_ssh(aux_config, monkeypatch):
    async def fake_call(**kwargs):
        return {"kind": "chitchat", "needs_ssh": False, "reason": "no"}, "aux"

    monkeypatch.setattr(roles, "_call_aux_json", fake_call)
    result = await roles.classify_intent("@host-1 проверь логи")
    assert result.source == "aux"
    # Heuristic host-ops must not be dropped by a wrong aux answer.
    assert result.needs_ssh is True


@pytest.mark.asyncio
async def test_verify_goal_continue_vs_finish(aux_config, monkeypatch):
    async def continue_call(**kwargs):
        return {"decision": "continue", "reason": "need ssh"}, "aux"

    monkeypatch.setattr(roles, "_call_aux_json", continue_call)
    cont = await roles.verify_goal(
        goal="глянь @h",
        assistant_so_far="found",
        tools_executed=True,
        has_task_evidence=False,
        inventory_only=True,
    )
    assert cont.decision == "continue"
    assert cont.source == "aux"

    async def finish_call(**kwargs):
        return {"decision": "finish", "reason": "done"}, "aux"

    monkeypatch.setattr(roles, "_call_aux_json", finish_call)
    fin = await roles.verify_goal(
        goal="Привет",
        assistant_so_far="hi",
        tools_executed=False,
        has_task_evidence=False,
        inventory_only=False,
    )
    assert fin.decision == "finish"


@pytest.mark.asyncio
async def test_verify_goal_fallback_when_aux_disabled(monkeypatch):
    cfg = ModelConfig(aux_llm_enabled=False)
    monkeypatch.setattr(roles, "_config", lambda: cfg)
    result = await roles.verify_goal(
        goal="x",
        assistant_so_far="",
        tools_executed=True,
        has_task_evidence=False,
        inventory_only=True,
    )
    assert result.source == "fallback"
    assert result.decision == "continue"


@pytest.mark.asyncio
async def test_summarize_uses_aux_or_truncate(aux_config, monkeypatch):
    async def ok(**kwargs):
        return {"summary": "short summary"}, "aux"

    monkeypatch.setattr(roles, "_call_aux_json", ok)
    out = await roles.summarize("y" * 5000, max_chars=200)
    assert out == "short summary"

    async def none(**kwargs):
        return None, "fallback"

    monkeypatch.setattr(roles, "_call_aux_json", none)
    out2 = await roles.summarize("z" * 5000, max_chars=120)
    assert len(out2) == 120


@pytest.mark.asyncio
async def test_safety_hint_never_authoritative(aux_config, monkeypatch):
    async def ok(**kwargs):
        return {"kind": "read_only", "reason": "looks safe"}, "aux"

    monkeypatch.setattr(roles, "_call_aux_json", ok)
    hint = await roles.classify_command_safety("rm -rf /")
    assert hint.kind == "read_only"
    assert hint.source == "aux"
    # Confirm gate is outside this module — hint is advisory only.


@pytest.mark.asyncio
async def test_call_aux_json_timeout(aux_config, monkeypatch):
    async def hang(**kwargs):
        await asyncio.sleep(60)
        return "x"

    monkeypatch.setattr(roles, "_complete_openai_compatible_json", hang)
    monkeypatch.setattr(roles, "aux_timeout_seconds", lambda config=None: 0.05)
    monkeypatch.setattr(
        roles,
        "_resolve_aux_endpoint",
        lambda config: ("openai_compatible", "m", "http://127.0.0.1:9/v1/chat/completions", ""),
    )
    parsed, source = await roles._call_aux_json(role="intent", system_prompt="s", user_prompt="u")
    assert parsed is None
    assert source == "fallback"


@pytest.mark.django_db
def test_settings_payload_includes_aux_fields():
    from core_ui.views.settings_config_views import _settings_config_payload

    model_manager.config = ModelConfig(
        aux_llm_enabled=True,
        aux_llm_provider="ollama",
        aux_llm_model="llama3.2",
        aux_llm_base_url="http://127.0.0.1:11434",
        aux_role_safety_enabled=False,
    )
    payload = _settings_config_payload(model_manager.config, "chat")
    assert payload["aux_llm_enabled"] is True
    assert payload["aux_llm_provider"] == "ollama"
    assert payload["aux_llm_model"] == "llama3.2"
    assert "aux_role_verifier_enabled" in payload


@pytest.mark.django_db
def test_settings_api_saves_aux_and_secret(client, settings, tmp_path, monkeypatch):
    settings.MODEL_CONFIG_PATH = str(tmp_path / "model_config.json")
    user = User.objects.create_superuser("aux-admin", "a@b.c", "x")
    client.force_login(user)
    model_manager.config = ModelConfig()
    model_manager.save_config = lambda: None  # type: ignore[method-assign]

    with (
        patch("core_ui.views.settings_config_views.set_llm_api_key") as set_key,
        patch("core_ui.views.settings_config_views._set_runtime_api_key"),
        patch("core_ui.views.settings_config_views._reset_llm_provider_cache"),
    ):
        resp = client.post(
            "/api/settings/",
            data={
                "aux_llm_enabled": True,
                "aux_llm_provider": "openai_compatible",
                "aux_llm_model": "qwen2.5",
                "aux_llm_base_url": "http://127.0.0.1:1234",
                "aux_llm_timeout_seconds": 6,
                "aux_role_verifier_enabled": True,
                "aux_role_intent_enabled": True,
                "aux_role_summarizer_enabled": False,
                "aux_role_safety_enabled": False,
                "api_keys": {"openai_compatible": "test-secret-key"},
            },
            content_type="application/json",
        )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    set_key.assert_called()
    assert model_manager.config.aux_llm_provider == "openai_compatible"
    assert model_manager.config.aux_llm_model == "qwen2.5"
    assert model_manager.config.aux_role_summarizer_enabled is False


@pytest.mark.django_db
def test_aux_model_test_endpoint_forbidden_for_non_admin(client):
    user = User.objects.create_user("aux-user", password="x")
    client.force_login(user)
    with (
        patch("core_ui.views.settings_config_views.user_can_feature", return_value=True),
        patch("core_ui.ai_model_policy.user_can_manage_ai_routing", return_value=False),
    ):
        resp = client.post("/api/settings/aux-model/test/", data="{}", content_type="application/json")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_aux_model_test_endpoint_ok(client):
    user = User.objects.create_superuser("aux-admin2", "a@b.c", "x")
    client.force_login(user)
    with patch(
        "app.core.aux_model_roles.test_aux_connection",
        new=AsyncMock(return_value={"ok": True, "provider": "ollama", "model": "llama3.2"}),
    ):
        resp = client.post("/api/settings/aux-model/test/", data="{}", content_type="application/json")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_resolve_purpose_aux_bucket():
    model_manager.config = ModelConfig(
        aux_llm_enabled=True,
        aux_llm_provider="ollama",
        aux_llm_model="llama3.2",
        chat_llm_provider="grok",
        chat_llm_model="grok-3",
    )
    provider, model = model_manager.resolve_purpose("aux_verifier")
    assert provider == "ollama"
    assert model == "llama3.2"
