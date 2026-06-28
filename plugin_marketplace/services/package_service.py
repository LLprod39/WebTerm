from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from django.db import transaction
from django.conf import settings

from app.plugins.validation import PluginValidationError, validate_plugin_manifest
from core_ui.models import UserActivityLog
from plugin_marketplace.models import PluginInstallation, PluginPackage
from plugin_marketplace.services.package_analysis_service import analyze_wtp_archive
from plugin_marketplace.services.package_retention_service import retain_package_file
from plugin_marketplace.services.static_scan_service import (
    StaticScanResult,
    combine_scan_results,
    scan_manifest,
    scan_package_entries,
)

MANIFEST_NAME = "webtrerm.plugin.json"


class PluginPackageValidationError(ValueError):
    pass


@dataclass(frozen=True)
class PackageValidationResult:
    ok: bool
    manifest: dict[str, Any]
    plugin_id: str
    version: str
    sha256: str
    file_count: int
    static_scan: StaticScanResult
    sbom: dict[str, Any]
    dependency_scan: dict[str, Any]
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _zip_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_wtp_package(path: str | Path) -> PackageValidationResult:
    package_path = Path(path)
    errors: list[str] = []
    warnings: list[str] = []
    if not package_path.exists():
        raise PluginPackageValidationError(f"Package does not exist: {package_path}")
    if not zipfile.is_zipfile(package_path):
        raise PluginPackageValidationError("Plugin package must be a zip archive.")

    allow_sandboxed_code = bool(getattr(settings, "PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES", False))
    allow_dynamic_frontend_bundles = bool(getattr(settings, "PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES", False))
    analysis = analyze_wtp_archive(package_path, allow_sandboxed_code=allow_sandboxed_code)
    with zipfile.ZipFile(package_path) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        manifest_names = [info.filename for info in infos if PurePosixPath(info.filename).name == MANIFEST_NAME]
        if not manifest_names:
            raise PluginPackageValidationError(f"Package must contain {MANIFEST_NAME}.")
        manifest_name = MANIFEST_NAME if MANIFEST_NAME in manifest_names else manifest_names[0]

        entry_scan = scan_package_entries(
            [(info.filename, info.file_size) for info in infos],
            allow_sandboxed_code=allow_sandboxed_code,
        )
        for finding in entry_scan.findings:
            message = f"{finding.message}: {finding.path}".rstrip(": ")
            if finding.severity == "blocker":
                errors.append(message)
            else:
                warnings.append(message)

        raw_manifest = archive.read(manifest_name)
    try:
        manifest_json = json.loads(raw_manifest.decode("utf-8"))
        manifest = validate_plugin_manifest(manifest_json)
        manifest_scan = scan_manifest(
            manifest.to_dict(include_surfaces=True),
            allow_sandboxed_code=allow_sandboxed_code,
            allow_dynamic_frontend_bundles=allow_dynamic_frontend_bundles,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, PluginValidationError) as exc:
        errors.append(str(exc))
        manifest_json = {}
        manifest_scan = StaticScanResult(passed=False)
        plugin_id = ""
        version = ""
    else:
        plugin_id = manifest.id
        version = manifest.version
    static_scan = combine_scan_results(entry_scan, manifest_scan)
    for finding in static_scan.findings:
        if finding.severity != "blocker":
            continue
        message = f"{finding.message}: {finding.path}".rstrip(": ")
        if message not in errors:
            errors.append(message)
    for blocker in analysis["dependency_scan"].get("blockers", []):
        message = f"Dependency scan blocker {blocker.get('code')}: {blocker.get('path')}".rstrip(": ")
        if message not in errors:
            errors.append(message)

    return PackageValidationResult(
        ok=not errors,
        manifest=manifest_json if isinstance(manifest_json, dict) else {},
        plugin_id=plugin_id,
        version=version,
        sha256=_zip_sha256(package_path),
        file_count=len(infos),
        static_scan=static_scan,
        sbom=analysis["sbom"],
        dependency_scan=analysis["dependency_scan"],
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


@transaction.atomic
def install_local_package(path: str | Path, *, actor=None, request=None) -> PluginInstallation:
    result = validate_wtp_package(path)
    if not result.ok:
        raise PluginPackageValidationError("; ".join(result.errors))
    manifest = validate_plugin_manifest(result.manifest)
    retention = retain_package_file(
        path,
        plugin_id=manifest.id,
        version=manifest.version,
        sha256=result.sha256,
        source=PluginPackage.SOURCE_LOCAL,
    )
    package, _created = PluginPackage.objects.update_or_create(
        plugin_id=manifest.id,
        version=manifest.version,
        defaults={
            "name": manifest.name,
            "slug": manifest.slug,
            "publisher_id": manifest.publisher.id,
            "publisher_name": manifest.publisher.name,
            "source": PluginPackage.SOURCE_LOCAL,
            "package_hash": result.sha256,
            "provenance": {"source": "local_file", "retention": retention},
            "sbom": result.sbom,
            "dependency_scan": result.dependency_scan,
            "manifest": manifest.to_dict(include_surfaces=True),
            "risk_tier": manifest.risk_tier,
            "review_status": PluginPackage.REVIEW_PENDING,
            "signature_status": PluginPackage.SIGNATURE_UNSIGNED,
        },
    )
    installation, _created = PluginInstallation.objects.update_or_create(
        plugin_id=manifest.id,
        defaults={
            "package": package,
            "status": PluginInstallation.STATUS_DISABLED,
            "installed_by": actor if getattr(actor, "is_authenticated", False) else None,
        },
    )
    from plugin_marketplace.services.install_service import record_event

    record_event(
        plugin_id=manifest.id,
        event_type="plugin_package_installed",
        status=UserActivityLog.STATUS_SUCCESS,
        actor=actor,
        request=request,
        installation=installation,
        message=f"Plugin package {manifest.id}@{manifest.version} installed disabled.",
        metadata={"sha256": result.sha256, "file_count": result.file_count},
    )
    return installation
