from __future__ import annotations

from typing import Any

from app.plugins.permissions import check_plugin_permission
from plugin_marketplace.models import PluginInstallation
from plugin_marketplace.services.access_scope_service import installation_allowed_for_user
from plugin_marketplace.services.backend_sandbox_service import execute_backend_sandbox, sandbox_executor_ref
from plugin_marketplace.services.health_service import PluginConnectorError, ping_connector


def _enabled(plugin_id: str, user=None) -> bool:
    installation = PluginInstallation.objects.prefetch_related("scoped_groups").filter(
        plugin_id=plugin_id,
        status=PluginInstallation.STATUS_ENABLED,
    ).first()
    return bool(installation and installation_allowed_for_user(installation, user))


def _permission_error(plugin_id: str, scope: str, user) -> str:
    if not scope:
        return ""
    decision = check_plugin_permission(plugin_id, scope, user)
    return "" if decision.allowed else decision.reason


def agent_tool_execution_provider(payload: dict[str, Any]) -> dict[str, Any]:
    tool = payload.get("tool") if isinstance(payload.get("tool"), dict) else {}
    plugin_id = str(tool.get("plugin_id") or payload.get("plugin_id") or "").strip()
    if not plugin_id or not _enabled(plugin_id, payload.get("user")):
        return {"success": False, "result": "Plugin is disabled or missing."}

    permission_error = _permission_error(plugin_id, str(tool.get("required_permission") or ""), payload.get("user"))
    if permission_error:
        return {"success": False, "result": permission_error}

    executor_ref = str(tool.get("executor_ref") or "").strip()
    if sandbox_executor_ref(executor_ref):
        result = execute_backend_sandbox(
            plugin_id=plugin_id,
            executor_ref=executor_ref,
            payload={
                "surface": "agent_tool",
                "tool": tool,
                "arguments": payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {},
            },
            user=payload.get("user"),
        )
        return {
            "success": bool(result.get("success")),
            "result": result.get("result") if result.get("success") else str(result.get("error") or "Sandbox execution failed."),
            "data": {"plugin_id": plugin_id, "sandbox": True, "raw": result},
        }
    if executor_ref == "plugin_marketplace.demo.agent_connector_ping":
        try:
            result = ping_connector(plugin_id, "demo-connector", actor=payload.get("user"), request=None)
        except PluginConnectorError as exc:
            return {"success": False, "result": str(exc)}
        return {
            "success": True,
            "result": f"Plugin agent tool ping completed: {result['connector_id']}",
            "data": {"plugin_id": plugin_id, **result},
        }

    return {"success": False, "result": f"No plugin agent tool executor is registered for {executor_ref}."}


def terminal_action_execution_provider(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action") if isinstance(payload.get("action"), dict) else {}
    plugin_id = str(action.get("plugin_id") or payload.get("plugin_id") or "").strip()
    if not plugin_id or not _enabled(plugin_id, payload.get("user")):
        return {"success": False, "error": "Plugin is disabled or missing."}

    permission_error = _permission_error(plugin_id, str(action.get("required_permission") or ""), payload.get("user"))
    if permission_error:
        return {"success": False, "error": permission_error}

    executor_ref = str(action.get("executor_ref") or "").strip()
    if sandbox_executor_ref(executor_ref):
        result = execute_backend_sandbox(
            plugin_id=plugin_id,
            executor_ref=executor_ref,
            payload={"surface": "terminal_action", "action": action},
            user=payload.get("user"),
        )
        if not result.get("success"):
            return {"success": False, "error": str(result.get("error") or "Sandbox execution failed.")}
        return {
            "success": True,
            "status": "ok",
            "message": "Plugin terminal action sandbox execution completed.",
            "plugin_id": plugin_id,
            "sandbox": True,
            "result": result.get("result"),
        }
    if executor_ref == "plugin_marketplace.demo.terminal_connector_ping":
        try:
            result = ping_connector(plugin_id, "demo-connector", actor=payload.get("user"), request=None)
        except PluginConnectorError as exc:
            return {"success": False, "error": str(exc)}
        return {
            "success": True,
            "status": "ok",
            "message": "Plugin terminal action ping completed.",
            "plugin_id": plugin_id,
            **result,
        }

    return {"success": False, "error": f"No plugin terminal action executor is registered for {executor_ref}."}
