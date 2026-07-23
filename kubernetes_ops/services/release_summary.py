from __future__ import annotations

from typing import Any

from kubernetes_ops.services.release_completion_audit import build_kubernetes_release_completion_audit


def build_kubernetes_release_summary(evidence: dict[str, Any]) -> dict[str, Any]:
    blockers = [str(item) for item in evidence.get("blockers") or []]
    preflight = evidence.get("preflight") if isinstance(evidence.get("preflight"), dict) else {}
    release_scope = evidence.get("release_scope") if isinstance(evidence.get("release_scope"), dict) else {}
    artifact_safety = evidence.get("artifact_safety") if isinstance(evidence.get("artifact_safety"), dict) else {}
    readiness = evidence.get("readiness") if isinstance(evidence.get("readiness"), dict) else {}
    normal_user_surface = (
        evidence.get("normal_user_surface") if isinstance(evidence.get("normal_user_surface"), dict) else {}
    )
    definition_of_done = (
        evidence.get("definition_of_done") if isinstance(evidence.get("definition_of_done"), dict) else {}
    )
    frontend_scan = (
        normal_user_surface.get("frontend_response_credential_scan")
        if isinstance(normal_user_surface.get("frontend_response_credential_scan"), dict)
        else {}
    )
    secret_read_controls = (
        evidence.get("secret_read_controls") if isinstance(evidence.get("secret_read_controls"), dict) else {}
    )
    provider_secret_lifecycle = (
        evidence.get("provider_secret_lifecycle") if isinstance(evidence.get("provider_secret_lifecycle"), dict) else {}
    )
    audit_redaction = evidence.get("audit_redaction") if isinstance(evidence.get("audit_redaction"), dict) else {}
    production_action_evidence = (
        evidence.get("production_action_evidence")
        if isinstance(evidence.get("production_action_evidence"), dict)
        else {}
    )
    production_action_summary = (
        production_action_evidence.get("summary") if isinstance(production_action_evidence.get("summary"), dict) else {}
    )
    summary = {
        "status": "ready" if evidence.get("production_ready") else "blocked",
        "production_ready": bool(evidence.get("production_ready")),
        "ready_for_sidebar": bool(evidence.get("ready_for_sidebar")),
        "blocker_count": len(blockers),
        "top_blockers": blockers[:8],
        "next_steps": _release_next_steps(blockers),
        "release_scope_status": str(release_scope.get("status") or ""),
        "release_scope_approval_ref": str(release_scope.get("approval_ref") or ""),
        "preflight_status": str(preflight.get("status") or ""),
        "preflight_age_seconds": preflight.get("age_seconds"),
        "preflight_max_age_seconds": preflight.get("max_age_seconds"),
        "artifact_safety_status": str(artifact_safety.get("status") or ""),
        "artifact_safety_issue_count": int(artifact_safety.get("issue_count") or 0),
        "normal_user_surface_status": str(normal_user_surface.get("status") or ""),
        "definition_of_done_status": str(definition_of_done.get("status") or ""),
        "definition_of_done_ready": int(definition_of_done.get("ready") or 0),
        "definition_of_done_total": int(definition_of_done.get("total") or 0),
        "frontend_payload_scan_status": str(frontend_scan.get("status") or ""),
        "sensitive_value_controls_status": str(secret_read_controls.get("status") or ""),
        "provider_lifecycle_status": str(provider_secret_lifecycle.get("status") or ""),
        "audit_redaction_status": str(audit_redaction.get("status") or ""),
        "production_action_evidence_status": str(production_action_evidence.get("status") or ""),
        "production_action_blocked_action_class_count": int(
            production_action_summary.get("blocked_action_class_count") or 0
        ),
        "readiness_summary": readiness.get("summary") or {},
    }
    readiness_checks = readiness.get("checks") if isinstance(readiness.get("checks"), list) else []
    summary["completion_audit"] = build_kubernetes_release_completion_audit(
        artifact_summary=summary,
        readiness_checks=readiness_checks,
        production_gate=release_scope,
        artifact_report={"status": "ready"},
        can_enable_sidebar=bool(evidence.get("production_ready") and evidence.get("ready_for_sidebar")),
    )
    return summary


def _release_next_steps(blockers: list[str]) -> list[str]:
    if not blockers:
        return ["Set KUBERNETES_OPS_READY_FOR_SIDEBAR=true only in the approved production environment."]
    steps: list[str] = []
    if any(item.startswith("release_scope:") for item in blockers):
        steps.append(
            "Run release evidence in production with non-local Rancher/Devtron/MCP endpoints, approval ref and core evidence refs."
        )
    if any(item.startswith("production_action_evidence:") for item in blockers):
        steps.append(
            "Regenerate production action evidence and fix rollback/native verification/blocked-action contracts."
        )
    if any(item.startswith("definition_of_done:") for item in blockers):
        steps.append("Close the Kubernetes Admin Mode Definition of Done proof before production sidebar enablement.")
    if any(item.startswith("readiness:identity_runtime") for item in blockers):
        steps.append("Configure production SSO/Keycloak runtime and trusted identity headers.")
    if any(item.startswith("readiness:provider_health") for item in blockers):
        steps.append("Fix provider sync health and wait for a fresh successful sync cycle.")
    if any(item.startswith("provider_probe:") for item in blockers):
        steps.append("Fix live Rancher/Devtron provider probes before approval.")
    if any(item.startswith("sync_dry_run:") for item in blockers):
        steps.append("Fix provider dry-run sync errors before approval.")
    if any(item.startswith("studio_mcp:") for item in blockers):
        steps.append("Fix the owned production Kubernetes MCP binding and READ_ONLY smoke policy.")
    if any(item.startswith("studio_diagnosis_draft:") for item in blockers):
        steps.append("Fix the read-only Studio Kubernetes diagnosis draft proof before release.")
    if any(item.startswith("readonly_rbac_live:") for item in blockers):
        steps.append("Run and pass the live read-only RBAC can-i proof on the target cluster.")
    if any(item.startswith("preflight:") for item in blockers):
        steps.append("Regenerate a fresh preflight artifact and fix failed required commands.")
    if any(item.startswith("interactive_transport_evidence:") for item in blockers):
        steps.append(
            "Run verify_kubernetes_ops_interactive_transport_evidence and fix recording, credential, network-policy or provider-contract prerequisites."
        )
    if any(item.startswith("interactive_live_smoke:") for item in blockers):
        steps.append(
            "Run verify_kubernetes_ops_interactive_live_smoke and provide production live-smoke evidence refs before enabling interactive streams."
        )
    if any(item.startswith("artifact_safety:") for item in blockers):
        steps.append("Remove raw secrets or credentialed URLs from release evidence output.")
    if any(item.startswith("action_controls:") for item in blockers):
        steps.append("Fix approval/request lifecycle safety proof before enabling any sidebar release.")
    if any(item.startswith("post_review_retention:") for item in blockers):
        steps.append("Fix Admin action post-review and recording retention cleanup proof before production release.")
    if any(item.startswith("external_evidence_bundle:") for item in blockers):
        steps.append(
            "Run verify_kubernetes_ops_external_evidence_bundle and provide production approval, provider, RBAC, SSO, MCP, rollback, native verification and interactive evidence refs."
        )
    if any(item.startswith("normal_user_surface:") for item in blockers):
        steps.append(
            "Fix WebTerm-only normal-user API proof: hide external links/provider config and keep fallback deeplink audit staff-only."
        )
    if any(item.startswith("secret_read_controls:") for item in blockers):
        steps.append("Fix Secret value redaction and gated reveal proof before production release.")
    if any(item.startswith("audit_redaction:") for item in blockers):
        steps.append("Fix Kubernetes audit/log redaction proof before production release.")
    if any(item.startswith("readiness:admin_interactive_transport") for item in blockers):
        steps.append(
            "Disable production interactive transports or set recording gates plus restricted credential evidence; for port-forward also provide network-policy evidence and an exact target allowlist."
        )
    if not steps:
        steps.append("Inspect the top blockers and rerun verify_kubernetes_ops_release after fixing them.")
    return steps[:8]
