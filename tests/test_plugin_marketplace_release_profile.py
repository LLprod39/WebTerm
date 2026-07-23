import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings

from plugin_marketplace.checks import plugin_marketplace_deploy_check
from plugin_marketplace.release_profile import plugin_marketplace_enabled
from web_ui.settings.plugin_marketplace import build_plugin_marketplace_settings


def test_plugin_marketplace_release_mode_defaults_by_environment(monkeypatch):
    monkeypatch.delenv("PLUGIN_MARKETPLACE_RELEASE_MODE", raising=False)

    assert build_plugin_marketplace_settings(debug=True)["PLUGIN_MARKETPLACE_RELEASE_MODE"] == "enabled"
    assert build_plugin_marketplace_settings(debug=False)["PLUGIN_MARKETPLACE_RELEASE_MODE"] == "disabled"


@override_settings(
    DEBUG=False,
    PLUGIN_MARKETPLACE_RELEASE_MODE="disabled",
    PLUGIN_MARKETPLACE_REQUIRE_CONFIGURED_SIGNING_KEYS=True,
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER=True,
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SECURITY_SCANNER=True,
    PLUGIN_MARKETPLACE_SIGNING_KEYS={},
    PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS=[],
    PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS=[],
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=False,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=False,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=False,
    PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES=False,
)
def test_disabled_release_profile_does_not_require_out_of_scope_trust_stack():
    assert plugin_marketplace_enabled() is False
    assert plugin_marketplace_deploy_check(None) == []


@override_settings(
    PLUGIN_MARKETPLACE_RELEASE_MODE="disabled",
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
)
def test_disabled_release_profile_rejects_executable_runtime_flags():
    assert {error.id for error in plugin_marketplace_deploy_check(None)} == {"plugin_marketplace.E031"}


@override_settings(PLUGIN_MARKETPLACE_RELEASE_MODE="unexpected")
def test_unknown_release_profile_fails_closed():
    assert plugin_marketplace_enabled() is False
    assert {error.id for error in plugin_marketplace_deploy_check(None)} == {"plugin_marketplace.E030"}


@pytest.mark.django_db
@override_settings(PLUGIN_MARKETPLACE_RELEASE_MODE="disabled")
def test_disabled_release_profile_is_hidden_from_staff_auth_payload():
    user = User.objects.create_user(username="plugin-release-admin", password="x", is_staff=True)
    client = Client()
    client.force_login(user)

    payload = client.get("/api/auth/session/").json()

    assert payload["user"]["features"]["plugins"] is False


@pytest.mark.django_db
@override_settings(PLUGIN_MARKETPLACE_RELEASE_MODE="enabled")
def test_enabled_release_profile_is_visible_only_to_staff():
    staff = User.objects.create_user(username="plugin-enabled-admin", password="x", is_staff=True)
    user = User.objects.create_user(username="plugin-enabled-user", password="x", is_staff=False)
    client = Client()

    client.force_login(staff)
    assert client.get("/api/auth/session/").json()["user"]["features"]["plugins"] is True

    client.force_login(user)
    assert client.get("/api/auth/session/").json()["user"]["features"]["plugins"] is False
