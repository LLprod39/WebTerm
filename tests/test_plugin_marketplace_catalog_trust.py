import copy

import pytest

from app.plugins.catalog import DEMO_PLUGIN_MANIFEST
from plugin_marketplace.models import MarketplaceCatalogItem, MarketplaceSource, PluginInstallation, PluginPackage
from plugin_marketplace.services.catalog_service import install_catalog_item, sync_catalog_payload
from plugin_marketplace.services.signing_service import canonical_manifest_hash, package_signature_status, sign_package


def _manifest() -> dict:
    manifest = copy.deepcopy(DEMO_PLUGIN_MANIFEST)
    manifest.update(
        {
            "id": "acme.catalog-trust",
            "name": "Catalog Trust",
            "slug": "catalog-trust",
            "version": "1.0.0",
            "publisher": {"id": "acme", "name": "Acme"},
        }
    )
    return manifest


@pytest.mark.django_db
def test_catalog_sync_does_not_trust_claimed_review_or_signature_status():
    source = MarketplaceSource.objects.create(name="Untrusted Catalog", source_url="local://untrusted")

    sync_catalog_payload(
        source,
        {
            "plugins": [
                {
                    "manifest": _manifest(),
                    "review_status": PluginPackage.REVIEW_VERIFIED,
                    "signature_status": PluginPackage.SIGNATURE_SIGNED,
                }
            ]
        },
    )

    item = MarketplaceCatalogItem.objects.get(source=source)
    assert item.review_status == PluginPackage.REVIEW_PENDING
    assert item.signature_status == PluginPackage.SIGNATURE_UNSIGNED


@pytest.mark.django_db
def test_self_asserted_catalog_item_cannot_install_without_trusted_package():
    manifest = _manifest()
    source = MarketplaceSource.objects.create(name="Forged Catalog", source_url="local://forged")
    item = MarketplaceCatalogItem.objects.create(
        source=source,
        plugin_id=manifest["id"],
        version=manifest["version"],
        manifest=manifest,
        compatibility={"api_versions": ["plugins.v1"]},
        review_status=PluginPackage.REVIEW_VERIFIED,
        signature_status=PluginPackage.SIGNATURE_SIGNED,
    )

    with pytest.raises(ValueError, match="trusted package record"):
        install_catalog_item(item.id)

    assert not PluginPackage.objects.filter(plugin_id=manifest["id"]).exists()
    assert not PluginInstallation.objects.filter(plugin_id=manifest["id"]).exists()


@pytest.mark.django_db
def test_manifest_hash_without_signature_payload_is_not_a_signature():
    manifest = _manifest()
    package = PluginPackage.objects.create(
        plugin_id=manifest["id"],
        version=manifest["version"],
        name=manifest["name"],
        slug=manifest["slug"],
        publisher_id="acme",
        publisher_name="Acme",
        source=PluginPackage.SOURCE_CATALOG,
        package_hash=canonical_manifest_hash(manifest),
        manifest=manifest,
        review_status=PluginPackage.REVIEW_VERIFIED,
        signature_status=PluginPackage.SIGNATURE_SIGNED,
        signature_payload={},
    )

    assert package_signature_status(package) == PluginPackage.SIGNATURE_INVALID


@pytest.mark.django_db
def test_catalog_install_reuses_locally_reviewed_and_signed_package():
    manifest = _manifest()
    source = MarketplaceSource.objects.create(name="Reviewed Catalog", source_url="local://reviewed")
    item = MarketplaceCatalogItem.objects.create(
        source=source,
        plugin_id=manifest["id"],
        version=manifest["version"],
        manifest=manifest,
        compatibility={"api_versions": ["plugins.v1"]},
    )
    package = PluginPackage.objects.create(
        plugin_id=manifest["id"],
        version=manifest["version"],
        name=manifest["name"],
        slug=manifest["slug"],
        publisher_id="acme",
        publisher_name="Acme",
        source=PluginPackage.SOURCE_CATALOG,
        package_hash="sha256:reviewed-package",
        manifest=manifest,
        review_status=PluginPackage.REVIEW_VERIFIED,
        signature_status=PluginPackage.SIGNATURE_UNSIGNED,
    )
    package = sign_package(package.id)

    installation = install_catalog_item(item.id)

    assert installation.package_id == package.id
    assert installation.status == PluginInstallation.STATUS_DISABLED
    package.refresh_from_db()
    assert package_signature_status(package) == PluginPackage.SIGNATURE_SIGNED
