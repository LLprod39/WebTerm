from io import StringIO
from pathlib import Path

import pytest
import yaml
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from servers.checks import playbook_bundle_storage_deploy_check
from servers.models import PlaybookAssetBundle
from servers.services.playbooks.bundle_storage import BundleStorageError, MediaRootPlaybookBundleStorage, path_is_within

ROOT = Path(__file__).resolve().parents[1]


def _volume_sources(service: dict) -> set[str]:
    sources: set[str] = set()
    for mount in service.get("volumes", []):
        if isinstance(mount, str):
            sources.add(mount.split(":", 1)[0])
        elif isinstance(mount, dict) and mount.get("source"):
            sources.add(str(mount["source"]))
    return sources


def _volume_target(service: dict, source: str) -> str:
    for mount in service.get("volumes", []):
        if isinstance(mount, str):
            parts = mount.split(":")
            if parts[0] == source and len(parts) >= 2:
                return parts[1]
        elif isinstance(mount, dict) and str(mount.get("source")) == source:
            return str(mount.get("target") or "")
    raise AssertionError(f"Volume {source!r} is not mounted")


def test_default_bundle_root_is_not_public_media():
    assert not path_is_within(settings.PLAYBOOK_BUNDLE_STORAGE_ROOT, settings.MEDIA_ROOT)


def test_production_bundle_storage_fails_closed_inside_media(tmp_path):
    media_root = tmp_path / "media"
    public_bundle_root = media_root / "playbook_bundles"
    with override_settings(
        DEBUG=False,
        MEDIA_ROOT=media_root,
        PLAYBOOK_BUNDLE_STORAGE_ROOT=public_bundle_root,
    ):
        with pytest.raises(BundleStorageError, match="outside MEDIA_ROOT"):
            MediaRootPlaybookBundleStorage()
        errors = playbook_bundle_storage_deploy_check(None)

    assert [error.id for error in errors] == ["servers.E001"]


def test_production_compose_mounts_private_bundles_only_where_required():
    compose = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert "playbook_bundles" in _volume_sources(services["backend"])
    assert "playbook_bundles" in _volume_sources(services["playbook-execution-worker"])
    for service_name in ("backend", "playbook-execution-worker"):
        service = services[service_name]
        assert service["environment"]["PLAYBOOK_BUNDLE_STORAGE_ROOT"] == _volume_target(service, "playbook_bundles")
    for service_name, service in services.items():
        if service_name not in {"backend", "playbook-execution-worker"}:
            assert "playbook_bundles" not in _volume_sources(service), service_name

    assert "playbook_bundles" in compose["volumes"]
    assert "playbook_bundles" not in _volume_sources(services["nginx"])


def test_nginx_explicitly_denies_legacy_playbook_media_paths():
    production = (ROOT / "docker" / "nginx" / "production.conf").read_text(encoding="utf-8")
    development = (ROOT / "docker" / "nginx" / "default.conf").read_text(encoding="utf-8")

    assert production.count("location ^~ /media/playbook_bundles/") == 2
    assert "location = /media/playbook_bundles" in production
    assert "location ^~ /media/playbook_bundles/" in development


@pytest.mark.django_db
def test_legacy_bundle_migration_copies_verifies_and_keeps_source(tmp_path):
    media_root = tmp_path / "media"
    source_root = media_root / "playbook_bundles"
    target_root = tmp_path / "private" / "playbook_bundles"
    storage_key = "ab/0123456789abcdef0123456789abcdef.zip"
    source = source_root / "ab" / "0123456789abcdef0123456789abcdef.zip"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"canonical-playbook-bundle")
    PlaybookAssetBundle.objects.create(
        storage_key=storage_key,
        content_hash="a" * 64,
        size_bytes=len(b"canonical-playbook-bundle"),
        file_count=1,
        scan_status=PlaybookAssetBundle.SCAN_CLEAN,
    )

    output = StringIO()
    with override_settings(
        DEBUG=False,
        MEDIA_ROOT=media_root,
        PLAYBOOK_BUNDLE_STORAGE_ROOT=target_root,
    ):
        call_command("migrate_playbook_bundle_storage", stdout=output)
        call_command("migrate_playbook_bundle_storage", stdout=output)
        call_command("migrate_playbook_bundle_storage", "--verify-only", stdout=output)

    target = target_root / "ab" / source.name
    assert target.read_bytes() == source.read_bytes()
    assert source.read_bytes() == b"canonical-playbook-bundle"
    assert "Legacy source files were not deleted" in output.getvalue()

    target.write_bytes(b"different-private-bytes")
    with (
        override_settings(
            DEBUG=False,
            MEDIA_ROOT=media_root,
            PLAYBOOK_BUNDLE_STORAGE_ROOT=target_root,
        ),
        pytest.raises(CommandError, match="refusing to overwrite"),
    ):
        call_command("migrate_playbook_bundle_storage")
    assert source.read_bytes() == b"canonical-playbook-bundle"
    assert target.read_bytes() == b"different-private-bytes"
