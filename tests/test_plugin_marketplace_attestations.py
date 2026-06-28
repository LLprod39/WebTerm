import copy
import hashlib
import io
import json
import zipfile

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings

from app.plugins.catalog import DEMO_PLUGIN_MANIFEST
from core_ui.models import UserAppPermission
from plugin_marketplace.checks import plugin_marketplace_deploy_check
from plugin_marketplace.models import PluginPackage
from plugin_marketplace.services.package_retention_service import (
    retain_package_bytes,
    retained_package_exists,
)
from plugin_marketplace.services.remote_package_service import RemotePackageError, stage_remote_package_bytes
from plugin_marketplace.services.signing_service import package_signature_status, sign_package


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


def _manifest(plugin_id: str = "acme.attested-remote", version: str = "1.0.0") -> dict:
    manifest = copy.deepcopy(DEMO_PLUGIN_MANIFEST)
    manifest.update({
        "id": plugin_id,
        "name": "Attested Remote",
        "slug": "attested-remote",
        "version": version,
        "publisher": {"id": "acme", "name": "Acme Apps", "verified": True},
    })
    return manifest


def _package_bytes(manifest: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("webtrerm.plugin.json", json.dumps(manifest))
        archive.writestr("README.md", "Remote package attestation test.")
    return buffer.getvalue()


@override_settings(
    DEBUG=False,
    PLUGIN_MARKETPLACE_SIGNING_KEYS={},
    PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID="missing",
    PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS=[],
    PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS=[],
    PLUGIN_MARKETPLACE_REQUIRE_CONFIGURED_SIGNING_KEYS=True,
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER=True,
)
def test_plugin_marketplace_deploy_check_requires_signing_keys_and_remote_host_allowlist():
    errors = plugin_marketplace_deploy_check(None)
    assert {error.id for error in errors} == {
        "plugin_marketplace.E001",
        "plugin_marketplace.E002",
        "plugin_marketplace.E003",
        "plugin_marketplace.E005",
        "plugin_marketplace.E016",
    }


@override_settings(
    DEBUG=False,
    PLUGIN_MARKETPLACE_SIGNING_KEYS={"prod-1": "secret"},
    PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID="prod-1",
    PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS=["packages.example"],
    PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS=["catalog.example"],
    PLUGIN_MARKETPLACE_REQUIRE_CONFIGURED_SIGNING_KEYS=True,
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER=False,
)
def test_plugin_marketplace_deploy_check_accepts_configured_trust_settings():
    assert plugin_marketplace_deploy_check(None) == []


@override_settings(
    DEBUG=False,
    PLUGIN_MARKETPLACE_SIGNING_PROVIDER="external_kms",
    PLUGIN_MARKETPLACE_SIGNING_KEYS={},
    PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID="kms-plugin-prod",
    PLUGIN_MARKETPLACE_EXTERNAL_SIGNING_ENDPOINT="https://kms.example/sign",
    PLUGIN_MARKETPLACE_EXTERNAL_VERIFY_ENDPOINT="https://kms.example/verify",
    PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS=["packages.example"],
    PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS=["catalog.example"],
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER=True,
)
def test_plugin_marketplace_deploy_check_accepts_external_signing_provider():
    assert plugin_marketplace_deploy_check(None) == []


@override_settings(
    DEBUG=False,
    PLUGIN_MARKETPLACE_SIGNING_KEYS={"prod-1": "secret"},
    PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID="prod-1",
    PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS=["packages.example"],
    PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS=["catalog.example"],
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER=False,
    PLUGIN_MARKETPLACE_SECURITY_SCAN_PROVIDER="local_static",
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SECURITY_SCANNER=True,
)
def test_plugin_marketplace_deploy_check_can_require_external_security_scanner():
    assert {error.id for error in plugin_marketplace_deploy_check(None)} == {"plugin_marketplace.E010"}


@override_settings(
    DEBUG=False,
    PLUGIN_MARKETPLACE_SIGNING_KEYS={"prod-1": "secret"},
    PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID="prod-1",
    PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS=["packages.example"],
    PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS=["catalog.example"],
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER=False,
    PLUGIN_MARKETPLACE_SECURITY_SCAN_PROVIDER="external",
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SECURITY_SCANNER=True,
    PLUGIN_MARKETPLACE_EXTERNAL_SECURITY_SCAN_ENDPOINT="https://scanner.example/scan",
)
def test_plugin_marketplace_deploy_check_accepts_external_security_scanner():
    assert plugin_marketplace_deploy_check(None) == []


@override_settings(
    DEBUG=False,
    PLUGIN_MARKETPLACE_SIGNING_KEYS={"prod-1": "secret"},
    PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID="prod-1",
    PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS=["packages.example"],
    PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS=["catalog.example"],
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER=False,
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=False,
)
def test_plugin_marketplace_deploy_check_blocks_partial_sandbox_configuration():
    assert {error.id for error in plugin_marketplace_deploy_check(None)} == {"plugin_marketplace.E015"}


@override_settings(
    DEBUG=False,
    PLUGIN_MARKETPLACE_SIGNING_KEYS={"prod-1": "secret"},
    PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID="prod-1",
    PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS=["packages.example"],
    PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS=["catalog.example"],
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER=False,
    PLUGIN_MARKETPLACE_SANDBOX_DEPENDENCY_ALLOWLIST=["requests"],
)
def test_plugin_marketplace_deploy_check_rejects_invalid_dependency_allowlist():
    assert {error.id for error in plugin_marketplace_deploy_check(None)} == {"plugin_marketplace.E017"}


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_SIGNING_PROVIDER="external_kms",
    PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID="kms-plugin-prod",
    PLUGIN_MARKETPLACE_EXTERNAL_SIGNING_ENDPOINT="https://kms.example/sign",
    PLUGIN_MARKETPLACE_EXTERNAL_VERIFY_ENDPOINT="https://kms.example/verify",
)
def test_external_signing_provider_signs_and_verifies_package(monkeypatch):
    package = PluginPackage.objects.create(
        plugin_id="acme.external-signed",
        version="1.0.0",
        name="External Signed",
        slug="external-signed",
        publisher_id="acme",
        publisher_name="Acme",
        source=PluginPackage.SOURCE_CATALOG,
        package_hash="sha256:external",
        manifest=_manifest(plugin_id="acme.external-signed"),
        review_status=PluginPackage.REVIEW_VERIFIED,
        signature_status=PluginPackage.SIGNATURE_UNSIGNED,
    )

    def _fake_post_json(url: str, payload: dict) -> dict:
        if url.endswith("/sign"):
            return {
                "alg": "external-kms-test",
                "key_id": payload["key_id"],
                "signature": f"signed:{payload['payload']['plugin_id']}:{payload['key_id']}",
                "signer": {"provider": "test-kms"},
            }
        assert url.endswith("/verify")
        return {"valid": payload["signature"] == "signed:acme.external-signed:kms-plugin-prod"}

    monkeypatch.setattr("plugin_marketplace.services.signing_service._post_json", _fake_post_json)

    signed = sign_package(package.id)
    assert signed.signature_status == PluginPackage.SIGNATURE_SIGNED
    assert signed.signature_payload["provider"] == "external_kms"
    assert signed.signature_payload["key_id"] == "kms-plugin-prod"
    assert package_signature_status(signed) == PluginPackage.SIGNATURE_SIGNED

    signed.manifest = {**signed.manifest, "name": "Tampered"}
    assert package_signature_status(signed) == PluginPackage.SIGNATURE_INVALID


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_SIGNING_PROVIDER="external_kms",
    PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID="kms-plugin-prod",
    PLUGIN_MARKETPLACE_EXTERNAL_SIGNING_ENDPOINT="https://kms.example/sign",
    PLUGIN_MARKETPLACE_EXTERNAL_VERIFY_ENDPOINT="https://kms.example/verify",
)
def test_external_signing_provider_rejects_mismatched_key_id(monkeypatch):
    package = PluginPackage.objects.create(
        plugin_id="acme.external-key-mismatch",
        version="1.0.0",
        name="External Key Mismatch",
        slug="external-key-mismatch",
        publisher_id="acme",
        publisher_name="Acme",
        source=PluginPackage.SOURCE_CATALOG,
        package_hash="sha256:external-key-mismatch",
        manifest=_manifest(plugin_id="acme.external-key-mismatch"),
        review_status=PluginPackage.REVIEW_VERIFIED,
        signature_status=PluginPackage.SIGNATURE_UNSIGNED,
    )

    def _fake_post_json(url: str, payload: dict) -> dict:
        return {
            "alg": "external-kms-test",
            "key_id": "different-key",
            "signature": "signed-by-different-key",
        }

    monkeypatch.setattr("plugin_marketplace.services.signing_service._post_json", _fake_post_json)

    with pytest.raises(ValueError, match="mismatched key id"):
        sign_package(package.id)


@pytest.mark.django_db
def test_package_attestation_passes_after_review_and_signing():
    user = User.objects.create_user(username="attestation-admin", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    data = _package_bytes(_manifest())
    sha256 = hashlib.sha256(data).hexdigest()
    stage_remote_package_bytes(
        data=data,
        source_url="https://packages.example/acme.attested-remote.wtp",
        expected_sha256=sha256,
        actor=user,
    )
    package = PluginPackage.objects.get(plugin_id="acme.attested-remote")

    failed = client.post(f"/api/plugins/review/packages/{package.id}/attest/")
    assert failed.status_code == 200, failed.content
    package.refresh_from_db()
    assert package.attestations[-1]["kind"] == "security_gate"
    assert package.attestations[-1]["status"] == "failed"

    reviewed = client.post(
        f"/api/plugins/review/packages/{package.id}/review/",
        data=_json({"status": "verified"}),
        content_type="application/json",
    )
    assert reviewed.status_code == 200, reviewed.content
    attested = client.post(f"/api/plugins/review/packages/{package.id}/attest/")
    assert attested.status_code == 200, attested.content
    package.refresh_from_db()
    assert package.review_status == PluginPackage.REVIEW_VERIFIED
    assert package.signature_status == PluginPackage.SIGNATURE_SIGNED
    assert package.attestations[-1]["status"] == "passed"


@pytest.mark.django_db
def test_package_sbom_export_returns_retained_package_metadata():
    user = User.objects.create_user(username="sbom-export-admin", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    data = _package_bytes(_manifest())
    sha256 = hashlib.sha256(data).hexdigest()
    stage_remote_package_bytes(
        data=data,
        source_url="https://packages.example/acme.attested-remote.wtp",
        expected_sha256=sha256,
        actor=user,
    )
    package = PluginPackage.objects.get(plugin_id="acme.attested-remote")

    exported = client.get(f"/api/plugins/review/packages/{package.id}/sbom/")

    assert exported.status_code == 200, exported.content
    assert "attachment" in exported.headers["Content-Disposition"]
    payload = exported.json()
    assert payload["plugin_id"] == "acme.attested-remote"
    assert payload["sbom"]["summary"]["file_count"] == 2
    assert payload["dependency_scan"]["passed"] is True


@pytest.mark.django_db
def test_package_security_scan_endpoint_records_local_scan_attestation():
    user = User.objects.create_user(username="security-scan-admin", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    data = _package_bytes(_manifest(plugin_id="acme.security-scan"))
    sha256 = hashlib.sha256(data).hexdigest()
    stage_remote_package_bytes(
        data=data,
        source_url="https://packages.example/acme.security-scan.wtp",
        expected_sha256=sha256,
        actor=user,
    )
    package = PluginPackage.objects.get(plugin_id="acme.security-scan")

    scanned = client.post(f"/api/plugins/review/packages/{package.id}/security-scan/")

    assert scanned.status_code == 200, scanned.content
    package.refresh_from_db()
    assert package.attestations[-1]["kind"] == "security_scan"
    assert package.attestations[-1]["status"] == "passed"
    assert package.attestations[-1]["report"]["provider"] == "local_static"


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_SECURITY_SCAN_PROVIDER="external",
    PLUGIN_MARKETPLACE_EXTERNAL_SECURITY_SCAN_ENDPOINT="https://scanner.example/scan",
)
def test_package_security_scan_endpoint_records_external_scan_attestation(monkeypatch):
    user = User.objects.create_user(username="external-security-scan-admin", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    data = _package_bytes(_manifest(plugin_id="acme.external-security-scan"))
    sha256 = hashlib.sha256(data).hexdigest()
    stage_remote_package_bytes(
        data=data,
        source_url="https://packages.example/acme.external-security-scan.wtp",
        expected_sha256=sha256,
        actor=user,
    )
    package = PluginPackage.objects.get(plugin_id="acme.external-security-scan")

    def _fake_scanner(url: str, payload: dict) -> dict:
        assert url == "https://scanner.example/scan"
        assert payload["plugin_id"] == "acme.external-security-scan"
        return {"scanner": "mock-sca", "passed": False, "findings": [{"severity": "high", "id": "CVE-demo"}]}

    monkeypatch.setattr("plugin_marketplace.services.package_security_scan_service._post_json", _fake_scanner)

    scanned = client.post(f"/api/plugins/review/packages/{package.id}/security-scan/")

    assert scanned.status_code == 200, scanned.content
    package.refresh_from_db()
    assert package.attestations[-1]["kind"] == "security_scan"
    assert package.attestations[-1]["status"] == "failed"
    assert package.attestations[-1]["report"]["scanner"] == "mock-sca"
    assert package.attestations[-1]["report"]["findings"][0]["id"] == "CVE-demo"


@pytest.mark.django_db
def test_retention_cleanup_deletes_only_unreferenced_packages():
    user = User.objects.create_user(username="retention-cleanup-admin", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    data = _package_bytes(_manifest())
    sha256 = hashlib.sha256(data).hexdigest()
    stage_remote_package_bytes(
        data=data,
        source_url="https://packages.example/acme.attested-remote.wtp",
        expected_sha256=sha256,
        actor=user,
    )
    package = PluginPackage.objects.get(plugin_id="acme.attested-remote")
    orphan = retain_package_bytes(
        data=b"orphan bytes",
        plugin_id="acme.orphan",
        version="1.0.0",
        sha256=hashlib.sha256(b"orphan bytes").hexdigest(),
        source="test",
    )

    inventory = client.get("/api/plugins/packages/retention/")
    assert inventory.status_code == 200, inventory.content
    assert inventory.json()["retention"]["summary"]["unreferenced_count"] >= 1

    cleaned = client.post(
        "/api/plugins/packages/retention/",
        data=_json({"dry_run": False}),
        content_type="application/json",
    )

    assert cleaned.status_code == 200, cleaned.content
    assert retained_package_exists(orphan) is False
    assert retained_package_exists(package.provenance["retention"]) is True


@pytest.mark.django_db
def test_remote_provenance_replay_passes_without_resetting_review_state(monkeypatch):
    user = User.objects.create_user(username="provenance-admin", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    data = _package_bytes(_manifest())
    sha256 = hashlib.sha256(data).hexdigest()
    stage_remote_package_bytes(
        data=data,
        source_url="https://packages.example/acme.attested-remote.wtp",
        expected_sha256=sha256,
        actor=user,
    )
    package = PluginPackage.objects.get(plugin_id="acme.attested-remote")
    assert client.post(f"/api/plugins/review/packages/{package.id}/review/", data=_json({"status": "verified"}), content_type="application/json").status_code == 200
    package.refresh_from_db()
    signed_payload = dict(package.signature_payload)

    monkeypatch.setattr(
        "plugin_marketplace.services.remote_package_service.fetch_remote_package_bytes",
        lambda _url: data,
    )
    replayed = client.post(f"/api/plugins/review/packages/{package.id}/replay-provenance/")
    assert replayed.status_code == 200, replayed.content
    package.refresh_from_db()
    assert package.review_status == PluginPackage.REVIEW_VERIFIED
    assert package.signature_status == PluginPackage.SIGNATURE_SIGNED
    assert package.signature_payload == signed_payload
    assert package.attestations[-1]["kind"] == "remote_provenance_replay"
    assert package.attestations[-1]["status"] == "passed"
    assert package.attestations[-1]["report"]["checks"][0]["source"] == "remote"


@pytest.mark.django_db
def test_remote_provenance_replay_uses_retained_package_when_remote_unavailable(monkeypatch):
    user = User.objects.create_user(username="provenance-retention-admin", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    data = _package_bytes(_manifest())
    sha256 = hashlib.sha256(data).hexdigest()
    stage_remote_package_bytes(
        data=data,
        source_url="https://packages.example/acme.attested-remote.wtp",
        expected_sha256=sha256,
        actor=user,
    )
    package = PluginPackage.objects.get(plugin_id="acme.attested-remote")
    assert client.post(f"/api/plugins/review/packages/{package.id}/review/", data=_json({"status": "verified"}), content_type="application/json").status_code == 200

    def _unavailable(_url: str) -> bytes:
        raise RemotePackageError("network unavailable")

    monkeypatch.setattr(
        "plugin_marketplace.services.remote_package_service.fetch_remote_package_bytes",
        _unavailable,
    )
    replayed = client.post(f"/api/plugins/review/packages/{package.id}/replay-provenance/")
    assert replayed.status_code == 200, replayed.content
    package.refresh_from_db()
    assert package.review_status == PluginPackage.REVIEW_VERIFIED
    assert package.signature_status == PluginPackage.SIGNATURE_SIGNED
    assert package.attestations[-1]["status"] == "passed"
    assert package.attestations[-1]["report"]["checks"][0]["source"] == "retention"


@pytest.mark.django_db
def test_remote_provenance_replay_invalidates_signed_package_on_hash_mismatch(monkeypatch):
    user = User.objects.create_user(username="provenance-mismatch-admin", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    data = _package_bytes(_manifest())
    sha256 = hashlib.sha256(data).hexdigest()
    stage_remote_package_bytes(
        data=data,
        source_url="https://packages.example/acme.attested-remote.wtp",
        expected_sha256=sha256,
        actor=user,
    )
    package = PluginPackage.objects.get(plugin_id="acme.attested-remote")
    assert client.post(f"/api/plugins/review/packages/{package.id}/review/", data=_json({"status": "verified"}), content_type="application/json").status_code == 200

    changed_data = _package_bytes(_manifest(version="1.0.1"))
    monkeypatch.setattr(
        "plugin_marketplace.services.remote_package_service.fetch_remote_package_bytes",
        lambda _url: changed_data,
    )
    replayed = client.post(f"/api/plugins/review/packages/{package.id}/replay-provenance/")
    assert replayed.status_code == 200, replayed.content
    package.refresh_from_db()
    assert package.review_status == PluginPackage.REVIEW_SUSPENDED
    assert package.signature_status == PluginPackage.SIGNATURE_INVALID
    assert package.attestations[-1]["status"] == "failed"
    assert any(check["name"] == "sha256" and check["ok"] is False for check in package.attestations[-1]["report"]["checks"])
