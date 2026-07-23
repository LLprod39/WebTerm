from __future__ import annotations

from typing import Any

from django.db import transaction

from core_ui.models import UserActivityLog
from plugin_marketplace.models import PluginInstallation, PluginPermissionGrant
from plugin_marketplace.services.access_scope_service import installation_allowed_for_user


def _manifest_permissions(installation: PluginInstallation) -> list[dict[str, Any]]:
    manifest = installation.package.manifest or {}
    permissions = manifest.get("permissions") or []
    return [item for item in permissions if isinstance(item, dict)]


def _declared_permission(installation: PluginInstallation, scope: str) -> dict[str, Any] | None:
    for item in _manifest_permissions(installation):
        if item.get("scope") == scope:
            return item
    return None


def permission_provider(plugin_id: str, scope: str, user=None) -> bool:
    grants = (
        PluginPermissionGrant.objects.select_related("installation")
        .prefetch_related("installation__scoped_groups")
        .filter(
            installation__plugin_id=plugin_id,
            installation__status=PluginInstallation.STATUS_ENABLED,
            scope=scope,
            granted=True,
        )
    )
    return any(installation_allowed_for_user(grant.installation, user) for grant in grants)


def permission_preview(installation: PluginInstallation) -> list[dict[str, Any]]:
    grants = {item.scope: item for item in installation.permission_grants.all()}
    result: list[dict[str, Any]] = []
    for item in _manifest_permissions(installation):
        scope = str(item.get("scope") or "")
        grant = grants.get(scope)
        result.append(
            {
                "scope": scope,
                "reason": item.get("reason", ""),
                "risk_tier": item.get("risk_tier", "read"),
                "granted": bool(grant and grant.granted),
                "grant_id": grant.id if grant else None,
            }
        )
    return result


@transaction.atomic
def grant_permission(installation_id: int, scope: str, *, actor=None, request=None) -> PluginPermissionGrant:
    installation = PluginInstallation.objects.select_for_update().select_related("package").get(id=installation_id)
    declared = _declared_permission(installation, scope)
    if declared is None:
        raise ValueError(f"Permission {scope} is not declared by plugin {installation.plugin_id}.")
    grant, _created = PluginPermissionGrant.objects.update_or_create(
        installation=installation,
        scope=scope,
        defaults={
            "granted": True,
            "reason": str(declared.get("reason") or ""),
            "risk_tier": str(declared.get("risk_tier") or "read"),
            "granted_by": actor if getattr(actor, "is_authenticated", False) else None,
        },
    )
    from plugin_marketplace.services.install_service import record_event

    record_event(
        plugin_id=installation.plugin_id,
        event_type="plugin_permission_granted",
        status=UserActivityLog.STATUS_SUCCESS,
        actor=actor,
        request=request,
        installation=installation,
        message=f"Permission {scope} granted.",
        metadata={"scope": scope},
    )
    return grant


@transaction.atomic
def revoke_permission(installation_id: int, scope: str, *, actor=None, request=None) -> PluginPermissionGrant:
    installation = PluginInstallation.objects.select_for_update().select_related("package").get(id=installation_id)
    declared = _declared_permission(installation, scope)
    if declared is None:
        raise ValueError(f"Permission {scope} is not declared by plugin {installation.plugin_id}.")
    grant, _created = PluginPermissionGrant.objects.update_or_create(
        installation=installation,
        scope=scope,
        defaults={
            "granted": False,
            "reason": str(declared.get("reason") or ""),
            "risk_tier": str(declared.get("risk_tier") or "read"),
            "granted_by": actor if getattr(actor, "is_authenticated", False) else None,
        },
    )
    from plugin_marketplace.services.install_service import record_event

    record_event(
        plugin_id=installation.plugin_id,
        event_type="plugin_permission_revoked",
        status=UserActivityLog.STATUS_SUCCESS,
        actor=actor,
        request=request,
        installation=installation,
        message=f"Permission {scope} revoked.",
        metadata={"scope": scope},
    )
    return grant
