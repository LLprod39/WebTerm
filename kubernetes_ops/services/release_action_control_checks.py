from __future__ import annotations

from typing import Any

from kubernetes_ops.models import K8sActionRequest


def action_controls_blocker(action_controls: dict[str, Any]) -> str:
    if not action_controls.get("success"):
        return f"action_controls:{action_controls.get('status') or 'failed'}"
    checks = [
        (not action_controls.get("native_execution_enabled"), "action_controls:native_execution_enabled"),
        (
            action_controls.get("approval_status") == K8sActionRequest.STATUS_APPROVED_EXTERNAL,
            "action_controls:approval_missing",
        ),
        (bool(action_controls.get("approval_recorded")), "action_controls:approval_not_recorded"),
        (bool(action_controls.get("external_verification_redacted")), "action_controls:redaction_failed"),
        (
            action_controls.get("blocked_execution_status") == K8sActionRequest.STATUS_EXECUTION_BLOCKED,
            "action_controls:execution_not_blocked",
        ),
        (bool(action_controls.get("terminal_execute_rejected")), "action_controls:terminal_execute_not_rejected"),
        (bool(action_controls.get("terminal_verify_rejected")), "action_controls:terminal_verify_not_rejected"),
        (action_controls.get("rollback_plan_status") == "required", "action_controls:rollback_plan_missing"),
        (
            action_controls.get("production_restart_template_status") == "ready",
            "action_controls:production_restart_template_missing",
        ),
        (
            bool(action_controls.get("production_restart_template_approval_required")),
            "action_controls:production_restart_template_approval_missing",
        ),
        (
            bool(action_controls.get("production_restart_template_verification_required")),
            "action_controls:production_restart_template_verification_missing",
        ),
        (
            bool(action_controls.get("production_restart_template_report_required")),
            "action_controls:production_restart_template_report_missing",
        ),
        (
            bool(action_controls.get("production_restart_template_safe")),
            "action_controls:production_restart_template_unsafe",
        ),
        (
            action_controls.get("rollback_scale_previous_replicas") == 2,
            "action_controls:rollback_scale_previous_replicas_missing",
        ),
        (
            bool(action_controls.get("rollback_apply_requires_dry_run")),
            "action_controls:rollback_apply_dry_run_missing",
        ),
        (
            bool(action_controls.get("rollback_delete_requires_restore_source")),
            "action_controls:rollback_delete_restore_missing",
        ),
        (bool(action_controls.get("rollback_plan_payload_safe")), "action_controls:rollback_plan_unsafe"),
        (
            action_controls.get("gitops_preview_blast_radius") == "gitops_merge_request",
            "action_controls:gitops_preview_missing",
        ),
        (
            action_controls.get("native_verification_plan_status") == "pending",
            "action_controls:native_verification_plan_missing",
        ),
        (
            "rollout_status_observed" in list(action_controls.get("native_verification_plan_check_ids") or []),
            "action_controls:native_restart_verification_missing",
        ),
        (
            "apply_action_completed" in list(action_controls.get("apply_verification_plan_check_ids") or []),
            "action_controls:native_apply_verification_missing",
        ),
        (
            action_controls.get("native_verification_auto_status") == "verified",
            "action_controls:native_auto_verification_missing",
        ),
        (
            action_controls.get("native_verification_auto_request_status") == K8sActionRequest.STATUS_VERIFIED_NATIVE,
            "action_controls:native_auto_verification_status_invalid",
        ),
        (
            bool(action_controls.get("native_verification_auto_recorded")),
            "action_controls:native_auto_verification_not_recorded",
        ),
        (
            set(action_controls.get("native_verification_auto_check_statuses") or []) == {"passed"},
            "action_controls:native_auto_verification_checks_invalid",
        ),
        (
            bool(action_controls.get("restricted_write_gate_required")),
            "action_controls:restricted_write_gate_not_required",
        ),
        (
            bool(action_controls.get("restricted_write_gate_blocks_without_ref")),
            "action_controls:restricted_write_gate_not_blocking",
        ),
        (
            bool(action_controls.get("restricted_write_gate_allows_with_ref")),
            "action_controls:restricted_write_gate_not_ready",
        ),
        (
            bool(action_controls.get("native_verification_plan_payload_safe")),
            "action_controls:native_verification_plan_unsafe",
        ),
        (
            action_controls.get("gitops_native_execution_mode") == "external_gitops",
            "action_controls:gitops_mode_invalid",
        ),
        (bool(action_controls.get("gitops_repository_sanitized")), "action_controls:gitops_secret_leak"),
        (bool(action_controls.get("gitops_merge_request_template")), "action_controls:gitops_template_missing"),
        (action_controls.get("gitops_provider") == "gitlab", "action_controls:gitops_provider_invalid"),
        (not action_controls.get("gitops_write_performed"), "action_controls:gitops_write_started"),
        (
            not action_controls.get("gitops_cluster_mutation_performed"),
            "action_controls:gitops_cluster_mutation_started",
        ),
        (bool(action_controls.get("gitops_gitlab_payload_ready")), "action_controls:gitops_gitlab_payload_missing"),
        (bool(action_controls.get("gitops_merge_request_draft")), "action_controls:gitops_draft_missing"),
        (
            bool(action_controls.get("gitops_merge_request_removes_source_branch")),
            "action_controls:gitops_cleanup_missing",
        ),
        (
            "fleet_bundle_reconciled" in list(action_controls.get("gitops_verification_plan_check_ids") or []),
            "action_controls:gitops_verification_missing",
        ),
    ]
    for passed, blocker in checks:
        if not passed:
            return blocker
    return ""
