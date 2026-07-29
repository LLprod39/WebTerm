from __future__ import annotations

from typing import Any

from plugin_marketplace.models import PluginPackage
from plugin_marketplace.services.signing_service import canonical_manifest_hash, package_signature_status


def package_trust_report(
    package: PluginPackage | None,
    *,
    expected_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if package is None:
        return {
            "trusted": False,
            "review_status": "unavailable",
            "signature_status": "unavailable",
            "manifest_matches": False,
            "errors": ["Catalog item does not have a trusted package record."],
        }

    errors: list[str] = []
    if package.review_status != PluginPackage.REVIEW_VERIFIED:
        errors.append(f"Trusted package review status is {package.review_status}.")

    signature_status = package_signature_status(package)
    if signature_status not in {PluginPackage.SIGNATURE_BUILTIN, PluginPackage.SIGNATURE_SIGNED}:
        errors.append(f"Trusted package cryptographic signature status is {signature_status}.")

    manifest_matches = expected_manifest is None or canonical_manifest_hash(
        package.manifest or {}
    ) == canonical_manifest_hash(expected_manifest)
    if not manifest_matches:
        errors.append("Catalog manifest does not match the trusted package manifest.")

    return {
        "trusted": not errors,
        "review_status": package.review_status,
        "signature_status": signature_status,
        "manifest_matches": manifest_matches,
        "errors": errors,
    }
