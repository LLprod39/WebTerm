from __future__ import annotations

from typing import Any

from django.conf import settings

from kubernetes_ops.permissions import (
    KUBERNETES_ADMIN_READ_FEATURE,
    KUBERNETES_ADMIN_WRITE_FEATURE,
    KUBERNETES_BREAK_GLASS_FEATURE,
    KUBERNETES_FEATURE,
    KUBERNETES_SECRET_READ_FEATURE,
    kubernetes_permission_policy,
)


def build_kubernetes_capabilities_payload(user) -> dict[str, Any]:
    policy = kubernetes_permission_policy(user)
    workflows = _workflows(policy)
    return {
        "success": True,
        "operation": "kubernetes_capabilities",
        "policy": {
            "mutates_state": False,
            "runs_live_checks": False,
            "source": "webterm_feature_permissions_and_runtime_flags",
        },
        "modes": _modes(policy),
        "workflows": workflows,
        "summary": _summary(workflows),
        "runtime_flags": _runtime_flags(),
        "blocked_capabilities": list(policy.get("blocked_capabilities") or []),
    }


def _modes(policy: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": "kubernetes",
            "feature": KUBERNETES_FEATURE,
            "granted": bool(policy.get("has_kubernetes_feature")),
            "active": bool(policy.get("can_read")),
            "purpose": "Safe read-only cockpit, diagnosis drafts and action requests.",
            "capabilities": list(policy.get("read_only_capabilities") or [])
            + list(policy.get("action_request_capabilities") or []),
        },
        {
            "id": "kubernetes_admin_read",
            "feature": KUBERNETES_ADMIN_READ_FEATURE,
            "granted": bool(policy.get("has_kubernetes_admin_read_feature")),
            "active": bool(policy.get("can_admin_read")),
            "purpose": "Live low-level resource explorer, YAML, events, logs and watch.",
            "capabilities": list(policy.get("admin_read_capabilities") or []),
        },
        {
            "id": "kubernetes_admin_write",
            "feature": KUBERNETES_ADMIN_WRITE_FEATURE,
            "granted": bool(policy.get("has_kubernetes_admin_write_feature")),
            "active": bool(policy.get("can_admin_write")),
            "purpose": "Controlled write sessions and dry-run-first mutations.",
            "capabilities": list(policy.get("admin_write_request_capabilities") or []),
        },
        {
            "id": "kubernetes_break_glass",
            "feature": KUBERNETES_BREAK_GLASS_FEATURE,
            "granted": bool(policy.get("has_kubernetes_break_glass_feature")),
            "active": bool(policy.get("can_break_glass")),
            "purpose": "Emergency time-limited exec, port-forward, terminal, node debug and node maintenance requests.",
            "capabilities": list(policy.get("break_glass_request_capabilities") or []),
        },
        {
            "id": "kubernetes_secret_read",
            "feature": KUBERNETES_SECRET_READ_FEATURE,
            "granted": bool(policy.get("has_kubernetes_secret_read_feature")),
            "active": bool(policy.get("can_view_secret_values")),
            "purpose": "Explicit gated Secret value reveal for approved admin-read sessions.",
            "capabilities": ["secret.values.view"] if policy.get("can_view_secret_values") else [],
        },
    ]


def _workflows(policy: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _workflow(
            policy,
            "safe_cockpit",
            "kubernetes",
            available=bool(policy.get("can_read")),
            requestable=bool(policy.get("can_read")),
            mutates_state=False,
            feature=KUBERNETES_FEATURE,
            requirements=["explicit_kubernetes_feature"],
        ),
        _workflow(
            policy,
            "diagnosis_draft",
            "kubernetes",
            available=bool(policy.get("can_create_diagnosis_draft")),
            requestable=bool(policy.get("can_read")),
            mutates_state=False,
            feature="studio_pipelines",
            requirements=["kubernetes_feature", "studio_pipelines_feature", "owned_read_only_kubernetes_mcp"],
        ),
        _workflow(
            policy,
            "action_request",
            "kubernetes",
            available=bool(policy.get("can_request_action_approval")),
            requestable=bool(policy.get("can_read")),
            mutates_state=False,
            feature=KUBERNETES_FEATURE,
            requirements=["explicit_kubernetes_feature"],
        ),
        _workflow(
            policy,
            "live_resource_explorer",
            "kubernetes_admin_read",
            available=bool(policy.get("can_live_resource_get")),
            requestable=bool(policy.get("can_admin_read")),
            mutates_state=False,
            feature=KUBERNETES_ADMIN_READ_FEATURE,
            runtime_flag="KUBERNETES_ADMIN_MODE_ENABLED",
            requirements=["active_admin_read_session"],
        ),
        _workflow(
            policy,
            "logs_stream",
            "kubernetes_admin_read",
            available=bool(policy.get("can_stream_logs")),
            requestable=bool(policy.get("can_admin_read")),
            mutates_state=False,
            feature=KUBERNETES_ADMIN_READ_FEATURE,
            runtime_flag="KUBERNETES_ADMIN_MODE_ENABLED",
            requirements=["active_admin_read_session", "logs_scope"],
        ),
        _workflow(
            policy,
            "secret_values",
            "kubernetes_secret_read",
            available=bool(policy.get("can_view_secret_values")),
            requestable=bool(policy.get("can_admin_read")),
            mutates_state=False,
            feature=KUBERNETES_SECRET_READ_FEATURE,
            runtime_flag="KUBERNETES_ADMIN_SECRET_READ_ENABLED",
            requirements=[
                "kubernetes_admin_read_feature",
                "kubernetes_secret_read_feature",
                "active_admin_read_session",
                "include_secret_values=1",
            ],
        ),
        _workflow(
            policy,
            "dry_run_apply",
            "kubernetes_admin_write",
            available=bool(policy.get("can_dry_run_apply")),
            requestable=bool(policy.get("can_admin_write")),
            mutates_state=False,
            feature=KUBERNETES_ADMIN_WRITE_FEATURE,
            runtime_flag="KUBERNETES_ADMIN_MODE_ENABLED",
            requirements=["active_approved_write_session"],
        ),
        _workflow(
            policy,
            "apply_yaml",
            "kubernetes_admin_write",
            available=bool(policy.get("can_apply_yaml") or policy.get("can_break_glass_apply")),
            requestable=bool(policy.get("can_admin_write") or policy.get("can_break_glass")),
            mutates_state=True,
            feature=KUBERNETES_ADMIN_WRITE_FEATURE,
            runtime_flag="KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED",
            requirements=[
                "active_approved_write_session",
                "fresh_matching_dry_run_proof",
                "ownership_guard",
                "production_restricted_credential_evidence_when_required",
            ],
        ),
        _workflow(
            policy,
            "patch",
            "kubernetes_admin_write",
            available=bool(policy.get("can_patch")),
            requestable=bool(policy.get("can_admin_write")),
            mutates_state=True,
            feature=KUBERNETES_ADMIN_WRITE_FEATURE,
            runtime_flag="KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED",
            requirements=["active_approved_write_session", "non_sensitive_patch_body", "ownership_guard"],
        ),
        _workflow(
            policy,
            "scale",
            "kubernetes_admin_write",
            available=bool(policy.get("can_scale")),
            requestable=bool(policy.get("can_admin_write")),
            mutates_state=True,
            feature=KUBERNETES_ADMIN_WRITE_FEATURE,
            runtime_flag="KUBERNETES_ADMIN_NATIVE_SCALE_ENABLED",
            requirements=["active_approved_write_session", "bounded_replica_count", "ownership_guard"],
        ),
        _workflow(
            policy,
            "rollout_restart",
            "kubernetes_admin_write",
            available=bool(policy.get("can_restart")),
            requestable=bool(policy.get("can_admin_write")),
            mutates_state=True,
            feature=KUBERNETES_ADMIN_WRITE_FEATURE,
            runtime_flag="KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED",
            requirements=["active_approved_write_session", "deployment_statefulset_or_daemonset", "ownership_guard"],
        ),
        _workflow(
            policy,
            "delete",
            "kubernetes_admin_write",
            available=bool(policy.get("can_delete")),
            requestable=bool(policy.get("can_admin_write")),
            mutates_state=True,
            feature=KUBERNETES_ADMIN_WRITE_FEATURE,
            runtime_flag="KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED",
            requirements=[
                "active_approved_write_session",
                "exact_typed_confirmation",
                "protected_namespace_guard",
                "ownership_guard",
            ],
        ),
        _workflow(
            policy,
            "pod_exec",
            "kubernetes_break_glass",
            available=bool(policy.get("can_exec")),
            requestable=bool(policy.get("can_break_glass")),
            mutates_state=True,
            feature=KUBERNETES_BREAK_GLASS_FEATURE,
            runtime_flag="KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED",
            transport_flag="KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED",
            requirements=[
                "active_approved_break_glass_session",
                "command_policy",
                "recording_enabled",
                "restricted_credential_evidence_when_required",
            ],
        ),
        _workflow(
            policy,
            "port_forward",
            "kubernetes_break_glass",
            available=bool(policy.get("can_port_forward")),
            requestable=bool(policy.get("can_break_glass")),
            mutates_state=True,
            feature=KUBERNETES_BREAK_GLASS_FEATURE,
            runtime_flag="KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED",
            transport_flag="KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED",
            requirements=[
                "active_approved_break_glass_session",
                "exact_target_allowlist",
                "recording_enabled",
                "network_policy_evidence_when_required",
            ],
        ),
        _workflow(
            policy,
            "node_maintenance",
            "kubernetes_break_glass",
            available=bool(policy.get("can_node_maintenance")),
            requestable=bool(policy.get("can_break_glass")),
            mutates_state=True,
            feature=KUBERNETES_BREAK_GLASS_FEATURE,
            runtime_flag="KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED",
            requirements=[
                "active_approved_break_glass_session",
                "node_scope",
                "reason",
                "eviction_preflight_for_drain",
            ],
        ),
        _workflow(
            policy,
            "node_drain",
            "kubernetes_break_glass",
            available=bool(policy.get("can_node_drain")),
            requestable=bool(policy.get("can_node_maintenance")),
            mutates_state=True,
            feature=KUBERNETES_BREAK_GLASS_FEATURE,
            runtime_flag="KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED",
            requirements=["active_approved_break_glass_session", "exact_confirmation", "safe_pod_eviction_plan"],
        ),
        _workflow(
            policy,
            "cluster_terminal",
            "kubernetes_break_glass",
            available=bool(policy.get("can_break_glass") and _flag("KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED")),
            requestable=bool(policy.get("can_break_glass")),
            mutates_state=True,
            feature=KUBERNETES_BREAK_GLASS_FEATURE,
            runtime_flag="KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED",
            transport_flag="KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED",
            requirements=[
                "active_approved_break_glass_session",
                "restricted_context",
                "recording_enabled",
                "provider_path_template",
            ],
        ),
        _workflow(
            policy,
            "node_debug",
            "kubernetes_break_glass",
            available=bool(policy.get("can_break_glass") and _flag("KUBERNETES_ADMIN_NODE_DEBUG_ENABLED")),
            requestable=bool(policy.get("can_break_glass")),
            mutates_state=True,
            feature=KUBERNETES_BREAK_GLASS_FEATURE,
            runtime_flag="KUBERNETES_ADMIN_NODE_DEBUG_ENABLED",
            transport_flag="KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED",
            requirements=[
                "active_approved_break_glass_session",
                "node_scope",
                "recording_enabled",
                "provider_path_template",
            ],
        ),
    ]


def _workflow(
    policy: dict[str, Any],
    workflow_id: str,
    mode: str,
    *,
    available: bool,
    requestable: bool,
    mutates_state: bool,
    feature: str,
    requirements: list[str],
    runtime_flag: str = "",
    transport_flag: str = "",
) -> dict[str, Any]:
    blocked_reason = ""
    if not available:
        blocked_reason = _blocked_reason(policy, feature=feature, runtime_flag=runtime_flag)
    return {
        "id": workflow_id,
        "mode": mode,
        "available": bool(available),
        "requestable": bool(requestable),
        "mutates_state": bool(mutates_state),
        "requires_session": any("session" in item for item in requirements),
        "feature_required": feature,
        "runtime_flag": runtime_flag,
        "runtime_enabled": _flag(runtime_flag) if runtime_flag else True,
        "transport_flag": transport_flag,
        "transport_enabled": _flag(transport_flag) if transport_flag else True,
        "requirements": requirements,
        "blocked_reason": blocked_reason,
    }


def _blocked_reason(policy: dict[str, Any], *, feature: str, runtime_flag: str) -> str:
    if feature == KUBERNETES_FEATURE and not policy.get("has_kubernetes_feature"):
        return "kubernetes_feature_required"
    if feature == KUBERNETES_ADMIN_READ_FEATURE and not policy.get("has_kubernetes_admin_read_feature"):
        return "kubernetes_admin_read_feature_required"
    if feature == KUBERNETES_ADMIN_WRITE_FEATURE and not policy.get("has_kubernetes_admin_write_feature"):
        return "kubernetes_admin_write_feature_required"
    if feature == KUBERNETES_BREAK_GLASS_FEATURE and not policy.get("has_kubernetes_break_glass_feature"):
        return "kubernetes_break_glass_feature_required"
    if feature == KUBERNETES_SECRET_READ_FEATURE and not policy.get("has_kubernetes_secret_read_feature"):
        return "kubernetes_secret_read_feature_required"
    if runtime_flag and not _flag(runtime_flag):
        return f"{runtime_flag.lower()}_disabled"
    if not policy.get("admin_mode_enabled") and feature in {
        KUBERNETES_ADMIN_READ_FEATURE,
        KUBERNETES_ADMIN_WRITE_FEATURE,
        KUBERNETES_BREAK_GLASS_FEATURE,
    }:
        return "kubernetes_admin_mode_disabled"
    return "policy_not_satisfied"


def _summary(workflows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(workflows),
        "available": sum(1 for item in workflows if item["available"]),
        "requestable": sum(1 for item in workflows if item["requestable"]),
        "mutating_available": sum(1 for item in workflows if item["available"] and item["mutates_state"]),
        "blocked": sum(1 for item in workflows if not item["available"]),
    }


def _runtime_flags() -> dict[str, bool]:
    names = (
        "KUBERNETES_ADMIN_MODE_ENABLED",
        "KUBERNETES_ADMIN_SECRET_READ_ENABLED",
        "KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED",
        "KUBERNETES_ADMIN_BREAK_GLASS_APPLY_BYPASS_ENABLED",
        "KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED",
        "KUBERNETES_ADMIN_NATIVE_SCALE_ENABLED",
        "KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED",
        "KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED",
        "KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED",
        "KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED",
        "KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED",
        "KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED",
        "KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED",
        "KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED",
        "KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED",
        "KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED",
        "KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED",
        "KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED",
        "KUBERNETES_ADMIN_NODE_DEBUG_ENABLED",
        "KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED",
        "KUBERNETES_ACTION_REQUEST_NATIVE_EXECUTION_ENABLED",
    )
    return {name: _flag(name) for name in names}


def _flag(name: str) -> bool:
    if not name:
        return True
    value = getattr(settings, name, False)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
