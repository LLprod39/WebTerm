import copy

import pytest
from django.test import override_settings

from app.plugins.catalog import DEMO_PLUGIN_MANIFEST
from plugin_marketplace.models import PluginPackage
from plugin_marketplace.services.package_security_scan_service import run_package_security_scan
from plugin_marketplace.services.signing_service import canonical_manifest_hash


def _package(*, plugin_id: str = "acme.scanned", slug: str = "scanned") -> PluginPackage:
    manifest = copy.deepcopy(DEMO_PLUGIN_MANIFEST)
    manifest.update(
        {
            "id": plugin_id,
            "name": "Scanned Plugin",
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
    return PluginPackage.objects.create(
        plugin_id=manifest["id"],
        version=manifest["version"],
        name=manifest["name"],
        slug=manifest["slug"],
        publisher_id="acme",
        publisher_name="Acme Apps",
        source=PluginPackage.SOURCE_CATALOG,
        package_hash=canonical_manifest_hash(manifest),
        manifest=manifest,
        sbom={"summary": {"file_count": 1}},
        dependency_scan={"passed": True, "blockers": [], "summary": {}},
        review_status=PluginPackage.REVIEW_VERIFIED,
        signature_status=PluginPackage.SIGNATURE_SIGNED,
    )


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_SECURITY_SCAN_PROVIDER="external",
    PLUGIN_MARKETPLACE_EXTERNAL_SECURITY_SCAN_ENDPOINT="https://scanner.example/scan",
    PLUGIN_MARKETPLACE_SECURITY_SCAN_BLOCK_SEVERITIES=["critical", "high"],
)
def test_external_security_scan_blocks_configured_finding_severity(monkeypatch):
    package = _package()

    def _fake_scanner(url: str, payload: dict) -> dict:
        assert url == "https://scanner.example/scan"
        assert payload["plugin_id"] == package.plugin_id
        return {"scanner": "mock-sca", "passed": True, "findings": [{"severity": "critical", "id": "CVE-critical"}]}

    monkeypatch.setattr("plugin_marketplace.services.package_security_scan_service._post_json", _fake_scanner)

    run_package_security_scan(package.id)

    package.refresh_from_db()
    attestation = package.attestations[-1]
    assert attestation["status"] == "failed"
    assert attestation["report"]["passed"] is False
    assert attestation["report"]["blocked_findings"][0]["id"] == "CVE-critical"


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_SECURITY_SCAN_PROVIDER="external",
    PLUGIN_MARKETPLACE_EXTERNAL_SECURITY_SCAN_ENDPOINT="https://scanner.example/scan",
    PLUGIN_MARKETPLACE_SECURITY_SCAN_BLOCK_SEVERITIES=["critical", "high"],
)
def test_external_security_scan_accepts_clean_status_without_blocking_findings(monkeypatch):
    package = _package(plugin_id="acme.scanned-clean", slug="scanned-clean")

    def _fake_scanner(url: str, payload: dict) -> dict:
        assert payload["plugin_id"] == package.plugin_id
        return {"scanner": "mock-sca", "status": "clean", "findings": [{"severity": "medium", "id": "CVE-medium"}]}

    monkeypatch.setattr("plugin_marketplace.services.package_security_scan_service._post_json", _fake_scanner)

    run_package_security_scan(package.id)

    package.refresh_from_db()
    attestation = package.attestations[-1]
    assert attestation["status"] == "passed"
    assert attestation["report"]["passed"] is True
    assert attestation["report"]["blocked_findings"] == []


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_SECURITY_SCAN_PROVIDER="external",
    PLUGIN_MARKETPLACE_EXTERNAL_SECURITY_SCAN_ENDPOINT="https://scanner.example/scan",
)
def test_external_security_scan_requires_explicit_provider_verdict(monkeypatch):
    package = _package(plugin_id="acme.scanned-no-verdict", slug="scanned-no-verdict")

    def _fake_scanner(url: str, payload: dict) -> dict:
        assert payload["plugin_id"] == package.plugin_id
        return {"scanner": "mock-sca", "findings": []}

    monkeypatch.setattr("plugin_marketplace.services.package_security_scan_service._post_json", _fake_scanner)

    run_package_security_scan(package.id)

    package.refresh_from_db()
    attestation = package.attestations[-1]
    assert attestation["status"] == "failed"
    assert attestation["report"]["passed"] is False
    assert attestation["report"]["verdict_present"] is False
    assert attestation["report"]["findings"] == []
