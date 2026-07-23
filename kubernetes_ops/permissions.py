from __future__ import annotations

from typing import Any

from django.conf import settings

from core_ui.access import feature_allowed_for_user

KUBERNETES_FEATURE = "kubernetes"
KUBERNETES_ADMIN_READ_FEATURE = "kubernetes_admin_read"
KUBERNETES_ADMIN_WRITE_FEATURE = "kubernetes_admin_write"
KUBERNETES_BREAK_GLASS_FEATURE = "kubernetes_break_glass"
KUBERNETES_SECRET_READ_FEATURE = "kubernetes_secret_read"
STUDIO_PIPELINES_FEATURE = "studio_pipelines"

READ_ONLY_CAPABILITIES = (
    "overview",
    "providers.read",
    "clusters.read",
    "inventory.read",
    "events.read",
    "audit.read",
    "workload.describe",
    "pod.logs.snapshot",
    "fleet.read",
    "devtron.read",
    "actions.status",
    "actions.report",
)
ACTION_REQUEST_CAPABILITIES = ("actions.request_approval",)
ADMIN_CAPABILITIES = (
    "providers.write",
    "providers.sync",
    "providers.probe",
    "deeplink.audit",
)
ADMIN_READ_CAPABILITIES = (
    "admin_session.read",
    "live_resource.get",
    "live_resource.watch",
    "full_yaml.view",
    "pod.logs.stream",
)
SECRET_READ_CAPABILITY = "secret.values.view"
ADMIN_WRITE_REQUEST_CAPABILITIES = (
    "admin_session.write",
    "apply_yaml.dry_run",
    "patch.request",
    "scale.request",
    "delete.request",
)
BREAK_GLASS_REQUEST_CAPABILITIES = (
    "admin_session.break_glass",
    "pod.exec.request",
    "port_forward.request",
    "node_debug.request",
    "node_maintenance.request",
    "cluster_terminal.request",
)
BLOCKED_CAPABILITIES = (
    "pod.exec",
    "pod.attach",
    "port_forward",
    "node_debug",
    "node_maintenance",
    "node_drain",
    "cluster_terminal",
    "rollout_restart",
    "patch",
    "scale",
    "delete",
    "apply_yaml",
)


def kubernetes_admin_mode_enabled() -> bool:
    return bool(getattr(settings, "KUBERNETES_ADMIN_MODE_ENABLED", True))


def kubernetes_permission_policy(user) -> dict[str, Any]:
    authenticated = bool(user and getattr(user, "is_authenticated", False))
    is_staff = bool(authenticated and getattr(user, "is_staff", False))
    admin_mode_enabled = kubernetes_admin_mode_enabled()
    has_kubernetes = bool(authenticated and feature_allowed_for_user(user, KUBERNETES_FEATURE))
    has_admin_read = bool(authenticated and feature_allowed_for_user(user, KUBERNETES_ADMIN_READ_FEATURE))
    has_admin_write = bool(authenticated and feature_allowed_for_user(user, KUBERNETES_ADMIN_WRITE_FEATURE))
    has_break_glass = bool(authenticated and feature_allowed_for_user(user, KUBERNETES_BREAK_GLASS_FEATURE))
    has_secret_read = bool(authenticated and feature_allowed_for_user(user, KUBERNETES_SECRET_READ_FEATURE))
    has_studio_pipelines = bool(authenticated and feature_allowed_for_user(user, STUDIO_PIPELINES_FEATURE))
    can_read = authenticated and has_kubernetes
    can_admin = can_read and is_staff
    can_admin_read = can_read and admin_mode_enabled and has_admin_read
    can_admin_write = can_read and admin_mode_enabled and has_admin_write
    can_break_glass = can_read and admin_mode_enabled and has_break_glass
    native_apply_enabled = bool(getattr(settings, "KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED", False))
    native_patch_enabled = bool(getattr(settings, "KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED", False))
    native_scale_enabled = bool(getattr(settings, "KUBERNETES_ADMIN_NATIVE_SCALE_ENABLED", False))
    native_restart_enabled = bool(getattr(settings, "KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED", False))
    native_delete_enabled = bool(getattr(settings, "KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED", False))
    native_exec_enabled = bool(getattr(settings, "KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED", False))
    native_port_forward_enabled = bool(getattr(settings, "KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED", False))
    native_node_maintenance_enabled = bool(getattr(settings, "KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED", False))
    node_drain_execution_enabled = bool(getattr(settings, "KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED", False))
    break_glass_apply_bypass_enabled = bool(
        getattr(settings, "KUBERNETES_ADMIN_BREAK_GLASS_APPLY_BYPASS_ENABLED", False)
    )
    native_action_request_execution_enabled = bool(
        getattr(settings, "KUBERNETES_ACTION_REQUEST_NATIVE_EXECUTION_ENABLED", False)
    )
    secret_read_enabled = bool(getattr(settings, "KUBERNETES_ADMIN_SECRET_READ_ENABLED", False))
    can_apply_yaml = can_admin_write and native_apply_enabled
    can_break_glass_apply = can_break_glass and native_apply_enabled and break_glass_apply_bypass_enabled
    can_patch = can_admin_write and native_patch_enabled
    can_scale = can_admin_write and native_scale_enabled
    can_restart = can_admin_write and native_restart_enabled
    can_delete = can_admin_write and native_delete_enabled
    can_exec = can_break_glass and native_exec_enabled
    can_port_forward = can_break_glass and native_port_forward_enabled
    can_node_maintenance = can_break_glass and native_node_maintenance_enabled
    can_node_drain = can_node_maintenance and node_drain_execution_enabled
    can_view_secret_values = can_admin_read and has_secret_read and secret_read_enabled
    admin_read_capabilities = list(ADMIN_READ_CAPABILITIES) if can_admin_read else []
    if can_view_secret_values:
        admin_read_capabilities.append(SECRET_READ_CAPABILITY)
    blocked_capabilities = [
        capability
        for capability in BLOCKED_CAPABILITIES
        if (capability != "apply_yaml" or not (can_apply_yaml or can_break_glass_apply))
        and (capability != "patch" or not can_patch)
        and (capability != "scale" or not can_scale)
        and (capability != "rollout_restart" or not can_restart)
        and (capability != "delete" or not can_delete)
        and (capability != "pod.exec" or not can_exec)
        and (capability != "port_forward" or not can_port_forward)
        and (capability != "node_maintenance" or not can_node_maintenance)
        and (capability != "node_drain" or not can_node_drain)
    ]

    return {
        "feature": KUBERNETES_FEATURE,
        "authenticated": authenticated,
        "is_staff": is_staff,
        "admin_mode_enabled": admin_mode_enabled,
        "has_kubernetes_feature": has_kubernetes,
        "has_kubernetes_admin_read_feature": has_admin_read,
        "has_kubernetes_admin_write_feature": has_admin_write,
        "has_kubernetes_break_glass_feature": has_break_glass,
        "has_kubernetes_secret_read_feature": has_secret_read,
        "has_studio_pipelines_feature": has_studio_pipelines,
        "can_read": can_read,
        "can_read_log_snapshots": can_read,
        "can_audit_deeplinks": can_admin,
        "can_create_diagnosis_draft": can_read and has_studio_pipelines,
        "can_request_action_approval": can_read,
        "can_execute_approved_action": native_action_request_execution_enabled
        and (can_apply_yaml or can_restart or can_scale or can_patch or can_delete),
        "can_admin_providers": can_admin,
        "can_sync_providers": can_admin,
        "can_probe_providers": can_admin,
        "can_admin_read": can_admin_read,
        "can_live_resource_get": can_admin_read,
        "can_live_resource_watch": can_admin_read,
        "can_view_full_yaml": can_admin_read,
        "can_view_secret_values": can_view_secret_values,
        "can_stream_logs": can_admin_read,
        "can_admin_write": can_admin_write,
        "can_request_mutating_session": can_admin_write,
        "can_dry_run_apply": can_admin_write,
        "can_apply_yaml": can_apply_yaml,
        "can_break_glass_apply": can_break_glass_apply,
        "can_patch": can_patch,
        "can_scale": can_scale,
        "can_restart": can_restart,
        "can_delete": can_delete,
        "can_port_forward": can_port_forward,
        "can_node_maintenance": can_node_maintenance,
        "can_node_drain": can_node_drain,
        "can_break_glass": can_break_glass,
        "can_request_break_glass_session": can_break_glass,
        "can_mutate_cluster_state": can_apply_yaml
        or can_break_glass_apply
        or can_patch
        or can_scale
        or can_restart
        or can_delete
        or can_node_maintenance,
        "can_exec": can_exec,
        "read_only_capabilities": list(READ_ONLY_CAPABILITIES) if can_read else [],
        "action_request_capabilities": list(ACTION_REQUEST_CAPABILITIES) if can_read else [],
        "admin_capabilities": list(ADMIN_CAPABILITIES) if can_admin else [],
        "admin_read_capabilities": admin_read_capabilities,
        "admin_write_request_capabilities": list(ADMIN_WRITE_REQUEST_CAPABILITIES) if can_admin_write else [],
        "break_glass_request_capabilities": list(BREAK_GLASS_REQUEST_CAPABILITIES) if can_break_glass else [],
        "blocked_capabilities": blocked_capabilities,
    }


def kubernetes_permission_check(user) -> dict[str, Any]:
    policy = kubernetes_permission_policy(user)
    if not policy["can_read"]:
        return {
            "id": "permission_matrix",
            "status": "missing",
            "detail": "Current user does not have explicit Kubernetes feature access.",
            "required": True,
        }
    detail = (
        "Explicit Kubernetes feature is required for reads and action approval requests; provider write/sync/probe "
        "are staff-only; low-level Admin Mode uses separate explicit grants; exec/debug/mutations are disabled."
    )
    if policy["can_create_diagnosis_draft"]:
        detail += " Studio diagnosis draft creation is available."
    else:
        detail += " Studio diagnosis draft creation also requires studio_pipelines."
    return {
        "id": "permission_matrix",
        "status": "ready",
        "detail": detail,
        "required": True,
    }
