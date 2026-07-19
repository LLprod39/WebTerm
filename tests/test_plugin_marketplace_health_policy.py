import pytest
from django.contrib.auth.models import User
from django.test import Client

from app.plugins.catalog import DEMO_PLUGIN_ID
from core_ui.models import UserAppPermission
from plugin_marketplace.models import PluginInstallation, PluginInstallEvent


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


@pytest.mark.django_db
def test_repeated_connector_health_failures_auto_quarantine_plugin():
    user = User.objects.create_user(username="plugin-health-policy", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    installation = client.get("/api/plugins/installed/").json()["installations"][0]
    assert client.post(f"/api/plugins/installed/{installation['id']}/enable/").status_code == 200

    for _index in range(3):
        response = client.get(f"/api/plugins/connectors/{DEMO_PLUGIN_ID}/demo-connector/health/")
        assert response.status_code == 200, response.content
        assert response.json()["health"]["status"] == "blocked"

    stored = PluginInstallation.objects.get(plugin_id=DEMO_PLUGIN_ID)
    assert stored.status == PluginInstallation.STATUS_QUARANTINED
    assert stored.health_failure_count == 3
    assert stored.quarantined_at is not None
    assert PluginInstallEvent.objects.filter(plugin_id=DEMO_PLUGIN_ID, event_type="plugin_auto_quarantined").exists()

    surfaces = client.get("/api/plugins/surfaces/")
    assert surfaces.status_code == 200
    assert surfaces.json()["surfaces"]["connectors"] == []
