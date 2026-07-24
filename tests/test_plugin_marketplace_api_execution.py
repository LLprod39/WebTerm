import json

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.test import Client

from app.plugins.catalog import DEMO_PLUGIN_ID
from core_ui.models import UserAppPermission
from plugin_marketplace.models import (
    PluginInstallEvent,
)
from studio.models import Pipeline, PipelineRun
from studio.pipeline_executor import PipelineExecutor


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


PLUGIN_STUDIO_NODE_TYPE = "plugin/webtrerm.demo-dashboard/demo-connector-ping"


@pytest.mark.django_db
def test_studio_plugin_node_execution_requires_secret_and_permission():
    user = User.objects.create_user(username="plugin-studio-exec", password="x", is_staff=True)
    _grant_feature(user, "settings", "studio_pipelines")
    client = Client()
    client.force_login(user)
    installation = client.get("/api/plugins/installed/").json()["installations"][0]
    assert client.post(f"/api/plugins/installed/{installation['id']}/enable/").status_code == 200
    assert (
        client.post(
            f"/api/plugins/installed/{installation['id']}/secrets/bind/",
            data=_json({"key": "demo_api_token", "secret_ref": "managed-demo-token-1111"}),
            content_type="application/json",
        ).status_code
        == 200
    )

    node = {
        "id": "plugin_ping",
        "type": PLUGIN_STUDIO_NODE_TYPE,
        "position": {"x": 0, "y": 0},
        "data": {"connector_id": "demo-connector"},
    }
    pipeline = Pipeline.objects.create(
        name="Plugin Studio execution",
        owner=user,
        nodes=[node],
        edges=[],
    )
    run = PipelineRun.objects.create(
        pipeline=pipeline,
        triggered_by=user,
        status=PipelineRun.STATUS_PENDING,
        nodes_snapshot=[node],
        edges_snapshot=[],
        context={},
    )

    denied = async_to_sync(PipelineExecutor(run)._execute_node)(node, {}, {})
    assert denied["status"] == "failed"
    assert "Plugin permission has not been granted" in denied["error"]

    granted = client.post(
        f"/api/plugins/installed/{installation['id']}/permissions/grant/",
        data=_json({"scope": "demo.connector.ping"}),
        content_type="application/json",
    )
    assert granted.status_code == 200, granted.content
    executed = async_to_sync(PipelineExecutor(run)._execute_node)(node, {}, {})
    assert executed["status"] == "completed"
    assert executed["connector_id"] == "demo-connector"
    assert PluginInstallEvent.objects.filter(plugin_id=DEMO_PLUGIN_ID, event_type="plugin_connector_ping").exists()


@pytest.mark.django_db
def test_terminal_action_execution_requires_secret_and_permission():
    user = User.objects.create_user(username="plugin-terminal-action", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    installation = client.get("/api/plugins/installed/").json()["installations"][0]

    missing = client.post(f"/api/plugins/terminal-actions/{DEMO_PLUGIN_ID}/demo-terminal-ping/execute/")
    assert missing.status_code == 404

    assert client.post(f"/api/plugins/installed/{installation['id']}/enable/").status_code == 200
    blocked = client.post(f"/api/plugins/terminal-actions/{DEMO_PLUGIN_ID}/demo-terminal-ping/execute/")
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "terminal_action_blocked"

    secret = client.post(
        f"/api/plugins/installed/{installation['id']}/secrets/bind/",
        data=_json({"key": "demo_api_token", "secret_ref": "managed-terminal-token-9999"}),
        content_type="application/json",
    )
    assert secret.status_code == 200, secret.content
    permission_blocked = client.post(f"/api/plugins/terminal-actions/{DEMO_PLUGIN_ID}/demo-terminal-ping/execute/")
    assert permission_blocked.status_code == 403

    granted = client.post(
        f"/api/plugins/installed/{installation['id']}/permissions/grant/",
        data=_json({"scope": "demo.connector.ping"}),
        content_type="application/json",
    )
    assert granted.status_code == 200, granted.content
    executed = client.post(f"/api/plugins/terminal-actions/{DEMO_PLUGIN_ID}/demo-terminal-ping/execute/")
    assert executed.status_code == 200, executed.content
    assert executed.json()["connector_id"] == "demo-connector"
    assert PluginInstallEvent.objects.filter(plugin_id=DEMO_PLUGIN_ID, event_type="plugin_connector_ping").exists()


@pytest.mark.django_db
def test_connector_health_and_ping_require_secret_and_permission():
    user = User.objects.create_user(username="plugin-connector", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    installation = client.get("/api/plugins/installed/").json()["installations"][0]

    disabled_health = client.get(f"/api/plugins/connectors/{DEMO_PLUGIN_ID}/demo-connector/health/")
    assert disabled_health.status_code == 404

    client.post(f"/api/plugins/installed/{installation['id']}/enable/")
    blocked_health = client.get(f"/api/plugins/connectors/{DEMO_PLUGIN_ID}/demo-connector/health/")
    assert blocked_health.status_code == 200
    assert blocked_health.json()["health"]["status"] == "blocked"

    blocked_ping = client.post(f"/api/plugins/connectors/{DEMO_PLUGIN_ID}/demo-connector/ping/")
    assert blocked_ping.status_code == 403

    secret = client.post(
        f"/api/plugins/installed/{installation['id']}/secrets/bind/",
        data=_json({"key": "demo_api_token", "secret_ref": "managed-demo-token-9999"}),
        content_type="application/json",
    )
    assert secret.status_code == 200, secret.content
    healthy = client.get(f"/api/plugins/connectors/{DEMO_PLUGIN_ID}/demo-connector/health/")
    assert healthy.status_code == 200
    assert healthy.json()["health"]["status"] == "healthy"

    permission_blocked = client.post(f"/api/plugins/connectors/{DEMO_PLUGIN_ID}/demo-connector/ping/")
    assert permission_blocked.status_code == 403
    assert permission_blocked.json()["code"] == "connector_blocked"

    granted = client.post(
        f"/api/plugins/installed/{installation['id']}/permissions/grant/",
        data=_json({"scope": "demo.connector.ping"}),
        content_type="application/json",
    )
    assert granted.status_code == 200, granted.content
    ping = client.post(f"/api/plugins/connectors/{DEMO_PLUGIN_ID}/demo-connector/ping/")
    assert ping.status_code == 200, ping.content
    assert PluginInstallEvent.objects.filter(plugin_id=DEMO_PLUGIN_ID, event_type="plugin_connector_ping").exists()
