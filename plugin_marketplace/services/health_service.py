from __future__ import annotations

from typing import Any

from django.utils import timezone

from app.plugins.connectors import active_connectors
from app.plugins.permissions import check_plugin_permission
from core_ui.models import UserActivityLog
from plugin_marketplace.models import PluginInstallation, PluginSecretBinding
from plugin_marketplace.services.egress_policy_service import (
    denied_egress_hosts,
    manifest_egress_hosts,
    normalize_egress_host,
)
from plugin_marketplace.services.install_service import enabled_plugin_ids_for_user, record_event


class PluginConnectorError(ValueError):
    pass


HEALTH_FAILURE_QUARANTINE_THRESHOLD = 3


def _find_connector(plugin_id: str, connector_id: str, user=None) -> dict[str, Any]:
    for connector in active_connectors(enabled_plugin_ids_for_user(user)):
        if connector.get("plugin_id") == plugin_id and connector.get("id") == connector_id:
            return connector
    raise PluginConnectorError("Connector was not found or the plugin is disabled.")


def _manifest_egress_hosts(installation: PluginInstallation) -> set[str]:
    return manifest_egress_hosts(installation.package.manifest or {})


def record_plugin_health_result(
    installation: PluginInstallation,
    *,
    status: str,
    error: str = "",
    actor=None,
    request=None,
    quarantine_event_type: str = "plugin_auto_quarantined",
    quarantine_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    now = timezone.now()
    installation.health_status = status
    installation.last_health_check_at = now
    if status == "healthy":
        installation.health_failure_count = 0
        installation.last_error = ""
        installation.save(update_fields=["health_status", "last_health_check_at", "health_failure_count", "last_error"])
        return

    installation.health_failure_count += 1
    installation.last_error = error
    update_fields = ["health_status", "last_health_check_at", "health_failure_count", "last_error"]
    if (
        installation.status == PluginInstallation.STATUS_ENABLED
        and installation.health_failure_count >= HEALTH_FAILURE_QUARANTINE_THRESHOLD
    ):
        installation.status = PluginInstallation.STATUS_QUARANTINED
        installation.disabled_at = now
        installation.enabled_at = None
        installation.quarantined_at = now
        update_fields.extend(["status", "disabled_at", "enabled_at", "quarantined_at"])
        record_event(
            plugin_id=installation.plugin_id,
            event_type=quarantine_event_type,
            status=UserActivityLog.STATUS_ERROR,
            actor=actor,
            request=request,
            installation=installation,
            message=quarantine_message
            or f"Plugin {installation.plugin_id} quarantined after repeated health failures.",
            metadata={
                "health_failure_count": installation.health_failure_count,
                "last_error": error,
                **(metadata or {}),
            },
        )
    installation.save(update_fields=update_fields)


def connector_health(plugin_id: str, connector_id: str, *, actor=None, request=None) -> dict[str, Any]:
    connector = _find_connector(plugin_id, connector_id, actor)
    installation = (
        PluginInstallation.objects.select_related("package")
        .prefetch_related("secret_bindings")
        .get(plugin_id=plugin_id)
    )
    checks: list[dict[str, Any]] = []
    status = "healthy"

    required_secret = str(connector.get("required_secret") or "").strip()
    if required_secret:
        bound = PluginSecretBinding.objects.filter(installation=installation, key=required_secret).exists()
        checks.append({"name": "secret_binding", "ok": bound, "key": required_secret})
        if not bound:
            status = "blocked"

    egress_host = str(connector.get("egress_host") or "").strip()
    if egress_host:
        normalized_host = normalize_egress_host(egress_host)
        allowed = normalized_host in _manifest_egress_hosts(installation)
        checks.append({"name": "egress_declaration", "ok": allowed, "host": normalized_host})
        if not allowed:
            status = "blocked"
        denied = denied_egress_hosts([normalized_host])
        if denied:
            checks.append({"name": "egress_policy", "ok": False, "host": normalized_host})
            status = "blocked"
    error = "; ".join(str(check.get("name") or "check") for check in checks if not check.get("ok"))
    record_plugin_health_result(installation, status=status, error=error, actor=actor, request=request)

    return {
        "plugin_id": plugin_id,
        "connector_id": connector_id,
        "status": status,
        "connector": connector,
        "checks": checks,
    }


def ping_connector(plugin_id: str, connector_id: str, *, actor=None, request=None) -> dict[str, Any]:
    health = connector_health(plugin_id, connector_id, actor=actor, request=request)
    if health["status"] != "healthy":
        raise PluginConnectorError("Connector health is blocked.")
    connector = health["connector"]
    required_permission = str(connector.get("required_permission") or "").strip()
    if required_permission:
        decision = check_plugin_permission(plugin_id, required_permission, actor)
        if not decision.allowed:
            raise PluginConnectorError(decision.reason)
    installation = PluginInstallation.objects.get(plugin_id=plugin_id)
    record_event(
        plugin_id=plugin_id,
        event_type="plugin_connector_ping",
        status=UserActivityLog.STATUS_SUCCESS,
        actor=actor,
        request=request,
        installation=installation,
        message=f"Connector {connector_id} ping executed.",
        metadata={"connector_id": connector_id},
    )
    return {"success": True, "status": "ok", "connector_id": connector_id}
