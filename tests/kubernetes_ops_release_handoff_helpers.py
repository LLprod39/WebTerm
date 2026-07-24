from __future__ import annotations


def _blocked_evidence() -> dict:
    return {
        "schema_version": "kubernetes_ops.release_evidence.v2",
        "generated_at": "2026-06-30T18:27:56+00:00",
        "production_ready": False,
        "ready_for_sidebar": False,
        "blockers": ["readiness:sidebar_release_scope=missing", "release_scope:local"],
        "release_scope": {
            "status": "local",
            "target_environment": "local",
            "approval_ref_present": False,
            "local_indicator_count": 8,
            "local_indicators": [
                {
                    "source": "provider_probe.provider_base_url",
                    "value": "https://host.docker.internal:8443",
                    "classification": "local",
                }
            ],
            "reason": "production target environment is not selected",
        },
        "artifact_safety": {"success": True, "status": "ready", "issue_count": 0},
        "action_controls": {
            "success": True,
            "status": "ready",
            "native_execution_enabled": False,
            "approval_status": "approved_external",
            "rollback_plan_status": "required",
            "production_restart_template_status": "ready",
            "native_verification_plan_status": "pending",
            "native_verification_auto_status": "verified",
            "native_verification_auto_request_status": "verified_native",
            "native_verification_auto_recorded": True,
            "native_verification_auto_check_statuses": ["passed"],
            "gitops_provider": "gitlab",
            "gitops_write_performed": False,
            "gitops_cluster_mutation_performed": False,
            "restricted_write_gate_required": True,
            "restricted_write_gate_blocks_without_ref": True,
            "restricted_write_gate_allows_with_ref": True,
        },
        "admin_mode_safety": {"success": True, "status": "ready", "provider_called": False, "admin_actions_created": 0},
        "post_review_retention": {
            "success": True,
            "status": "ready",
            "checks": {
                "pending_post_review_detected": True,
                "retention_apply_deleted_events": 1,
                "post_review_redacted": True,
            },
        },
        "external_evidence_bundle": {
            "success": True,
            "status": "ready",
            "summary": {
                "missing_required_ref_count": 0,
                "artifact_ready_count": 6,
                "artifact_check_count": 6,
                "local_indicator_count": 0,
            },
        },
        "production_action_evidence": {
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
        },
        "interactive_transport_evidence": {
            "success": True,
            "status": "ready",
            "summary": {"enabled_transport_count": 0, "blocker_count": 0},
        },
        "interactive_live_smoke": {
            "success": True,
            "status": "ready",
            "summary": {
                "simulated_check_count": 4,
                "live_transport_contract_count": 4,
                "live_smoke_required": False,
                "production_live_provider_evidence": False,
            },
        },
        "interactive_shell_streams": {
            "success": True,
            "status": "ready",
            "actions_created": 2,
            "recordings_created": 2,
            "recording_events_created": 4,
            "provider_requests_safe": True,
        },
        "definition_of_done": {
            "success": True,
            "status": "ready",
            "ready": 13,
            "missing": 0,
            "total": 13,
            "missing_ids": [],
        },
        "normal_user_surface": {
            "success": True,
            "status": "ready",
            "reader_external_link_policy": {"visible": False, "mode": "webterm_native_only"},
            "frontend_response_credential_scan": {
                "status": "ready",
                "surfaces_checked": 16,
                "provider_secret_reference_serialized": False,
                "forbidden_values_found": False,
            },
        },
        "secret_read_controls": {
            "success": True,
            "status": "ready",
            "default_redacted": True,
            "secret_list_metadata_only": True,
            "secret_read_rejected_without_grant": True,
            "secret_read_rejected_without_runtime_flag": True,
            "secret_read_allowed_with_all_gates": True,
        },
        "provider_secret_lifecycle": {
            "success": True,
            "status": "ready",
            "storage_mode": "managed",
            "rotation_supported": True,
            "persistent_rows": False,
            "checks": {"plaintext_not_serialized": True},
        },
        "audit_redaction": {
            "success": True,
            "status": "ready",
            "serializers_checked": ["serialize_audit_event", "serialize_cluster_event"],
            "checks": {
                "api_serializer_raw_values_absent": True,
                "cluster_event_raw_values_absent": True,
                "credentialed_url_sanitized": True,
                "rollback_removed_audit_event": True,
                "rollback_removed_cluster": True,
            },
        },
        "release_summary": {
            "status": "blocked",
            "top_blockers": ["readiness:sidebar_release_scope=missing", "release_scope:local"],
            "next_steps": [
                "Run release evidence in production with non-local Rancher/Devtron/MCP endpoints, approval ref and core evidence refs."
            ],
        },
    }
