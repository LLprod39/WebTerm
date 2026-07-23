import json
import zipfile
from io import BytesIO

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from app.plugins.catalog import DEMO_PLUGIN_MANIFEST
from core_ui.models import UserAppPermission
from plugin_marketplace.models import PluginInstallation, PluginInstallEvent, PluginPackage


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


def _wtp_upload(manifest: dict, name: str = "plugin.wtp") -> SimpleUploadedFile:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("webtrerm.plugin.json", json.dumps(manifest))
        archive.writestr("README.md", "Internal test plugin")
    buffer.seek(0)
    return SimpleUploadedFile(name, buffer.read(), content_type="application/zip")


@pytest.mark.django_db
def test_admin_can_upload_local_package_and_install_disabled():
    user = User.objects.create_user(username="upload-plugin-admin", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)

    manifest = dict(DEMO_PLUGIN_MANIFEST)
    manifest.update(
        {
            "id": "acme.uploaded-extension",
            "name": "Uploaded Extension",
            "slug": "uploaded-extension",
            "publisher": {"id": "acme", "name": "Acme"},
        }
    )

    response = client.post(
        "/api/plugins/packages/install-local-upload/",
        data={"package": _wtp_upload(manifest, "uploaded-extension.wtp")},
    )

    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["plugin_id"] == "acme.uploaded-extension"
    assert payload["status"] == PluginInstallation.STATUS_DISABLED
    installation = PluginInstallation.objects.get(plugin_id="acme.uploaded-extension")
    package = PluginPackage.objects.get(plugin_id="acme.uploaded-extension")
    assert installation.status == PluginInstallation.STATUS_DISABLED
    assert package.source == PluginPackage.SOURCE_LOCAL
    assert package.provenance["retention"]["retained"] is True
    assert PluginInstallEvent.objects.filter(
        plugin_id="acme.uploaded-extension",
        event_type="plugin_package_installed",
    ).exists()


@pytest.mark.django_db
def test_upload_local_package_requires_file():
    user = User.objects.create_user(username="upload-plugin-missing", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)

    response = client.post("/api/plugins/packages/install-local-upload/", data={})

    assert response.status_code == 400
    assert response.json()["code"] == "missing_package"
