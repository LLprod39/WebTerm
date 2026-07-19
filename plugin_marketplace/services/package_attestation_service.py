from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from app.plugins.validation import PluginValidationError, validate_plugin_manifest
from core_ui.models import UserActivityLog
from plugin_marketplace.models import PluginPackage
from plugin_marketplace.services import remote_package_service
from plugin_marketplace.services.package_retention_service import PackageRetentionError, read_retained_package_bytes
from plugin_marketplace.services.package_service import PluginPackageValidationError, validate_wtp_package
from plugin_marketplace.services.signing_service import canonical_manifest_hash, package_signature_status
from plugin_marketplace.services.static_scan_service import scan_manifest


class PackageAttestationError(ValueError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _append_attestation(
    package: PluginPackage,
    *,
    kind: str,
    status: str,
    report: dict[str, Any],
    actor=None,
    request=None,
) -> dict[str, Any]:
    attestation = {
        "kind": kind,
        "status": status,
        "report": report,
        "created_at": timezone.now().isoformat(),
        "actor_id": getattr(actor, "id", None) if getattr(actor, "is_authenticated", False) else None,
    }
    attestations = list(package.attestations or [])
    attestations.append(attestation)
    limit = int(getattr(settings, "PLUGIN_MARKETPLACE_ATTESTATION_RETENTION_LIMIT", 20) or 20)
    package.attestations = attestations[-max(limit, 1):]
    package.save(update_fields=["attestations", "updated_at"])
    from plugin_marketplace.services.install_service import record_event

    record_event(
        plugin_id=package.plugin_id,
        event_type="plugin_package_attested",
        status=UserActivityLog.STATUS_SUCCESS if status == "passed" else UserActivityLog.STATUS_ERROR,
        actor=actor,
        request=request,
        message=f"Plugin package attestation {kind} finished with {status}.",
        metadata={"package_id": package.id, "kind": kind, "status": status},
    )
    return attestation


def append_package_attestation(
    package: PluginPackage,
    *,
    kind: str,
    status: str,
    report: dict[str, Any],
    actor=None,
    request=None,
) -> dict[str, Any]:
    return _append_attestation(package, kind=kind, status=status, report=report, actor=actor, request=request)


@transaction.atomic
def attest_package_security(package_id: int, *, actor=None, request=None) -> PluginPackage:
    package = PluginPackage.objects.select_for_update().get(id=package_id)
    manifest = package.manifest or {}
    checks: list[dict[str, Any]] = []
    try:
        parsed = validate_plugin_manifest(manifest).to_dict(include_surfaces=True)
    except PluginValidationError as exc:
        parsed = manifest if isinstance(manifest, dict) else {}
        checks.append({"name": "manifest_schema", "ok": False, "errors": exc.errors})
    else:
        checks.append({"name": "manifest_schema", "ok": True, "errors": []})

    scan = scan_manifest(
        parsed,
        allow_sandboxed_code=bool(getattr(settings, "PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES", False)),
        allow_dynamic_frontend_bundles=bool(getattr(settings, "PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES", False)),
    )
    signature_status = package_signature_status(package)
    checks.append({"name": "static_no_code_scan", "ok": scan.passed, "findings": scan.to_dict()["findings"]})
    checks.append(
        {
            "name": "signature",
            "ok": signature_status in {PluginPackage.SIGNATURE_BUILTIN, PluginPackage.SIGNATURE_SIGNED},
            "status": signature_status,
        }
    )
    checks.append(
        {
            "name": "package_hash",
            "ok": bool(package.package_hash),
            "package_hash": package.package_hash,
            "manifest_hash": canonical_manifest_hash(parsed),
        }
    )
    dependency_scan = package.dependency_scan if isinstance(package.dependency_scan, dict) else {}
    if dependency_scan:
        checks.append(
            {
                "name": "dependency_scan",
                "ok": bool(dependency_scan.get("passed", False)),
                "summary": dependency_scan.get("summary", {}),
                "blockers": dependency_scan.get("blockers", []),
            }
        )
    status = "passed" if all(check["ok"] for check in checks) else "failed"
    _append_attestation(
        package,
        kind="security_gate",
        status=status,
        report={"checks": checks},
        actor=actor,
        request=request,
    )
    package.refresh_from_db()
    return package


def _remote_provenance(package: PluginPackage) -> tuple[str, str]:
    provenance = package.provenance if isinstance(package.provenance, dict) else {}
    source_url = str(provenance.get("source_url") or "").strip()
    expected_sha256 = str(provenance.get("expected_sha256") or provenance.get("downloaded_sha256") or "").strip()
    if not source_url or not expected_sha256:
        raise PackageAttestationError("Package does not have replayable remote provenance.")
    return source_url, expected_sha256


def _retained_data_for_package(package: PluginPackage) -> bytes:
    provenance = package.provenance if isinstance(package.provenance, dict) else {}
    retention = provenance.get("retention") if isinstance(provenance.get("retention"), dict) else {}
    return read_retained_package_bytes(retention)


def _validate_remote_bytes(data: bytes) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(suffix=".wtp", delete=False) as handle:
        handle.write(data)
        package_path = Path(handle.name)
    try:
        result = validate_wtp_package(package_path)
    finally:
        package_path.unlink(missing_ok=True)
    if not result.ok:
        raise PluginPackageValidationError("; ".join(result.errors))
    manifest = validate_plugin_manifest(result.manifest)
    return {
        "plugin_id": manifest.id,
        "version": manifest.version,
        "file_count": result.file_count,
        "static_scan": result.static_scan.to_dict(),
        "sbom": result.sbom,
        "dependency_scan": result.dependency_scan,
    }


@transaction.atomic
def replay_remote_package_provenance(package_id: int, *, actor=None, request=None) -> PluginPackage:
    package = PluginPackage.objects.select_for_update().get(id=package_id)
    source_url, expected_sha256 = _remote_provenance(package)
    try:
        data = remote_package_service.fetch_remote_package_bytes(source_url)
    except remote_package_service.RemotePackageError as exc:
        try:
            data = _retained_data_for_package(package)
        except PackageRetentionError as retention_exc:
            _append_attestation(
                package,
                kind="remote_provenance_replay",
                status="unavailable",
                report={"source_url": source_url, "error": str(exc), "retention_error": str(retention_exc)},
                actor=actor,
                request=request,
            )
            package.refresh_from_db()
            return package
        data_source = "retention"
    else:
        data_source = "remote"

    actual_sha256 = _sha256(data)
    checks = [
        {
            "name": "package_source",
            "ok": True,
            "source": data_source,
        },
        {
            "name": "sha256",
            "ok": actual_sha256.lower() == expected_sha256.lower(),
            "expected_sha256": expected_sha256.lower(),
            "actual_sha256": actual_sha256.lower(),
        }
    ]
    if checks[0]["ok"]:
        try:
            validated = _validate_remote_bytes(data)
        except (PluginPackageValidationError, PluginValidationError, ValueError) as exc:
            checks.append({"name": "package_validation", "ok": False, "error": str(exc)})
        else:
            checks.append(
                {
                    "name": "manifest_identity",
                    "ok": validated["plugin_id"] == package.plugin_id and validated["version"] == package.version,
                    "plugin_id": validated["plugin_id"],
                    "version": validated["version"],
                    "file_count": validated["file_count"],
                }
            )
            checks.append({"name": "static_no_code_scan", "ok": validated["static_scan"]["passed"], "findings": validated["static_scan"]["findings"]})
            checks.append(
                {
                    "name": "dependency_scan",
                    "ok": validated["dependency_scan"]["passed"],
                    "summary": validated["dependency_scan"]["summary"],
                    "blockers": validated["dependency_scan"]["blockers"],
                }
            )
    status = "passed" if all(check["ok"] for check in checks) else "failed"
    package.refresh_from_db()
    if status == "failed" and package.signature_status != PluginPackage.SIGNATURE_BUILTIN:
        package.signature_status = PluginPackage.SIGNATURE_INVALID
        if package.review_status == PluginPackage.REVIEW_VERIFIED:
            package.review_status = PluginPackage.REVIEW_SUSPENDED
        package.save(update_fields=["signature_status", "review_status", "updated_at"])
    _append_attestation(
        package,
        kind="remote_provenance_replay",
        status=status,
        report={"source_url": source_url, "checks": checks},
        actor=actor,
        request=request,
    )
    package.refresh_from_db()
    return package
