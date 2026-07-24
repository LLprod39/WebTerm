from __future__ import annotations

from django.contrib.auth.models import User

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sActionRequest
from kubernetes_ops.services.release_contract import RELEASE_EVIDENCE_SCHEMA_VERSION

PRODUCTION_RELEASE_SETTINGS = {
    "KUBERNETES_OPS_RELEASE_ENVIRONMENT": "production",
    "KUBERNETES_OPS_PRODUCTION_APPROVAL_REF": "CHG-K8S-1",
    "KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF": "artifact:production-bundle",
    "KUBERNETES_OPS_IDENTITY_RUNTIME_EVIDENCE_REF": "artifact:sso-proof",
    "KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF": "artifact:provider-proof",
    "KUBERNETES_OPS_READONLY_RBAC_EVIDENCE_REF": "artifact:rbac-proof",
    "KUBERNETES_OPS_KUBERNETES_MCP_EVIDENCE_REF": "artifact:mcp-proof",
    "KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF": "artifact:rollback-proof",
    "KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF": "artifact:native-verification-proof",
}
READY_PREFLIGHT_RESULT_IDS = [
    "django_check",
    "architecture_guard",
    "migrations_dry_run",
    "kubernetes_backend_tests",
    "readonly_rbac_validate",
    "sync_prune_safety",
    "readonly_rbac_live",
    "local_platform_evidence",
    "live_provider_smoke",
    "interactive_transport_evidence",
    "interactive_live_smoke",
    "interactive_production_controls",
    "production_action_evidence",
    "external_evidence_bundle",
]


def _grant(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(user=user, feature=feature, defaults={"allowed": True})


def _ready_report(ready_for_sidebar: bool) -> dict:
    return {
        "success": True,
        "status": "ready" if ready_for_sidebar else "configured",
        "ready_for_sidebar": ready_for_sidebar,
        "summary": {"ready": 12, "missing": 0, "manual": 0, "total": 12},
        "checks": [{"id": "architecture_guard", "status": "ready", "detail": "ok", "required": True}],
        "worker_state": {"status": "running", "is_stale": False},
        "access_model": {"status": "ready", "native_mutations_enabled": False, "exec_enabled": False},
        "identity_runtime": {
            "status": "ready",
            "identity_provider": "Keycloak/OIDC",
            "enforced": True,
            "webterm_login_gateway": {"status": "ready"},
        },
        "production_gate": {
            "target_environment": "production",
            "core_evidence_ready": True,
            "missing_reference_count": 0,
        },
    }


def _ready_rbac_live(context: str = "prod-kz") -> dict:
    return {
        "success": True,
        "status": "ready",
        "context": context,
        "applied": True,
        "service_account": "system:serviceaccount:webterm-system:webterm-kubernetes-readonly",
        "allowed_count": 7,
        "denied_count": 7,
        "errors": [],
    }


def _ready_interactive_transport() -> dict:
    return {
        "success": True,
        "status": "ready",
        "path": "artifacts/kubernetes_ops_interactive_transport_evidence.json",
        "schema_version": "kubernetes_ops.interactive_transport_evidence.v1",
        "age_seconds": 60,
        "max_age_seconds": 86400,
        "summary": {},
        "admin_interactive_transport": {"status": "ready"},
        "errors": [],
    }


def _ready_preflight() -> dict:
    return {
        "success": True,
        "status": "ready",
        "schema_version": "kubernetes_ops.release_preflight.v1",
        "release_evidence_schema_version": RELEASE_EVIDENCE_SCHEMA_VERSION,
        "results": [{"id": item, "success": True, "status": "ready"} for item in READY_PREFLIGHT_RESULT_IDS],
        "failed": [],
        "errors": [],
    }


def _ready_action_controls() -> dict:
    return {
        "success": True,
        "status": "ready",
        "native_execution_enabled": False,
        "approval_status": K8sActionRequest.STATUS_APPROVED_EXTERNAL,
        "approval_recorded": True,
        "external_verification_redacted": True,
        "blocked_execution_status": K8sActionRequest.STATUS_EXECUTION_BLOCKED,
        "terminal_execute_rejected": True,
        "terminal_verify_rejected": True,
        "rollback_plan_status": "required",
        "rollback_scale_previous_replicas": 2,
        "rollback_apply_requires_dry_run": True,
        "rollback_delete_requires_restore_source": True,
        "rollback_plan_payload_safe": True,
        "production_restart_template_status": "ready",
        "production_restart_template_approval_required": True,
        "production_restart_template_verification_required": True,
        "production_restart_template_report_required": True,
        "production_restart_template_safe": True,
        "native_verification_plan_status": "pending",
        "native_verification_plan_check_ids": [
            "rollout_status_observed",
            "pod_readiness_observed",
            "recent_warning_events_checked",
        ],
        "apply_verification_plan_check_ids": [
            "apply_action_completed",
            "resource_generation_observed",
            "recent_warning_events_checked",
        ],
        "native_verification_auto_status": "verified",
        "native_verification_auto_request_status": K8sActionRequest.STATUS_VERIFIED_NATIVE,
        "native_verification_auto_recorded": True,
        "native_verification_auto_check_statuses": ["passed", "passed", "passed"],
        "restricted_write_gate_required": True,
        "restricted_write_gate_blocks_without_ref": True,
        "restricted_write_gate_allows_with_ref": True,
        "restricted_write_gate_setting": "KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF",
        "restricted_write_gate_target_environment": "production",
        "native_verification_plan_payload_safe": True,
        "gitops_preview_blast_radius": "gitops_merge_request",
        "gitops_native_execution_mode": "external_gitops",
        "gitops_repository_sanitized": True,
        "gitops_merge_request_template": True,
        "gitops_provider": "gitlab",
        "gitops_write_performed": False,
        "gitops_cluster_mutation_performed": False,
        "gitops_gitlab_payload_ready": True,
        "gitops_merge_request_draft": True,
        "gitops_merge_request_removes_source_branch": True,
        "gitops_verification_plan_check_ids": [
            "merge_request_reviewed",
            "ci_pipeline_passed",
            "fleet_bundle_reconciled",
        ],
    }


def _ready_production_action_evidence() -> dict:
    return {
        "success": True,
        "status": "ready",
        "summary": {
            "rollback_action_class_count": 5,
            "native_verification_check_count": 10,
            "action_class_contract_count": 5,
            "blocked_action_class_count": 11,
        },
        "coverage": {
            "rollback_contract_complete": True,
            "native_verification_contract_complete": True,
            "blocked_action_contract_complete": True,
        },
    }
