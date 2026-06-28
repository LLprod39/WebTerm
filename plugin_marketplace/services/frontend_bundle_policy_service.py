from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from plugin_marketplace.models import PluginPackage
from plugin_marketplace.services.signing_service import canonical_manifest_hash

DYNAMIC_FRONTEND_BUNDLE_RENDERERS = {"javascript", "remote", "web_worker"}
FRONTEND_BUNDLE_REVIEW_ATTESTATION_KIND = "frontend_bundle_review"
_BUNDLE_SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")


def dynamic_frontend_bundle_renderers(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    surfaces = manifest.get("surfaces") if isinstance(manifest.get("surfaces"), dict) else {}
    renderers = []
    for surface, items in surfaces.items():
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            renderer = str(item.get("renderer") or "").strip().lower()
            if renderer in DYNAMIC_FRONTEND_BUNDLE_RENDERERS:
                renderers.append(
                    {
                        "surface": str(surface),
                        "index": index,
                        "renderer": renderer,
                        "bundle_url": str(item.get("bundle_url") or item.get("src") or "").strip(),
                        "bundle_sha256": str(item.get("bundle_sha256") or item.get("sha256") or "").strip(),
                    }
                )
    return renderers


def allow_dynamic_frontend_bundles() -> bool:
    return bool(getattr(settings, "PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES", False))


def _allowed_frontend_bundle_hosts() -> set[str]:
    configured = getattr(settings, "PLUGIN_MARKETPLACE_FRONTEND_BUNDLE_ALLOWED_HOSTS", [])
    if isinstance(configured, str):
        configured = [configured]
    return {str(item).strip().lower() for item in configured if str(item).strip()}


def frontend_bundle_surface_blockers(item: dict[str, Any]) -> list[str]:
    renderer = str(item.get("renderer") or "").strip().lower()
    if renderer not in DYNAMIC_FRONTEND_BUNDLE_RENDERERS:
        return []
    bundle_url = str(item.get("bundle_url") or item.get("src") or "").strip()
    bundle_sha256 = str(item.get("bundle_sha256") or item.get("sha256") or "").strip()
    blockers: list[str] = []
    parsed = urlparse(bundle_url)
    if parsed.scheme != "https" or not parsed.netloc:
        blockers.append("Dynamic frontend bundle URL must be HTTPS.")
    allowed_hosts = _allowed_frontend_bundle_hosts()
    host = (parsed.hostname or "").lower()
    if allowed_hosts and host not in allowed_hosts:
        blockers.append("Dynamic frontend bundle host is not allowed.")
    if not _BUNDLE_SHA256_RE.fullmatch(bundle_sha256):
        blockers.append("Dynamic frontend bundle must declare a 64-character SHA-256 hex digest.")
    return blockers


def _created_at(value: Any):
    if not value:
        return None
    parsed = value if hasattr(value, "utcoffset") else parse_datetime(str(value))
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _latest_frontend_bundle_review(package: PluginPackage) -> dict[str, Any] | None:
    attestations = package.attestations if isinstance(package.attestations, list) else []
    candidates = [
        item
        for item in attestations
        if isinstance(item, dict)
        and str(item.get("kind") or "") == FRONTEND_BUNDLE_REVIEW_ATTESTATION_KIND
        and str(item.get("status") or "") == "passed"
    ]
    candidates.sort(key=lambda item: _created_at(item.get("created_at")) or timezone.datetime.min.replace(tzinfo=timezone.utc))
    return candidates[-1] if candidates else None


def _attestation_matches_package(package: PluginPackage, attestation: dict[str, Any]) -> bool:
    report = attestation.get("report") if isinstance(attestation.get("report"), dict) else {}
    package_hash = str(report.get("package_hash") or "").strip()
    manifest_hash = str(report.get("manifest_hash") or "").strip()
    if package_hash and package_hash != package.package_hash:
        return False
    if manifest_hash and manifest_hash != canonical_manifest_hash(package.manifest or {}):
        return False
    return True


def frontend_bundle_policy_for_package(package: PluginPackage) -> dict[str, Any]:
    manifest = package.manifest if isinstance(package.manifest, dict) else {}
    renderers = dynamic_frontend_bundle_renderers(manifest)
    if not renderers:
        return {"required": False, "allowed": True, "renderers": [], "blockers": [], "checks": []}

    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    settings_snapshot = {
        "allow_dynamic_frontend_bundles": allow_dynamic_frontend_bundles(),
        "allow_sandboxed_code_packages": bool(getattr(settings, "PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES", False)),
        "frontend_sandbox_enabled": bool(getattr(settings, "PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED", False)),
    }
    if not settings_snapshot["allow_dynamic_frontend_bundles"]:
        blockers.append("Dynamic frontend bundles are not allowed by policy.")
    if not settings_snapshot["allow_sandboxed_code_packages"]:
        blockers.append("Sandboxed code packages are not allowed by policy.")
    if not settings_snapshot["frontend_sandbox_enabled"]:
        blockers.append("Frontend sandbox runtime is not enabled.")
    for renderer in renderers:
        path = f"surfaces.{renderer['surface']}[{renderer['index']}]"
        for blocker in frontend_bundle_surface_blockers(renderer):
            blockers.append(f"{path}: {blocker}")

    review_ok = package.review_status == PluginPackage.REVIEW_VERIFIED
    signature_ok = package.signature_status in {PluginPackage.SIGNATURE_BUILTIN, PluginPackage.SIGNATURE_SIGNED}
    checks.append({"name": "package_review_verified", "ok": review_ok, "status": package.review_status})
    checks.append({"name": "package_signature_trusted", "ok": signature_ok, "status": package.signature_status})
    if not review_ok:
        blockers.append("Package must be reviewed before dynamic frontend bundle distribution.")
    if not signature_ok:
        blockers.append("Package must be signed before dynamic frontend bundle distribution.")

    attestation = _latest_frontend_bundle_review(package)
    attestation_ok = bool(attestation and _attestation_matches_package(package, attestation))
    checks.append(
        {
            "name": FRONTEND_BUNDLE_REVIEW_ATTESTATION_KIND,
            "ok": attestation_ok,
            "status": attestation.get("status") if attestation else "missing",
        }
    )
    if not attestation_ok:
        blockers.append(f"Required attestation missing or stale: {FRONTEND_BUNDLE_REVIEW_ATTESTATION_KIND}.")

    return {
        "required": True,
        "allowed": not blockers,
        "renderers": renderers,
        "settings": settings_snapshot,
        "required_attestation_kind": FRONTEND_BUNDLE_REVIEW_ATTESTATION_KIND,
        "checks": checks,
        "blockers": blockers,
    }


def frontend_bundle_enable_blockers(package: PluginPackage) -> list[str]:
    return [f"Frontend bundle policy: {item}" for item in frontend_bundle_policy_for_package(package)["blockers"]]
