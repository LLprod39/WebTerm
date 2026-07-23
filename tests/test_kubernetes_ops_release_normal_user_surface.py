from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.test import override_settings

from core_ui.models import UserAppPermission
from kubernetes_ops.models import (
    K8sActionRequest,
    K8sAppRef,
    K8sCluster,
    K8sFleetBundle,
    K8sNetworkRef,
    K8sPodRef,
    K8sProvider,
    K8sWorkloadRef,
)
from kubernetes_ops.services.provider_probe import KubernetesProviderProbeResult
from kubernetes_ops.services.release_contract import RELEASE_EVIDENCE_SCHEMA_VERSION
from kubernetes_ops.services.release_evidence import build_kubernetes_release_evidence
from kubernetes_ops.services.release_normal_user_surface import build_kubernetes_release_normal_user_surface_evidence
from kubernetes_ops.services.sync import KubernetesSyncResult

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


def _ready_admin_mode_safety() -> dict:
    return {"success": True, "status": "ready", "provider_called": False, "admin_actions_created": 0}


def test_release_normal_user_surface_proof_is_rollback_only_and_ready(db):
    initial_counts = {
        "providers": K8sProvider.objects.count(),
        "clusters": K8sCluster.objects.count(),
        "apps": K8sAppRef.objects.count(),
        "workloads": K8sWorkloadRef.objects.count(),
        "pods": K8sPodRef.objects.count(),
        "network": K8sNetworkRef.objects.count(),
        "bundles": K8sFleetBundle.objects.count(),
    }

    evidence = build_kubernetes_release_normal_user_surface_evidence(True)

    assert evidence["success"] is True
    assert evidence["status"] == "ready"
    assert evidence["mode"] == "transaction_rollback"
    assert evidence["checked_count"] == 41
    assert evidence["reader"]["can_read"] is True
    assert evidence["reader"]["can_audit_deeplinks"] is False
    assert evidence["staff"]["can_audit_deeplinks"] is True
    assert evidence["reader_external_link_policy"]["mode"] == "webterm_native_only"
    assert evidence["staff_external_link_policy"]["mode"] == "staff_admin_fallback"
    assert evidence["frontend_response_credential_scan"] == {
        "status": "ready",
        "surfaces_checked": 31,
        "provider_secret_reference_serialized": False,
        "forbidden_values_found": False,
    }
    check_ids = {item["id"] for item in evidence["checks"]}
    assert "reader_frontend_response_credentials_absent" in check_ids
    assert "reader_helm_releases_external_links_hidden" in check_ids
    assert "reader_devtron_detail_external_links_hidden" in check_ids
    assert "reader_diagnostics_summary_read_only" in check_ids
    assert "reader_diagnostics_summary_has_no_external_hosts_or_tokens" in check_ids
    assert "reader_action_summary_read_only" in check_ids
    assert "reader_action_summary_has_no_external_hosts_or_tokens" in check_ids
    assert "reader_capabilities_read_only" in check_ids
    assert "reader_capabilities_has_no_external_hosts_or_tokens" in check_ids
    assert "staff_frontend_response_credentials_absent" in check_ids
    assert "staff_helm_releases_fallback_links_sanitized" in check_ids
    assert "staff_devtron_detail_fallback_links_sanitized" in check_ids
    assert "staff_diagnostics_summary_read_only" in check_ids
    assert "staff_diagnostics_summary_has_no_external_hosts_or_tokens" in check_ids
    assert "staff_action_summary_read_only" in check_ids
    assert "staff_action_summary_has_no_external_hosts_or_tokens" in check_ids
    assert "staff_capabilities_read_only" in check_ids
    assert "staff_capabilities_has_no_external_hosts_or_tokens" in check_ids
    assert "staff_release_summary_read_only" in check_ids
    assert "staff_release_summary_has_no_external_hosts_or_tokens" in check_ids
    assert "raw-token" not in str(evidence)
    assert "RANCHER_TOKEN" not in str(evidence)
    assert "release-provider-token" not in str(evidence)
    assert "release-kubeconfig-context" not in str(evidence)
    assert "release-rancher.example.test" not in str(evidence["reader"])
    assert K8sProvider.objects.count() == initial_counts["providers"]
    assert K8sCluster.objects.count() == initial_counts["clusters"]
    assert K8sAppRef.objects.count() == initial_counts["apps"]
    assert K8sWorkloadRef.objects.count() == initial_counts["workloads"]
    assert K8sPodRef.objects.count() == initial_counts["pods"]
    assert K8sNetworkRef.objects.count() == initial_counts["network"]
    assert K8sFleetBundle.objects.count() == initial_counts["bundles"]


def test_release_normal_user_surface_proof_can_be_skipped():
    evidence = build_kubernetes_release_normal_user_surface_evidence(False)

    assert evidence["success"] is False
    assert evidence["status"] == "skipped"


@pytest.mark.django_db
def test_kubernetes_release_evidence_blocks_broken_normal_user_surface(monkeypatch):
    user = User.objects.create_user(username="release-admin-normal-user-surface", password="x", is_staff=True)
    _grant(user, "kubernetes", "studio_pipelines", "studio_mcp")
    provider = K8sProvider.objects.create(
        name="rancher-main",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://rancher.prod.example.com",
        auth_mode=K8sProvider.AUTH_NONE,
    )
    cluster = K8sCluster.objects.create(name="prod-kz-1", labels={"kube_context": "prod-kz"})
    K8sAppRef.objects.create(name="payments-api", cluster=cluster, namespace="payments", owner=K8sAppRef.OWNER_DEVTRON)

    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.build_kubernetes_readiness_report",
        lambda user, **_kwargs: _ready_report(False),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.probe_kubernetes_provider",
        lambda _provider: KubernetesProviderProbeResult(
            provider_id=provider.id,
            provider_name=provider.name,
            provider_kind=provider.kind,
            success=True,
            status="ready",
            path="/v3/clusters",
        ),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.sync_kubernetes_providers",
        lambda dry_run: [
            KubernetesSyncResult(
                provider_id=provider.id,
                provider_name=provider.name,
                provider_kind=provider.kind,
                success=True,
                clusters=1,
                dry_run=dry_run,
            )
        ],
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.owned_kubernetes_mcp_server",
        lambda _user: SimpleNamespace(id=7, name="Kubernetes MCP", last_test_ok=True),
    )

    async def fake_call_mcp_tool(_mcp, _tool_name, _arguments):
        return {
            "content": [{"type": "text", "text": "MUTATES_STATE: false"}],
            "structuredContent": {"policy": {"permission_mode": "READ_ONLY", "mutates_state": False}},
        }

    monkeypatch.setattr("kubernetes_ops.services.release_evidence.call_mcp_tool", fake_call_mcp_tool)
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._action_controls_evidence",
        lambda _user, _enabled: _ready_action_controls(),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._admin_mode_safety_evidence",
        lambda _user, _enabled: _ready_admin_mode_safety(),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._studio_diagnosis_draft_evidence",
        lambda _user, _enabled: {"success": True, "status": "ready"},
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._readonly_rbac_live_evidence",
        lambda _enabled: {"success": True, "status": "ready", "allowed_count": 7, "denied_count": 7},
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.load_kubernetes_release_preflight_artifact",
        lambda: _ready_preflight(),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._normal_user_surface_evidence",
        lambda _enabled: {
            "success": False,
            "status": "failed",
            "checks": [{"id": "reader_external_links_hidden", "success": False}],
        },
    )

    with override_settings(
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production", KUBERNETES_OPS_PRODUCTION_APPROVAL_REF="CHG-K8S-1"
    ):
        evidence = build_kubernetes_release_evidence(user=user)

    assert evidence["production_ready"] is False
    assert evidence["normal_user_surface"]["status"] == "failed"
    assert "normal_user_surface:failed" in evidence["blockers"]
    assert (
        "Fix WebTerm-only normal-user API proof: hide external links/provider config and keep fallback deeplink audit staff-only."
        in evidence["release_summary"]["next_steps"]
    )
