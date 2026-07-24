from __future__ import annotations

from django.test import override_settings
from django.utils import timezone

from kubernetes_ops.services.release_contract import RELEASE_EVIDENCE_SCHEMA_VERSION
from kubernetes_ops.services.release_evidence_checklist import build_kubernetes_production_evidence_checklist
from kubernetes_ops.services.release_external_evidence_bundle import EXTERNAL_EVIDENCE_BUNDLE_SCHEMA_VERSION
from kubernetes_ops.services.release_readiness_summary import build_kubernetes_release_readiness_summary
from tests.kubernetes_ops_release_readiness_summary_helpers import (
    _write_external_bundle,
    _write_release_artifact,
)


def test_release_readiness_summary_returns_safe_production_evidence_checklist(monkeypatch, tmp_path):
    now = timezone.now().isoformat()
    _write_release_artifact(
        tmp_path,
        {
            "schema_version": RELEASE_EVIDENCE_SCHEMA_VERSION,
            "generated_at": now,
            "production_ready": True,
            "ready_for_sidebar": True,
            "release_scope": {"status": "ready"},
            "artifact_safety": {"success": True, "status": "ready", "issue_count": 0, "issues": []},
            "completion_audit": {
                "status": "complete",
                "production_evidence_complete": True,
                "sidebar_enablement_complete": True,
            },
            "blockers": [],
            "release_summary": {
                "status": "ready",
                "production_ready": True,
                "ready_for_sidebar": True,
                "blocker_count": 0,
                "top_blockers": [],
                "next_steps": [],
                "release_scope_status": "ready",
                "preflight_status": "ready",
                "artifact_safety_status": "ready",
                "normal_user_surface_status": "ready",
                "definition_of_done_status": "ready",
                "definition_of_done_ready": 13,
                "definition_of_done_total": 13,
                "frontend_payload_scan_status": "ready",
                "sensitive_value_controls_status": "ready",
                "provider_lifecycle_status": "ready",
                "audit_redaction_status": "ready",
                "production_action_evidence_status": "ready",
                "production_action_blocked_action_class_count": 11,
            },
        },
    )
    required_refs = [
        ("production_approval", "KUBERNETES_OPS_PRODUCTION_APPROVAL_REF"),
        ("production_evidence", "KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF"),
        ("identity_runtime", "KUBERNETES_OPS_IDENTITY_RUNTIME_EVIDENCE_REF"),
        ("live_provider", "KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF"),
        ("readonly_rbac", "KUBERNETES_OPS_READONLY_RBAC_EVIDENCE_REF"),
        ("kubernetes_mcp", "KUBERNETES_OPS_KUBERNETES_MCP_EVIDENCE_REF"),
        ("production_rollback", "KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF"),
        ("native_verification", "KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF"),
    ]
    _write_external_bundle(
        tmp_path,
        {
            "schema_version": EXTERNAL_EVIDENCE_BUNDLE_SCHEMA_VERSION,
            "status": "ready",
            "success": True,
            "checked_at": now,
            "dangerous_live_action_started": False,
            "summary": {
                "required_ref_count": len(required_refs),
                "missing_required_ref_count": 0,
                "artifact_check_count": 2,
                "artifact_ready_count": 2,
                "local_indicator_count": 0,
            },
            "references": [
                {"id": ref_id, "setting": setting, "required": True, "present": True}
                for ref_id, setting in required_refs
            ],
            "artifact_checks": [
                {
                    "id": "live_provider_smoke",
                    "status": "ready",
                    "success": True,
                    "checked_at": now,
                    "schema_version": "v",
                    "local_indicators": [],
                    "errors": [],
                },
                {
                    "id": "readonly_rbac_live",
                    "status": "ready",
                    "success": True,
                    "checked_at": now,
                    "schema_version": "",
                    "local_indicators": [],
                    "errors": [],
                },
            ],
            "errors": [],
        },
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_readiness_summary.build_kubernetes_readiness_report",
        lambda **_kwargs: {
            "status": "ready",
            "ready_for_sidebar": True,
            "summary": {"ready": 18, "missing": 0, "manual": 0, "total": 18},
            "production_gate": {
                "target_environment": "production",
                "production_target": True,
                "approval_ref_present": True,
                "local_indicator_count": 0,
                "missing_required_references": [],
                "required_references": [
                    {
                        "id": ref_id,
                        "setting": setting,
                        "expected": "<evidence-ref>",
                        "required": True,
                        "present": True,
                    }
                    for ref_id, setting in required_refs
                ],
            },
            "checks": [],
        },
    )

    with override_settings(BASE_DIR=tmp_path, KUBERNETES_OPS_READY_FOR_SIDEBAR=True):
        payload = build_kubernetes_release_readiness_summary(user=None)

    checklist = payload["production_evidence_checklist"]
    assert checklist["status"] == "ready"
    assert checklist["production_target"] is True
    assert checklist["core_missing_required_count"] == 0
    assert checklist["external_bundle"]["status"] == "ready"
    assert checklist["external_bundle"]["missing_required_ref_count"] == 0
    assert checklist["external_bundle"]["artifact_ready_count"] == 2
    assert checklist["blockers"] == []
    assert checklist["gap_summary"]["ready_for_release_evidence"] is True
    assert checklist["gap_summary"]["blocking_gap_count"] == 0
    assert checklist["gap_summary"]["next_gap_id"] == "ready"
    assert checklist["gap_summary"]["next_command_ids"] == ["release_evidence", "release_handoff"]
    assert payload["completion_audit"]["status"] == "complete"
    assert payload["artifact"]["completion_audit_status"] == "complete"
    assert payload["artifact"]["production_evidence_complete"] is True
    assert payload["artifact"]["sidebar_enablement_complete"] is True
    assert payload["completion_audit"]["core_backend_complete"] is True
    assert payload["completion_audit"]["runtime_readiness_complete"] is True
    assert payload["completion_audit"]["production_evidence_complete"] is True
    assert payload["completion_audit"]["sidebar_enablement_complete"] is True
    assert payload["completion_audit"]["remaining"] == []
    assert payload["operator_command_plan"]["status"] == "ready"
    assert payload["operator_command_plan"]["recommended_next"]["id"] == "release_handoff"
    assert payload["operator_command_plan"]["recommended_next"]["type"] == "command"
    assert payload["operator_command_plan"]["blocking_summary"]["production_blocking_gap_count"] == 0
    assert payload["operator_command_plan"]["blocking_summary"]["recommended_next_id"] == "release_handoff"
    assert payload["operator_command_plan"]["manual_steps"] == []
    assert payload["backend_workstream"]["status"] == "ready_for_sidebar"
    assert payload["backend_workstream"]["backend_complete"] is True
    assert payload["backend_workstream"]["external_production_blocker_count"] == 0
    assert payload["backend_workstream"]["next_backend_step"] == {"id": "none", "type": "complete", "gap_count": 0}
    execution_plan = payload["production_execution_plan"]
    assert execution_plan["status"] == "ready"
    assert execution_plan["can_enable_sidebar"] is True
    assert execution_plan["recommended_next"]["id"] == "enable_sidebar_after_approval"
    assert execution_plan["blocked_until"] == []
    assert execution_plan["command_count"] == 10
    assert "verify_kubernetes_ops_external_evidence_bundle" in str(payload["operator_command_plan"])
    assert "artifact:production-bundle" not in str(checklist)
    assert "artifact:production-bundle" not in str(payload["operator_command_plan"])


def test_production_evidence_checklist_gap_summary_prioritizes_external_missing_refs(tmp_path):
    now = timezone.now().isoformat()
    required_refs = [
        ("production_approval", "KUBERNETES_OPS_PRODUCTION_APPROVAL_REF"),
        ("live_provider", "KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF"),
    ]
    _write_external_bundle(
        tmp_path,
        {
            "schema_version": EXTERNAL_EVIDENCE_BUNDLE_SCHEMA_VERSION,
            "status": "missing",
            "success": False,
            "checked_at": now,
            "dangerous_live_action_started": False,
            "summary": {
                "required_ref_count": len(required_refs),
                "missing_required_ref_count": 1,
                "artifact_check_count": 1,
                "artifact_ready_count": 1,
                "local_indicator_count": 0,
            },
            "references": [
                {
                    "id": "production_approval",
                    "setting": "KUBERNETES_OPS_PRODUCTION_APPROVAL_REF",
                    "required": True,
                    "present": True,
                },
                {
                    "id": "live_provider",
                    "setting": "KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF",
                    "required": True,
                    "present": False,
                },
            ],
            "artifact_checks": [
                {
                    "id": "live_provider_smoke",
                    "status": "ready",
                    "success": True,
                    "checked_at": now,
                    "schema_version": "v",
                    "local_indicators": [],
                    "errors": [],
                },
            ],
            "errors": ["reference:live_provider:KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF:missing"],
        },
    )
    production_gate = {
        "target_environment": "production",
        "production_target": True,
        "approval_ref_present": True,
        "required_references": [
            {"id": ref_id, "setting": setting, "expected": "<evidence-ref>", "required": True, "present": True}
            for ref_id, setting in required_refs
        ],
    }

    with override_settings(BASE_DIR=tmp_path):
        checklist = build_kubernetes_production_evidence_checklist(production_gate=production_gate)

    assert checklist["status"] == "missing_external_bundle"
    assert checklist["gap_summary"]["next_gap_id"] == "set_external_bundle_refs"
    assert checklist["gap_summary"]["next_manual_step_id"] == "set_external_evidence_refs"
    assert checklist["gap_summary"]["next_command_ids"] == ["external_evidence_bundle"]
    assert checklist["gap_summary"]["missing_external_ref_count"] == 1
    assert checklist["gap_summary"]["missing_settings"] == ["KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF"]
    assert "reference:live_provider" not in str(checklist)
