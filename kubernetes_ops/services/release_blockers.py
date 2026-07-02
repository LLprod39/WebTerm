from __future__ import annotations

from typing import Any

from kubernetes_ops.services.release_action_control_checks import action_controls_blocker
from kubernetes_ops.services.release_audit_redaction import audit_redaction_blocker
from kubernetes_ops.services.release_provider_secret_lifecycle import provider_secret_lifecycle_blocker
from kubernetes_ops.services.release_secret_read_controls import secret_read_controls_blocker


def build_kubernetes_release_blockers(
    *,
    readiness: dict[str, Any],
    provider_probes: list[dict[str, Any]],
    sync_dry_run: list[dict[str, Any]],
    studio_mcp: dict[str, Any],
    studio_diagnosis_draft: dict[str, Any],
    action_controls: dict[str, Any],
    admin_mode_safety: dict[str, Any],
    post_review_retention: dict[str, Any],
    external_evidence_bundle: dict[str, Any],
    interactive_transport_evidence: dict[str, Any],
    interactive_live_smoke: dict[str, Any],
    interactive_shell_streams: dict[str, Any],
    normal_user_surface: dict[str, Any],
    secret_read_controls: dict[str, Any],
    provider_secret_lifecycle: dict[str, Any],
    audit_redaction: dict[str, Any],
    production_action_evidence: dict[str, Any],
    readonly_rbac_live: dict[str, Any],
    preflight: dict[str, Any],
    release_scope: dict[str, Any],
    definition_of_done: dict[str, Any],
) -> list[str]:
    blockers = [f"readiness:{item.get('id')}={item.get('status')}" for item in readiness.get("checks", []) if item.get("status") != "ready"]
    blockers.extend(f"provider_probe:{item.get('provider_name') or item.get('reason')}={item.get('status')}" for item in provider_probes if not item.get("success"))
    blockers.extend(f"sync_dry_run:{item.get('provider_name') or item.get('reason')}=failed" for item in sync_dry_run if not item.get("success"))
    if not studio_mcp.get("success"):
        blockers.append(f"studio_mcp:{studio_mcp.get('status') or 'failed'}")
    if not studio_diagnosis_draft.get("success"):
        blockers.append(f"studio_diagnosis_draft:{studio_diagnosis_draft.get('status') or 'failed'}")
    _append_if(blockers, action_controls_blocker(action_controls))
    _append_if(blockers, _admin_mode_safety_blocker(admin_mode_safety))
    if not post_review_retention.get("success"):
        blockers.append(f"post_review_retention:{post_review_retention.get('status') or 'failed'}")
    if not external_evidence_bundle.get("success"):
        blockers.append(f"external_evidence_bundle:{external_evidence_bundle.get('status') or 'failed'}")
    if not interactive_transport_evidence.get("success"):
        blockers.append(f"interactive_transport_evidence:{interactive_transport_evidence.get('status') or 'failed'}")
    if not interactive_live_smoke.get("success"):
        blockers.append(f"interactive_live_smoke:{interactive_live_smoke.get('status') or 'failed'}")
    _append_if(blockers, _interactive_shell_streams_blocker(interactive_shell_streams))
    if not normal_user_surface.get("success"):
        blockers.append(f"normal_user_surface:{normal_user_surface.get('status') or 'failed'}")
    _append_if(blockers, secret_read_controls_blocker(secret_read_controls))
    _append_if(blockers, provider_secret_lifecycle_blocker(provider_secret_lifecycle))
    _append_if(blockers, audit_redaction_blocker(audit_redaction))
    if not production_action_evidence.get("success"):
        blockers.append(f"production_action_evidence:{production_action_evidence.get('status') or 'failed'}")
    if not readonly_rbac_live.get("success"):
        blockers.append(f"readonly_rbac_live:{readonly_rbac_live.get('status') or 'failed'}")
    if not preflight.get("success"):
        blockers.append(f"preflight:{preflight.get('status') or 'failed'}")
    if not release_scope.get("success"):
        blockers.append(f"release_scope:{release_scope.get('status') or 'failed'}")
    if not definition_of_done.get("success"):
        blockers.append(f"definition_of_done:{definition_of_done.get('status') or 'failed'}")
    return blockers


def _append_if(blockers: list[str], blocker: str) -> None:
    if blocker:
        blockers.append(blocker)


def _admin_mode_safety_blocker(evidence: dict[str, Any]) -> str:
    if not evidence.get("success"):
        return f"admin_mode_safety:{evidence.get('status') or 'failed'}"
    if evidence.get("provider_called"):
        return "admin_mode_safety:provider_called"
    if evidence.get("admin_actions_created"):
        return "admin_mode_safety:action_created"
    return ""


def _interactive_shell_streams_blocker(evidence: dict[str, Any]) -> str:
    if not evidence.get("success"):
        return f"interactive_shell_streams:{evidence.get('status') or 'failed'}"
    if not evidence.get("provider_requests_safe"):
        return "interactive_shell_streams:provider_request_unsafe"
    if evidence.get("actions_created") != 2:
        return "interactive_shell_streams:action_count_invalid"
    if evidence.get("recordings_created") != 2:
        return "interactive_shell_streams:recording_count_invalid"
    return ""
