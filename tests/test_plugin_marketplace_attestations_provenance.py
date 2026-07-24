import copy
import hashlib
import io
import json
import zipfile

import pytest
from django.contrib.auth.models import User
from django.test import Client

from app.plugins.catalog import DEMO_PLUGIN_MANIFEST
from core_ui.models import UserAppPermission
from plugin_marketplace.models import PluginPackage
from plugin_marketplace.services.package_retention_service import (
    retain_package_bytes,
    retained_package_exists,
)
from plugin_marketplace.services.remote_package_service import RemotePackageError, stage_remote_package_bytes


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
    manifest.update(
        {
            "id": plugin_id,
            "name": "Attested Remote",
            "slug": "attested-remote",
            "version": version,
            "publisher": {"id": "acme", "name": "Acme Apps", "verified": True},
        }
    )
    return manifest


def _package_bytes(manifest: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("webtrerm.plugin.json", json.dumps(manifest))
        archive.writestr("README.md", "Remote package attestation test.")
    return buffer.getvalue()


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
    assert (
        client.post(
            f"/api/plugins/review/packages/{package.id}/review/",
            data=_json({"status": "verified"}),
            content_type="application/json",
        ).status_code
        == 200
    )
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
    assert (
        client.post(
            f"/api/plugins/review/packages/{package.id}/review/",
            data=_json({"status": "verified"}),
            content_type="application/json",
        ).status_code
        == 200
    )

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
    assert (
        client.post(
            f"/api/plugins/review/packages/{package.id}/review/",
            data=_json({"status": "verified"}),
            content_type="application/json",
        ).status_code
        == 200
    )

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
    assert any(
        check["name"] == "sha256" and check["ok"] is False for check in package.attestations[-1]["report"]["checks"]
    )
