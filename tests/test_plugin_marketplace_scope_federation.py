import json

import pytest
from django.contrib.auth.models import Group, User
from django.test import Client, override_settings

from app.plugins.catalog import DEMO_PLUGIN_ID, DEMO_PLUGIN_MANIFEST
from core_ui.models import UserAppPermission
from plugin_marketplace.models import MarketplaceCatalogItem, PluginInstallEvent, PluginPackage
from studio.pipeline_validation import validate_pipeline_definition

PLUGIN_STUDIO_NODE_TYPE = "plugin/webtrerm.demo-dashboard/demo-connector-ping"


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
def test_plugin_installation_scope_limits_surfaces_and_permissions_to_access_group():
    alpha = Group.objects.create(name="Alpha Ops")
    beta = Group.objects.create(name="Beta Ops")
    owner = User.objects.create_user(username="plugin-alpha", password="x", is_staff=True)
    outsider = User.objects.create_user(username="plugin-beta", password="x", is_staff=True)
    owner.groups.add(alpha)
    outsider.groups.add(beta)
    _grant_feature(owner, "settings", "studio_pipelines")
    _grant_feature(outsider, "settings", "studio_pipelines")

    owner_client = Client()
    owner_client.force_login(owner)
    installation = owner_client.get("/api/plugins/installed/").json()["installations"][0]
    assert owner_client.post(f"/api/plugins/installed/{installation['id']}/enable/").status_code == 200
    assert (
        owner_client.post(
            f"/api/plugins/installed/{installation['id']}/permissions/grant/",
            data=_json({"scope": "demo.alerts.send"}),
            content_type="application/json",
        ).status_code
        == 200
    )

    scope = owner_client.post(
        f"/api/plugins/installed/{installation['id']}/scope/update/",
        data=_json({"group_ids": [alpha.id]}),
        content_type="application/json",
    )
    assert scope.status_code == 200, scope.content
    assert scope.json()["scope"]["mode"] == "groups"

    owner_surfaces = owner_client.get("/api/plugins/surfaces/")
    assert owner_surfaces.status_code == 200
    assert owner_surfaces.json()["surfaces"]["pages"][0]["plugin_id"] == DEMO_PLUGIN_ID
    owner_nodes = owner_client.get("/api/studio/node-manifests/")
    assert PLUGIN_STUDIO_NODE_TYPE in {item["type"] for item in owner_nodes.json()["nodes"]}
    nodes = [
        {"id": "trigger", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"is_active": True}},
        {"id": "plugin_ping", "type": PLUGIN_STUDIO_NODE_TYPE, "position": {"x": 240, "y": 0}, "data": {}},
    ]
    edges = [{"id": "e1", "source": "trigger", "target": "plugin_ping", "sourceHandle": "out"}]
    assert validate_pipeline_definition(nodes=nodes, edges=edges, owner=owner) == []
    assert owner_client.post("/api/plugins/demo/action/").status_code == 200

    outsider_client = Client()
    outsider_client.force_login(outsider)
    outsider_surfaces = outsider_client.get("/api/plugins/surfaces/")
    assert outsider_surfaces.status_code == 200
    assert outsider_surfaces.json()["surfaces"]["pages"] == []
    outsider_nodes = outsider_client.get("/api/studio/node-manifests/")
    assert PLUGIN_STUDIO_NODE_TYPE not in {item["type"] for item in outsider_nodes.json()["nodes"]}
    assert any(
        "unknown type" in item for item in validate_pipeline_definition(nodes=nodes, edges=edges, owner=outsider)
    )
    assert outsider_client.get(f"/api/plugins/pages/{DEMO_PLUGIN_ID}/overview/").status_code == 404
    assert outsider_client.post("/api/plugins/demo/action/").status_code == 403

    outsider_catalog = outsider_client.get("/api/plugins/catalog/")
    demo = next(item for item in outsider_catalog.json()["plugins"] if item["id"] == DEMO_PLUGIN_ID)
    assert demo["enabled"] is False
    assert demo["surfaces"]["pages"] == []
    assert PluginInstallEvent.objects.filter(plugin_id=DEMO_PLUGIN_ID, event_type="plugin_scope_updated").exists()


@pytest.mark.django_db
@override_settings(PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS=["catalog.example"])
def test_federated_marketplace_source_sync_fetches_https_catalog(monkeypatch):
    user = User.objects.create_user(username="catalog-federated", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)

    source = client.post(
        "/api/plugins/marketplace/sources/",
        data=_json({"name": "Federated", "source_url": "https://catalog.example/webtrerm/catalog.json"}),
        content_type="application/json",
    )
    assert source.status_code == 200, source.content
    source_id = source.json()["source"]["id"]
    assert source.json()["source"]["federated"] is True
    assert source.json()["source"]["sync_mode"] == "remote"

    manifest = dict(DEMO_PLUGIN_MANIFEST)
    manifest.update(
        {
            "id": "acme.federated-alerts",
            "name": "Federated Alerts",
            "slug": "federated-alerts",
            "version": "0.2.0",
            "api_version": "plugins.v1",
            "publisher": {"id": "acme", "name": "Acme Federation", "verified": True},
        }
    )
    payload = _json(
        {
            "plugins": [
                {
                    "manifest": manifest,
                    "compatibility": {"api_versions": ["plugins.v1"]},
                    "review_status": "verified",
                    "signature_status": "signed",
                }
            ],
        }
    ).encode("utf-8")

    class FakeResponse:
        headers = {"Content-Length": str(len(payload))}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return payload

    def fake_urlopen(url, timeout):
        assert url == "https://catalog.example/webtrerm/catalog.json"
        assert timeout == 20
        return FakeResponse()

    monkeypatch.setattr("plugin_marketplace.services.catalog_service.urllib.request.urlopen", fake_urlopen)

    sync = client.post(f"/api/plugins/marketplace/sources/{source_id}/sync-remote/")
    assert sync.status_code == 200, sync.content
    assert sync.json()["synced"] == 1
    assert sync.json()["source"]["last_error"] == ""
    item = MarketplaceCatalogItem.objects.get(plugin_id="acme.federated-alerts")
    assert item.source_id == source_id
    assert item.review_status == PluginPackage.REVIEW_VERIFIED
    assert item.signature_status == PluginPackage.SIGNATURE_SIGNED
