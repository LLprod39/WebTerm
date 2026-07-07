from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.services.release_external_evidence_bundle import EXTERNAL_EVIDENCE_BUNDLE_SCHEMA_VERSION
from kubernetes_ops.services.release_contract import RELEASE_EVIDENCE_SCHEMA_VERSION
from kubernetes_ops.services.release_evidence_checklist import build_kubernetes_production_evidence_checklist
from kubernetes_ops.services.release_readiness_summary import build_kubernetes_release_readiness_summary


def _grant_kubernetes(user: User) -> None:
    UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)


def _write_release_artifact(tmp_path, payload: dict) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "kubernetes_ops_release_evidence.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_external_bundle(tmp_path, payload: dict) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    (artifact_dir / "kubernetes_ops_external_evidence_bundle.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.django_db
def test_release_summary_endpoint_is_staff_only(monkeypatch):
    user = User.objects.create_user(username="k8s-release-summary-reader", password="x")
    staff = User.objects.create_user(username="k8s-release-summary-staff", password="x", is_staff=True)
    _grant_kubernetes(user)
    _grant_kubernetes(staff)
    monkeypatch.setattr(
        "kubernetes_ops.release_views.build_kubernetes_release_readiness_summary",
        lambda **_kwargs: {"success": True, "operation": "release_readiness_summary"},
    )
    client = Client()

    client.force_login(user)
    reader_response = client.get(reverse("api_kubernetes_release_summary"))

    client.force_login(staff)
    staff_response = client.get(reverse("api_kubernetes_release_summary"))

    assert reader_response.status_code == 403
    assert reader_response.json()["code"] == "admin_required"
    assert staff_response.status_code == 200
    assert staff_response.json()["operation"] == "release_readiness_summary"


@pytest.mark.django_db
def test_release_readiness_summary_is_safe_and_operator_readable(monkeypatch, tmp_path):
    _write_release_artifact(
        tmp_path,
        {
            "schema_version": RELEASE_EVIDENCE_SCHEMA_VERSION,
            "generated_at": timezone.now().isoformat(),
            "production_ready": False,
            "ready_for_sidebar": False,
            "release_scope": {"status": "local", "approval_ref": ""},
            "artifact_safety": {"success": True, "status": "ready", "issue_count": 0, "issues": []},
            "blockers": ["release_scope:local"],
            "release_summary": {
                "status": "blocked",
                "production_ready": False,
                "ready_for_sidebar": False,
                "blocker_count": 1,
                "top_blockers": ["release_scope:local"],
                "next_steps": ["Run release evidence in production with non-local endpoints."],
                "release_scope_status": "local",
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
            "provider_probes": [{"token": "raw-artifact-token"}],
            "normal_user_surface": {"password": "raw-artifact-password"},
        },
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_readiness_summary.build_kubernetes_readiness_report",
        lambda **_kwargs: {
            "status": "not_configured",
            "ready_for_sidebar": False,
            "summary": {"ready": 17, "missing": 1, "manual": 0, "total": 18},
            "production_gate": {
                "target_environment": "local",
                "production_target": False,
                "local_indicator_count": 1,
                "missing_required_references": [
                    {
                        "id": "live_provider",
                        "setting": "KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF",
                        "expected": "<production Rancher/Fleet/Devtron live provider evidence ref>",
                    }
                ],
            },
            "checks": [
                {
                    "id": "sidebar_release_scope",
                    "status": "missing",
                    "detail": "Sidebar is locked because release environment is local.",
                    "required": True,
                }
            ],
        },
    )

    with override_settings(BASE_DIR=tmp_path, KUBERNETES_OPS_READY_FOR_SIDEBAR=False):
        payload = build_kubernetes_release_readiness_summary(user=None)

    assert payload["success"] is True
    assert payload["status"] == "blocked"
    assert payload["can_enable_sidebar"] is False
    assert payload["target_environment"] == "local"
    assert payload["artifact"]["status"] == "ready"
    assert payload["proofs"]["definition_of_done"] == {"status": "ready", "ready": 13, "total": 13}
    assert payload["proofs"]["provider_secret_lifecycle"] == "ready"
    assert payload["proofs"]["audit_redaction"] == "ready"
    assert payload["progress"]["stage"] == "core_backend_ready_production_blocked"
    assert payload["progress"]["backend_definition_of_done"]["percent"] == 100
    assert payload["progress"]["runtime_readiness"] == {
        "ready": 17,
        "missing": 1,
        "manual": 0,
        "total": 18,
        "percent": 94,
        "status": "not_configured",
    }
    assert payload["progress"]["release_surface"]["frontend_payload_scan"] == "ready"
    assert payload["progress"]["remaining_categories"] == ["production_scope", "release_artifact", "release_evidence"]
    assert payload["completion_audit"]["status"] == "incomplete"
    assert payload["completion_audit"]["core_backend_complete"] is True
    assert payload["completion_audit"]["runtime_readiness_complete"] is True
    assert payload["completion_audit"]["production_evidence_complete"] is False
    assert payload["completion_audit"]["runtime_missing_required_checks"] == []
    assert payload["completion_audit"]["production_scope_readiness_checks"] == ["sidebar_release_scope"]
    assert payload["completion_audit"]["remaining"] == ["production_evidence", "sidebar_enablement"]
    assert payload["backend_workstream"]["status"] == "backend_ready_production_blocked"
    assert payload["backend_workstream"]["backend_complete"] is True
    assert payload["backend_workstream"]["core_backend_complete"] is True
    assert payload["backend_workstream"]["runtime_readiness_complete"] is True
    assert payload["backend_workstream"]["core_backend_percent"] == 100
    assert payload["backend_workstream"]["remaining_backend_gap_count"] == 0
    assert payload["backend_workstream"]["remaining_backend_gaps"] == []
    assert payload["backend_workstream"]["safe_to_continue_frontend"] is True
    assert payload["backend_workstream"]["next_backend_step"]["id"] == "select_production_environment"
    assert payload["backend_workstream"]["external_production_blocker_summary"]["primary_category"] == "production_scope"
    external_blocker_ids = {item["id"] for item in payload["backend_workstream"]["external_production_blockers"]}
    assert {"sidebar_release_scope", "target_environment", "select_production_environment", "production_scope", "release_artifact"} <= external_blocker_ids
    assert payload["production_evidence_checklist"]["status"] == "not_required"
    assert payload["production_evidence_checklist"]["production_target"] is False
    assert payload["production_evidence_checklist"]["external_bundle"]["status"] == "missing"
    assert payload["production_evidence_checklist"]["gap_summary"] == {
        "status": "not_required",
        "production_target": False,
        "ready_for_release_evidence": False,
        "blocking_gap_count": 1,
        "missing_core_ref_count": 0,
        "missing_external_ref_count": 0,
        "missing_external_artifact_count": 0,
        "local_indicator_count": 0,
        "external_bundle_status": "missing",
        "next_gap_id": "select_production_environment",
        "next_manual_step_id": "select_production_environment",
        "next_command_ids": [],
        "missing_settings": [],
        "external_artifact_ids": [],
    }
    assert payload["operator_command_plan"]["recommended_next"]["id"] == "select_production_environment"
    assert payload["operator_command_plan"]["blocking_summary"]["next_gap_id"] == "select_production_environment"
    assert payload["operator_command_plan"]["blocking_summary"]["production_blocking_gap_count"] == 1
    execution_plan = payload["production_execution_plan"]
    assert execution_plan["status"] == "blocked"
    assert execution_plan["recommended_next"]["id"] == "select_production_environment"
    assert execution_plan["blocked_until_count"] >= 5
    assert execution_plan["phase_count"] == 4
    assert execution_plan["command_count"] == 10
    blocked_ids = {item["id"] for item in execution_plan["blocked_until"]}
    assert {"target_environment", "local_indicators", "production_ready", "ready_for_sidebar"} <= blocked_ids
    configure_phase = next(phase for phase in execution_plan["phases"] if phase["id"] == "configure_production_scope")
    assert "KUBERNETES_OPS_RELEASE_ENVIRONMENT" in configure_phase["settings"]
    assert "KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF" in configure_phase["settings"]
    assert "KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF" in configure_phase["settings"]
    execution_command_ids = {
        command["id"]
        for phase in execution_plan["phases"]
        for command in phase.get("commands", [])
    }
    assert {"live_provider_smoke", "external_evidence_bundle", "preflight", "release_evidence", "release_handoff"} <= execution_command_ids
    command_ids = {item["id"] for item in payload["operator_command_plan"]["commands"]}
    assert {"external_evidence_bundle", "live_provider_smoke", "readonly_rbac_live", "release_evidence", "release_handoff"} <= command_ids
    assert payload["missing_required_references"][0]["setting"] == "KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF"
    assert {group["id"] for group in payload["blocker_groups"]} >= {"production_scope", "release_artifact", "release_evidence"}
    assert "runtime_readiness" not in {group["id"] for group in payload["blocker_groups"]}
    assert "Run release evidence in production with non-local endpoints." in payload["next_steps"]
    assert "verify_kubernetes_ops_release" in str(payload["required_commands"])
    assert "raw-artifact-token" not in str(payload)
    assert "raw-artifact-password" not in str(payload)


def test_release_readiness_progress_prefers_production_blocked_when_core_backend_is_ready(monkeypatch, tmp_path):
    _write_release_artifact(
        tmp_path,
        {
            "schema_version": RELEASE_EVIDENCE_SCHEMA_VERSION,
            "generated_at": timezone.now().isoformat(),
            "production_ready": False,
            "ready_for_sidebar": False,
            "release_scope": {"status": "local"},
            "artifact_safety": {"success": True, "status": "ready", "issue_count": 0, "issues": []},
            "blockers": ["release_scope:local"],
            "release_summary": {
                "status": "blocked",
                "production_ready": False,
                "ready_for_sidebar": False,
                "blocker_count": 1,
                "top_blockers": ["release_scope:local"],
                "next_steps": ["Run release evidence in production with non-local endpoints."],
                "release_scope_status": "local",
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
    monkeypatch.setattr(
        "kubernetes_ops.services.release_readiness_summary.build_kubernetes_readiness_report",
        lambda **_kwargs: {
            "status": "configured",
            "ready_for_sidebar": False,
            "summary": {"ready": 18, "missing": 0, "manual": 0, "total": 18},
            "production_gate": {
                "target_environment": "local",
                "production_target": False,
                "local_indicator_count": 1,
                "missing_required_references": [],
            },
            "checks": [],
        },
    )

    with override_settings(BASE_DIR=tmp_path, KUBERNETES_OPS_READY_FOR_SIDEBAR=False):
        payload = build_kubernetes_release_readiness_summary(user=None)

    assert payload["progress"]["stage"] == "core_backend_ready_production_blocked"
    assert payload["progress"]["plain_status"] == "Core backend proof is ready, but production/sidebar enablement is still blocked by release scope or evidence."
    assert payload["progress"]["backend_definition_of_done"]["percent"] == 100
    assert payload["progress"]["runtime_readiness"]["percent"] == 100
    assert payload["progress"]["remaining_categories"] == ["production_scope", "release_artifact", "release_evidence"]
    assert payload["completion_audit"]["core_backend_complete"] is True
    assert payload["completion_audit"]["runtime_readiness_complete"] is True
    assert payload["completion_audit"]["production_evidence_complete"] is False
    assert payload["completion_audit"]["remaining"] == ["production_evidence", "sidebar_enablement"]
    assert payload["backend_workstream"]["status"] == "backend_ready_production_blocked"
    assert payload["backend_workstream"]["backend_complete"] is True
    assert payload["backend_workstream"]["remaining_backend_gap_count"] == 0
    assert payload["backend_workstream"]["external_production_blocker_count"] >= 4


def test_release_readiness_summary_requires_artifact_sidebar_ready(monkeypatch, tmp_path):
    _write_release_artifact(
        tmp_path,
        {
            "schema_version": RELEASE_EVIDENCE_SCHEMA_VERSION,
            "generated_at": timezone.now().isoformat(),
            "production_ready": True,
            "ready_for_sidebar": False,
            "release_scope": {"status": "ready"},
            "artifact_safety": {"success": True, "status": "ready", "issue_count": 0, "issues": []},
            "completion_audit": {
                "status": "incomplete",
                "production_evidence_complete": True,
                "sidebar_enablement_complete": False,
            },
            "blockers": ["readiness:ready_for_sidebar=missing"],
            "release_summary": {
                "status": "blocked",
                "production_ready": True,
                "ready_for_sidebar": False,
                "blocker_count": 1,
                "top_blockers": ["readiness:ready_for_sidebar=missing"],
                "next_steps": ["Regenerate release evidence after sidebar readiness is green."],
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
                "required_references": [],
            },
            "checks": [],
        },
    )

    with override_settings(BASE_DIR=tmp_path, KUBERNETES_OPS_READY_FOR_SIDEBAR=False):
        payload = build_kubernetes_release_readiness_summary(user=None)

    assert payload["status"] == "blocked"
    assert payload["can_enable_sidebar"] is False
    assert payload["artifact"]["production_ready"] is True
    assert payload["artifact"]["ready_for_sidebar"] is False
    assert payload["artifact"]["production_evidence_complete"] is True
    assert payload["artifact"]["sidebar_enablement_complete"] is False
    assert payload["completion_audit"]["production_evidence_complete"] is True
    assert payload["completion_audit"]["sidebar_enablement_complete"] is False
    assert payload["backend_workstream"]["status"] == "backend_ready_production_blocked"
    assert payload["progress"]["stage"] == "release_artifact_incomplete"
    artifact_group = next(group for group in payload["blocker_groups"] if group["id"] == "release_artifact")
    assert artifact_group["count"] >= 1
    execution_plan = payload["production_execution_plan"]
    assert execution_plan["status"] == "blocked"
    blocked_ids = {item["id"] for item in execution_plan["blocked_until"]}
    assert {"ready_for_sidebar", "sidebar_enablement_complete"} <= blocked_ids


def test_release_readiness_summary_requires_artifact_completion_audit(monkeypatch, tmp_path):
    _write_release_artifact(
        tmp_path,
        {
            "schema_version": RELEASE_EVIDENCE_SCHEMA_VERSION,
            "generated_at": timezone.now().isoformat(),
            "production_ready": True,
            "ready_for_sidebar": True,
            "release_scope": {"status": "ready"},
            "artifact_safety": {"success": True, "status": "ready", "issue_count": 0, "issues": []},
            "completion_audit": {
                "status": "incomplete",
                "production_evidence_complete": False,
                "sidebar_enablement_complete": False,
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
                "required_references": [],
            },
            "checks": [],
        },
    )

    with override_settings(BASE_DIR=tmp_path, KUBERNETES_OPS_READY_FOR_SIDEBAR=False):
        payload = build_kubernetes_release_readiness_summary(user=None)

    assert payload["status"] == "blocked"
    assert payload["can_enable_sidebar"] is False
    assert payload["artifact"]["production_evidence_complete"] is False
    assert payload["completion_audit"]["production_evidence_complete"] is False
    assert payload["completion_audit"]["sidebar_enablement_complete"] is False
    assert payload["backend_workstream"]["status"] == "backend_ready_production_blocked"
    assert payload["operator_command_plan"]["status"] == "attention_required"
    blocked_ids = {item["id"] for item in payload["production_execution_plan"]["blocked_until"]}
    assert {"production_evidence_complete", "sidebar_enablement_complete"} <= blocked_ids


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
                {"id": "live_provider_smoke", "status": "ready", "success": True, "checked_at": now, "schema_version": "v", "local_indicators": [], "errors": []},
                {"id": "readonly_rbac_live", "status": "ready", "success": True, "checked_at": now, "schema_version": "", "local_indicators": [], "errors": []},
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
                {"id": "production_approval", "setting": "KUBERNETES_OPS_PRODUCTION_APPROVAL_REF", "required": True, "present": True},
                {"id": "live_provider", "setting": "KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF", "required": True, "present": False},
            ],
            "artifact_checks": [
                {"id": "live_provider_smoke", "status": "ready", "success": True, "checked_at": now, "schema_version": "v", "local_indicators": [], "errors": []},
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
