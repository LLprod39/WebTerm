from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Iterable

from django.conf import settings

SUPPORTED_DEPENDENCY_MANIFEST_NAMES = {"requirements.txt", "pyproject.toml", "package.json"}


def normalize_dependency_allowlist(values: Iterable[str] | None) -> set[str]:
    normalized: set[str] = set()
    for item in values or []:
        value = str(item or "").strip().lower()
        if ":" not in value:
            continue
        ecosystem, name = value.split(":", 1)
        ecosystem = ecosystem.strip()
        name = name.strip()
        if ecosystem and name:
            normalized.add(f"{ecosystem}:{name}")
    return normalized


def invalid_dependency_allowlist_entries(values: Iterable[str] | None) -> list[str]:
    invalid: list[str] = []
    for item in values or []:
        value = str(item or "").strip()
        if not value:
            continue
        if ":" not in value:
            invalid.append(value)
            continue
        ecosystem, name = value.split(":", 1)
        if not ecosystem.strip() or not name.strip():
            invalid.append(value)
    return invalid


def configured_sandbox_dependency_allowlist() -> set[str]:
    configured = getattr(settings, "PLUGIN_MARKETPLACE_SANDBOX_DEPENDENCY_ALLOWLIST", []) or []
    return normalize_dependency_allowlist(configured)


def dependency_key(dependency: dict[str, Any]) -> str:
    ecosystem = str(dependency.get("ecosystem") or "").strip().lower()
    name = str(dependency.get("name") or "").strip().lower()
    return f"{ecosystem}:{name}" if ecosystem and name else ""


def _manifest_parse_supported(manifest: dict[str, Any]) -> bool:
    if "parse_supported" in manifest:
        return bool(manifest.get("parse_supported"))
    name = PurePosixPath(str(manifest.get("path") or "")).name.lower()
    return name in SUPPORTED_DEPENDENCY_MANIFEST_NAMES


def dependency_policy_blockers(
    *,
    dependencies: list[dict[str, Any]],
    dependency_manifests: list[dict[str, Any]],
    allow_sandboxed_code: bool,
    allowlist: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    if not dependency_manifests:
        return []
    if not allow_sandboxed_code:
        return [
            {"code": "dependency_manifest_not_allowed_no_code", "path": str(item.get("path") or "")}
            for item in dependency_manifests
        ]

    normalized_allowlist = (
        normalize_dependency_allowlist(allowlist)
        if allowlist is not None
        else configured_sandbox_dependency_allowlist()
    )
    blockers: list[dict[str, Any]] = []
    for manifest in dependency_manifests:
        if not _manifest_parse_supported(manifest):
            blockers.append(
                {
                    "code": "dependency_manifest_not_supported_for_allowlist",
                    "path": str(manifest.get("path") or ""),
                }
            )
    for dependency in dependencies:
        key = dependency_key(dependency)
        if key and key not in normalized_allowlist:
            blockers.append(
                {
                    "code": "dependency_not_allowlisted",
                    "dependency": key,
                    "ecosystem": str(dependency.get("ecosystem") or ""),
                    "name": str(dependency.get("name") or ""),
                    "source": str(dependency.get("source") or ""),
                }
            )
    return blockers
