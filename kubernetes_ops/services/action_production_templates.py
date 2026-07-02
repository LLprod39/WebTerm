from __future__ import annotations

from typing import Any

from kubernetes_ops.models import K8sActionRequest
from kubernetes_ops.services.action_sanitizers import reference_action_text, sanitize_action_value


PRODUCTION_ROLLOUT_RESTART_TEMPLATE_SCHEMA = "kubernetes_ops.production_rollout_restart_template.v1"
PRODUCTION_RESTART_CHECK_IDS = ["rollout_status_observed", "pod_readiness_observed", "recent_warning_events_checked"]


def rollout_restart_production_template(
    *,
    target: dict[str, Any],
    preview: dict[str, Any],
    rollback_plan: dict[str, Any],
) -> dict[str, Any]:
    safe_target = _safe_target(target)
    return {
        "schema_version": PRODUCTION_ROLLOUT_RESTART_TEMPLATE_SCHEMA,
        "status": "ready",
        "action": K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART,
        "mode": "approval_verification_report",
        "target": safe_target,
        "direct_execution": False,
        "native_execution_default": "disabled",
        "payload_stored": False,
        "sensitive_values_stored": False,
        "approval": {
            "required": True,
            "status": K8sActionRequest.STATUS_PENDING_APPROVAL,
            "approval_ref_required": True,
            "reason_required": True,
        },
        "execution": {
            "external_first": True,
            "allowed_modes": ["external_rancher_or_devtron", "external_gitops", "webterm_native_gated"],
            "webterm_native_requires": [
                "KUBERNETES_ACTION_REQUEST_NATIVE_EXECUTION_ENABLED",
                "KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED",
                "approved_admin_write_session",
                "restricted_credential_evidence_for_production",
            ],
        },
        "verification": {
            "required": True,
            "check_ids": list(PRODUCTION_RESTART_CHECK_IDS),
            "expected_evidence": list(preview.get("expected_verification") or []),
        },
        "report": {
            "required": True,
            "endpoint": "/api/kubernetes/actions/{action_id}/report/",
            "contains": ["request", "execution_policy", "rollback_plan", "verification", "audit_timeline"],
        },
        "rollback": {
            "required": True,
            "strategy": reference_action_text(rollback_plan.get("strategy") or "rollout_recovery"),
            "evidence_required": [reference_action_text(item) for item in rollback_plan.get("evidence_required") or []],
        },
        "lifecycle": [
            {"id": "request", "result_status": K8sActionRequest.STATUS_PENDING_APPROVAL},
            {"id": "approve", "result_status": K8sActionRequest.STATUS_APPROVED_EXTERNAL},
            {"id": "execute", "result_status": "external_or_webterm_native_gated"},
            {"id": "verify", "result_status": "verified_external_or_verified_native"},
            {"id": "report", "result_status": "report_available"},
        ],
    }


def production_rollout_restart_template_is_safe(template: dict[str, Any]) -> bool:
    return (
        template.get("status") == "ready"
        and template.get("direct_execution") is False
        and template.get("payload_stored") is False
        and template.get("sensitive_values_stored") is False
        and "token" not in str(template).lower()
    )


def _safe_target(target: dict[str, Any]) -> dict[str, Any]:
    safe = sanitize_action_value(target)
    return {
        "cluster_id": reference_action_text(safe.get("cluster_id") or ""),
        "cluster_name": reference_action_text(safe.get("cluster_name") or ""),
        "namespace": reference_action_text(safe.get("namespace") or ""),
        "kind": reference_action_text(safe.get("kind") or ""),
        "name": reference_action_text(safe.get("name") or ""),
    }
