from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import override_settings

from kubernetes_ops.models import K8sActionRequest, K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.services.release_contract import RELEASE_EVIDENCE_SCHEMA_VERSION
from kubernetes_ops.services.release_evidence import build_kubernetes_release_evidence


READY_PREFLIGHT_RESULT_IDS = (
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
    "production_action_evidence",
    "external_evidence_bundle",
)


def _ready_report(ready_for_sidebar: bool) -> dict:
    return {
        "success": True,
        "status": "ready" if ready_for_sidebar else "configured",
        "ready_for_sidebar": ready_for_sidebar,
        "summary": {"ready": 12, "missing": 0, "manual": 0, "total": 12},
        "checks": [{"id": "architecture_guard", "status": "ready", "detail": "ok", "required": True}],
        "worker_state": {"status": "running", "is_stale": False},
        "access_model": {"status": "ready", "native_mutations_enabled": False, "exec_enabled": False},
        "identity_runtime": {"status": "ready", "identity_provider": "Keycloak/OIDC", "enforced": True, "webterm_login_gateway": {"status": "ready"}},
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
        "production_restart_template_status": "ready",
        "production_restart_template_approval_required": True,
        "production_restart_template_verification_required": True,
        "production_restart_template_report_required": True,
        "production_restart_template_safe": True,
        "rollback_scale_previous_replicas": 2,
        "rollback_apply_requires_dry_run": True,
        "rollback_delete_requires_restore_source": True,
        "rollback_plan_payload_safe": True,
        "native_verification_plan_status": "pending",
        "native_verification_plan_check_ids": ["rollout_status_observed", "pod_readiness_observed", "recent_warning_events_checked"],
        "apply_verification_plan_check_ids": ["apply_action_completed", "resource_generation_observed", "recent_warning_events_checked"],
        "native_verification_auto_status": "verified",
        "native_verification_auto_request_status": K8sActionRequest.STATUS_VERIFIED_NATIVE,
        "native_verification_auto_recorded": True,
        "native_verification_auto_check_statuses": ["passed", "passed", "passed"],
        "restricted_write_gate_required": True,
        "restricted_write_gate_blocks_without_ref": True,
        "restricted_write_gate_allows_with_ref": True,
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
        "gitops_verification_plan_check_ids": ["merge_request_reviewed", "ci_pipeline_passed", "fleet_bundle_reconciled"],
    }


@pytest.fixture(autouse=True)
def _ready_studio_diagnosis_draft(monkeypatch):
    monkeypatch.setattr("kubernetes_ops.services.release_evidence._studio_diagnosis_draft_evidence", lambda _user, _enabled: {"success": True, "status": "ready"})


@pytest.mark.django_db
def test_kubernetes_release_evidence_blocks_when_admin_mode_safety_fails(monkeypatch):
    user = User.objects.create_user(username="release-admin-mode-safety-fail", password="x", is_staff=True)
    monkeypatch.setattr("kubernetes_ops.services.release_evidence.build_kubernetes_readiness_report", lambda user, **_kwargs: _ready_report(False))
    monkeypatch.setattr("kubernetes_ops.services.release_evidence._provider_probe_evidence", lambda _enabled: [{"success": True, "status": "ready", "provider_name": "rancher-main"}])
    monkeypatch.setattr("kubernetes_ops.services.release_evidence._sync_dry_run_evidence", lambda _enabled: [{"success": True, "status": "ready", "provider_name": "rancher-main", "dry_run": True}])
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._studio_mcp_evidence",
        lambda _user, _enabled: {
            "success": True,
            "status": "ready",
            "policy": {"permission_mode": "READ_ONLY", "mutates_state": False},
            "policy_errors": [],
        },
    )
    monkeypatch.setattr("kubernetes_ops.services.release_evidence._action_controls_evidence", lambda _user, _enabled: _ready_action_controls())
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._admin_mode_safety_evidence",
        lambda _user, _enabled: {"success": False, "status": "failed", "provider_called": True, "admin_actions_created": 1},
    )
    monkeypatch.setattr("kubernetes_ops.services.release_evidence._readonly_rbac_live_evidence", lambda _enabled: {"success": True, "status": "ready"})
    monkeypatch.setattr("kubernetes_ops.services.release_evidence.load_kubernetes_release_preflight_artifact", lambda: _ready_preflight())
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.build_kubernetes_release_scope_report",
        lambda **_kwargs: {"success": True, "status": "ready", "approval_ref_present": True},
    )

    with override_settings(KUBERNETES_OPS_RELEASE_ENVIRONMENT="production", KUBERNETES_OPS_PRODUCTION_APPROVAL_REF="CHG-K8S-1"):
        evidence = build_kubernetes_release_evidence(user=user)

    assert evidence["production_ready"] is False
    assert "admin_mode_safety:failed" in evidence["blockers"]
    assert evidence["release_summary"]["status"] == "blocked"


@pytest.mark.django_db
def test_kubernetes_release_evidence_admin_mode_safety_is_rolled_back(monkeypatch):
    user = User.objects.create_user(username="release-admin-mode-safety-proof", password="x", is_staff=True)
    monkeypatch.setattr("kubernetes_ops.services.release_evidence.build_kubernetes_readiness_report", lambda user, **_kwargs: _ready_report(False))
    session_count = K8sAdminSession.objects.count()
    action_count = K8sAdminAction.objects.count()
    provider_count = K8sProvider.objects.count()
    cluster_count = K8sCluster.objects.count()

    evidence = build_kubernetes_release_evidence(
        user=user,
        run_provider_probe=False,
        run_sync_dry_run=False,
        run_mcp_call=False,
        run_action_controls=False,
        run_readonly_rbac_live=False,
    )

    assert evidence["admin_mode_safety"]["success"] is True
    assert evidence["admin_mode_safety"]["persistent_rows"] is False
    assert evidence["admin_mode_safety"]["admin_actions_created"] == 0
    assert K8sAdminSession.objects.count() == session_count
    assert K8sAdminAction.objects.count() == action_count
    assert K8sProvider.objects.count() == provider_count
    assert K8sCluster.objects.count() == cluster_count


@pytest.mark.django_db
def test_kubernetes_release_evidence_action_controls_require_staff(monkeypatch):
    user = User.objects.create_user(username="release-action-reader", password="x", is_staff=False)
    monkeypatch.setattr("kubernetes_ops.services.release_evidence.build_kubernetes_readiness_report", lambda user, **_kwargs: _ready_report(True))

    evidence = build_kubernetes_release_evidence(user=user, run_provider_probe=False, run_sync_dry_run=False, run_mcp_call=False)

    assert evidence["action_controls"]["status"] == "missing"
    assert "action_controls:missing" in evidence["blockers"]
