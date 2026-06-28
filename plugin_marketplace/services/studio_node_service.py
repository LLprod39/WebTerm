from __future__ import annotations

from typing import Any

from app.plugins.permissions import check_plugin_permission
from plugin_marketplace.models import PluginInstallation
from plugin_marketplace.services.access_scope_service import installation_allowed_for_user
from plugin_marketplace.services.backend_sandbox_service import execute_backend_sandbox, sandbox_executor_ref
from plugin_marketplace.services.health_service import PluginConnectorError, ping_connector


def _enabled_installation(plugin_id: str, user=None) -> PluginInstallation | None:
    installation = PluginInstallation.objects.prefetch_related("scoped_groups").filter(
        plugin_id=plugin_id,
        status=PluginInstallation.STATUS_ENABLED,
    ).first()
    if installation is None or not installation_allowed_for_user(installation, user):
        return None
    return installation


def studio_node_execution_provider(payload: dict[str, Any]) -> dict[str, Any]:
    manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else {}
    metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    plugin_id = str(metadata.get("plugin_id") or payload.get("plugin_id") or "").strip()
    node_type = str(manifest.get("type") or payload.get("node_type") or "").strip()
    user = payload.get("user")

    if not plugin_id or _enabled_installation(plugin_id, user) is None:
        return {"status": "failed", "error": "Plugin is disabled or missing."}

    required_permission = str(metadata.get("required_permission") or "").strip()
    if required_permission:
        decision = check_plugin_permission(plugin_id, required_permission, user)
        if not decision.allowed:
            return {"status": "failed", "error": decision.reason}

    executor_ref = str(metadata.get("executor_ref") or "").strip()
    if sandbox_executor_ref(executor_ref):
        result = execute_backend_sandbox(
            plugin_id=plugin_id,
            executor_ref=executor_ref,
            payload={
                "surface": "studio_node",
                "node_type": node_type,
                "data": payload.get("data") if isinstance(payload.get("data"), dict) else {},
                "context": payload.get("context") if isinstance(payload.get("context"), dict) else {},
            },
            user=user,
        )
        if not result.get("success"):
            return {"status": "failed", "error": str(result.get("error") or "Sandbox execution failed.")}
        return {
            "status": "completed",
            "plugin_id": plugin_id,
            "node_type": node_type,
            "output": result.get("result"),
            "sandbox": True,
        }
    if executor_ref == "plugin_marketplace.demo.connector_ping":
        connector_id = str(
            (payload.get("data") if isinstance(payload.get("data"), dict) else {}).get("connector_id")
            or metadata.get("connector_id")
            or "demo-connector"
        ).strip()
        try:
            result = ping_connector(plugin_id, connector_id, actor=user, request=None)
        except PluginConnectorError as exc:
            return {"status": "failed", "error": str(exc)}
        return {
            **result,
            "status": "completed",
            "output": f"Plugin connector {connector_id} ping executed.",
            "plugin_id": plugin_id,
            "node_type": node_type,
        }

    return {
        "status": "failed",
        "error": f"No plugin Studio node executor is registered for {executor_ref or node_type}.",
    }
