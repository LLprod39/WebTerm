from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

from plugin_marketplace.models import PluginPackage

SAFE_SEGMENT_RE = re.compile(r"[^A-Za-z0-9_.-]+")


class PackageRetentionError(ValueError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_segment(value: str) -> str:
    cleaned = SAFE_SEGMENT_RE.sub("-", value.strip())[:140].strip(".-")
    if not cleaned:
        raise PackageRetentionError("Package retention path segment is empty.")
    return cleaned


def _retention_root() -> Path:
    configured = getattr(settings, "PLUGIN_MARKETPLACE_PACKAGE_RETENTION_DIR", None)
    root = Path(configured) if configured else Path(settings.MEDIA_ROOT) / "plugin_packages"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _relative_package_path(*, plugin_id: str, version: str, sha256: str) -> Path:
    if not re.fullmatch(r"[a-fA-F0-9]{64}", sha256):
        raise PackageRetentionError("Package sha256 is invalid.")
    return Path(_safe_segment(plugin_id)) / _safe_segment(version) / f"{sha256.lower()}.wtp"


def _resolve_retained_path(relative_path: str) -> Path:
    root = _retention_root()
    candidate = (root / relative_path).resolve()
    if root != candidate and root not in candidate.parents:
        raise PackageRetentionError("Retained package path escapes retention root.")
    return candidate


def retain_package_bytes(
    *,
    data: bytes,
    plugin_id: str,
    version: str,
    sha256: str,
    source: str,
) -> dict[str, Any]:
    actual_sha256 = _sha256(data)
    if actual_sha256.lower() != sha256.lower():
        raise PackageRetentionError("Package bytes do not match sha256.")
    relative_path = _relative_package_path(plugin_id=plugin_id, version=version, sha256=sha256)
    target = _resolve_retained_path(str(relative_path))
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_suffix(".tmp")
    tmp_path.write_bytes(data)
    tmp_path.replace(target)
    return {
        "retained": True,
        "storage": "local_file",
        "path": str(relative_path).replace("\\", "/"),
        "sha256": actual_sha256.lower(),
        "size": len(data),
        "source": source,
    }


def retain_package_file(
    path: str | Path,
    *,
    plugin_id: str,
    version: str,
    sha256: str,
    source: str,
) -> dict[str, Any]:
    return retain_package_bytes(
        data=Path(path).read_bytes(),
        plugin_id=plugin_id,
        version=version,
        sha256=sha256,
        source=source,
    )


def retained_package_exists(retention: dict[str, Any]) -> bool:
    relative_path = str(retention.get("path") or "")
    if not relative_path:
        return False
    return _resolve_retained_path(relative_path).exists()


def read_retained_package_bytes(retention: dict[str, Any]) -> bytes:
    relative_path = str(retention.get("path") or "")
    expected_sha256 = str(retention.get("sha256") or "").lower()
    if not relative_path or not expected_sha256:
        raise PackageRetentionError("Package retention metadata is incomplete.")
    data = _resolve_retained_path(relative_path).read_bytes()
    if _sha256(data).lower() != expected_sha256:
        raise PackageRetentionError("Retained package hash does not match retention metadata.")
    return data


def _referenced_retention_paths() -> set[str]:
    references = set()
    for provenance in PluginPackage.objects.values_list("provenance", flat=True):
        if not isinstance(provenance, dict):
            continue
        retention = provenance.get("retention") if isinstance(provenance.get("retention"), dict) else {}
        relative_path = str(retention.get("path") or "").replace("\\", "/")
        if relative_path:
            references.add(relative_path)
    return references


def retention_inventory() -> dict[str, Any]:
    root = _retention_root()
    referenced = _referenced_retention_paths()
    files = []
    for path in sorted(root.rglob("*.wtp")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(root).as_posix()
        size = path.stat().st_size
        files.append(
            {
                "path": relative_path,
                "size": size,
                "referenced": relative_path in referenced,
                "modified_at": timezone.datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.get_current_timezone()
                ).isoformat(),
            }
        )
    return {
        "root": str(root),
        "files": files,
        "summary": {
            "file_count": len(files),
            "referenced_count": sum(1 for item in files if item["referenced"]),
            "unreferenced_count": sum(1 for item in files if not item["referenced"]),
            "total_bytes": sum(int(item["size"]) for item in files),
        },
    }


def cleanup_retained_packages(*, dry_run: bool = True, max_age_days: int | None = None) -> dict[str, Any]:
    configured_days = int(getattr(settings, "PLUGIN_MARKETPLACE_RETAINED_PACKAGE_MAX_AGE_DAYS", 0) or 0)
    age_days = configured_days if max_age_days is None else int(max_age_days)
    cutoff = None
    if age_days > 0:
        cutoff = timezone.now().timestamp() - (age_days * 24 * 60 * 60)
    root = _retention_root()
    referenced = _referenced_retention_paths()
    deleted = []
    kept = []
    for path in sorted(root.rglob("*.wtp")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(root).as_posix()
        stat = path.stat()
        is_referenced = relative_path in referenced
        expired = cutoff is not None and stat.st_mtime < cutoff
        deletable = (not is_referenced) and (cutoff is None or expired)
        record = {
            "path": relative_path,
            "size": stat.st_size,
            "referenced": is_referenced,
            "expired": expired,
        }
        if deletable:
            deleted.append(record)
            if not dry_run:
                path.unlink(missing_ok=True)
        else:
            kept.append(record)
    return {
        "dry_run": dry_run,
        "max_age_days": age_days,
        "deleted": deleted,
        "kept_count": len(kept),
        "summary": {
            "delete_count": len(deleted),
            "delete_bytes": sum(int(item["size"]) for item in deleted),
            "kept_count": len(kept),
        },
    }
