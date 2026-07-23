from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

from kubernetes_ops.services.admin_interactive_transport_readiness import (
    PORT_FORWARD_NETWORK_POLICY_EVIDENCE_SETTING,
    RESTRICTED_CREDENTIAL_EVIDENCE_SETTING,
)
from kubernetes_ops.services.release_artifact import build_kubernetes_release_evidence_artifact_report
from kubernetes_ops.services.release_backend_workstream import (
    build_kubernetes_release_backend_workstream,
    build_kubernetes_release_backend_workstream_blocker_groups,
    can_enable_kubernetes_release_sidebar,
)
from kubernetes_ops.services.release_contract import build_kubernetes_release_contract
from kubernetes_ops.services.release_external_evidence_bundle import (
    IDENTITY_RUNTIME_EVIDENCE_SETTING,
    KUBERNETES_MCP_EVIDENCE_SETTING,
    LIVE_PROVIDER_EVIDENCE_SETTING,
    PRODUCTION_EVIDENCE_SETTING,
    PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_SETTING,
    PRODUCTION_ROLLBACK_EVIDENCE_SETTING,
    READONLY_RBAC_EVIDENCE_SETTING,
)
from kubernetes_ops.services.release_handoff_plan import (
    build_kubernetes_handoff_execution_plan,
    render_kubernetes_handoff_execution_plan_markdown,
)
from kubernetes_ops.services.release_handoff_workstream import (
    backend_workstream_primary_blocker_category,
    safe_release_handoff_backend_workstream,
)
from kubernetes_ops.services.release_interactive_live_smoke import INTERACTIVE_LIVE_SMOKE_EVIDENCE_SETTING
from kubernetes_ops.services.release_operator_command_plan import (
    build_kubernetes_handoff_operator_command_plan,
    build_kubernetes_handoff_production_checklist,
    render_kubernetes_operator_command_plan_markdown,
)
from kubernetes_ops.services.release_summary import build_kubernetes_release_summary

HANDOFF_SCHEMA_VERSION = "kubernetes_ops.release_handoff.v1"


def build_kubernetes_release_handoff(*, evidence_path: Path | None = None) -> dict[str, Any]:
    path = evidence_path or Path(settings.BASE_DIR) / "artifacts" / "kubernetes_ops_release_evidence.json"
    evidence = _load_evidence(path)
    artifact_report = (
        _artifact_report_for_explicit_path(path, evidence)
        if evidence_path is not None
        else build_kubernetes_release_evidence_artifact_report(require_ready=False)
    )

    release_summary = _summary(evidence)
    release_scope = evidence.get("release_scope") if isinstance(evidence.get("release_scope"), dict) else {}
    blockers = [str(item) for item in evidence.get("blockers") or release_summary.get("top_blockers") or []]
    production_ready = bool(evidence.get("production_ready"))
    ready_for_sidebar = bool(evidence.get("ready_for_sidebar"))
    completion_audit = _completion_audit(evidence, release_summary)
    blocker_groups = build_kubernetes_release_backend_workstream_blocker_groups(evidence)
    production_evidence_checklist = build_kubernetes_handoff_production_checklist(release_scope)
    can_enable_sidebar = can_enable_kubernetes_release_sidebar(
        production_ready=production_ready,
        ready_for_sidebar=ready_for_sidebar,
        completion_audit=completion_audit,
        artifact_ready=artifact_report.get("status") == "ready",
        release_scope_ready=release_scope.get("status") == "ready",
    )

    handoff = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        "status": "ready" if can_enable_sidebar else "blocked",
        "can_enable_sidebar": can_enable_sidebar,
        "evidence": {
            "path": str(path),
            "loaded": bool(evidence),
            "generated_at": str(evidence.get("generated_at") or ""),
            "schema_version": str(evidence.get("schema_version") or ""),
            "artifact_status": str(artifact_report.get("status") or ""),
            "artifact_errors": list(artifact_report.get("errors") or []),
            "production_ready": production_ready,
            "ready_for_sidebar": ready_for_sidebar,
        },
        "release_scope": {
            "status": str(release_scope.get("status") or ""),
            "target_environment": str(release_scope.get("target_environment") or ""),
            "approval_ref_present": bool(release_scope.get("approval_ref_present")),
            "core_evidence_ready": bool(release_scope.get("core_evidence_ready")),
            "missing_reference_count": int(release_scope.get("missing_reference_count") or 0),
            "missing_required_references": list(release_scope.get("missing_required_references") or []),
            "local_indicator_count": int(release_scope.get("local_indicator_count") or 0),
            "reason": str(release_scope.get("reason") or ""),
        },
        "blockers": blockers,
        "completion_audit": completion_audit,
        "backend_workstream": _backend_workstream(
            completion_audit=completion_audit,
            blocker_groups=blocker_groups,
            production_evidence_checklist=production_evidence_checklist,
            can_enable_sidebar=can_enable_sidebar,
        ),
        "release_proofs": _release_proofs(evidence),
        "next_steps": list(release_summary.get("next_steps") or _default_next_steps(evidence)),
        "required_commands": build_kubernetes_release_contract()["required_preflight_commands"],
        "operator_command_plan": build_kubernetes_handoff_operator_command_plan(
            production_evidence_checklist=production_evidence_checklist,
            blocker_groups=blocker_groups,
            can_enable_sidebar=can_enable_sidebar,
        ),
        "production_env_flags": [
            {"name": "KUBERNETES_OPS_RELEASE_ENVIRONMENT", "expected": "production"},
            {"name": "KUBERNETES_OPS_PRODUCTION_APPROVAL_REF", "expected": "<change-or-approval-id>"},
            {"name": PRODUCTION_EVIDENCE_SETTING, "expected": "<operator-reviewed production evidence bundle ref>"},
            {"name": IDENTITY_RUNTIME_EVIDENCE_SETTING, "expected": "<production SSO/Keycloak runtime evidence ref>"},
            {
                "name": LIVE_PROVIDER_EVIDENCE_SETTING,
                "expected": "<production Rancher/Fleet/Devtron live provider evidence ref>",
            },
            {"name": READONLY_RBAC_EVIDENCE_SETTING, "expected": "<production read-only RBAC can-i evidence ref>"},
            {
                "name": KUBERNETES_MCP_EVIDENCE_SETTING,
                "expected": "<production Kubernetes MCP READ_ONLY smoke evidence ref>",
            },
            {"name": PRODUCTION_ROLLBACK_EVIDENCE_SETTING, "expected": "<production rollback drill evidence ref>"},
            {
                "name": PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_SETTING,
                "expected": "<production native verification evidence ref>",
            },
            {"name": "KUBERNETES_OPS_READY_FOR_SIDEBAR", "expected": "true only after production_ready=true"},
            {"name": "KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS", "expected": "86400 or stricter"},
            {
                "name": RESTRICTED_CREDENTIAL_EVIDENCE_SETTING,
                "expected": "<reviewed restricted credential/RBAC proof before any production interactive transport>",
            },
            {
                "name": PORT_FORWARD_NETWORK_POLICY_EVIDENCE_SETTING,
                "expected": "<reviewed network policy/egress proof before production port-forward tunnel>",
            },
            {
                "name": INTERACTIVE_LIVE_SMOKE_EVIDENCE_SETTING,
                "expected": "<reviewed production live-smoke proof before enabling production interactive streams>",
            },
        ],
        "external_evidence_required": [
            "Non-local Rancher/Fleet/Devtron provider endpoints and successful live probes.",
            "Fresh successful provider sync dry-run and running sync worker.",
            "Live read-only Kubernetes RBAC can-i proof on the target cluster.",
            "External evidence bundle with reviewed production refs for approval, providers, RBAC, SSO, MCP, rollback, native verification and interactive gates.",
            "Production rollback drill evidence for restart/scale/apply/patch/delete request classes before sidebar enablement.",
            "Production native verification evidence proving post-action read-only checks close requests without weak or stale evidence.",
            "Fresh interactive transport prerequisite artifact proving recording, restricted credential and provider-contract gates.",
            "Fresh interactive live-smoke artifact proving provider opener contracts and external production live-stream evidence refs.",
            "Fresh interactive production controls artifact proving restricted credential, recording, provider-contract and port-forward network-policy contracts.",
            "Owned production Kubernetes MCP binding with READ_ONLY diagnosis smoke.",
            "Production SSO/Keycloak runtime gate and explicit approval reference.",
            "Reviewed restricted credential evidence before production exec, port-forward, cluster terminal, or node debug transport.",
            "Reviewed port-forward network policy evidence, exact target allowlist, protected namespace denylist, and short TTL before production port-forward tunnel.",
        ],
        "safety_guards": [
            "Native exec/attach/port-forward/apply/delete/scale/restart remain disabled.",
            "Provider-native interactive transports require recording gates plus restricted credential evidence in production.",
            "Provider-native port-forward additionally requires network policy evidence and an exact target allowlist in production.",
            "Provider secrets stay behind managed/external secret references.",
            "Release evidence must pass artifact safety self-scan before sidebar enablement.",
        ],
    }
    handoff["production_execution_plan"] = build_kubernetes_handoff_execution_plan(handoff)
    return handoff


def render_kubernetes_release_handoff_markdown(handoff: dict[str, Any]) -> str:
    evidence = handoff.get("evidence") if isinstance(handoff.get("evidence"), dict) else {}
    release_scope = handoff.get("release_scope") if isinstance(handoff.get("release_scope"), dict) else {}
    blockers = [str(item) for item in handoff.get("blockers") or []]
    next_steps = [str(item) for item in handoff.get("next_steps") or []]
    completion_audit = handoff.get("completion_audit") if isinstance(handoff.get("completion_audit"), dict) else {}
    backend_workstream = (
        handoff.get("backend_workstream") if isinstance(handoff.get("backend_workstream"), dict) else {}
    )
    proofs = handoff.get("release_proofs") if isinstance(handoff.get("release_proofs"), list) else []
    operator_command_plan = (
        handoff.get("operator_command_plan") if isinstance(handoff.get("operator_command_plan"), dict) else {}
    )
    commands = handoff.get("required_commands") if isinstance(handoff.get("required_commands"), list) else []
    env_flags = handoff.get("production_env_flags") if isinstance(handoff.get("production_env_flags"), list) else []
    external = [str(item) for item in handoff.get("external_evidence_required") or []]
    guards = [str(item) for item in handoff.get("safety_guards") or []]

    lines = [
        "# Kubernetes Ops Production Handoff",
        "",
        f"- Status: {handoff.get('status') or 'unknown'}",
        f"- Can enable sidebar: {'yes' if handoff.get('can_enable_sidebar') else 'no'}",
        f"- Evidence: {evidence.get('path') or ''}",
        f"- Evidence generated at: {evidence.get('generated_at') or 'missing'}",
        f"- Release scope: {release_scope.get('status') or 'missing'} ({release_scope.get('reason') or 'no reason'})",
        f"- Missing production refs: {int(release_scope.get('missing_reference_count') or 0)}",
        "",
        "## Current Blockers",
    ]
    lines.extend([f"- {item}" for item in blockers] or ["- none"])
    lines.extend(
        [
            "",
            "## Completion Audit",
            f"- Core backend complete: {_yes_no(completion_audit.get('core_backend_complete'))}",
            f"- Runtime readiness complete: {_yes_no(completion_audit.get('runtime_readiness_complete'))}",
            f"- Production evidence complete: {_yes_no(completion_audit.get('production_evidence_complete'))}",
            f"- Sidebar enablement complete: {_yes_no(completion_audit.get('sidebar_enablement_complete'))}",
            f"- Remaining: {', '.join(str(item) for item in completion_audit.get('remaining') or []) or 'none'}",
            "",
            "## Backend Workstream",
            f"- Status: {backend_workstream.get('status') or 'unknown'}",
            f"- Backend complete: {_yes_no(backend_workstream.get('backend_complete'))}",
            f"- Core backend proofs: {int(backend_workstream.get('core_backend_proof_ready_count') or 0)}/{int(backend_workstream.get('core_backend_proof_count') or 0)} ({backend_workstream.get('core_backend_percent') if backend_workstream.get('core_backend_percent') is not None else 'n/a'}%)",
            f"- Remaining backend gaps: {int(backend_workstream.get('remaining_backend_gap_count') or 0)}",
            f"- External production blockers: {int(backend_workstream.get('external_production_blocker_count') or 0)}",
            f"- External blocker primary category: {backend_workstream_primary_blocker_category(backend_workstream)}",
            f"- Safe to continue frontend: {_yes_no(backend_workstream.get('safe_to_continue_frontend'))}",
            f"- Next step: {((backend_workstream.get('next_backend_step') if isinstance(backend_workstream.get('next_backend_step'), dict) else {}) or {}).get('id') or 'unknown'}",
            "",
            "## Release Proofs",
        ]
    )
    for item in proofs:
        if not isinstance(item, dict):
            continue
        detail = str(item.get("detail") or "").strip()
        suffix = f" - {detail}" if detail else ""
        lines.append(f"- `{item.get('id')}`: {item.get('status')}{suffix}")
    if not proofs:
        lines.append("- none")
    lines.extend(["", "## Next Steps"])
    lines.extend(
        [f"{index}. {item}" for index, item in enumerate(next_steps, start=1)]
        or ["1. Inspect release evidence and rerun release checks."]
    )
    lines.extend([""])
    lines.extend(render_kubernetes_operator_command_plan_markdown(operator_command_plan))
    lines.extend([""])
    lines.extend(render_kubernetes_handoff_execution_plan_markdown(handoff.get("production_execution_plan") or {}))
    lines.extend(["", "## Required Commands"])
    for item in commands:
        if not isinstance(item, dict):
            continue
        lines.append(f"- `{item.get('command')}`")
    lines.extend(["", "## Production Env Flags"])
    for item in env_flags:
        if not isinstance(item, dict):
            continue
        lines.append(f"- `{item.get('name')}`: {item.get('expected')}")
    missing_refs = (
        release_scope.get("missing_required_references")
        if isinstance(release_scope.get("missing_required_references"), list)
        else []
    )
    lines.extend(["", "## Missing Production Refs"])
    for item in missing_refs:
        if not isinstance(item, dict):
            continue
        lines.append(f"- `{item.get('setting')}`: {item.get('expected')}")
    if not missing_refs:
        lines.append("- none")
    lines.extend(["", "## External Evidence Required"])
    lines.extend([f"- {item}" for item in external] or ["- none"])
    lines.extend(["", "## Safety Guards"])
    lines.extend([f"- {item}" for item in guards] or ["- none"])
    return "\n".join(lines).rstrip() + "\n"


def _yes_no(value: object) -> str:
    return "yes" if bool(value) else "no"


def _load_evidence(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _summary(evidence: dict[str, Any]) -> dict[str, Any]:
    summary = evidence.get("release_summary") if isinstance(evidence.get("release_summary"), dict) else {}
    if summary and isinstance(summary.get("completion_audit"), dict):
        return summary
    return build_kubernetes_release_summary(evidence)


def _completion_audit(evidence: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    root_audit = evidence.get("completion_audit") if isinstance(evidence.get("completion_audit"), dict) else {}
    if root_audit:
        return root_audit
    return summary.get("completion_audit") if isinstance(summary.get("completion_audit"), dict) else {}


def _backend_workstream(
    *,
    completion_audit: dict[str, Any],
    blocker_groups: list[dict[str, Any]],
    production_evidence_checklist: dict[str, Any],
    can_enable_sidebar: bool,
) -> dict[str, Any]:
    return safe_release_handoff_backend_workstream(
        build_kubernetes_release_backend_workstream(
            completion_audit=completion_audit,
            blocker_groups=blocker_groups,
            production_evidence_checklist=production_evidence_checklist,
            can_enable_sidebar=can_enable_sidebar,
        )
    )


def _default_next_steps(evidence: dict[str, Any]) -> list[str]:
    if not evidence:
        return ["Generate a fresh release evidence artifact before production handoff."]
    return ["Inspect release evidence and rerun verify_kubernetes_ops_release after fixing blockers."]


def _release_proofs(evidence: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _proof("action_controls", evidence.get("action_controls")),
        _proof("admin_mode_safety", evidence.get("admin_mode_safety")),
        _proof("post_review_retention", evidence.get("post_review_retention")),
        _proof("external_evidence_bundle", evidence.get("external_evidence_bundle")),
        _proof("production_action_evidence", evidence.get("production_action_evidence")),
        _proof("interactive_transport_evidence", evidence.get("interactive_transport_evidence")),
        _proof("interactive_live_smoke", evidence.get("interactive_live_smoke")),
        _proof("interactive_shell_streams", evidence.get("interactive_shell_streams")),
        _proof("definition_of_done", evidence.get("definition_of_done")),
        _proof("normal_user_surface", evidence.get("normal_user_surface")),
        _proof("secret_read_controls", evidence.get("secret_read_controls")),
        _proof("provider_secret_lifecycle", evidence.get("provider_secret_lifecycle")),
        _proof("audit_redaction", evidence.get("audit_redaction")),
    ]


def _proof(proof_id: str, payload: object) -> dict[str, str]:
    data = payload if isinstance(payload, dict) else {}
    return {
        "id": proof_id,
        "status": str(data.get("status") or "missing"),
        "success": str(bool(data.get("success"))).lower(),
        "detail": _proof_detail(proof_id, data),
    }


def _proof_detail(proof_id: str, data: dict[str, Any]) -> str:
    if proof_id == "interactive_shell_streams":
        return (
            f"actions={int(data.get('actions_created') or 0)}, "
            f"recordings={int(data.get('recordings_created') or 0)}, "
            f"events={int(data.get('recording_events_created') or 0)}, "
            f"provider_requests_safe={bool(data.get('provider_requests_safe'))}"
        )
    if proof_id == "interactive_transport_evidence":
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        return (
            f"enabled={int(summary.get('enabled_transport_count') or 0)}, "
            f"blockers={int(summary.get('blocker_count') or 0)}, "
            f"dangerous_live_action_started=False"
        )
    if proof_id == "external_evidence_bundle":
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        return (
            f"refs_missing={int(summary.get('missing_required_ref_count') or 0)}, "
            f"artifacts={int(summary.get('artifact_ready_count') or 0)}/{int(summary.get('artifact_check_count') or 0)}, "
            f"local_indicators={int(summary.get('local_indicator_count') or 0)}"
        )
    if proof_id == "production_action_evidence":
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        coverage = data.get("coverage") if isinstance(data.get("coverage"), dict) else {}
        return (
            f"rollback_actions={int(summary.get('rollback_action_class_count') or 0)}, "
            f"native_checks={int(summary.get('native_verification_check_count') or 0)}, "
            f"blocked_actions={int(summary.get('blocked_action_class_count') or 0)}, "
            f"blocked_contract={bool(coverage.get('blocked_action_contract_complete'))}"
        )
    if proof_id == "interactive_live_smoke":
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        return (
            f"simulated_checks={int(summary.get('simulated_check_count') or 0)}, "
            f"live_contracts={int(summary.get('live_transport_contract_count') or 0)}, "
            f"required={bool(summary.get('live_smoke_required'))}, "
            f"production_live_provider_evidence={bool(summary.get('production_live_provider_evidence'))}"
        )
    if proof_id == "admin_mode_safety":
        return f"provider_called={bool(data.get('provider_called'))}, admin_actions_created={int(data.get('admin_actions_created') or 0)}"
    if proof_id == "post_review_retention":
        checks = data.get("checks") if isinstance(data.get("checks"), dict) else {}
        return (
            f"pending_review={bool(checks.get('pending_post_review_detected'))}, "
            f"deleted_events={int(checks.get('retention_apply_deleted_events') or 0)}, "
            f"post_review_redacted={bool(checks.get('post_review_redacted'))}"
        )
    if proof_id == "action_controls":
        return (
            f"native_execution_enabled={bool(data.get('native_execution_enabled'))}, "
            f"approval_status={data.get('approval_status') or ''}, "
            f"rollback_plan={data.get('rollback_plan_status') or 'missing'}, "
            f"restart_template={data.get('production_restart_template_status') or 'missing'}, "
            f"verification_plan={data.get('native_verification_plan_status') or 'missing'}, "
            f"auto_verification={data.get('native_verification_auto_status') or 'missing'}, "
            f"gitops={data.get('gitops_provider') or 'missing'}, "
            f"git_write={bool(data.get('gitops_write_performed'))}, "
            f"cluster_mutation={bool(data.get('gitops_cluster_mutation_performed'))}, "
            f"restricted_write_gate={'ready' if data.get('restricted_write_gate_allows_with_ref') else 'missing'}"
        )
    if proof_id == "definition_of_done":
        missing_ids = data.get("missing_ids") if isinstance(data.get("missing_ids"), list) else []
        missing_preview = ",".join(str(item) for item in missing_ids[:4])
        return (
            f"ready={int(data.get('ready') or 0)}/{int(data.get('total') or 0)}, "
            f"missing={int(data.get('missing') or 0)}, "
            f"missing_ids={missing_preview or 'none'}"
        )
    if proof_id == "normal_user_surface":
        policy = (
            data.get("reader_external_link_policy") if isinstance(data.get("reader_external_link_policy"), dict) else {}
        )
        credential_scan = (
            data.get("frontend_response_credential_scan")
            if isinstance(data.get("frontend_response_credential_scan"), dict)
            else {}
        )
        scan_detail = (
            f", credential_scan={credential_scan.get('status') or 'missing'}, "
            f"surfaces={int(credential_scan.get('surfaces_checked') or 0)}, "
            f"secret_ref_serialized={bool(credential_scan.get('provider_secret_reference_serialized'))}, "
            f"forbidden_values={bool(credential_scan.get('forbidden_values_found'))}"
        )
        if policy:
            return f"reader_external_links_visible={bool(policy.get('visible'))}{scan_detail}"
        reader = data.get("reader") if isinstance(data.get("reader"), dict) else {}
        return f"reader_can_audit_deeplinks={reader.get('can_audit_deeplinks') if reader else ''}{scan_detail}"
    if proof_id == "secret_read_controls":
        return (
            f"default_redacted={bool(data.get('default_redacted'))}, "
            f"list_metadata_only={bool(data.get('secret_list_metadata_only'))}, "
            f"denied_without_grant={bool(data.get('secret_read_rejected_without_grant'))}, "
            f"denied_without_runtime_flag={bool(data.get('secret_read_rejected_without_runtime_flag'))}, "
            f"allowed_all_gates={bool(data.get('secret_read_allowed_with_all_gates'))}"
        )
    if proof_id == "provider_secret_lifecycle":
        checks = data.get("checks") if isinstance(data.get("checks"), dict) else {}
        return (
            f"storage={data.get('storage_mode') or 'missing'}, "
            f"rotation_supported={bool(data.get('rotation_supported'))}, "
            f"plaintext_serialized={not bool(checks.get('plaintext_not_serialized'))}, "
            f"persistent_rows={bool(data.get('persistent_rows'))}"
        )
    if proof_id == "audit_redaction":
        checks = data.get("checks") if isinstance(data.get("checks"), dict) else {}
        return (
            f"api_serializer_redacted={bool(checks.get('api_serializer_raw_values_absent'))}, "
            f"cluster_event_redacted={bool(checks.get('cluster_event_raw_values_absent'))}, "
            f"credentialed_url_sanitized={bool(checks.get('credentialed_url_sanitized'))}, "
            f"persistent_rows={not bool(checks.get('rollback_removed_audit_event') and checks.get('rollback_removed_cluster'))}"
        )
    return ""


def _artifact_report_for_explicit_path(path: Path, evidence: dict[str, Any]) -> dict[str, Any]:
    if not evidence:
        return {"status": "missing", "errors": ["release evidence artifact is missing or unreadable"]}
    artifact_safety = evidence.get("artifact_safety") if isinstance(evidence.get("artifact_safety"), dict) else {}
    errors: list[str] = []
    if artifact_safety.get("success") is not True:
        errors.append(f"artifact_safety is {artifact_safety.get('status') or 'missing'}")
    return {
        "status": "ready" if not errors else "manual",
        "path": str(path),
        "errors": errors,
    }
