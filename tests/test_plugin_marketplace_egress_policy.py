import json

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings

from app.plugins.catalog import DEMO_PLUGIN_ID
from core_ui.models import UserAppPermission


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


@pytest.mark.django_db
def test_connector_health_blocks_admin_denied_egress_after_policy_change():
    user = User.objects.create_user(username="plugin-connector-egress-policy", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    installation = client.get("/api/plugins/installed/").json()["installations"][0]

    enabled = client.post(f"/api/plugins/installed/{installation['id']}/enable/")
    assert enabled.status_code == 200, enabled.content
    secret = client.post(
        f"/api/plugins/installed/{installation['id']}/secrets/bind/",
        data=_json({"key": "demo_api_token", "secret_ref": "managed-demo-token-9999"}),
        content_type="application/json",
    )
    assert secret.status_code == 200, secret.content

    with override_settings(PLUGIN_MARKETPLACE_EGRESS_DENIED_HOSTS=["example.com"]):
        health = client.get(f"/api/plugins/connectors/{DEMO_PLUGIN_ID}/demo-connector/health/")
        assert health.status_code == 200, health.content
        payload = health.json()["health"]
        assert payload["status"] == "blocked"
        assert any(check["name"] == "egress_policy" for check in payload["checks"])
