from __future__ import annotations

import hashlib
import json
from typing import Any

from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from django.utils import timezone

from app.plugins.catalog import ensure_builtin_plugins_registered, project_plugin_catalog
from app.plugins.registry import plugin_registry
from core_ui.activity import log_user_activity
from core_ui.models import UserActivityLog
from plugin_marketplace.models import PluginInstallation, PluginInstallEvent, PluginPackage
from plugin_marketplace.services.access_scope_service import installation_allowed_for_user
from plugin_marketplace.services.package_attestation_policy_service import attestation_enable_blockers
from plugin_marketplace.services.sandbox_policy_service import sandbox_enable_blockers
from plugin_marketplace.services.serialization import catalog_payload, installation_payload


def _actor_or_none(actor):
    if isinstance(actor, AnonymousUser):
        return None
    if getattr(actor, "is_authenticated", False):
        return actor
    return None


def _manifest_hash(manifest: dict[str, Any]) -> str:
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def ensure_builtin_packages() -> list[PluginInstallation]:
    ensure_builtin_plugins_registered()
    installations: list[PluginInstallation] = []
    for manifest in plugin_registry.all():
        payload = manifest.to_dict(include_surfaces=True)
        package, _created = PluginPackage.objects.update_or_create(
            plugin_id=manifest.id,
            version=manifest.version,
            defaults={
                "name": manifest.name,
                "slug": manifest.slug,
                "publisher_id": manifest.publisher.id,
                "publisher_name": manifest.publisher.name,
                "source": PluginPackage.SOURCE_BUILTIN,
                "package_hash": _manifest_hash(payload),
                "manifest": payload,
                "risk_tier": manifest.risk_tier,
                "review_status": PluginPackage.REVIEW_VERIFIED,
                "signature_status": PluginPackage.SIGNATURE_BUILTIN,
            },
        )
        installation, _created = PluginInstallation.objects.get_or_create(
            plugin_id=manifest.id,
            defaults={"package": package, "status": PluginInstallation.STATUS_DISABLED},
        )
        if installation.package_id != package.id:
            installation.package = package
            installation.save(update_fields=["package"])
        installations.append(installation)
    return installations


def enabled_plugin_ids() -> set[str]:
    ensure_builtin_packages()
    return set(
        PluginInstallation.objects.filter(status=PluginInstallation.STATUS_ENABLED)
        .values_list("plugin_id", flat=True)
    )


def enabled_plugin_ids_for_user(user) -> set[str]:
    ensure_builtin_packages()
    installations = PluginInstallation.objects.filter(
        status=PluginInstallation.STATUS_ENABLED,
    ).prefetch_related("scoped_groups")
    return {
        installation.plugin_id
        for installation in installations
        if installation_allowed_for_user(installation, user)
    }


def enabled_installed_plugin_manifests() -> list[dict[str, Any]]:
    installations = (
        PluginInstallation.objects.select_related("package")
        .filter(status=PluginInstallation.STATUS_ENABLED)
        .exclude(package__source=PluginPackage.SOURCE_BUILTIN)
    )
    return [
        item.package.manifest
        for item in installations
        if isinstance(item.package.manifest, dict)
    ]


def list_catalog_plugins(user=None) -> list[dict[str, Any]]:
    ensure_builtin_packages()
    enabled = enabled_plugin_ids_for_user(user) if user is not None else enabled_plugin_ids()
    installations = {
        item.plugin_id: item
        for item in PluginInstallation.objects.select_related("package").prefetch_related("scoped_groups").all()
    }
    return [
        catalog_payload(
            manifest,
            installations.get(str(manifest.get("id") or "")),
            enabled=str(manifest.get("id") or "") in enabled,
        )
        for manifest in project_plugin_catalog(enabled)
    ]


def list_installations() -> list[dict[str, Any]]:
    ensure_builtin_packages()
    installations = PluginInstallation.objects.select_related("package", "installed_by").prefetch_related("scoped_groups").all()
    return [installation_payload(item) for item in installations]


def record_event(
    *,
    plugin_id: str,
    event_type: str,
    status: str = UserActivityLog.STATUS_INFO,
    actor=None,
    request=None,
    installation: PluginInstallation | None = None,
    message: str = "",
    metadata: dict[str, Any] | None = None,
) -> PluginInstallEvent:
    safe_actor = _actor_or_none(actor)
    event = PluginInstallEvent.objects.create(
        installation=installation,
        plugin_id=plugin_id,
        event_type=event_type,
        status=status,
        actor=safe_actor,
        message=message,
        metadata=metadata or {},
    )
    log_user_activity(
        user=safe_actor,
        request=request,
        category="plugins",
        action=event_type,
        status=status,
        description=message,
        entity_type="plugin",
        entity_id=plugin_id,
        entity_name=plugin_id,
        metadata=metadata or {},
    )
    return event


@transaction.atomic
def set_installation_status(
    installation_id: int,
    *,
    enable: bool,
    actor=None,
    request=None,
) -> PluginInstallation:
    ensure_builtin_packages()
    installation = PluginInstallation.objects.select_for_update().select_related("package").get(id=installation_id)
    if enable and installation.status in {
        PluginInstallation.STATUS_BLOCKED,
        PluginInstallation.STATUS_QUARANTINED,
        PluginInstallation.STATUS_UNINSTALLING,
    }:
        raise ValueError(f"Plugin cannot be enabled from status {installation.status}.")
    if enable:
        package = installation.package
        if package.review_status != PluginPackage.REVIEW_VERIFIED:
            raise ValueError(f"Plugin package review status is {package.review_status}.")
        if package.signature_status not in {PluginPackage.SIGNATURE_BUILTIN, PluginPackage.SIGNATURE_SIGNED}:
            raise ValueError(f"Plugin package signature status is {package.signature_status}.")
        sandbox_blockers = sandbox_enable_blockers(package)
        if sandbox_blockers:
            raise ValueError("; ".join(sandbox_blockers))
        attestation_blockers = attestation_enable_blockers(package)
        if attestation_blockers:
            raise ValueError("; ".join(attestation_blockers))

    now = timezone.now()
    previous_status = installation.status
    if enable:
        installation.status = PluginInstallation.STATUS_ENABLED
        installation.enabled_at = now
        installation.disabled_at = None
        action = "plugin_enabled"
        message = f"Plugin {installation.plugin_id} enabled."
    else:
        installation.status = PluginInstallation.STATUS_DISABLED
        installation.disabled_at = now
        action = "plugin_disabled"
        message = f"Plugin {installation.plugin_id} disabled."
    installation.save(update_fields=["status", "enabled_at", "disabled_at"])
    record_event(
        plugin_id=installation.plugin_id,
        event_type=action,
        status=UserActivityLog.STATUS_SUCCESS,
        actor=actor,
        request=request,
        installation=installation,
        message=message,
        metadata={
            "package_id": installation.package_id,
            "previous_status": previous_status,
            "new_status": installation.status,
        },
    )
    return installation
