import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from app.core.model_config import ModelConfig, model_manager
from core_ui.models import UserAppPermission


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


@pytest.mark.django_db
def test_explicit_platform_settings_capability_can_refresh_provider_models(monkeypatch):
    user = User.objects.create_user(username="settings-model-refresh-user", password="x")
    UserAppPermission.objects.update_or_create(
        user=user,
        feature="settings",
        defaults={"allowed": True},
    )
    client = Client()
    client.force_login(user)

    async def fake_fetch(self):
        return ["llama3.2:latest"]

    monkeypatch.setattr("app.core.model_config.ModelManager.fetch_available_ollama_models", fake_fetch, raising=False)

    refresh = client.post(
        "/api/models/refresh/",
        data=_json({"provider": "ollama"}),
        content_type="application/json",
    )

    assert refresh.status_code == 200
    assert refresh.json()["models"] == ["llama3.2:latest"]


@pytest.mark.django_db
def test_non_staff_with_settings_cannot_manage_access():
    user = User.objects.create_user(username="settings-access-user", password="x")
    UserAppPermission.objects.update_or_create(
        user=user,
        feature="settings",
        defaults={"allowed": True},
    )
    client = Client()
    client.force_login(user)

    response = client.get("/api/access/users/")

    assert response.status_code == 403
    assert response.json()["error"] == "Only admins can manage access"


@pytest.mark.django_db
def test_non_staff_with_settings_cannot_update_runtime_limits():
    user = User.objects.create_user(username="settings-runtime-limit-user", password="x")
    UserAppPermission.objects.update_or_create(
        user=user,
        feature="settings",
        defaults={"allowed": True},
    )
    client = Client()
    client.force_login(user)

    response = client.post(
        "/api/settings/",
        data=_json({"agent_active_runs_per_user_limit": 1}),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["error"] == "Only admins can update runtime limits"


@pytest.mark.django_db
def test_staff_can_update_runtime_limits(monkeypatch):
    from core_ui.views import settings_config_views

    updates: list[dict] = []
    monkeypatch.setattr(settings_config_views.model_manager, "update_config", lambda **kwargs: updates.append(kwargs))
    monkeypatch.setattr(settings_config_views.model_manager, "save_config", lambda: None)

    user = User.objects.create_user(username="settings-runtime-limit-admin", password="x", is_staff=True)
    client = Client()
    client.force_login(user)

    response = client.post(
        "/api/settings/",
        data=_json({"llm_daily_token_limit_per_user": 1000, "mcp_http_retry_attempts": 99}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert {"llm_daily_token_limit_per_user": 1000} in updates
    assert {"mcp_http_retry_attempts": 10} in updates


def test_domain_auth_reads_model_config_path(monkeypatch, tmp_path):
    from core_ui import domain_auth

    original_config = model_manager.config
    config_path = tmp_path / "runtime-model-config.json"
    monkeypatch.setenv("MODEL_CONFIG_PATH", str(config_path))

    try:
        model_manager.config = ModelConfig(
            domain_auth_enabled=True,
            domain_auth_header="X-Forwarded-User",
            domain_auth_auto_create=True,
            domain_auth_default_profile="server_only",
        )
        model_manager.save_config()
        model_manager.config = ModelConfig(
            domain_auth_enabled=False,
            domain_auth_header="REMOTE_USER",
            domain_auth_auto_create=False,
            domain_auth_default_profile="custom",
        )
        domain_auth._MODEL_CONFIG_LOADED = False
        domain_auth._MODEL_CONFIG_MTIME = None

        assert domain_auth._env_enabled() is True
        assert domain_auth._header_name() == "X-Forwarded-User"
    finally:
        model_manager.config = original_config
        domain_auth._MODEL_CONFIG_LOADED = False
        domain_auth._MODEL_CONFIG_MTIME = None
