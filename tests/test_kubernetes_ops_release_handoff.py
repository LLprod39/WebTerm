from __future__ import annotations

import json
from io import StringIO

from django.core.management import call_command

from kubernetes_ops.services.release_handoff import (
    build_kubernetes_release_handoff,
    render_kubernetes_release_handoff_markdown,
)


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
                {"source": "provider_probe.provider_base_url", "value": "https://host.docker.internal:8443", "classification": "local"}
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
            "next_steps": ["Run release evidence in production with non-local Rancher/Devtron/MCP endpoints, approval ref and core evidence refs."],
        },
    }


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
    assert {"target_environment", "no_local_indicators", "select_production_environment", "production_scope"} <= external_blocker_ids
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
    production_action_evidence = next(item for item in handoff["release_proofs"] if item["id"] == "production_action_evidence")
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
    phase_commands = {
        command["id"]
        for phase in execution_plan["phases"]
        for command in phase.get("commands", [])
    }
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
    assert local_commands["local_demo_seed"]["command"] == "python manage.py seed_kubernetes_ops_demo --username admin --admin-write"
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
    assert any("port-forward additionally requires network policy evidence" in item for item in handoff["safety_guards"])


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


def test_kubernetes_release_handoff_markdown_is_operator_readable(tmp_path):
    evidence_path = tmp_path / "release.json"
    evidence_path.write_text(json.dumps(_blocked_evidence()), encoding="utf-8")

    markdown = render_kubernetes_release_handoff_markdown(build_kubernetes_release_handoff(evidence_path=evidence_path))

    assert markdown.startswith("# Kubernetes Ops Production Handoff")
    assert "- Status: blocked" in markdown
    assert "- Can enable sidebar: no" in markdown
    assert "- release_scope:local" in markdown
    assert "## Completion Audit" in markdown
    assert "- Core backend complete: yes" in markdown
    assert "- Production evidence complete: no" in markdown
    assert "- Remaining: production_evidence, sidebar_enablement" in markdown
    assert "## Backend Workstream" in markdown
    assert "- Status: backend_ready_production_blocked" in markdown
    assert "- Backend complete: yes" in markdown
    assert "- Core backend proofs: 7/7 (100%)" in markdown
    assert "- Remaining backend gaps: 0" in markdown
    assert "- External blocker primary category: production_scope" in markdown
    assert "- Safe to continue frontend: yes" in markdown
    assert "- Next step: select_production_environment" in markdown
    assert "## Operator Command Plan" in markdown
    assert "- Recommended next: select_production_environment (manual)" in markdown
    assert "- Local demo smoke (`local_demo_smoke`)" in markdown
    assert "`local_demo_fixture`: `python .tools/k8s-provider-fixture.py --host 127.0.0.1 --port 18090`" in markdown
    assert "`local_demo_seed`: `python manage.py seed_kubernetes_ops_demo --username admin --admin-write`" in markdown
    assert "## Production Execution Plan" in markdown
    assert "- Recommended next: Select the production release environment." in markdown
    assert "### Blocked Until" in markdown
    assert "`local_indicators`: local/test markers must be removed from evidence (8)" in markdown
    assert "### Phases" in markdown
    assert "Collect production prerequisite evidence" in markdown
    assert (
        "command: `python manage.py verify_kubernetes_ops_external_evidence_bundle "
        "--output artifacts/kubernetes_ops_external_evidence_bundle.json`"
    ) in markdown
    assert "Generate release artifacts" in markdown
    assert (
        "command: `python manage.py verify_kubernetes_ops_release --username <staff-user> "
        "--output artifacts/kubernetes_ops_release_evidence.json`"
    ) in markdown
    assert "## Release Proofs" in markdown
    assert "`post_review_retention`: ready - pending_review=True, deleted_events=1, post_review_redacted=True" in markdown
    assert "`external_evidence_bundle`: ready - refs_missing=0, artifacts=6/6, local_indicators=0" in markdown
    assert "`production_action_evidence`: ready - rollback_actions=5, native_checks=10, blocked_actions=11, blocked_contract=True" in markdown
    assert "`interactive_transport_evidence`: ready - enabled=0, blockers=0, dangerous_live_action_started=False" in markdown
    assert "`interactive_live_smoke`: ready - simulated_checks=4, live_contracts=4, required=False, production_live_provider_evidence=False" in markdown
    assert "`interactive_shell_streams`: ready - actions=2, recordings=2, events=4, provider_requests_safe=True" in markdown
    assert "`definition_of_done`: ready - ready=13/13, missing=0, missing_ids=none" in markdown
    assert (
        "`normal_user_surface`: ready - reader_external_links_visible=False, credential_scan=ready, surfaces=16, "
        "secret_ref_serialized=False, forbidden_values=False"
    ) in markdown
    assert "`action_controls`: ready - native_execution_enabled=False, approval_status=approved_external, rollback_plan=required, restart_template=ready, verification_plan=pending, auto_verification=verified, gitops=gitlab, git_write=False, cluster_mutation=False, restricted_write_gate=ready" in markdown
    assert "`secret_read_controls`: ready - default_redacted=True, list_metadata_only=True, denied_without_grant=True, denied_without_runtime_flag=True, allowed_all_gates=True" in markdown
    assert "`provider_secret_lifecycle`: ready - storage=managed, rotation_supported=True, plaintext_serialized=False, persistent_rows=False" in markdown
    assert "`audit_redaction`: ready - api_serializer_redacted=True, cluster_event_redacted=True, credentialed_url_sanitized=True, persistent_rows=False" in markdown
    assert "`python manage.py verify_kubernetes_ops_release --username <staff-user> --output artifacts/kubernetes_ops_release_evidence.json`" in markdown
    assert "`python manage.py render_kubernetes_ops_release_handoff --output artifacts/kubernetes_ops_release_handoff.md`" in markdown
    assert "`KUBERNETES_OPS_READY_FOR_SIDEBAR`" in markdown
    assert "`KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF`" in markdown
    assert "`KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF`" in markdown
    assert "`KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF`" in markdown
    assert "`KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF`" in markdown
    assert "`KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF`" in markdown
    assert "`KUBERNETES_ADMIN_INTERACTIVE_LIVE_SMOKE_EVIDENCE_REF`" in markdown
    assert "Provider-native interactive transports require recording gates" in markdown


def test_render_kubernetes_ops_release_handoff_command_outputs_summary(tmp_path):
    evidence_path = tmp_path / "release.json"
    output_path = tmp_path / "handoff.md"
    evidence_path.write_text(json.dumps(_blocked_evidence()), encoding="utf-8")
    stdout = StringIO()

    call_command(
        "render_kubernetes_ops_release_handoff",
        "--evidence",
        str(evidence_path),
        "--output",
        str(output_path),
        stdout=stdout,
    )

    assert output_path.exists()
    assert "# Kubernetes Ops Production Handoff" in output_path.read_text(encoding="utf-8")
    output = stdout.getvalue()
    assert "Wrote Kubernetes Ops release handoff:" in output
    assert "status=blocked" in output
    assert "can_enable_sidebar=False" in output
    assert "backend_workstream=backend_ready_production_blocked" in output
    assert "external_primary=production_scope" in output
