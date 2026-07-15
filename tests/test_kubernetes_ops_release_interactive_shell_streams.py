from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from kubernetes_ops.models import (
    K8sActionRequest,
    K8sAdminAction,
    K8sAdminRecording,
    K8sAdminRecordingEvent,
    K8sProvider,
)
from kubernetes_ops.services.release_blockers import build_kubernetes_release_blockers
from kubernetes_ops.services.release_interactive_shell_streams import (
    build_kubernetes_release_interactive_shell_stream_evidence,
)


@pytest.mark.django_db
def test_release_interactive_shell_stream_evidence_is_transaction_rollback_and_redacted():
    user = User.objects.create_user(username="release-shell-proof", password="x", is_staff=True)
    initial = {
        "providers": K8sProvider.objects.count(),
        "actions": K8sAdminAction.objects.count(),
        "recordings": K8sAdminRecording.objects.count(),
        "events": K8sAdminRecordingEvent.objects.count(),
    }

    proof = build_kubernetes_release_interactive_shell_stream_evidence(user, True)

    assert proof["status"] == "ready"
    assert proof["mode"] == "transaction_rollback"
    assert proof["actions_created"] == 2
    assert proof["recordings_created"] == 2
    assert proof["recording_events_created"] >= 4
    assert proof["provider_requests_safe"] is True
    assert proof["production_live_provider_evidence"] is False
    assert {item["id"] for item in proof["checks"]} == {
        "cluster_terminal_stream",
        "node_debug_stream",
        "provider_interactive_shell_stream_opener",
    }
    assert "release-terminal-secret" not in str(proof)
    assert "release-node-secret" not in str(proof)
    assert "provider-secret" not in str(proof)
    assert K8sProvider.objects.count() == initial["providers"]
    assert K8sAdminAction.objects.count() == initial["actions"]
    assert K8sAdminRecording.objects.count() == initial["recordings"]
    assert K8sAdminRecordingEvent.objects.count() == initial["events"]


def test_release_blockers_include_failed_interactive_shell_stream_proof():
    blockers = build_kubernetes_release_blockers(
        readiness={"checks": []},
        provider_probes=[],
        sync_dry_run=[],
        studio_mcp={"success": True},
        studio_diagnosis_draft={"success": True},
        action_controls={
            "success": True,
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
        },
        admin_mode_safety={"success": True, "provider_called": False, "admin_actions_created": 0},
        post_review_retention={"success": True, "status": "ready"},
        external_evidence_bundle={"success": True, "status": "ready"},
        interactive_transport_evidence={"success": True, "status": "ready"},
        interactive_live_smoke={"success": True, "status": "ready"},
        interactive_shell_streams={"success": False, "status": "failed", "provider_requests_safe": False},
        normal_user_surface={"success": True},
        secret_read_controls={
            "success": True,
            "status": "ready",
            "default_redacted": True,
            "raw_secret_absent_from_default_response": True,
            "raw_secret_absent_from_action_summary": True,
            "secret_read_rejected_without_grant": True,
            "secret_read_rejected_without_runtime_flag": True,
            "provider_not_called_for_denied_reveal": True,
            "secret_read_capability_disabled_by_default": True,
            "secret_list_metadata_only": True,
            "secret_list_raw_secret_absent": True,
            "secret_list_action_summary_raw_secret_absent": True,
            "secret_list_action_summary_flags_boolean": True,
            "secret_read_allowed_with_all_gates": True,
            "allowed_action_summary_raw_secret_absent": True,
            "actions_created": 3,
        },
        provider_secret_lifecycle={"success": True, "status": "ready"},
        audit_redaction={"success": True, "status": "ready"},
        production_action_evidence={"success": True, "status": "ready"},
        readonly_rbac_live={"success": True},
        preflight={"success": True},
        release_scope={"success": True},
        definition_of_done={"success": True, "status": "ready"},
    )

    assert blockers == ["interactive_shell_streams:failed"]
