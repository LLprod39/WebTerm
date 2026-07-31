from __future__ import annotations

from typing import Any

from django.conf import settings

from core_ui.models import UserActivityLog
from plugin_marketplace.models import PluginInstallation
from plugin_marketplace.services.backend_sandbox_runner_service import execute_sandbox_package
from plugin_marketplace.services.health_service import record_plugin_health_result
from plugin_marketplace.services.install_service import record_event
from plugin_marketplace.services.package_retention_service import PackageRetentionError, read_retained_package_bytes
from plugin_marketplace.services.sandbox_policy_service import sandbox_policy_for_package


def sandbox_executor_ref(executor_ref: str) -> bool:
    return str(executor_ref or "").strip().startswith("sandbox:")


def _sandbox_enabled() -> bool:
    return bool(getattr(settings, "PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED", False)) and bool(
        getattr(settings, "PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES", False)
    )


def _retained_package_bytes(installation: PluginInstallation) -> bytes:
    provenance = installation.package.provenance if isinstance(installation.package.provenance, dict) else {}
    retention = provenance.get("retention") if isinstance(provenance.get("retention"), dict) else {}
    return read_retained_package_bytes(retention)


def _sandbox_failure(
    installation: PluginInstallation,
    *,
    executor_ref: str,
    error: str,
    user=None,
    request=None,
    event_type: str = "plugin_backend_sandbox_failed",
) -> dict[str, Any]:
    record_plugin_health_result(
        installation,
        status="sandbox_failed",
        error=error,
        actor=user,
        request=request,
        quarantine_event_type="plugin_backend_sandbox_auto_quarantined",
        quarantine_message=f"Plugin {installation.plugin_id} quarantined after repeated backend sandbox failures.",
        metadata={"executor_ref": executor_ref},
    )
    record_event(
        plugin_id=installation.plugin_id,
        event_type=event_type,
        status=UserActivityLog.STATUS_ERROR,
        actor=user,
        request=request,
        installation=installation,
        message=f"Plugin backend sandbox executor {executor_ref} failed.",
        metadata={
            "executor_ref": executor_ref,
            "success": False,
            "error": error,
            "health_failure_count": installation.health_failure_count,
        },
    )
    return {"success": False, "error": error}


def execute_backend_sandbox(
    *,
    plugin_id: str,
    executor_ref: str,
    payload: dict[str, Any],
    user=None,
    request=None,
) -> dict[str, Any]:
    installation = (
        PluginInstallation.objects.select_related("package")
        .filter(plugin_id=plugin_id, status=PluginInstallation.STATUS_ENABLED)
        .first()
    )
    if not installation:
        return {"success": False, "error": "Plugin is disabled or missing."}
    if not _sandbox_enabled():
        return _sandbox_failure(
            installation,
            executor_ref=executor_ref,
            error="Plugin backend code execution is not enabled.",
            user=user,
            request=request,
            event_type="plugin_backend_sandbox_blocked",
        )
    policy = sandbox_policy_for_package(installation.package)
    if not policy.get("allowed"):
        return _sandbox_failure(
            installation,
            executor_ref=executor_ref,
            error="; ".join(policy.get("blockers") or ["Plugin code execution policy blocked execution."]),
            user=user,
            request=request,
            event_type="plugin_backend_sandbox_blocked",
        )
    try:
        package_bytes = _retained_package_bytes(installation)
    except PackageRetentionError as exc:
        return _sandbox_failure(
            installation,
            executor_ref=executor_ref,
            error=str(exc),
            user=user,
            request=request,
        )

    result = execute_sandbox_package(
        package_bytes=package_bytes,
        executor_ref=executor_ref,
        payload={"plugin_id": plugin_id, "executor_ref": executor_ref, "payload": payload},
    )

    record_event(
        plugin_id=plugin_id,
        event_type="plugin_backend_sandbox_executed",
        status=UserActivityLog.STATUS_SUCCESS if result.get("success") else UserActivityLog.STATUS_ERROR,
        actor=user,
        request=request,
        installation=installation,
        message=f"Plugin backend sandbox executor {executor_ref} finished.",
        metadata={
            "executor_ref": executor_ref,
            "success": bool(result.get("success")),
            "error": "" if result.get("success") else str(result.get("error") or "Sandbox execution failed."),
        },
    )
    if result.get("success"):
        record_plugin_health_result(
            installation,
            status="healthy",
            actor=user,
            request=request,
            metadata={"executor_ref": executor_ref},
        )
    else:
        record_plugin_health_result(
            installation,
            status="sandbox_failed",
            error=str(result.get("error") or "Sandbox execution failed."),
            actor=user,
            request=request,
            quarantine_event_type="plugin_backend_sandbox_auto_quarantined",
            quarantine_message=f"Plugin {installation.plugin_id} quarantined after repeated backend sandbox failures.",
            metadata={"executor_ref": executor_ref},
        )
    return result
