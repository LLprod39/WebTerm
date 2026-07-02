from __future__ import annotations
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.test import override_settings

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sActionRequest, K8sAppRef, K8sCluster, K8sProvider
from kubernetes_ops.services.provider_probe import KubernetesProviderProbeResult
from kubernetes_ops.services.release_contract import RELEASE_EVIDENCE_SCHEMA_VERSION
from kubernetes_ops.services.release_evidence import build_kubernetes_release_evidence
from kubernetes_ops.services.sync import KubernetesSyncResult


PRODUCTION_RELEASE_SETTINGS = {"KUBERNETES_OPS_RELEASE_ENVIRONMENT": "production", "KUBERNETES_OPS_PRODUCTION_APPROVAL_REF": "CHG-K8S-1", "KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF": "artifact:production-bundle", "KUBERNETES_OPS_IDENTITY_RUNTIME_EVIDENCE_REF": "artifact:sso-proof", "KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF": "artifact:provider-proof", "KUBERNETES_OPS_READONLY_RBAC_EVIDENCE_REF": "artifact:rbac-proof", "KUBERNETES_OPS_KUBERNETES_MCP_EVIDENCE_REF": "artifact:mcp-proof", "KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF": "artifact:rollback-proof", "KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF": "artifact:native-verification-proof"}
READY_PREFLIGHT_RESULT_IDS = "django_check architecture_guard migrations_dry_run kubernetes_backend_tests readonly_rbac_validate sync_prune_safety readonly_rbac_live local_platform_evidence live_provider_smoke interactive_transport_evidence interactive_live_smoke interactive_production_controls production_action_evidence external_evidence_bundle".split()


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
        "identity_runtime": {"status": "ready", "identity_provider": "Keycloak/OIDC", "enforced": True, "webterm_login_gateway": {"status": "ready"}},
        "production_gate": {"target_environment": "production", "core_evidence_ready": True, "missing_reference_count": 0},
    }


def _ready_rbac_live(context: str = "prod-kz") -> dict:
    return {"success": True, "status": "ready", "context": context, "applied": True, "service_account": "system:serviceaccount:webterm-system:webterm-kubernetes-readonly", "allowed_count": 7, "denied_count": 7, "errors": []}


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
        "rollback_plan_status": "required", "rollback_scale_previous_replicas": 2, "rollback_apply_requires_dry_run": True, "rollback_delete_requires_restore_source": True, "rollback_plan_payload_safe": True,
        "production_restart_template_status": "ready", "production_restart_template_approval_required": True, "production_restart_template_verification_required": True, "production_restart_template_report_required": True, "production_restart_template_safe": True,
        "native_verification_plan_status": "pending",
        "native_verification_plan_check_ids": ["rollout_status_observed", "pod_readiness_observed", "recent_warning_events_checked"],
        "apply_verification_plan_check_ids": ["apply_action_completed", "resource_generation_observed", "recent_warning_events_checked"],
        "native_verification_auto_status": "verified", "native_verification_auto_request_status": K8sActionRequest.STATUS_VERIFIED_NATIVE, "native_verification_auto_recorded": True, "native_verification_auto_check_statuses": ["passed", "passed", "passed"],
        "restricted_write_gate_required": True, "restricted_write_gate_blocks_without_ref": True, "restricted_write_gate_allows_with_ref": True, "restricted_write_gate_setting": "KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF", "restricted_write_gate_target_environment": "production",
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


@pytest.fixture(autouse=True)
def _ready_studio_diagnosis_draft(monkeypatch):
    monkeypatch.setattr("kubernetes_ops.services.release_evidence._studio_diagnosis_draft_evidence", lambda _user, _enabled: {"success": True, "status": "ready"})
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

    monkeypatch.setattr("kubernetes_ops.services.release_evidence.build_kubernetes_readiness_report", lambda user, **_kwargs: _ready_report(False))
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
    monkeypatch.setattr("kubernetes_ops.services.release_evidence._readonly_rbac_live_evidence", lambda _enabled: _ready_rbac_live())
    monkeypatch.setattr("kubernetes_ops.services.release_evidence.load_kubernetes_release_preflight_artifact", lambda: _ready_preflight())

    with override_settings(**PRODUCTION_RELEASE_SETTINGS):
        evidence = build_kubernetes_release_evidence(user=user)

    assert evidence["production_ready"] is True
    assert evidence["ready_for_sidebar"] is False
    assert evidence["enablement"]["env_flag_required"] is True
    assert evidence["schema_version"] == RELEASE_EVIDENCE_SCHEMA_VERSION
    assert evidence["blockers"] == []
    command_ids = {item["id"] for item in evidence["release_contract"]["required_preflight_commands"]}
    assert {"django_check", "architecture_guard", "migrations_dry_run", "kubernetes_backend_tests", "release_evidence"} <= command_ids
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
    assert (evidence["action_controls"]["status"], evidence["action_controls"]["mode"], evidence["action_controls"]["approval_status"]) == ("ready", "transaction_rollback", K8sActionRequest.STATUS_APPROVED_EXTERNAL)
    assert (evidence["action_controls"]["approval_recorded"], evidence["action_controls"]["native_execution_enabled"]) == (True, False)
    assert (evidence["action_controls"]["scale_request_status"], evidence["action_controls"]["scale_preview_blast_radius"], evidence["action_controls"]["scale_preview_replicas"], evidence["action_controls"]["scale_target_redacted"]) == (K8sActionRequest.STATUS_PENDING_APPROVAL, "single_workload", 2, True)
    assert (evidence["action_controls"]["external_verification_status"], evidence["action_controls"]["external_verification_redacted"], evidence["action_controls"]["terminal_execute_rejected"], evidence["action_controls"]["blocked_execution_status"], evidence["action_controls"]["terminal_verify_rejected"]) == (K8sActionRequest.STATUS_VERIFIED_EXTERNAL, True, True, K8sActionRequest.STATUS_EXECUTION_BLOCKED, True)
    assert (evidence["action_controls"]["rollback_plan_status"], evidence["action_controls"]["rollback_scale_previous_replicas"], evidence["action_controls"]["rollback_apply_requires_dry_run"], evidence["action_controls"]["rollback_delete_requires_restore_source"], evidence["action_controls"]["rollback_plan_payload_safe"]) == ("required", 2, True, True, True)
    assert (evidence["action_controls"]["production_restart_template_status"], evidence["action_controls"]["production_restart_template_approval_required"], evidence["action_controls"]["production_restart_template_verification_required"], evidence["action_controls"]["production_restart_template_report_required"], evidence["action_controls"]["production_restart_template_safe"]) == ("ready", True, True, True, True)
    assert (evidence["action_controls"]["native_verification_plan_status"], "rollout_status_observed" in evidence["action_controls"]["native_verification_plan_check_ids"], "apply_action_completed" in evidence["action_controls"]["apply_verification_plan_check_ids"], evidence["action_controls"]["native_verification_plan_payload_safe"], evidence["action_controls"]["native_verification_auto_status"], evidence["action_controls"]["native_verification_auto_request_status"], evidence["action_controls"]["native_verification_auto_recorded"], set(evidence["action_controls"]["native_verification_auto_check_statuses"])) == ("pending", True, True, True, "verified", K8sActionRequest.STATUS_VERIFIED_NATIVE, True, {"passed"})
    assert (evidence["action_controls"]["restricted_write_gate_required"], evidence["action_controls"]["restricted_write_gate_blocks_without_ref"], evidence["action_controls"]["restricted_write_gate_allows_with_ref"], evidence["action_controls"]["restricted_write_gate_setting"]) == (True, True, True, "KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF")
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
    assert (evidence["normal_user_surface"]["reader"]["can_audit_deeplinks"], evidence["normal_user_surface"]["staff"]["can_audit_deeplinks"]) == (False, True)
    secret_controls = evidence["secret_read_controls"]
    assert secret_controls["status"] == "ready"
    assert all(secret_controls[key] is True for key in ("default_redacted", "secret_list_metadata_only", "secret_list_raw_secret_absent", "secret_list_action_summary_flags_boolean", "secret_read_rejected_without_grant", "secret_read_rejected_without_runtime_flag", "provider_not_called_for_denied_reveal", "secret_read_allowed_with_all_gates"))
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
    assert (audit["core_backend_complete"], audit["production_evidence_complete"], audit["remaining"]) == (True, True, ["sidebar_enablement"])
    assert {item["id"] for item in audit["core_backend_proofs"]} >= {"provider_secret_lifecycle", "audit_redaction", "production_action_evidence"}
    assert evidence["release_summary"]["next_steps"] == ["Set KUBERNETES_OPS_READY_FOR_SIDEBAR=true only in the approved production environment."]


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

    monkeypatch.setattr("kubernetes_ops.services.release_evidence.build_kubernetes_readiness_report", lambda user, **_kwargs: _ready_report(False))
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
            "structuredContent": {"policy": {"permission_mode": "ASSISTED", "mutates_state": True, "requires_approval": True}},
        }

    monkeypatch.setattr("kubernetes_ops.services.release_evidence.call_mcp_tool", fake_call_mcp_tool)
    monkeypatch.setattr("kubernetes_ops.services.release_evidence._readonly_rbac_live_evidence", lambda _enabled: _ready_rbac_live())
    monkeypatch.setattr("kubernetes_ops.services.release_evidence.load_kubernetes_release_preflight_artifact", lambda: _ready_preflight())

    with override_settings(**PRODUCTION_RELEASE_SETTINGS):
        evidence = build_kubernetes_release_evidence(user=user)

    assert evidence["production_ready"] is False
    assert evidence["studio_mcp"]["status"] == "policy_violation"
    assert "permission_mode is ASSISTED" in evidence["studio_mcp"]["policy_errors"]
    assert "mutates_state is not false" in evidence["studio_mcp"]["policy_errors"]
    assert "requires_approval is true" in evidence["studio_mcp"]["policy_errors"]
    assert "studio_mcp:policy_violation" in evidence["blockers"]


@pytest.mark.django_db
def test_kubernetes_release_evidence_redacts_studio_mcp_content_preview(monkeypatch):
    user = User.objects.create_user(username="release-admin-redacted-mcp", password="x", is_staff=True)
    _grant(user, "kubernetes", "studio_pipelines", "studio_mcp")
    provider = K8sProvider.objects.create(
        name="rancher-main",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://rancher.prod.example.com",
        auth_mode=K8sProvider.AUTH_NONE,
    )
    cluster = K8sCluster.objects.create(name="prod-kz-1", labels={"kube_context": "prod-kz"})
    K8sAppRef.objects.create(name="payments-api", cluster=cluster, namespace="payments", owner=K8sAppRef.OWNER_DEVTRON)

    monkeypatch.setattr("kubernetes_ops.services.release_evidence.build_kubernetes_readiness_report", lambda user, **_kwargs: _ready_report(False))
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
            "content": [{"type": "text", "text": "status ok\npassword=super-secret\nAuthorization: Bearer abc.def"}],
            "structuredContent": {"policy": {"permission_mode": "READ_ONLY", "mutates_state": False}},
        }

    monkeypatch.setattr("kubernetes_ops.services.release_evidence.call_mcp_tool", fake_call_mcp_tool)
    monkeypatch.setattr("kubernetes_ops.services.release_evidence._readonly_rbac_live_evidence", lambda _enabled: _ready_rbac_live())
    monkeypatch.setattr("kubernetes_ops.services.release_evidence.load_kubernetes_release_preflight_artifact", lambda: _ready_preflight())

    with override_settings(**PRODUCTION_RELEASE_SETTINGS):
        evidence = build_kubernetes_release_evidence(user=user)

    assert evidence["production_ready"] is True
    assert evidence["studio_mcp"]["status"] == "ready"
    preview = evidence["studio_mcp"]["content_preview"]
    assert "super-secret" not in preview
    assert "abc.def" not in preview
    assert "[REDACTED:" in preview


@pytest.mark.django_db
def test_kubernetes_release_evidence_redacts_provider_and_sync_payloads(monkeypatch):
    user = User.objects.create_user(username="release-admin-redacted-provider", password="x", is_staff=True)
    provider = K8sProvider.objects.create(
        name="rancher-main",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://svc-user:provider-secret@rancher.prod.example.com:8443/dashboard?token=raw-url-token",
        auth_mode=K8sProvider.AUTH_NONE,
    )
    monkeypatch.setattr("kubernetes_ops.services.release_evidence.build_kubernetes_readiness_report", lambda user, **_kwargs: _ready_report(False))
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.probe_kubernetes_provider",
        lambda _provider: KubernetesProviderProbeResult(
            provider_id=provider.id,
            provider_name=provider.name,
            provider_kind=provider.kind,
            success=False,
            status="error",
            path="https://probe-user:probe-secret@rancher.prod.example.com/v3/clusters?token=probe-url-token",
            error="password=provider-password\nAuthorization: Bearer provider.jwt",
        ),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.sync_kubernetes_providers",
        lambda dry_run: [
            KubernetesSyncResult(
                provider_id=provider.id,
                provider_name=provider.name,
                provider_kind=provider.kind,
                success=False,
                dry_run=dry_run,
                error="token=sync-secret\nAuthorization: Bearer sync.jwt",
            )
        ],
    )
    monkeypatch.setattr("kubernetes_ops.services.release_evidence.load_kubernetes_release_preflight_artifact", lambda: _ready_preflight())

    evidence = build_kubernetes_release_evidence(
        user=user,
        run_mcp_call=False,
        run_action_controls=False,
        run_readonly_rbac_live=False,
    )

    provider_payload = evidence["provider_probes"][0]
    sync_payload = evidence["sync_dry_run"][0]
    assert provider_payload["provider_base_url"] == "https://rancher.prod.example.com:8443"
    assert provider_payload["path"] == "https://rancher.prod.example.com/v3/clusters"
    serialized = str(evidence)
    for secret in ("provider-secret", "raw-url-token", "probe-secret", "probe-url-token", "provider-password", "provider.jwt", "sync-secret", "sync.jwt"):
        assert secret not in serialized
    assert "[REDACTED:" in provider_payload["error"]
    assert "[REDACTED:" in sync_payload["error"]
    assert evidence["artifact_safety"]["status"] == "ready"


@pytest.mark.django_db
def test_kubernetes_release_evidence_self_scan_blocks_raw_artifact_leak(monkeypatch):
    user = User.objects.create_user(username="release-admin-artifact-leak", password="x", is_staff=True)
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.build_kubernetes_readiness_report",
        lambda user, **_kwargs: _ready_report(False),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._provider_probe_evidence",
        lambda _enabled: [
            {"success": True, "status": "ready", "provider_name": "leaky-provider", "token": "raw-provider-token"}
        ],
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._sync_dry_run_evidence",
        lambda _enabled: [
            {"success": True, "status": "ready", "provider_name": "leaky-provider", "dry_run": True}
        ],
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._studio_mcp_evidence",
        lambda _user, _enabled: {
            "success": True,
            "status": "ready",
            "policy": {"permission_mode": "READ_ONLY", "mutates_state": False},
            "policy_errors": [],
        },
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._action_controls_evidence",
        lambda _user, _enabled: _ready_action_controls(),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._admin_mode_safety_evidence",
        lambda _user, _enabled: {
            "success": True,
            "status": "ready",
            "provider_called": False,
            "admin_actions_created": 0,
        },
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._readonly_rbac_live_evidence",
        lambda _enabled: _ready_rbac_live(),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.load_kubernetes_release_preflight_artifact",
        lambda: _ready_preflight(),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence.build_kubernetes_release_scope_report",
        lambda **_kwargs: {"success": True, "status": "ready", "approval_ref_present": True},
    )

    with override_settings(
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_OPS_PRODUCTION_APPROVAL_REF="CHG-K8S-1",
    ):
        evidence = build_kubernetes_release_evidence(user=user)

    assert evidence["production_ready"] is False
    assert "artifact_safety:unsafe" in evidence["blockers"]
    assert evidence["artifact_safety"]["status"] == "unsafe"
    assert evidence["artifact_safety"]["issue_count"] > 0
    assert "raw-provider-token" not in str(evidence["artifact_safety"]["issues"])
    assert "Remove raw secrets or credentialed URLs from release evidence output." in evidence["release_summary"]["next_steps"]
