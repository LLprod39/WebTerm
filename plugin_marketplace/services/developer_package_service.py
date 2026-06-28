from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from django.conf import settings

from app.plugins.validation import PluginValidationError, validate_plugin_manifest
from plugin_marketplace.services.package_service import (
    MANIFEST_NAME,
    PluginPackageValidationError,
    validate_wtp_package,
)
from plugin_marketplace.services.source_dependency_scan_service import analyze_plugin_source_dependencies
from plugin_marketplace.services.static_scan_service import (
    StaticScanResult,
    combine_scan_results,
    scan_manifest,
    scan_package_entries,
)

EXCLUDED_DIRS = {".git", ".hg", ".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__", "dist", "node_modules", "venv", ".venv"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)
SAFE_FILENAME_RE = re.compile(r"[^a-z0-9_.-]+")


@dataclass(frozen=True)
class SourceValidationResult:
    ok: bool
    manifest: dict[str, Any]
    plugin_id: str
    version: str
    file_count: int
    static_scan: StaticScanResult
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "plugin_id": self.plugin_id,
            "version": self.version,
            "file_count": self.file_count,
            "static_scan": self.static_scan.to_dict(),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class PackedPluginResult:
    path: Path
    plugin_id: str
    version: str
    sha256: str
    file_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "plugin_id": self.plugin_id,
            "version": self.version,
            "sha256": self.sha256,
            "file_count": self.file_count,
        }


def _allow_sandboxed_code() -> bool:
    return bool(getattr(settings, "PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES", False))


def _allow_dynamic_frontend_bundles() -> bool:
    return bool(getattr(settings, "PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES", False))


def _should_skip(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if any(part in EXCLUDED_DIRS for part in rel.parts):
        return True
    return path.suffix.lower() in EXCLUDED_SUFFIXES


def _source_files(source_dir: Path) -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for path in source_dir.rglob("*"):
        if not path.is_file() or _should_skip(path, source_dir):
            continue
        relative = path.relative_to(source_dir).as_posix()
        files.append((path, relative))
    return sorted(files, key=lambda item: item[1])


def _safe_archive_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(path.parts) and not path.is_absolute() and ".." not in path.parts and "\\" not in name


def _package_filename(manifest: dict[str, Any]) -> str:
    publisher = manifest.get("publisher") if isinstance(manifest.get("publisher"), dict) else {}
    publisher_id = str(publisher.get("id") or "publisher").lower()
    slug = str(manifest.get("slug") or "plugin").lower()
    stem = SAFE_FILENAME_RE.sub("-", f"webtrerm-plugin-{publisher_id}-{slug}").strip("-.")
    return f"{stem or 'webtrerm-plugin'}.wtp"


def validate_plugin_source_dir(path: str | Path) -> SourceValidationResult:
    source_dir = Path(path)
    if not source_dir.exists():
        raise PluginPackageValidationError(f"Plugin source directory does not exist: {source_dir}")
    if not source_dir.is_dir():
        raise PluginPackageValidationError(f"Plugin source path must be a directory: {source_dir}")

    files = _source_files(source_dir)
    errors: list[str] = []
    warnings: list[str] = []
    for _path, relative in files:
        if not _safe_archive_name(relative):
            errors.append(f"Source file path is unsafe: {relative}")

    manifest_path = source_dir / MANIFEST_NAME
    if not manifest_path.exists():
        raise PluginPackageValidationError(f"Plugin source directory must contain {MANIFEST_NAME} at its root.")

    entry_scan = scan_package_entries(
        [(relative, path.stat().st_size) for path, relative in files],
        allow_sandboxed_code=_allow_sandboxed_code(),
    )
    for finding in entry_scan.findings:
        message = f"{finding.message}: {finding.path}".rstrip(": ")
        if finding.severity == "blocker":
            errors.append(message)
        else:
            warnings.append(message)

    try:
        raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = validate_plugin_manifest(raw_manifest)
        manifest_payload = manifest.to_dict(include_surfaces=True)
        manifest_scan = scan_manifest(
            manifest_payload,
            allow_sandboxed_code=_allow_sandboxed_code(),
            allow_dynamic_frontend_bundles=_allow_dynamic_frontend_bundles(),
        )
        plugin_id = manifest.id
        version = manifest.version
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, PluginValidationError) as exc:
        raw_manifest = {}
        manifest_scan = StaticScanResult(passed=False)
        plugin_id = ""
        version = ""
        errors.append(str(exc))

    static_scan = combine_scan_results(entry_scan, manifest_scan)
    for finding in static_scan.findings:
        if finding.severity != "blocker":
            continue
        message = f"{finding.message}: {finding.path}".rstrip(": ")
        if message not in errors:
            errors.append(message)

    dependency_scan = analyze_plugin_source_dependencies(files, allow_sandboxed_code=_allow_sandboxed_code())[
        "dependency_scan"
    ]
    for blocker in dependency_scan.get("blockers", []):
        code = str(blocker.get("code") or "dependency_policy_blocker")
        detail = str(blocker.get("dependency") or blocker.get("path") or blocker.get("source") or "").strip()
        message = f"Dependency scan blocker {code}: {detail}".rstrip(": ")
        if message not in errors:
            errors.append(message)

    return SourceValidationResult(
        ok=not errors,
        manifest=raw_manifest if isinstance(raw_manifest, dict) else {},
        plugin_id=plugin_id,
        version=version,
        file_count=len(files),
        static_scan=static_scan,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _write_zip_entry(archive: zipfile.ZipFile, path: Path, relative: str) -> None:
    info = zipfile.ZipInfo(relative, date_time=ZIP_DATE_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, path.read_bytes())


def pack_plugin_source(
    path: str | Path,
    *,
    output_dir: str | Path | None = None,
    output_path: str | Path | None = None,
    overwrite: bool = False,
) -> PackedPluginResult:
    source_dir = Path(path)
    result = validate_plugin_source_dir(source_dir)
    if not result.ok:
        raise PluginPackageValidationError("; ".join(result.errors))

    if output_path is not None:
        destination = Path(output_path)
    else:
        base_dir = Path(output_dir) if output_dir is not None else source_dir / "dist"
        destination = base_dir / _package_filename(result.manifest)
    if destination.exists() and not overwrite:
        raise PluginPackageValidationError(f"Package already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    temp_path = destination.with_name(f".{destination.name}.tmp")
    if temp_path.exists():
        temp_path.unlink()
    try:
        with zipfile.ZipFile(temp_path, "w") as archive:
            for file_path, relative in _source_files(source_dir):
                _write_zip_entry(archive, file_path, relative)
        package_result = validate_wtp_package(temp_path)
        if not package_result.ok:
            raise PluginPackageValidationError("; ".join(package_result.errors))
        temp_path.replace(destination)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise

    return PackedPluginResult(
        path=destination,
        plugin_id=package_result.plugin_id,
        version=package_result.version,
        sha256=package_result.sha256,
        file_count=package_result.file_count,
    )
