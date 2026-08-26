"""Verified read boundary for project bundles used by validation and execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from servers.models import PlaybookAssetBundle
from servers.services.playbooks.bundle_archive import BundleLimits, inspect_project_bundle
from servers.services.playbooks.bundle_storage import PlaybookBundleStorage, get_playbook_bundle_storage
from servers.services.playbooks.controller_policy import analyze_project_files_controller_policy


class BundleRuntimeError(RuntimeError):
    """Stored project bytes no longer match their immutable database evidence."""


@dataclass(frozen=True)
class RuntimeProjectBundle:
    files: dict[str, bytes]
    entrypoint: str
    content_hash: str


def load_revision_runtime_bundle(
    revision: Any,
    *,
    storage: PlaybookBundleStorage | None = None,
) -> RuntimeProjectBundle | None:
    if not getattr(revision, "asset_bundle_id", None):
        return None
    asset = revision.asset_bundle
    if asset is None or asset.scan_status != PlaybookAssetBundle.SCAN_CLEAN:
        raise BundleRuntimeError("The attached project bundle is not approved for execution")

    limits = BundleLimits.from_settings()
    stored_limit = max(limits.max_archive_bytes, limits.max_total_bytes + limits.max_files * 1024)
    try:
        archive = (storage or get_playbook_bundle_storage()).read(asset.storage_key, max_bytes=stored_limit)
        inspected = inspect_project_bundle(archive, limits=limits)
    except Exception as exc:
        raise BundleRuntimeError("The stored project bundle could not be verified") from exc
    if inspected.content_hash != asset.content_hash:
        raise BundleRuntimeError("The stored project bundle failed its integrity check")
    revision_hash = str(getattr(revision, "bundle_hash", "") or "")
    if revision_hash and inspected.content_hash != revision_hash:
        raise BundleRuntimeError("The revision bundle hash no longer matches its artifact")

    metadata = revision.metadata if isinstance(getattr(revision, "metadata", None), dict) else {}
    scan_report = asset.scan_report if isinstance(asset.scan_report, dict) else {}
    entrypoint = str(
        metadata.get("bundle_entrypoint") or scan_report.get("entrypoint") or inspected.manifest.get("entrypoint") or ""
    )
    files = {item.path: item.content for item in inspected.files}
    if not entrypoint or entrypoint not in files:
        raise BundleRuntimeError("The project bundle entrypoint is missing")
    return RuntimeProjectBundle(files=files, entrypoint=entrypoint, content_hash=inspected.content_hash)


def apply_runtime_bundle_evidence(report: dict[str, Any], bundle: RuntimeProjectBundle | None) -> None:
    """Remove only dependency blockers proven present in the verified bundle."""

    if bundle is None:
        return
    paths = {str(PurePosixPath(path)) for path in bundle.files}
    kept: list[dict[str, Any]] = []
    for issue in report.get("issues") or []:
        code = issue.get("code") if isinstance(issue, dict) else ""
        message = str(issue.get("message") or "") if isinstance(issue, dict) else ""
        resolved = False
        if code == "missing_role_bundle":
            role = message.partition("'")[2].partition("'")[0]
            resolved = bool(role) and any(
                path == f"roles/{role}" or path.startswith(f"roles/{role}/") for path in paths
            )
        elif code == "missing_project_asset":
            asset_path = message.partition(":")[2].strip()
            normalized = str(PurePosixPath(asset_path.lstrip("./"))) if asset_path else ""
            resolved = normalized in paths
        if not resolved and isinstance(issue, dict):
            kept.append(issue)
    existing = {
        (
            str(issue.get("code") or ""),
            str(issue.get("path") or ""),
            str(issue.get("message") or ""),
        )
        for issue in kept
        if isinstance(issue, dict)
    }
    for issue in analyze_project_files_controller_policy(
        bundle.files,
        skip_paths={bundle.entrypoint},
    ):
        key = (
            str(issue.get("code") or ""),
            str(issue.get("path") or ""),
            str(issue.get("message") or ""),
        )
        if key not in existing:
            kept.append(issue)
            existing.add(key)
    report["issues"] = kept
