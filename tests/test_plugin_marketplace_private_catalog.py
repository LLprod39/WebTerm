import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from app.plugins.catalog import DEMO_PLUGIN_MANIFEST
from core_ui.models import UserAppPermission
from plugin_marketplace.models import MarketplaceCatalogItem, MarketplaceSource


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
def test_private_catalog_source_payload_redacts_credentials():
    user = User.objects.create_user(username="catalog-redaction-admin", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)

    source = client.post(
        "/api/plugins/marketplace/sources/",
        data=_json({
            "name": "Private With Token",
            "source_url": "https://user:pass@catalog.example/feed.json?token=secret-value&version=1",
        }),
        content_type="application/json",
    )
    assert source.status_code == 200, source.content
    source_id = source.json()["source"]["id"]
    stored = MarketplaceSource.objects.get(id=source_id)
    assert "secret-value" in stored.source_url

    sources = client.get("/api/plugins/marketplace/sources/")

    assert sources.status_code == 200, sources.content
    content = sources.content.decode("utf-8")
    assert "secret-value" not in content
    assert "user:pass" not in content
    payload = sources.json()["sources"][0]
    assert payload["credentials_redacted"] is True
    assert payload["source_url"] == "https://***:***@catalog.example/feed.json?token=***&version=1"


@pytest.mark.django_db
def test_private_catalog_item_embeds_redacted_source_payload():
    user = User.objects.create_user(username="catalog-item-redaction-admin", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    source_id = client.post(
        "/api/plugins/marketplace/sources/",
        data=_json({
            "name": "Private Item Source",
            "source_url": "https://catalog.example/feed.json?api_key=private-key",
        }),
        content_type="application/json",
    ).json()["source"]["id"]
    manifest = dict(DEMO_PLUGIN_MANIFEST)
    manifest.update({
        "id": "acme.catalog-redacted",
        "name": "Catalog Redacted",
        "slug": "catalog-redacted",
        "publisher": {"id": "acme", "name": "Acme"},
    })
    sync = client.post(
        f"/api/plugins/marketplace/sources/{source_id}/sync/",
        data=_json({
            "plugins": [{
                "manifest": manifest,
                "compatibility": {"api_versions": ["plugins.v1"]},
                "review_status": "verified",
                "signature_status": "signed",
            }],
        }),
        content_type="application/json",
    )
    assert sync.status_code == 200, sync.content
    assert MarketplaceCatalogItem.objects.filter(plugin_id="acme.catalog-redacted").exists()

    catalog = client.get("/api/plugins/marketplace/catalog/")

    assert catalog.status_code == 200, catalog.content
    content = catalog.content.decode("utf-8")
    assert "private-key" not in content
    item = catalog.json()["items"][0]
    assert item["source"]["credentials_redacted"] is True
    assert item["source"]["source_url"] == "https://catalog.example/feed.json?api_key=***"
