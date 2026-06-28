import json

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.test import Client

from app.plugins.catalog import DEMO_PLUGIN_ID
from app.plugins.catalog import DEMO_PLUGIN_MANIFEST
from core_ui.models import UserActivityLog, UserAppPermission
from plugin_marketplace.models import PluginInstallEvent, PluginInstallation, PluginPackage, PluginPermissionGrant, PluginSecretBinding
from studio.models import Pipeline, PipelineRun
from studio.pipeline_executor import PipelineExecutor
from studio.pipeline_validation import validate_pipeline_definition


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
def test_catalog_bootstraps_builtin_plugin_disabled():
    user = User.objects.create_user(username="plugin-admin", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)

    response = client.get("/api/plugins/catalog/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["registered"] >= 1
    demo = next(item for item in payload["plugins"] if item["id"] == DEMO_PLUGIN_ID)
    assert demo["enabled"] is False
    assert demo["surfaces"]["pages"] == []
    assert PluginInstallation.objects.filter(plugin_id=DEMO_PLUGIN_ID, status="disabled").exists()


@pytest.mark.django_db
def test_admin_can_enable_grant_and_execute_demo_action():
    user = User.objects.create_user(username="plugin-flow", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)

    installed = client.get("/api/plugins/installed/")
    assert installed.status_code == 200, installed.content
    installation = next(item for item in installed.json()["installations"] if item["plugin_id"] == DEMO_PLUGIN_ID)

    denied = client.post("/api/plugins/demo/action/")
    assert denied.status_code == 403
    assert denied.json()["code"] == "permission_denied"

    enabled = client.post(f"/api/plugins/installed/{installation['id']}/enable/")
    assert enabled.status_code == 200, enabled.content
    assert enabled.json()["status"] == "enabled"

    catalog = client.get("/api/plugins/catalog/").json()
    demo = next(item for item in catalog["plugins"] if item["id"] == DEMO_PLUGIN_ID)
    assert demo["enabled"] is True
    assert demo["surfaces"]["pages"][0]["id"] == "overview"

    permissions = client.get(f"/api/plugins/installed/{installation['id']}/permissions/")
    assert permissions.status_code == 200, permissions.content
    assert permissions.json()["permissions"][0]["granted"] is False

    granted = client.post(
        f"/api/plugins/installed/{installation['id']}/permissions/grant/",
        data=_json({"scope": "demo.alerts.send"}),
        content_type="application/json",
    )
    assert granted.status_code == 200, granted.content
    assert granted.json()["granted"] is True
    assert PluginPermissionGrant.objects.filter(scope="demo.alerts.send", granted=True).exists()

    action = client.post("/api/plugins/demo/action/")
    assert action.status_code == 200, action.content
    assert action.json()["success"] is True
    assert PluginInstallEvent.objects.filter(plugin_id=DEMO_PLUGIN_ID, event_type="plugin_demo_action").exists()
    assert UserActivityLog.objects.filter(category="plugins", action="plugin_demo_action").exists()


@pytest.mark.django_db
def test_non_staff_settings_user_cannot_manage_plugins():
    user = User.objects.create_user(username="plugin-user", password="x", is_staff=False)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)

    catalog = client.get("/api/plugins/catalog/")
    installed = client.get("/api/plugins/installed/")

    assert catalog.status_code == 200
    assert installed.status_code == 403
    assert installed.json()["code"] == "admin_required"


@pytest.mark.django_db
def test_unknown_permission_scope_is_rejected():
    user = User.objects.create_user(username="plugin-scope", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    installation = client.get("/api/plugins/installed/").json()["installations"][0]

    response = client.post(
        f"/api/plugins/installed/{installation['id']}/permissions/grant/",
        data=_json({"scope": "unknown.scope"}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_permission"


@pytest.mark.django_db
def test_private_catalog_sync_and_install_disabled():
    user = User.objects.create_user(username="catalog-admin", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)

    source = client.post(
        "/api/plugins/marketplace/sources/",
        data=_json({"name": "Private", "source_url": "local://private"}),
        content_type="application/json",
    )
    assert source.status_code == 200, source.content
    source_id = source.json()["source"]["id"]

    manifest = dict(DEMO_PLUGIN_MANIFEST)
    manifest.update({
        "id": "acme.slack-alerts",
        "name": "Slack Alerts",
        "slug": "slack-alerts",
        "version": "0.1.0",
        "api_version": "plugins.v1",
        "publisher": {"id": "acme", "name": "Acme Automation", "verified": True},
    })
    sync = client.post(
        f"/api/plugins/marketplace/sources/{source_id}/sync/",
        data=_json({
            "plugins": [{
                "manifest": manifest,
                "package_url": "local://packages/acme.slack-alerts.wtp",
                "compatibility": {"api_versions": ["plugins.v1"]},
                "review_status": "verified",
                "signature_status": "signed",
            }],
        }),
        content_type="application/json",
    )
    assert sync.status_code == 200, sync.content
    assert sync.json()["synced"] == 1

    catalog = client.get("/api/plugins/marketplace/catalog/")
    assert catalog.status_code == 200, catalog.content
    item = catalog.json()["items"][0]
    assert item["plugin_id"] == "acme.slack-alerts"
    assert item["compatibility_report"]["compatible"] is True

    install = client.post(f"/api/plugins/marketplace/catalog/{item['id']}/install/")
    assert install.status_code == 200, install.content
    installation = PluginInstallation.objects.get(plugin_id="acme.slack-alerts")
    package = PluginPackage.objects.get(plugin_id="acme.slack-alerts")
    assert installation.status == PluginInstallation.STATUS_DISABLED
    assert package.source == PluginPackage.SOURCE_CATALOG
    assert PluginInstallEvent.objects.filter(plugin_id="acme.slack-alerts", event_type="plugin_catalog_installed").exists()


@pytest.mark.django_db
def test_private_catalog_blocks_incompatible_plugin_install():
    user = User.objects.create_user(username="catalog-incompatible", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    source_id = client.post(
        "/api/plugins/marketplace/sources/",
        data=_json({"name": "Private", "source_url": "local://private"}),
        content_type="application/json",
    ).json()["source"]["id"]

    manifest = dict(DEMO_PLUGIN_MANIFEST)
    manifest.update({
        "id": "acme.future-plugin",
        "name": "Future Plugin",
        "slug": "future-plugin",
        "version": "1.0.0",
        "api_version": "plugins.v9",
        "publisher": {"id": "acme", "name": "Acme Automation"},
    })
    sync = client.post(
        f"/api/plugins/marketplace/sources/{source_id}/sync/",
        data=_json({
            "plugins": [{
                "manifest": manifest,
                "compatibility": {"api_versions": ["plugins.v9"]},
                "review_status": "verified",
                "signature_status": "signed",
            }],
        }),
        content_type="application/json",
    )
    assert sync.status_code == 200, sync.content
    item = client.get("/api/plugins/marketplace/catalog/").json()["items"][0]
    assert item["compatibility_report"]["compatible"] is False

    install = client.post(f"/api/plugins/marketplace/catalog/{item['id']}/install/")

    assert install.status_code == 409
    assert install.json()["code"] == "incompatible_plugin"
    assert not PluginInstallation.objects.filter(plugin_id="acme.future-plugin").exists()


@pytest.mark.django_db
def test_plugin_settings_and_secret_binding_are_validated_and_masked():
    user = User.objects.create_user(username="plugin-settings", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    manifest = dict(DEMO_PLUGIN_MANIFEST)
    manifest.update({
        "id": "acme.configurable",
        "name": "Configurable Plugin",
        "slug": "configurable",
        "publisher": {"id": "acme", "name": "Acme"},
        "settings_schema": {
            "type": "object",
            "required": ["display_label"],
            "properties": {"display_label": {"type": "string"}},
        },
        "secrets": [{"id": "api_token", "label": "API token", "kind": "bearer_token", "required": True}],
    })
    package = PluginPackage.objects.create(
        plugin_id="acme.configurable",
        version="0.1.0",
        name="Configurable Plugin",
        slug="configurable",
        publisher_id="acme",
        publisher_name="Acme",
        source=PluginPackage.SOURCE_LOCAL,
        manifest=manifest,
        review_status=PluginPackage.REVIEW_VERIFIED,
        signature_status=PluginPackage.SIGNATURE_SIGNED,
    )
    installation = PluginInstallation.objects.create(plugin_id="acme.configurable", package=package)

    invalid = client.post(
        f"/api/plugins/installed/{installation.id}/settings/update/",
        data=_json({"settings": {"display_label": 42}}),
        content_type="application/json",
    )
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "invalid_settings"

    valid = client.post(
        f"/api/plugins/installed/{installation.id}/settings/update/",
        data=_json({"settings": {"display_label": "Ops alerts"}}),
        content_type="application/json",
    )
    assert valid.status_code == 200, valid.content
    assert valid.json()["settings"]["display_label"] == "Ops alerts"

    secret = client.post(
        f"/api/plugins/installed/{installation.id}/secrets/bind/",
        data=_json({"key": "api_token", "secret_ref": "managed-secret-token-123456"}),
        content_type="application/json",
    )
    assert secret.status_code == 200, secret.content
    assert "managed-secret-token-123456" not in secret.content.decode("utf-8")
    assert secret.json()["secrets"][0]["secret_ref"] == "...3456"
    assert PluginSecretBinding.objects.get(installation=installation, key="api_token").secret_ref == "managed-secret-token-123456"


@pytest.mark.django_db
def test_active_plugin_page_surface_tracks_enable_disable():
    user = User.objects.create_user(username="plugin-pages", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    installation = client.get("/api/plugins/installed/").json()["installations"][0]

    before = client.get("/api/plugins/surfaces/")
    assert before.status_code == 200
    assert before.json()["surfaces"]["pages"] == []
    assert before.json()["surfaces"]["dashboard_widgets"] == []
    missing = client.get(f"/api/plugins/pages/{DEMO_PLUGIN_ID}/overview/")
    assert missing.status_code == 404

    client.post(f"/api/plugins/installed/{installation['id']}/enable/")
    active = client.get("/api/plugins/surfaces/")
    assert active.status_code == 200
    assert active.json()["surfaces"]["pages"][0]["id"] == "overview"
    assert active.json()["surfaces"]["dashboard_widgets"][0]["id"] == "demo-health"
    assert active.json()["surfaces"]["connectors"][0]["id"] == "demo-connector"
    assert active.json()["surfaces"]["agent_tools"][0]["name"] == "plugin_webtrerm_demo_dashboard_ping"
    assert active.json()["surfaces"]["terminal_actions"][0]["id"] == "demo-terminal-ping"
    assert active.json()["surfaces"]["hooks"][0]["event"] == "plugin.demo.audit"
    page = client.get(f"/api/plugins/pages/{DEMO_PLUGIN_ID}/overview/")
    assert page.status_code == 200
    assert page.json()["page"]["title"] == "Demo Plugin Overview"

    client.post(f"/api/plugins/installed/{installation['id']}/disable/")
    disabled = client.get(f"/api/plugins/pages/{DEMO_PLUGIN_ID}/overview/")
    assert disabled.status_code == 404


@pytest.mark.django_db
def test_studio_plugin_node_manifest_and_validation_track_enable_disable():
    user = User.objects.create_user(username="plugin-studio-node", password="x", is_staff=True)
    _grant_feature(user, "settings", "studio_pipelines")
    client = Client()
    client.force_login(user)
    installation = client.get("/api/plugins/installed/").json()["installations"][0]

    before = client.get("/api/studio/node-manifests/")
    assert before.status_code == 200
    assert PLUGIN_STUDIO_NODE_TYPE not in {item["type"] for item in before.json()["nodes"]}

    nodes = [
        {"id": "trigger", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"is_active": True}},
        {
            "id": "plugin_ping",
            "type": PLUGIN_STUDIO_NODE_TYPE,
            "position": {"x": 240, "y": 0},
            "data": {"connector_id": "demo-connector"},
        },
    ]
    edges = [{"id": "e1", "source": "trigger", "target": "plugin_ping", "sourceHandle": "out"}]
    assert any("unknown type" in item for item in validate_pipeline_definition(nodes=nodes, edges=edges, owner=user))

    enabled = client.post(f"/api/plugins/installed/{installation['id']}/enable/")
    assert enabled.status_code == 200, enabled.content
    after = client.get("/api/studio/node-manifests/")
    assert after.status_code == 200
    plugin_node = next(item for item in after.json()["nodes"] if item["type"] == PLUGIN_STUDIO_NODE_TYPE)
    assert plugin_node["metadata"]["plugin_id"] == DEMO_PLUGIN_ID
    assert plugin_node["metadata"]["required_permission"] == "demo.connector.ping"
    assert validate_pipeline_definition(nodes=nodes, edges=edges, owner=user) == []

    disabled = client.post(f"/api/plugins/installed/{installation['id']}/disable/")
    assert disabled.status_code == 200, disabled.content
    assert any("unknown type" in item for item in validate_pipeline_definition(nodes=nodes, edges=edges, owner=user))


@pytest.mark.django_db
def test_studio_plugin_node_execution_requires_secret_and_permission():
    user = User.objects.create_user(username="plugin-studio-exec", password="x", is_staff=True)
    _grant_feature(user, "settings", "studio_pipelines")
    client = Client()
    client.force_login(user)
    installation = client.get("/api/plugins/installed/").json()["installations"][0]
    assert client.post(f"/api/plugins/installed/{installation['id']}/enable/").status_code == 200
    assert client.post(
        f"/api/plugins/installed/{installation['id']}/secrets/bind/",
        data=_json({"key": "demo_api_token", "secret_ref": "managed-demo-token-1111"}),
        content_type="application/json",
    ).status_code == 200

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
