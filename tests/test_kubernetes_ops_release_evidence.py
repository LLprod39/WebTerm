from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.test import override_settings

from kubernetes_ops.models import K8sActionRequest, K8sAppRef, K8sCluster, K8sProvider
from kubernetes_ops.services.provider_probe import KubernetesProviderProbeResult
from kubernetes_ops.services.release_contract import RELEASE_EVIDENCE_SCHEMA_VERSION
from kubernetes_ops.services.release_evidence import build_kubernetes_release_evidence
from kubernetes_ops.services.sync import KubernetesSyncResult
from tests.kubernetes_ops_release_evidence_helpers import (
    PRODUCTION_RELEASE_SETTINGS,
    _grant,
    _ready_interactive_transport,
    _ready_preflight,
    _ready_production_action_evidence,
    _ready_rbac_live,
    _ready_report,
)


@pytest.fixture(autouse=True)
def _ready_studio_diagnosis_draft(monkeypatch):
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._studio_diagnosis_draft_evidence",
        lambda _user, _enabled: {"success": True, "status": "ready"},
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._production_action_evidence",
        lambda _enabled: _ready_production_action_evidence(),
    )


@pytest.mark.django_db
def test_kubernetes_release_evidence_green_before_sidebar_flag_when_all_runtime_proofs_pass(monkeypatch):
    user = User.objects.create_user(username="release-admin", password="x", is_staff=True)
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

    async def fake_call_mcp_tool(_mcp, tool_name, arguments):
        assert tool_name == "kubernetes_describe_workload"
        assert arguments["namespace"] == "payments"
        return {
            "content": [{"type": "text", "text": "MUTATES_STATE: false"}],
            "structuredContent": {"policy": {"permission_mode": "READ_ONLY", "mutates_state": False}},
        }

    monkeypatch.setattr("kubernetes_ops.services.release_evidence.call_mcp_tool", fake_call_mcp_tool)
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._readonly_rbac_live_evidence", lambda _enabled: _ready_rbac_live()
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.load_kubernetes_release_preflight_artifact",
        lambda: _ready_preflight(),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.load_kubernetes_interactive_transport_evidence_artifact",
        _ready_interactive_transport,
    )

    with override_settings(**PRODUCTION_RELEASE_SETTINGS):
        evidence = build_kubernetes_release_evidence(user=user)

    assert evidence["production_ready"] is True
    assert evidence["ready_for_sidebar"] is False
    assert evidence["enablement"]["env_flag_required"] is True
    assert evidence["schema_version"] == RELEASE_EVIDENCE_SCHEMA_VERSION
    assert evidence["blockers"] == []
    command_ids = {item["id"] for item in evidence["release_contract"]["required_preflight_commands"]}
    assert {
        "django_check",
        "architecture_guard",
        "migrations_dry_run",
        "kubernetes_backend_tests",
        "release_evidence",
    } <= command_ids
    assert evidence["release_scope"]["status"] == "ready"
    assert evidence["release_scope"]["approval_ref_present"] is True
    assert evidence["provider_probes"][0]["status"] == "ready"
    assert evidence["sync_dry_run"][0]["dry_run"] is True
    assert evidence["studio_mcp"]["policy"]["mutates_state"] is False
    assert evidence["studio_mcp"]["policy_errors"] == []
    assert evidence["readiness"]["access_model"]["status"] == "ready"
    assert evidence["readiness"]["access_model"]["native_mutations_enabled"] is False
    assert evidence["readiness"]["identity_runtime"]["status"] == "ready"
    assert evidence["readiness"]["identity_runtime"]["identity_provider"] == "Keycloak/OIDC"
    assert evidence["readiness"]["production_gate"]["core_evidence_ready"] is True
    assert evidence["readonly_rbac_live"]["status"] == "ready"
    assert evidence["readonly_rbac_live"]["allowed_count"] == 7
    assert evidence["readonly_rbac_live"]["denied_count"] == 7
    assert evidence["preflight"]["status"] == "ready"
    assert (
        evidence["action_controls"]["status"],
        evidence["action_controls"]["mode"],
        evidence["action_controls"]["approval_status"],
    ) == ("ready", "transaction_rollback", K8sActionRequest.STATUS_APPROVED_EXTERNAL)
    assert evidence["action_controls"]["approval_principals_distinct"] is True
    assert (
        evidence["action_controls"]["approval_recorded"],
        evidence["action_controls"]["native_execution_enabled"],
    ) == (True, False)
    assert (
        evidence["action_controls"]["scale_request_status"],
        evidence["action_controls"]["scale_preview_blast_radius"],
        evidence["action_controls"]["scale_preview_replicas"],
        evidence["action_controls"]["scale_target_redacted"],
    ) == (K8sActionRequest.STATUS_PENDING_APPROVAL, "single_workload", 2, True)
    assert (
        evidence["action_controls"]["external_verification_status"],
        evidence["action_controls"]["external_verification_redacted"],
        evidence["action_controls"]["terminal_execute_rejected"],
        evidence["action_controls"]["blocked_execution_status"],
        evidence["action_controls"]["terminal_verify_rejected"],
    ) == (K8sActionRequest.STATUS_VERIFIED_EXTERNAL, True, True, K8sActionRequest.STATUS_EXECUTION_BLOCKED, True)
    assert (
        evidence["action_controls"]["rollback_plan_status"],
        evidence["action_controls"]["rollback_scale_previous_replicas"],
        evidence["action_controls"]["rollback_apply_requires_dry_run"],
        evidence["action_controls"]["rollback_delete_requires_restore_source"],
        evidence["action_controls"]["rollback_plan_payload_safe"],
    ) == ("required", 2, True, True, True)
    assert (
        evidence["action_controls"]["production_restart_template_status"],
        evidence["action_controls"]["production_restart_template_approval_required"],
        evidence["action_controls"]["production_restart_template_verification_required"],
        evidence["action_controls"]["production_restart_template_report_required"],
        evidence["action_controls"]["production_restart_template_safe"],
    ) == ("ready", True, True, True, True)
    assert (
        evidence["action_controls"]["native_verification_plan_status"],
        "rollout_status_observed" in evidence["action_controls"]["native_verification_plan_check_ids"],
        "apply_action_completed" in evidence["action_controls"]["apply_verification_plan_check_ids"],
        evidence["action_controls"]["native_verification_plan_payload_safe"],
        evidence["action_controls"]["native_verification_auto_status"],
        evidence["action_controls"]["native_verification_auto_request_status"],
        evidence["action_controls"]["native_verification_auto_recorded"],
        set(evidence["action_controls"]["native_verification_auto_check_statuses"]),
    ) == ("pending", True, True, True, "verified", K8sActionRequest.STATUS_VERIFIED_NATIVE, True, {"passed"})
    assert (
        evidence["action_controls"]["restricted_write_gate_required"],
        evidence["action_controls"]["restricted_write_gate_blocks_without_ref"],
        evidence["action_controls"]["restricted_write_gate_allows_with_ref"],
        evidence["action_controls"]["restricted_write_gate_setting"],
    ) == (True, True, True, "KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF")
    assert evidence["action_controls"]["gitops_request_status"] == K8sActionRequest.STATUS_PENDING_APPROVAL
    assert evidence["action_controls"]["gitops_preview_blast_radius"] == "gitops_merge_request"
    assert evidence["action_controls"]["gitops_native_execution_mode"] == "external_gitops"
    assert evidence["action_controls"]["gitops_repository_sanitized"] is True
    assert evidence["action_controls"]["gitops_merge_request_template"] is True
    assert evidence["action_controls"]["fleet_pause_target_redacted"] is True
    assert evidence["action_controls"]["devtron_rollback_execution_mode"] == "external_devtron"
    assert evidence["action_controls"]["devtron_rollback_links_sanitized"] is True
    assert evidence["admin_mode_safety"]["status"] == "ready"
    assert evidence["admin_mode_safety"]["checked_count"] == 10
    assert evidence["admin_mode_safety"]["provider_called"] is False
    assert evidence["admin_mode_safety"]["admin_actions_created"] == 0
    assert evidence["interactive_shell_streams"]["status"] == "ready"
    assert evidence["normal_user_surface"]["status"] == "ready"
    assert (
        evidence["normal_user_surface"]["reader"]["can_audit_deeplinks"],
        evidence["normal_user_surface"]["staff"]["can_audit_deeplinks"],
    ) == (False, True)
    secret_controls = evidence["secret_read_controls"]
    assert secret_controls["status"] == "ready"
    assert all(
        secret_controls[key] is True
        for key in (
            "default_redacted",
            "secret_list_metadata_only",
            "secret_list_raw_secret_absent",
            "secret_list_action_summary_flags_boolean",
            "secret_read_rejected_without_grant",
            "secret_read_rejected_without_runtime_flag",
            "provider_not_called_for_denied_reveal",
            "secret_read_allowed_with_all_gates",
        )
    )
    lifecycle = evidence["provider_secret_lifecycle"]
    assert lifecycle["status"] == "ready"
    assert lifecycle["storage_mode"] == "managed"
    assert lifecycle["rotation_supported"] is True
    assert lifecycle["persistent_rows"] is False
    assert all(lifecycle["checks"].values())
    audit_redaction = evidence["audit_redaction"]
    assert audit_redaction["status"] == "ready"
    assert audit_redaction["serializers_checked"] == ["serialize_audit_event", "serialize_cluster_event"]
    assert all(audit_redaction["checks"].values())
    assert evidence["artifact_safety"]["status"] == "ready"
    assert evidence["definition_of_done"]["status"] == "ready"
    assert evidence["definition_of_done"]["ready"] == evidence["definition_of_done"]["total"] == 13
    production_action_evidence = evidence["production_action_evidence"]
    assert production_action_evidence["status"] == "ready"
    assert production_action_evidence["summary"]["blocked_action_class_count"] == 11
    assert production_action_evidence["coverage"]["blocked_action_contract_complete"] is True
    assert (evidence["release_summary"]["status"], evidence["release_summary"]["blocker_count"]) == ("ready", 0)
    assert evidence["release_summary"]["definition_of_done_status"] == "ready"
    assert evidence["release_summary"]["provider_lifecycle_status"] == "ready"
    assert evidence["release_summary"]["audit_redaction_status"] == "ready"
    assert evidence["release_summary"]["production_action_evidence_status"] == "ready"
    assert evidence["release_summary"]["production_action_blocked_action_class_count"] == 11
    audit = evidence["release_summary"]["completion_audit"]
    assert evidence["completion_audit"] == audit
    assert (audit["core_backend_complete"], audit["production_evidence_complete"], audit["remaining"]) == (
        True,
        True,
        ["sidebar_enablement"],
    )
    assert {item["id"] for item in audit["core_backend_proofs"]} >= {
        "provider_secret_lifecycle",
        "audit_redaction",
        "production_action_evidence",
    }
    assert evidence["release_summary"]["next_steps"] == [
        "Set KUBERNETES_OPS_READY_FOR_SIDEBAR=true only in the approved production environment."
    ]


@pytest.mark.django_db
def test_kubernetes_release_evidence_blocks_mutating_studio_mcp_policy(monkeypatch):
    user = User.objects.create_user(username="release-admin-mutating-mcp", password="x", is_staff=True)
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

    async def fake_call_mcp_tool(_mcp, tool_name, arguments):
        return {
            "content": [{"type": "text", "text": "mutation-capable result"}],
            "structuredContent": {
                "policy": {"permission_mode": "ASSISTED", "mutates_state": True, "requires_approval": True}
            },
        }

    monkeypatch.setattr("kubernetes_ops.services.release_evidence.call_mcp_tool", fake_call_mcp_tool)
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._readonly_rbac_live_evidence", lambda _enabled: _ready_rbac_live()
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.load_kubernetes_release_preflight_artifact",
        lambda: _ready_preflight(),
    )

    with override_settings(**PRODUCTION_RELEASE_SETTINGS):
        evidence = build_kubernetes_release_evidence(user=user)

    assert evidence["production_ready"] is False
    assert evidence["studio_mcp"]["status"] == "policy_violation"
    assert "permission_mode is ASSISTED" in evidence["studio_mcp"]["policy_errors"]
    assert "mutates_state is not false" in evidence["studio_mcp"]["policy_errors"]
    assert "requires_approval is true" in evidence["studio_mcp"]["policy_errors"]
    assert "studio_mcp:policy_violation" in evidence["blockers"]
