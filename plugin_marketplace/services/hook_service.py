from __future__ import annotations

from typing import Any

from app.plugins.hooks import active_hooks
from app.plugins.permissions import check_plugin_permission
from core_ui.models import UserActivityLog
from plugin_marketplace.models import PluginInstallation
from plugin_marketplace.services.access_scope_service import installation_allowed_for_user
from plugin_marketplace.services.backend_sandbox_service import execute_backend_sandbox, sandbox_executor_ref
from plugin_marketplace.services.install_service import record_event


def _enabled_installation(plugin_id: str, user=None) -> PluginInstallation | None:
    installation = (
        PluginInstallation.objects.prefetch_related("scoped_groups")
        .filter(
            plugin_id=plugin_id,
            status=PluginInstallation.STATUS_ENABLED,
        )
        .first()
    )
    if installation is None or not installation_allowed_for_user(installation, user):
        return None
    return installation


def _hook_definition(plugin_id: str, hook_id: str) -> dict[str, Any] | None:
    for hook in active_hooks({plugin_id}):
        if hook.get("plugin_id") == plugin_id and hook.get("id") == hook_id:
            return hook
    return None


def plugin_hook_execution_provider(payload: dict[str, Any]) -> dict[str, Any]:
    plugin_id = str(payload.get("plugin_id") or "")
    hook_id = str(payload.get("hook_id") or "")
    event = str(payload.get("event") or "")
    user = payload.get("user")
    hook = _hook_definition(plugin_id, hook_id)
    installation = _enabled_installation(plugin_id, user)
    if not hook or not installation:
        return {"success": False, "status": "missing", "plugin_id": plugin_id, "hook_id": hook_id}

    required_permission = str(hook.get("required_permission") or "")
    if required_permission:
        decision = check_plugin_permission(plugin_id, required_permission, user)
        if not decision.allowed:
            return {
                "success": False,
                "status": "blocked",
                "plugin_id": plugin_id,
                "hook_id": hook_id,
                "error": decision.reason,
            }

    executor_ref = str(hook.get("executor_ref") or "").strip()
    if sandbox_executor_ref(executor_ref):
        result = execute_backend_sandbox(
            plugin_id=plugin_id,
            executor_ref=executor_ref,
            payload={"surface": "hook", "hook_id": hook_id, "event": event, "payload": payload.get("payload") or {}},
            user=user,
        )
        return {
            "success": bool(result.get("success")),
            "status": "completed" if result.get("success") else "failed",
            "plugin_id": plugin_id,
            "hook_id": hook_id,
            "event": event,
            "sandbox": True,
            "result": result.get("result"),
            "error": "" if result.get("success") else str(result.get("error") or "Sandbox execution failed."),
        }

    record_event(
        plugin_id=plugin_id,
        event_type="plugin_hook_executed",
        status=UserActivityLog.STATUS_SUCCESS,
        actor=user,
        installation=installation,
        message=f"Plugin hook {hook_id} handled event {event}.",
        metadata={
            "hook_id": hook_id,
            "event": event,
            "payload_keys": sorted((payload.get("payload") or {}).keys()),
        },
    )
    return {
        "success": True,
        "status": "completed",
        "plugin_id": plugin_id,
        "hook_id": hook_id,
        "event": event,
    }
