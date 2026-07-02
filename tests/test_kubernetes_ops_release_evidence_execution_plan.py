from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from kubernetes_ops.services.release_artifact_safety import build_kubernetes_release_evidence_artifact_safety_report
from kubernetes_ops.services.release_evidence import build_kubernetes_release_evidence


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
    assert build_kubernetes_release_evidence_artifact_safety_report({"production_execution_plan": plan})["status"] == "ready"
