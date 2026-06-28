import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from app.plugins.catalog import DEMO_PLUGIN_ID
from core_ui.models import UserAppPermission
from plugin_marketplace.models import PluginInstallEvent


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
def test_plugin_hook_event_requires_enablement_and_permission():
    user = User.objects.create_user(username="plugin-hook", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    installation = client.get("/api/plugins/installed/").json()["installations"][0]

    missing = client.post(
        "/api/plugins/hooks/emit/",
        data=_json({"event": "plugin.demo.audit", "payload": {"message": "hello"}}),
        content_type="application/json",
    )
    assert missing.status_code == 404

    assert client.post(f"/api/plugins/installed/{installation['id']}/enable/").status_code == 200
    blocked = client.post(
        "/api/plugins/hooks/emit/",
        data=_json({"event": "plugin.demo.audit", "payload": {"message": "hello"}}),
        content_type="application/json",
    )
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "hook_blocked"

    granted = client.post(
        f"/api/plugins/installed/{installation['id']}/permissions/grant/",
        data=_json({"scope": "demo.alerts.send"}),
        content_type="application/json",
    )
    assert granted.status_code == 200, granted.content
    emitted = client.post(
        "/api/plugins/hooks/emit/",
        data=_json({"event": "plugin.demo.audit", "payload": {"message": "hello"}}),
        content_type="application/json",
    )
    assert emitted.status_code == 200, emitted.content
    assert emitted.json()["results"][0]["hook_id"] == "demo-audit-hook"
    assert PluginInstallEvent.objects.filter(plugin_id=DEMO_PLUGIN_ID, event_type="plugin_hook_executed").exists()
