from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from kubernetes_ops.services.release_artifact_safety import build_kubernetes_release_evidence_artifact_safety_report
from kubernetes_ops.services.release_evidence import _attach_backend_workstream, build_kubernetes_release_evidence


@pytest.mark.django_db
def test_release_evidence_embeds_safe_production_execution_plan():
    user = User.objects.create_user(username="release-plan-admin", password="x", is_staff=True)

    evidence = build_kubernetes_release_evidence(
        user=user,
        run_provider_probe=False,
        run_sync_dry_run=False,
        run_mcp_call=False,
        run_action_controls=False,
        run_admin_mode_safety=False,
        run_post_review_retention=False,
        run_external_evidence_bundle=False,
        run_interactive_transport_evidence=False,
        run_interactive_live_smoke=False,
        run_interactive_shell_streams=False,
        run_normal_user_surface=False,
        run_readonly_rbac_live=False,
        run_secret_read_controls=False,
        run_provider_secret_lifecycle=False,
        run_audit_redaction=False,
        run_production_action_evidence=False,
    )

    plan = evidence["production_execution_plan"]
    backend_workstream = evidence["backend_workstream"]

    assert plan["status"] == "blocked"
    assert plan["can_enable_sidebar"] is False
    assert plan["recommended_next"]["id"] == "select_production_environment"
    assert plan["phase_count"] == 4
    assert plan["command_count"] == 10
    configure_phase = next(item for item in plan["phases"] if item["id"] == "configure_production_scope")
    assert "KUBERNETES_OPS_RELEASE_ENVIRONMENT" in configure_phase["settings"]
    assert "KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF" in configure_phase["settings"]
    assert "KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF" in configure_phase["settings"]
    command_ids = {command["id"] for phase in plan["phases"] for command in phase.get("commands", [])}
    assert {
        "live_provider_smoke",
        "readonly_rbac_live",
        "external_evidence_bundle",
        "preflight_evidence",
        "release_evidence",
        "release_handoff",
    } <= command_ids
    assert backend_workstream["status"] in {"backend_incomplete", "backend_ready_production_blocked"}
    assert backend_workstream["core_backend_complete"] is False
    assert backend_workstream["safe_to_continue_frontend"] is False
    assert backend_workstream["next_backend_step"]["type"] == "backend"
    assert backend_workstream["remaining_backend_gap_count"] > 0
    assert backend_workstream["external_production_blocker_summary"]["primary_category"] == "production_scope"
    external_blocker_ids = {item["id"] for item in backend_workstream["external_production_blockers"]}
    assert {"production_scope", "release_artifact", "release_evidence"} <= external_blocker_ids
    assert (
        build_kubernetes_release_evidence_artifact_safety_report({"production_execution_plan": plan})["status"]
        == "ready"
    )
    assert (
        build_kubernetes_release_evidence_artifact_safety_report({"backend_workstream": backend_workstream})["status"]
        == "ready"
    )


def test_release_evidence_backend_workstream_requires_completion_audit_gate():
    evidence = {
        "production_ready": True,
        "ready_for_sidebar": True,
        "blockers": [],
        "readiness": {"production_gate": {"target_environment": "production"}},
        "release_scope": {
            "status": "ready",
            "target_environment": "production",
            "local_indicator_count": 0,
            "missing_required_references": [],
        },
        "artifact_safety": {"success": True, "status": "ready"},
        "completion_audit": {
            "core_backend_complete": True,
            "runtime_readiness_complete": True,
            "production_evidence_complete": False,
            "sidebar_enablement_complete": False,
            "core_backend_proofs": [
                {"id": "definition_of_done", "status": "ready", "complete": True},
                {"id": "normal_user_surface", "status": "ready", "complete": True},
            ],
            "runtime_missing_required_checks": [],
            "production_scope_readiness_checks": [],
            "production_evidence_checks": [{"id": "release_artifact", "complete": False, "detail": "missing"}],
        },
    }

    _attach_backend_workstream(evidence)

    assert evidence["backend_workstream"]["status"] == "backend_ready_production_blocked"
    assert evidence["backend_workstream"]["backend_complete"] is True
    assert evidence["backend_workstream"]["safe_to_continue_frontend"] is True
    assert evidence["backend_workstream"]["next_backend_step"]["type"] == "production_evidence"
