import copy
import json
import zipfile
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from app.plugins.catalog import DEMO_PLUGIN_MANIFEST
from plugin_marketplace.checks import plugin_marketplace_deploy_check
from plugin_marketplace.models import MarketplaceCatalogItem, MarketplaceSource, PluginInstallation, PluginPackage
from plugin_marketplace.services.catalog_service import compatibility_report
from plugin_marketplace.services.install_service import set_installation_status
from plugin_marketplace.services.lifecycle_service import installation_impact
from plugin_marketplace.services.package_attestation_service import append_package_attestation
from plugin_marketplace.services.package_service import install_local_package


def _manifest(*, plugin_id: str = "acme.attested", slug: str = "attested") -> dict:
    manifest = copy.deepcopy(DEMO_PLUGIN_MANIFEST)
    manifest.update(
        {
            "id": plugin_id,
            "name": "Attested Plugin",
            "slug": slug,
            "version": "1.0.0",
            "publisher": {"id": "acme", "name": "Acme Apps", "verified": True},
            "permissions": [],
            "secrets": [],
            "egress": [],
            "surfaces": {},
            "actions": [],
        }
    )
    return manifest


def _install_reviewed_package(tmp_path, manifest: dict) -> tuple[PluginInstallation, PluginPackage]:
    package_path = tmp_path / f"{manifest['slug']}.wtp"
    with zipfile.ZipFile(package_path, "w") as archive:
        archive.writestr("webtrerm.plugin.json", json.dumps(manifest))
    installation = install_local_package(package_path)
    package = PluginPackage.objects.get(plugin_id=manifest["id"])
    package.review_status = PluginPackage.REVIEW_VERIFIED
    package.signature_status = PluginPackage.SIGNATURE_SIGNED
    package.save(update_fields=["review_status", "signature_status", "updated_at"])
    return installation, package


def _catalog_item(manifest: dict) -> MarketplaceCatalogItem:
    source = MarketplaceSource.objects.create(name="Attested Catalog", source_url="local://attested")
    return MarketplaceCatalogItem.objects.create(
        source=source,
        plugin_id=manifest["id"],
        version=manifest["version"],
        manifest=manifest,
        compatibility={"api_versions": ["plugins.v1"]},
        review_status=PluginPackage.REVIEW_VERIFIED,
        signature_status=PluginPackage.SIGNATURE_SIGNED,
    )


@pytest.mark.django_db
@override_settings(PLUGIN_MARKETPLACE_REQUIRED_ATTESTATION_KINDS=["security_scan"])
def test_required_attestation_blocks_plugin_enable(tmp_path):
    installation, _package = _install_reviewed_package(tmp_path, _manifest())

    with pytest.raises(ValueError) as exc:
        set_installation_status(installation.id, enable=True)

    assert "Attestation policy: Required attestation missing: security_scan." in str(exc.value)


@pytest.mark.django_db
@override_settings(PLUGIN_MARKETPLACE_REQUIRED_ATTESTATION_KINDS=["security_scan"])
def test_passed_required_attestation_allows_plugin_enable(tmp_path):
    installation, package = _install_reviewed_package(tmp_path, _manifest(plugin_id="acme.attested-ok", slug="attested-ok"))
    append_package_attestation(package, kind="security_scan", status="passed", report={"scanner": "test"})

    enabled = set_installation_status(installation.id, enable=True)

    assert enabled.status == PluginInstallation.STATUS_ENABLED
    impact = installation_impact(enabled)
    assert impact["package"]["attestation_policy"]["allowed"] is True
    assert impact["package"]["ready_to_enable"] is True


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_REQUIRED_ATTESTATION_KINDS=["security_scan"],
    PLUGIN_MARKETPLACE_ATTESTATION_MAX_AGE_DAYS=1,
)
def test_stale_required_attestation_blocks_plugin_enable(tmp_path):
    installation, package = _install_reviewed_package(tmp_path, _manifest(plugin_id="acme.attested-stale", slug="attested-stale"))
    attestation = append_package_attestation(package, kind="security_scan", status="passed", report={"scanner": "test"})
    attestation["created_at"] = (timezone.now() - timedelta(days=3)).isoformat()
    package.attestations = [attestation]
    package.save(update_fields=["attestations", "updated_at"])

    with pytest.raises(ValueError) as exc:
        set_installation_status(installation.id, enable=True)

    assert "Attestation policy: Required attestation stale: security_scan." in str(exc.value)


@pytest.mark.django_db
@override_settings(PLUGIN_MARKETPLACE_REQUIRED_ATTESTATION_KINDS=["security_scan"])
def test_catalog_compatibility_requires_matching_package_attestation(tmp_path):
    manifest = _manifest(plugin_id="acme.attested-catalog", slug="attested-catalog")
    _installation, package = _install_reviewed_package(tmp_path, manifest)
    item = _catalog_item(manifest)

    blocked = compatibility_report(item)
    assert blocked["compatible"] is False
    assert "Attestation policy: Required attestation missing: security_scan." in blocked["errors"]

    append_package_attestation(package, kind="security_scan", status="passed", report={"scanner": "test"})
    allowed = compatibility_report(item)

    assert allowed["compatible"] is True
    assert allowed["attestation_policy"]["allowed"] is True


@override_settings(
    DEBUG=False,
    PLUGIN_MARKETPLACE_SIGNING_KEYS={"prod-1": "secret"},
    PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID="prod-1",
    PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS=["packages.example"],
    PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS=["catalog.example"],
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER=False,
    PLUGIN_MARKETPLACE_REQUIRED_ATTESTATION_KINDS=["Bad Kind"],
)
def test_deploy_check_rejects_invalid_required_attestation_kind():
    assert {error.id for error in plugin_marketplace_deploy_check(None)} == {"plugin_marketplace.E020"}
