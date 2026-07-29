from __future__ import annotations

import hashlib
import json
import re
import tomllib
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from plugin_marketplace.archive_paths import is_safe_archive_member
from plugin_marketplace.services.dependency_policy_service import (
    configured_sandbox_dependency_allowlist,
    dependency_policy_blockers,
    normalize_dependency_allowlist,
)

DEPENDENCY_MANIFEST_NAMES = {
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
}
PARSED_DEPENDENCY_MANIFEST_NAMES = {"requirements.txt", "pyproject.toml", "package.json"}
EXECUTABLE_SUFFIXES = (".py", ".pyc", ".pyd", ".ps1", ".bat", ".cmd", ".sh", ".exe", ".dll", ".so", ".dylib")
INSTALL_SCRIPT_NAMES = {"install.sh", "postinstall.sh", "setup.py", "manage.py"}
REQUIREMENT_NAME_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dependency_from_requirement(line: str) -> str:
    stripped = line.split("#", 1)[0].strip()
    if not stripped or stripped.startswith(("-", "git+", "http://", "https://")):
        return ""
    match = REQUIREMENT_NAME_RE.match(stripped)
    return match.group(1).lower() if match else ""


def _parse_requirements(raw: bytes) -> list[dict[str, Any]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return []
    dependencies = []
    for line in text.splitlines():
        name = _dependency_from_requirement(line)
        if name:
            dependencies.append({"ecosystem": "python", "name": name, "source": "requirements.txt"})
    return dependencies


def _parse_pyproject(raw: bytes) -> list[dict[str, Any]]:
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return []
    project = data.get("project") if isinstance(data.get("project"), dict) else {}
    raw_dependencies = project.get("dependencies") if isinstance(project.get("dependencies"), list) else []
    dependencies = []
    for item in raw_dependencies:
        name = _dependency_from_requirement(str(item))
        if name:
            dependencies.append({"ecosystem": "python", "name": name, "source": "pyproject.toml"})
    optional = project.get("optional-dependencies") if isinstance(project.get("optional-dependencies"), dict) else {}
    for group_items in optional.values():
        if not isinstance(group_items, list):
            continue
        for item in group_items:
            name = _dependency_from_requirement(str(item))
            if name:
                dependencies.append({"ecosystem": "python", "name": name, "source": "pyproject.toml", "optional": True})
    return dependencies


def _parse_package_json(raw: bytes) -> list[dict[str, Any]]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    dependencies = []
    for field in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        values = data.get(field) if isinstance(data.get(field), dict) else {}
        for name, version in values.items():
            dependencies.append(
                {
                    "ecosystem": "npm",
                    "name": str(name),
                    "version": str(version),
                    "source": "package.json",
                    "scope": field,
                }
            )
    return dependencies


def _parse_dependency_manifest(name: str, raw: bytes) -> list[dict[str, Any]]:
    basename = PurePosixPath(name).name.lower()
    if basename == "requirements.txt":
        return _parse_requirements(raw)
    if basename == "pyproject.toml":
        return _parse_pyproject(raw)
    if basename == "package.json":
        return _parse_package_json(raw)
    return []


def _sandbox_code_entry_allowed(name: str) -> bool:
    lowered = str(PurePosixPath(name)).lower()
    return lowered.startswith("backend/") and lowered.endswith(".py")


def analyze_wtp_archive(
    path: str | Path,
    *,
    allow_sandboxed_code: bool = False,
    dependency_allowlist: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    package_path = Path(path)
    files = []
    dependency_manifests = []
    dependencies = []
    blockers = []
    warnings = []
    allowlist = (
        normalize_dependency_allowlist(dependency_allowlist)
        if dependency_allowlist is not None
        else configured_sandbox_dependency_allowlist()
    )

    with zipfile.ZipFile(package_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            raw = archive.read(info.filename)
            basename = PurePosixPath(info.filename).name.lower()
            safe_path = is_safe_archive_member(info.filename)
            file_record = {
                "path": info.filename,
                "size": info.file_size,
                "sha256": _sha256(raw),
                "safe_path": safe_path,
            }
            files.append(file_record)
            if not safe_path:
                blockers.append({"code": "unsafe_path", "path": info.filename})
            if basename in INSTALL_SCRIPT_NAMES or (
                basename.endswith(EXECUTABLE_SUFFIXES)
                and not (allow_sandboxed_code and _sandbox_code_entry_allowed(info.filename))
            ):
                blockers.append({"code": "executable_or_install_file", "path": info.filename})
            if basename in DEPENDENCY_MANIFEST_NAMES:
                manifest_dependencies = _parse_dependency_manifest(info.filename, raw)
                dependency_manifests.append(
                    {
                        "path": info.filename,
                        "sha256": file_record["sha256"],
                        "dependencies_found": len(manifest_dependencies),
                        "parse_supported": basename in PARSED_DEPENDENCY_MANIFEST_NAMES,
                    }
                )
                dependencies.extend(manifest_dependencies)
            if info.file_size > 2 * 1024 * 1024:
                warnings.append({"code": "large_entry", "path": info.filename, "size": info.file_size})

    blockers.extend(
        dependency_policy_blockers(
            dependencies=dependencies,
            dependency_manifests=dependency_manifests,
            allow_sandboxed_code=allow_sandboxed_code,
            allowlist=allowlist,
        )
    )

    dependency_scan = {
        "passed": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "policy": {
            "allow_sandboxed_code": allow_sandboxed_code,
            "allowlist_count": len(allowlist),
        },
        "summary": {
            "dependency_manifest_count": len(dependency_manifests),
            "dependency_count": len(dependencies),
            "blocked_file_count": len(blockers),
        },
        "dependency_manifests": dependency_manifests,
        "dependencies": dependencies[:200],
        "truncated": len(dependencies) > 200,
    }
    sbom = {
        "format": "webtrerm.plugin.sbom.v1",
        "files": files[:500],
        "components": dependencies[:200],
        "dependency_manifests": dependency_manifests,
        "summary": {
            "file_count": len(files),
            "component_count": len(dependencies),
            "dependency_manifest_count": len(dependency_manifests),
        },
        "truncated": len(files) > 500 or len(dependencies) > 200,
    }
    return {"sbom": sbom, "dependency_scan": dependency_scan}
