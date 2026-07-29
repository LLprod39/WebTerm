import json
import zipfile

import pytest

from app.plugins.catalog import DEMO_PLUGIN_MANIFEST
from plugin_marketplace.sandbox_worker import _extract_package
from plugin_marketplace.services.package_service import validate_wtp_package

UNSAFE_WINDOWS_ARCHIVE_PATHS = (
    r"C:\outside.txt",
    r"C:outside.txt",
    r"..\outside.txt",
    r"backend\..\outside.txt",
    r"\rooted\outside.txt",
    r"\\server\share\outside.txt",
    r"\\?\C:\outside.txt",
    "backend/plugin.py:stream",
)


def _write_package(path, member_name: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("webtrerm.plugin.json", json.dumps(DEMO_PLUGIN_MANIFEST))
        archive.writestr(member_name, "untrusted")


@pytest.mark.parametrize("member_name", UNSAFE_WINDOWS_ARCHIVE_PATHS)
def test_package_validation_rejects_windows_archive_path_variants(tmp_path, member_name):
    package = tmp_path / "unsafe.wtp"
    _write_package(package, member_name)

    result = validate_wtp_package(package)

    assert result.ok is False
    assert any(item.code == "unsafe_path" and item.path == member_name for item in result.static_scan.findings)
    assert any(
        item["code"] == "unsafe_path" and item["path"] == member_name for item in result.dependency_scan["blockers"]
    )


@pytest.mark.parametrize("member_name", UNSAFE_WINDOWS_ARCHIVE_PATHS)
def test_sandbox_rejects_unsafe_member_before_writing_files(tmp_path, member_name):
    package = tmp_path / "unsafe.wtp"
    destination = tmp_path / "extracted"
    destination.mkdir()
    _write_package(package, member_name)

    with pytest.raises(ValueError, match="unsafe package path"):
        _extract_package(package, destination)

    assert list(destination.rglob("*")) == []
