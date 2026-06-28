import copy
import hashlib
import io
import json
import zipfile

import pytest
from django.contrib.auth.models import User

from app.plugins.catalog import DEMO_PLUGIN_MANIFEST
from plugin_marketplace.models import PluginInstallEvent, PluginInstallation, PluginPackage
from plugin_marketplace.services.package_retention_service import retained_package_exists
from plugin_marketplace.services.remote_package_service import (
    RemotePackageError,
    fetch_remote_package_bytes,
    stage_remote_package_bytes,
)


def _remote_manifest() -> dict:
    manifest = copy.deepcopy(DEMO_PLUGIN_MANIFEST)
    manifest.update({
        "id": "acme.remote-alerts",
        "name": "Remote Alerts",
        "slug": "remote-alerts",
        "version": "1.0.0",
        "publisher": {"id": "acme", "name": "Acme Apps", "verified": True},
    })
    return manifest


def _package_bytes(manifest: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("webtrerm.plugin.json", json.dumps(manifest))
        archive.writestr("README.md", "Remote package test.")
    return buffer.getvalue()


@pytest.mark.django_db
def test_remote_package_bytes_stage_disabled_with_provenance():
    user = User.objects.create_user(username="remote-package-admin", password="x", is_staff=True)
    data = _package_bytes(_remote_manifest())
    sha256 = hashlib.sha256(data).hexdigest()

    installation = stage_remote_package_bytes(
        data=data,
        source_url="https://packages.example/acme.remote-alerts.wtp",
        expected_sha256=sha256,
        actor=user,
    )

    assert installation.status == PluginInstallation.STATUS_DISABLED
    package = PluginPackage.objects.get(plugin_id="acme.remote-alerts")
    assert package.source == PluginPackage.SOURCE_CATALOG
    assert package.package_hash == sha256
    assert package.review_status == PluginPackage.REVIEW_PENDING
    assert package.signature_status == PluginPackage.SIGNATURE_UNSIGNED
    assert package.provenance["source_url"] == "https://packages.example/acme.remote-alerts.wtp"
    assert package.provenance["downloaded_sha256"] == sha256
    assert package.provenance["retention"]["retained"] is True
    assert retained_package_exists(package.provenance["retention"]) is True
    assert package.sbom["summary"]["file_count"] == 2
    assert package.dependency_scan["passed"] is True
    assert PluginInstallEvent.objects.filter(plugin_id="acme.remote-alerts", event_type="plugin_remote_package_staged").exists()


@pytest.mark.django_db
def test_remote_package_hash_mismatch_does_not_stage_package():
    data = _package_bytes(_remote_manifest())

    with pytest.raises(RemotePackageError, match="hash does not match"):
        stage_remote_package_bytes(
            data=data,
            source_url="https://packages.example/acme.remote-alerts.wtp",
            expected_sha256="0" * 64,
        )

    assert not PluginPackage.objects.filter(plugin_id="acme.remote-alerts").exists()


def test_remote_package_download_requires_https():
    with pytest.raises(RemotePackageError, match="HTTPS"):
        fetch_remote_package_bytes("http://packages.example/acme.remote-alerts.wtp")
