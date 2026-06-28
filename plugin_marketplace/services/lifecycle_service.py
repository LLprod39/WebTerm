from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from app.plugins.contracts import SURFACE_KINDS
from app.plugins.validation import validate_plugin_manifest
from core_ui.models import UserActivityLog
from plugin_marketplace.models import (
    PluginInstallation,
    PluginPackage,
    PluginPermissionGrant,
    PluginSecretBinding,
)
from plugin_marketplace.services.egress_policy_service import manifest_egress_hosts
from plugin_marketplace.services.install_service import record_event
from plugin_marketplace.services.package_attestation_policy_service import attestation_enable_blockers, attestation_policy_for_package
from plugin_marketplace.services.sandbox_policy_service import sandbox_enable_blockers, sandbox_policy_for_package


def _manifest_permissions(manifest: dict[str, Any]) -> set[str]:
    return {
        str(item.get("scope") or "").strip()
        for item in manifest.get("permissions", [])
        if isinstance(item, dict) and str(item.get("scope") or "").strip()
    }


def _manifest_secrets(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id") or "").strip(): item
        for item in manifest.get("secrets", [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }


def _manifest_egress(manifest: dict[str, Any]) -> set[str]:
    return manifest_egress_hosts(manifest)


def _surface_counts(manifest: dict[str, Any]) -> dict[str, int]:
    surfaces = manifest.get("surfaces") if isinstance(manifest.get("surfaces"), dict) else {}
    return {
        kind: len(items) if isinstance(items, list) else 0
        for kind, items in surfaces.items()
        if kind in SURFACE_KINDS
    }


def _surface_items(manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    surfaces = manifest.get("surfaces") if isinstance(manifest.get("surfaces"), dict) else {}
    payload: dict[str, list[dict[str, Any]]] = {}
    for kind in SURFACE_KINDS:
        items = surfaces.get(kind) if isinstance(surfaces, dict) else []
        payload[kind] = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    return payload


def _declared_setting_keys(manifest: dict[str, Any]) -> set[str]:
    schema = manifest.get("settings_schema") if isinstance(manifest.get("settings_schema"), dict) else {}
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    return {str(key) for key in properties.keys()}


def _package_ready(package: PluginPackage) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if package.review_status != PluginPackage.REVIEW_VERIFIED:
        errors.append(f"Package review status is {package.review_status}.")
    if package.signature_status not in {PluginPackage.SIGNATURE_BUILTIN, PluginPackage.SIGNATURE_SIGNED}:
        errors.append(f"Package signature status is {package.signature_status}.")
    errors.extend(sandbox_enable_blockers(package))
    errors.extend(attestation_enable_blockers(package))
    return not errors, errors


def installation_impact(installation: PluginInstallation) -> dict[str, Any]:
    manifest = installation.package.manifest or {}
    declared_permissions = _manifest_permissions(manifest)
    grants = {
        grant.scope: grant.granted
        for grant in installation.permission_grants.all()
    }
    declared_secrets = _manifest_secrets(manifest)
    bound_secrets = {
        binding.key
        for binding in installation.secret_bindings.all()
    }
    ready, enable_blockers = _package_ready(installation.package)
    return {
        "installation_id": installation.id,
        "plugin_id": installation.plugin_id,
        "status": installation.status,
        "package": {
            "id": installation.package_id,
            "version": installation.package.version,
            "review_status": installation.package.review_status,
            "signature_status": installation.package.signature_status,
            "sandbox_policy": sandbox_policy_for_package(installation.package),
            "attestation_policy": attestation_policy_for_package(installation.package),
            "ready_to_enable": ready,
            "enable_blockers": enable_blockers,
        },
        "surfaces": {
            "counts": _surface_counts(manifest),
            "items": _surface_items(manifest),
        },
        "permissions": {
            "declared": sorted(declared_permissions),
            "granted": sorted(scope for scope, granted in grants.items() if granted),
            "missing": sorted(scope for scope in declared_permissions if not grants.get(scope)),
            "stale_grants": sorted(scope for scope in grants if scope not in declared_permissions),
        },
        "secrets": {
            "declared": sorted(declared_secrets.keys()),
            "bound": sorted(bound_secrets),
            "missing_required": sorted(
                key
                for key, secret in declared_secrets.items()
                if bool(secret.get("required")) and key not in bound_secrets
            ),
        },
        "settings": {
            "stored_keys": sorted(str(key) for key in installation.settings.keys()),
            "declared_keys": sorted(_declared_setting_keys(manifest)),
        },
        "egress_hosts": sorted(_manifest_egress(manifest)),
        "uninstall": {
            "soft_supported": True,
            "full_supported": False,
            "reversible": PluginPackage.objects.filter(plugin_id=installation.plugin_id).exclude(id=installation.package_id).exists(),
        },
    }


def update_impact_report(installation: PluginInstallation, candidate_manifest: dict[str, Any]) -> dict[str, Any]:
    candidate = validate_plugin_manifest(candidate_manifest).to_dict(include_surfaces=True)
    current = installation.package.manifest or {}
    current_permissions = _manifest_permissions(current)
    candidate_permissions = _manifest_permissions(candidate)
    current_secrets = set(_manifest_secrets(current).keys())
    candidate_secrets = set(_manifest_secrets(candidate).keys())
    current_egress = _manifest_egress(current)
    candidate_egress = _manifest_egress(candidate)
    current_settings = _declared_setting_keys(current)
    candidate_settings = _declared_setting_keys(candidate)
    current_surfaces = _surface_counts(current)
    candidate_surfaces = _surface_counts(candidate)
    return {
        "plugin_id": installation.plugin_id,
        "current_version": installation.package.version,
        "candidate_version": candidate["version"],
        "same_plugin": candidate["id"] == installation.plugin_id,
        "permissions": {
            "added": sorted(candidate_permissions - current_permissions),
            "removed": sorted(current_permissions - candidate_permissions),
            "unchanged": sorted(current_permissions.intersection(candidate_permissions)),
        },
        "secrets": {
            "added": sorted(candidate_secrets - current_secrets),
            "removed": sorted(current_secrets - candidate_secrets),
        },
        "egress_hosts": {
            "added": sorted(candidate_egress - current_egress),
            "removed": sorted(current_egress - candidate_egress),
        },
        "settings": {
            "added": sorted(candidate_settings - current_settings),
            "removed": sorted(current_settings - candidate_settings),
            "stored_unknown_after_update": sorted(set(installation.settings.keys()) - candidate_settings),
        },
        "surfaces": {
            "current_counts": current_surfaces,
            "candidate_counts": candidate_surfaces,
        },
        "requires_permission_review": bool(candidate_permissions - current_permissions),
        "requires_secret_review": bool(candidate_secrets - current_secrets),
        "requires_egress_review": bool(candidate_egress - current_egress),
    }


@transaction.atomic
def update_installation_package(
    installation_id: int,
    package_id: int,
    *,
    actor=None,
    request=None,
) -> PluginInstallation:
    installation = PluginInstallation.objects.select_for_update().select_related("package").get(id=installation_id)
    target = PluginPackage.objects.select_for_update().get(id=package_id)
    if target.plugin_id != installation.plugin_id:
        raise ValueError("Target package belongs to a different plugin.")
    ready, errors = _package_ready(target)
    if not ready:
        raise ValueError("; ".join(errors))
    if target.id == installation.package_id:
        return installation
    previous_package_id = installation.package_id
    previous_status = installation.status
    installation.package = target
    installation.status = PluginInstallation.STATUS_DISABLED
    installation.disabled_at = timezone.now()
    installation.enabled_at = None
    installation.save(update_fields=["package", "status", "disabled_at", "enabled_at"])
    record_event(
        plugin_id=installation.plugin_id,
        event_type="plugin_package_updated",
        status=UserActivityLog.STATUS_SUCCESS,
        actor=actor,
        request=request,
        installation=installation,
        message=f"Plugin {installation.plugin_id} switched to package version {target.version}.",
        metadata={
            "previous_package_id": previous_package_id,
            "package_id": target.id,
            "previous_status": previous_status,
            "new_status": installation.status,
        },
    )
    return installation


@transaction.atomic
def rollback_installation(
    installation_id: int,
    *,
    package_id: int | None = None,
    actor=None,
    request=None,
) -> PluginInstallation:
    installation = PluginInstallation.objects.select_for_update().select_related("package").get(id=installation_id)
    if package_id:
        target = PluginPackage.objects.select_for_update().get(id=package_id)
    else:
        target = (
            PluginPackage.objects.select_for_update()
            .filter(plugin_id=installation.plugin_id)
            .exclude(id=installation.package_id)
            .order_by("-created_at", "-id")
            .first()
        )
    if not target:
        raise ValueError("No rollback package is available for this plugin.")
    if target.plugin_id != installation.plugin_id:
        raise ValueError("Rollback package belongs to a different plugin.")
    ready, errors = _package_ready(target)
    if not ready:
        raise ValueError("; ".join(errors))

    previous_package_id = installation.package_id
    previous_status = installation.status
    installation.package = target
    installation.status = PluginInstallation.STATUS_DISABLED
    installation.disabled_at = timezone.now()
    installation.enabled_at = None
    installation.save(update_fields=["package", "status", "disabled_at", "enabled_at"])
    record_event(
        plugin_id=installation.plugin_id,
        event_type="plugin_package_rolled_back",
        status=UserActivityLog.STATUS_SUCCESS,
        actor=actor,
        request=request,
        installation=installation,
        message=f"Plugin {installation.plugin_id} rolled back to package version {target.version}.",
        metadata={
            "previous_package_id": previous_package_id,
            "package_id": target.id,
            "previous_status": previous_status,
            "new_status": installation.status,
        },
    )
    return installation


@transaction.atomic
def soft_uninstall_installation(
    installation_id: int,
    *,
    revoke_permissions: bool = False,
    remove_secret_bindings: bool = False,
    actor=None,
    request=None,
) -> PluginInstallation:
    installation = PluginInstallation.objects.select_for_update().select_related("package").get(id=installation_id)
    previous_status = installation.status
    revoked_count = 0
    removed_secret_count = 0
    if revoke_permissions:
        revoked_count = PluginPermissionGrant.objects.filter(installation=installation, granted=True).update(
            granted=False,
            updated_at=timezone.now(),
        )
    if remove_secret_bindings:
        removed_secret_count, _ = PluginSecretBinding.objects.filter(installation=installation).delete()

    installation.status = PluginInstallation.STATUS_DISABLED
    installation.disabled_at = timezone.now()
    installation.enabled_at = None
    installation.save(update_fields=["status", "disabled_at", "enabled_at"])
    record_event(
        plugin_id=installation.plugin_id,
        event_type="plugin_soft_uninstalled",
        status=UserActivityLog.STATUS_SUCCESS,
        actor=actor,
        request=request,
        installation=installation,
        message=f"Plugin {installation.plugin_id} soft-uninstalled.",
        metadata={
            "previous_status": previous_status,
            "new_status": installation.status,
            "revoked_permissions": revoked_count,
            "removed_secret_bindings": removed_secret_count,
        },
    )
    return installation


@transaction.atomic
def quarantine_installation_by_plugin(
    plugin_id: str,
    *,
    reason: str = "",
    actor=None,
    request=None,
) -> PluginInstallation:
    plugin_id = plugin_id.strip()
    if not plugin_id:
        raise ValueError("plugin_id is required.")

    installation = PluginInstallation.objects.select_for_update().select_related("package").get(plugin_id=plugin_id)
    previous_status = installation.status
    installation.status = PluginInstallation.STATUS_QUARANTINED
    installation.enabled_at = None
    installation.disabled_at = timezone.now()
    installation.quarantined_at = timezone.now()
    installation.last_error = reason.strip()
    installation.save(update_fields=["status", "enabled_at", "disabled_at", "quarantined_at", "last_error"])
    record_event(
        plugin_id=installation.plugin_id,
        event_type="plugin_quarantined",
        status=UserActivityLog.STATUS_SUCCESS,
        actor=actor,
        request=request,
        installation=installation,
        message=f"Plugin {installation.plugin_id} quarantined.",
        metadata={"previous_status": previous_status, "reason": installation.last_error},
    )
    return installation
