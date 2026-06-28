from __future__ import annotations

from typing import Any

from plugin_marketplace.models import PluginInstallation, PluginPackage
from plugin_marketplace.services.access_scope_service import installation_scope_payload
from plugin_marketplace.services.package_attestation_policy_service import attestation_policy_for_package
from plugin_marketplace.services.sandbox_policy_service import sandbox_policy_for_package


def package_payload(package: PluginPackage, *, include_manifest: bool = True) -> dict[str, Any]:
    payload = {
        "id": package.id,
        "plugin_id": package.plugin_id,
        "version": package.version,
        "name": package.name,
        "slug": package.slug,
        "publisher": {
            "id": package.publisher_id,
            "name": package.publisher_name,
        },
        "source": package.source,
        "package_hash": package.package_hash,
        "signature_payload": package.signature_payload,
        "provenance": package.provenance,
        "attestations": package.attestations,
        "sbom": package.sbom,
        "dependency_scan": package.dependency_scan,
        "sandbox_policy": sandbox_policy_for_package(package),
        "attestation_policy": attestation_policy_for_package(package),
        "risk_tier": package.risk_tier,
        "review_status": package.review_status,
        "signature_status": package.signature_status,
        "created_at": package.created_at.isoformat() if package.created_at else None,
        "updated_at": package.updated_at.isoformat() if package.updated_at else None,
    }
    if include_manifest:
        payload["manifest"] = package.manifest
    return payload


def installation_payload(installation: PluginInstallation) -> dict[str, Any]:
    return {
        "id": installation.id,
        "plugin_id": installation.plugin_id,
        "status": installation.status,
        "package": package_payload(installation.package, include_manifest=True),
        "settings": installation.settings,
        "scope": installation_scope_payload(installation),
        "health_status": installation.health_status,
        "health_failure_count": installation.health_failure_count,
        "last_error": installation.last_error,
        "installed_at": installation.installed_at.isoformat() if installation.installed_at else None,
        "enabled_at": installation.enabled_at.isoformat() if installation.enabled_at else None,
        "disabled_at": installation.disabled_at.isoformat() if installation.disabled_at else None,
        "quarantined_at": installation.quarantined_at.isoformat() if installation.quarantined_at else None,
    }


def catalog_payload(
    manifest: dict[str, Any],
    installation: PluginInstallation | None,
    *,
    enabled: bool | None = None,
) -> dict[str, Any]:
    package = installation.package if installation else None
    effective_enabled = (
        bool(installation and installation.status == PluginInstallation.STATUS_ENABLED)
        if enabled is None
        else enabled
    )
    return {
        "id": manifest.get("id"),
        "name": manifest.get("name"),
        "slug": manifest.get("slug"),
        "version": manifest.get("version"),
        "summary": manifest.get("summary"),
        "description": manifest.get("description", ""),
        "publisher": manifest.get("publisher", {}),
        "categories": manifest.get("categories", []),
        "risk_tier": manifest.get("risk_tier", "info"),
        "permissions": manifest.get("permissions", []),
        "surfaces": manifest.get("surfaces", {}),
        "actions": manifest.get("actions", []),
        "installation": installation_payload(installation) if installation else None,
        "review_status": package.review_status if package else "unavailable",
        "signature_status": package.signature_status if package else "unavailable",
        "enabled": effective_enabled,
    }
