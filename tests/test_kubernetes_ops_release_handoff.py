from __future__ import annotations

import json

from kubernetes_ops.services.release_handoff import build_kubernetes_release_handoff
from tests.kubernetes_ops_release_handoff_helpers import _blocked_evidence


def test_kubernetes_release_handoff_summarizes_blocked_local_evidence(tmp_path):
    evidence_path = tmp_path / "release.json"
    evidence_path.write_text(json.dumps(_blocked_evidence()), encoding="utf-8")

    handoff = build_kubernetes_release_handoff(evidence_path=evidence_path)

    assert handoff["status"] == "blocked"
    assert handoff["can_enable_sidebar"] is False
    assert handoff["evidence"]["loaded"] is True
    assert handoff["release_scope"]["status"] == "local"
    assert handoff["release_scope"]["local_indicator_count"] == 8
    assert "release_scope:local" in handoff["blockers"]
    assert handoff["completion_audit"]["core_backend_complete"] is True
    assert handoff["completion_audit"]["runtime_readiness_complete"] is True
    assert handoff["completion_audit"]["production_evidence_complete"] is False
    assert handoff["completion_audit"]["remaining"] == ["production_evidence", "sidebar_enablement"]
    assert handoff["backend_workstream"]["status"] == "backend_ready_production_blocked"
    assert handoff["backend_workstream"]["backend_complete"] is True
    assert handoff["backend_workstream"]["core_backend_percent"] == 100
    assert handoff["backend_workstream"]["remaining_backend_gap_count"] == 0
    assert handoff["backend_workstream"]["safe_to_continue_frontend"] is True
    assert handoff["backend_workstream"]["next_backend_step"]["id"] == "select_production_environment"
    blocker_summary = handoff["backend_workstream"]["external_production_blocker_summary"]
    assert blocker_summary["primary_category"] == "production_scope"
    assert blocker_summary["category_count"] >= 3
    assert blocker_summary["plain_status"] == "Select production release scope and remove local/demo evidence first."
    blocker_categories = {item["id"]: item for item in blocker_summary["categories"]}
    assert "production_scope" in blocker_categories
    assert blocker_categories["production_scope"]["count"] >= 2
    external_blocker_ids = {item["id"] for item in handoff["backend_workstream"]["external_production_blockers"]}
    assert {
        "target_environment",
        "no_local_indicators",
        "select_production_environment",
        "production_scope",
    } <= external_blocker_ids
    proof_status = {item["id"]: item["status"] for item in handoff["release_proofs"]}
    assert proof_status["post_review_retention"] == "ready"
    assert proof_status["external_evidence_bundle"] == "ready"
    assert proof_status["production_action_evidence"] == "ready"
    assert proof_status["interactive_transport_evidence"] == "ready"
    assert proof_status["interactive_live_smoke"] == "ready"
    assert proof_status["interactive_shell_streams"] == "ready"
    assert proof_status["definition_of_done"] == "ready"
    assert proof_status["secret_read_controls"] == "ready"
    assert proof_status["provider_secret_lifecycle"] == "ready"
    assert proof_status["audit_redaction"] == "ready"
    definition_of_done = next(item for item in handoff["release_proofs"] if item["id"] == "definition_of_done")
    assert "ready=13/13" in definition_of_done["detail"]
    assert "missing=0" in definition_of_done["detail"]
    normal_user_surface = next(item for item in handoff["release_proofs"] if item["id"] == "normal_user_surface")
    assert "credential_scan=ready" in normal_user_surface["detail"]
    assert "secret_ref_serialized=False" in normal_user_surface["detail"]
    assert "forbidden_values=False" in normal_user_surface["detail"]
    production_action_evidence = next(
        item for item in handoff["release_proofs"] if item["id"] == "production_action_evidence"
    )
    assert "rollback_actions=5" in production_action_evidence["detail"]
    assert "native_checks=10" in production_action_evidence["detail"]
    assert "blocked_actions=11" in production_action_evidence["detail"]
    assert "blocked_contract=True" in production_action_evidence["detail"]
    interactive = next(item for item in handoff["release_proofs"] if item["id"] == "interactive_shell_streams")
    assert "actions=2" in interactive["detail"]
    assert "recordings=2" in interactive["detail"]
    assert "events=4" in interactive["detail"]
    assert handoff["next_steps"] == [
        "Run release evidence in production with non-local Rancher/Devtron/MCP endpoints, approval ref and core evidence refs."
    ]
    execution_plan = handoff["production_execution_plan"]
    assert execution_plan["status"] == "blocked"
    assert execution_plan["can_enable_sidebar"] is False
    assert execution_plan["recommended_next"]["id"] == "select_production_environment"
    blocked_ids = {item["id"] for item in execution_plan["blocked_until"]}
    assert {
        "target_environment",
        "production_approval_ref",
        "local_indicators",
        "production_ready",
        "ready_for_sidebar",
        "production_evidence_complete",
        "sidebar_enablement_complete",
    } <= blocked_ids
    phase_commands = {command["id"] for phase in execution_plan["phases"] for command in phase.get("commands", [])}
    assert {
        "live_provider_smoke",
        "readonly_rbac_live",
        "external_evidence_bundle",
        "preflight_evidence",
        "release_evidence",
        "release_handoff",
    } <= phase_commands
    assert "https://host.docker.internal:8443" not in str(handoff)
    command_ids = {item["id"] for item in handoff["required_commands"]}
    assert {
        "preflight_evidence",
        "release_evidence",
        "release_handoff",
        "readonly_rbac_live",
        "interactive_transport_evidence",
        "interactive_live_smoke",
        "interactive_production_controls",
        "external_evidence_bundle",
    } <= command_ids
    operator_plan = handoff["operator_command_plan"]
    assert operator_plan["recommended_next"]["id"] == "select_production_environment"
    assert operator_plan["blocking_summary"]["next_gap_id"] == "select_production_environment"
    local_phase = next(phase for phase in operator_plan["phases"] if phase["id"] == "local_demo_smoke")
    local_commands = {command["id"]: command for command in local_phase["commands"]}
    assert local_commands["local_demo_fixture"]["scope"] == "local_demo"
    assert ".tools/k8s-provider-fixture.py" in local_commands["local_demo_fixture"]["command"]
    assert (
        local_commands["local_demo_seed"]["command"]
        == "python manage.py seed_kubernetes_ops_demo --username admin --admin-write"
    )
    env_flags = {item["name"]: item["expected"] for item in handoff["production_env_flags"]}
    assert "KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF" in env_flags
    assert "KUBERNETES_OPS_IDENTITY_RUNTIME_EVIDENCE_REF" in env_flags
    assert "KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF" in env_flags
    assert "KUBERNETES_OPS_READONLY_RBAC_EVIDENCE_REF" in env_flags
    assert "KUBERNETES_OPS_KUBERNETES_MCP_EVIDENCE_REF" in env_flags
    assert "KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF" in env_flags
    assert "KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF" in env_flags
    assert "KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF" in env_flags
    assert "interactive transport" in env_flags["KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF"]
    assert "KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF" in env_flags
    assert "port-forward tunnel" in env_flags["KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF"]
    assert "KUBERNETES_ADMIN_INTERACTIVE_LIVE_SMOKE_EVIDENCE_REF" in env_flags
    assert any("restricted credential evidence" in item for item in handoff["external_evidence_required"])
    assert any("External evidence bundle" in item for item in handoff["external_evidence_required"])
    assert any("rollback drill evidence" in item for item in handoff["external_evidence_required"])
    assert any("native verification evidence" in item for item in handoff["external_evidence_required"])
    assert any("interactive transport prerequisite artifact" in item for item in handoff["external_evidence_required"])
    assert any("interactive live-smoke artifact" in item for item in handoff["external_evidence_required"])
    assert any("interactive production controls artifact" in item for item in handoff["external_evidence_required"])
    assert any("port-forward network policy evidence" in item for item in handoff["external_evidence_required"])
    assert any("interactive transports require recording gates" in item for item in handoff["safety_guards"])
    assert any(
        "port-forward additionally requires network policy evidence" in item for item in handoff["safety_guards"]
    )


def test_kubernetes_release_handoff_recomputes_stale_backend_workstream(tmp_path):
    evidence = _blocked_evidence()
    evidence["backend_workstream"] = {
        "status": "ready_for_sidebar",
        "plain_status": "stale derived payload",
        "backend_complete": True,
        "core_backend_complete": True,
        "runtime_readiness_complete": True,
        "core_backend_proof_count": 7,
        "core_backend_proof_ready_count": 7,
        "core_backend_percent": 100,
        "remaining_backend_gap_count": 0,
        "remaining_backend_gaps": [],
        "external_production_blocker_count": 0,
        "external_production_blockers": [],
        "safe_to_continue_frontend": True,
        "next_backend_step": {"id": "none", "type": "complete", "gap_count": 0},
    }
    evidence_path = tmp_path / "release.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    handoff = build_kubernetes_release_handoff(evidence_path=evidence_path)

    workstream = handoff["backend_workstream"]
    assert workstream["status"] == "backend_ready_production_blocked"
    assert workstream["next_backend_step"]["id"] == "select_production_environment"
    assert workstream["external_production_blocker_count"] > 0
    assert workstream["external_production_blocker_summary"]["primary_category"] == "production_scope"
    blocker_ids = {item["id"] for item in workstream["external_production_blockers"]}
    assert {"production_scope", "release_artifact", "release_evidence"} <= blocker_ids


def test_kubernetes_release_handoff_requires_ready_for_sidebar_gate(tmp_path):
    evidence = _blocked_evidence()
    evidence.update(
        {
            "production_ready": True,
            "ready_for_sidebar": False,
            "blockers": ["readiness:ready_for_sidebar=missing"],
            "release_scope": {
                "status": "ready",
                "target_environment": "production",
                "approval_ref_present": True,
                "core_evidence_ready": True,
                "missing_reference_count": 0,
                "missing_required_references": [],
                "local_indicator_count": 0,
                "reason": "",
            },
        }
    )
    evidence.pop("release_summary", None)
    evidence_path = tmp_path / "release.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    handoff = build_kubernetes_release_handoff(evidence_path=evidence_path)

    assert handoff["status"] == "blocked"
    assert handoff["can_enable_sidebar"] is False
    assert handoff["backend_workstream"]["status"] == "backend_ready_production_blocked"
    assert handoff["completion_audit"]["production_evidence_complete"] is True
    assert handoff["completion_audit"]["sidebar_enablement_complete"] is False
    execution_plan = handoff["production_execution_plan"]
    assert execution_plan["status"] == "blocked"
    assert execution_plan["can_enable_sidebar"] is False
    blocked_ids = {item["id"] for item in execution_plan["blocked_until"]}
    assert {"ready_for_sidebar", "sidebar_enablement_complete"} <= blocked_ids


def test_kubernetes_release_handoff_requires_completion_audit_green(tmp_path):
    evidence = _blocked_evidence()
    evidence.update(
        {
            "production_ready": True,
            "ready_for_sidebar": True,
            "blockers": [],
            "release_scope": {
                "status": "ready",
                "target_environment": "production",
                "approval_ref_present": True,
                "core_evidence_ready": True,
                "missing_reference_count": 0,
                "missing_required_references": [],
                "local_indicator_count": 0,
                "reason": "",
            },
            "completion_audit": {
                "core_backend_complete": True,
                "runtime_readiness_complete": True,
                "production_evidence_complete": False,
                "sidebar_enablement_complete": False,
                "remaining": ["production_evidence", "sidebar_enablement"],
            },
        }
    )
    evidence.pop("release_summary", None)
    evidence_path = tmp_path / "release.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    handoff = build_kubernetes_release_handoff(evidence_path=evidence_path)

    assert handoff["status"] == "blocked"
    assert handoff["can_enable_sidebar"] is False
    assert handoff["backend_workstream"]["status"] == "backend_ready_production_blocked"
    execution_plan = handoff["production_execution_plan"]
    assert execution_plan["status"] == "blocked"
    blocked_ids = {item["id"] for item in execution_plan["blocked_until"]}
    assert {"production_evidence_complete", "sidebar_enablement_complete"} <= blocked_ids


def test_kubernetes_release_handoff_prefers_root_completion_audit(tmp_path):
    evidence = _blocked_evidence()
    evidence["completion_audit"] = {
        "core_backend_complete": True,
        "runtime_readiness_complete": True,
        "production_evidence_complete": True,
        "sidebar_enablement_complete": False,
        "remaining": ["sidebar_enablement"],
    }
    evidence_path = tmp_path / "release.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    handoff = build_kubernetes_release_handoff(evidence_path=evidence_path)

    assert handoff["completion_audit"]["production_evidence_complete"] is True
    assert handoff["completion_audit"]["remaining"] == ["sidebar_enablement"]
