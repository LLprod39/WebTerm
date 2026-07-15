from __future__ import annotations

from typing import Any

PREREQUISITE_COMMAND_IDS = (
    "live_provider_smoke",
    "readonly_rbac_live",
    "interactive_transport_evidence",
    "interactive_live_smoke",
    "interactive_production_controls",
    "production_action_evidence",
    "external_evidence_bundle",
)

RELEASE_COMMAND_IDS = ("preflight_evidence", "preflight", "release_evidence", "release_handoff")
COMMAND_ID_ALIASES = {"preflight": "preflight_evidence", "preflight_evidence": "preflight_evidence"}

DEFAULT_PRODUCTION_SETTINGS = (
    "KUBERNETES_OPS_RELEASE_ENVIRONMENT",
    "KUBERNETES_OPS_PRODUCTION_APPROVAL_REF",
    "KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF",
    "KUBERNETES_OPS_IDENTITY_RUNTIME_EVIDENCE_REF",
    "KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF",
    "KUBERNETES_OPS_READONLY_RBAC_EVIDENCE_REF",
    "KUBERNETES_OPS_KUBERNETES_MCP_EVIDENCE_REF",
    "KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF",
    "KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF",
    "KUBERNETES_OPS_READY_FOR_SIDEBAR",
    "KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS",
    "KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF",
    "KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF",
    "KUBERNETES_ADMIN_INTERACTIVE_LIVE_SMOKE_EVIDENCE_REF",
)


def build_kubernetes_handoff_execution_plan(handoff: dict[str, Any]) -> dict[str, Any]:
    release_scope = handoff.get("release_scope") if isinstance(handoff.get("release_scope"), dict) else {}
    evidence = handoff.get("evidence") if isinstance(handoff.get("evidence"), dict) else {}
    completion = handoff.get("completion_audit") if isinstance(handoff.get("completion_audit"), dict) else {}
    commands = _command_map(handoff.get("required_commands"))
    requested_can_enable_sidebar = bool(handoff.get("can_enable_sidebar"))
    blocked_until = _blocked_until(release_scope=release_scope, evidence=evidence, completion=completion)
    can_enable_sidebar = requested_can_enable_sidebar and not blocked_until
    recommended_next = _recommended_next(
        can_enable_sidebar=can_enable_sidebar,
        release_scope=release_scope,
        evidence=evidence,
        blocked_until=blocked_until,
    )
    phases = [
        _manual_phase(
            "configure_production_scope",
            "Configure production scope",
            [
                "Set KUBERNETES_OPS_RELEASE_ENVIRONMENT=production only for the real target.",
                "Set approval and evidence reference env vars; do not paste provider tokens.",
            ],
            _production_settings(handoff),
        ),
        _command_phase(
            "collect_production_evidence",
            "Collect production prerequisite evidence",
            commands,
            PREREQUISITE_COMMAND_IDS,
        ),
        _command_phase(
            "generate_release_artifacts",
            "Generate release artifacts",
            commands,
            RELEASE_COMMAND_IDS,
        ),
        _manual_phase(
            "enable_sidebar_after_green",
            "Enable sidebar after green handoff",
            ["Set KUBERNETES_OPS_READY_FOR_SIDEBAR=true only after production_ready=true and approved operator change."],
            ["KUBERNETES_OPS_READY_FOR_SIDEBAR"],
        ),
    ]
    return {
        "status": "ready" if can_enable_sidebar else "blocked",
        "can_enable_sidebar": can_enable_sidebar,
        "recommended_next": recommended_next,
        "blocked_until": blocked_until,
        "blocked_until_count": len(blocked_until),
        "phases": phases,
        "phase_count": len(phases),
        "command_count": sum(len(phase.get("commands") or []) for phase in phases),
    }


def build_kubernetes_release_evidence_execution_plan(evidence: dict[str, Any]) -> dict[str, Any]:
    release_scope = evidence.get("release_scope") if isinstance(evidence.get("release_scope"), dict) else {}
    artifact_safety = evidence.get("artifact_safety") if isinstance(evidence.get("artifact_safety"), dict) else {}
    release_contract = evidence.get("release_contract") if isinstance(evidence.get("release_contract"), dict) else {}
    commands = release_contract.get("required_preflight_commands") if isinstance(release_contract.get("required_preflight_commands"), list) else []
    completion = evidence.get("completion_audit") if isinstance(evidence.get("completion_audit"), dict) else {}
    can_enable_sidebar = (
        bool(evidence.get("production_ready"))
        and bool(evidence.get("ready_for_sidebar"))
        and str(artifact_safety.get("status") or "") == "ready"
        and str(release_scope.get("status") or "") == "ready"
    )
    return build_kubernetes_handoff_execution_plan(
        {
            "can_enable_sidebar": can_enable_sidebar,
            "release_scope": {
                "status": str(release_scope.get("status") or ""),
                "target_environment": str(release_scope.get("target_environment") or "local"),
                "approval_ref_present": bool(release_scope.get("approval_ref_present")),
                "missing_reference_count": int(release_scope.get("missing_reference_count") or 0),
                "missing_required_references": list(release_scope.get("missing_required_references") or []),
                "local_indicator_count": int(release_scope.get("local_indicator_count") or 0),
                "reason": str(release_scope.get("reason") or ""),
            },
            "evidence": {
                "artifact_status": str(artifact_safety.get("status") or ""),
                "production_ready": bool(evidence.get("production_ready")),
                "ready_for_sidebar": bool(evidence.get("ready_for_sidebar")),
            },
            "completion_audit": completion,
            "required_commands": commands,
            "production_env_flags": [],
        }
    )


def render_kubernetes_handoff_execution_plan_markdown(plan: dict[str, Any]) -> list[str]:
    recommended = plan.get("recommended_next") if isinstance(plan.get("recommended_next"), dict) else {}
    lines = [
        "## Production Execution Plan",
        f"- Status: {plan.get('status') or 'unknown'}",
        f"- Recommended next: {recommended.get('label') or recommended.get('id') or 'operator review'}",
        "",
        "### Blocked Until",
    ]
    blockers = plan.get("blocked_until") if isinstance(plan.get("blocked_until"), list) else []
    if blockers:
        for item in blockers:
            if isinstance(item, dict):
                lines.append(f"- `{item.get('id')}`: {item.get('detail')}")
    else:
        lines.append("- none")
    lines.extend(["", "### Phases"])
    for phase in plan.get("phases") or []:
        if not isinstance(phase, dict):
            continue
        lines.append(f"- {phase.get('title')} (`{phase.get('id')}`)")
        for step in phase.get("manual_steps") or []:
            lines.append(f"  - manual: {step}")
        for command in phase.get("commands") or []:
            if isinstance(command, dict):
                lines.append(f"  - command: `{command.get('command')}`")
    return lines


def _blocked_until(*, release_scope: dict[str, Any], evidence: dict[str, Any], completion: dict[str, Any]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    if str(release_scope.get("target_environment") or "") != "production":
        blockers.append({"id": "target_environment", "detail": "target environment must be production"})
    if not release_scope.get("approval_ref_present"):
        blockers.append({"id": "production_approval_ref", "detail": "production approval reference must be present"})
    for item in release_scope.get("missing_required_references") or []:
        if isinstance(item, dict):
            blockers.append(
                {
                    "id": str(item.get("id") or "production_ref"),
                    "detail": f"{item.get('setting') or 'production evidence ref'} must be present",
                }
            )
    local_indicator_count = int(release_scope.get("local_indicator_count") or 0)
    if local_indicator_count:
        blockers.append({"id": "local_indicators", "detail": f"local/test markers must be removed from evidence ({local_indicator_count})"})
    if str(evidence.get("artifact_status") or "") != "ready":
        blockers.append({"id": "release_artifact", "detail": "release evidence artifact must pass safety checks"})
    if not evidence.get("production_ready"):
        blockers.append({"id": "production_ready", "detail": "release evidence must report production_ready=true"})
    if not evidence.get("ready_for_sidebar"):
        blockers.append({"id": "ready_for_sidebar", "detail": "release evidence must report ready_for_sidebar=true"})
    if completion.get("production_evidence_complete") is not True:
        blockers.append({"id": "production_evidence_complete", "detail": "completion audit must mark production evidence complete"})
    if completion.get("sidebar_enablement_complete") is not True:
        blockers.append({"id": "sidebar_enablement_complete", "detail": "completion audit must mark sidebar enablement complete"})
    return blockers


def _recommended_next(
    *,
    can_enable_sidebar: bool,
    release_scope: dict[str, Any],
    evidence: dict[str, Any],
    blocked_until: list[dict[str, str]],
) -> dict[str, Any]:
    blocker_ids = {item["id"] for item in blocked_until}
    if can_enable_sidebar:
        return {"type": "manual", "id": "enable_sidebar_after_approval", "label": "Enable sidebar after approved production change."}
    if "target_environment" in blocker_ids:
        return {"type": "manual", "id": "select_production_environment", "label": "Select the production release environment."}
    if "production_approval_ref" in blocker_ids or release_scope.get("missing_reference_count"):
        return {"type": "manual", "id": "set_production_evidence_refs", "label": "Set approval and required production evidence refs."}
    if "local_indicators" in blocker_ids:
        return {"type": "manual", "id": "replace_local_evidence", "label": "Replace local/test evidence with non-local production proofs."}
    if evidence.get("artifact_status") != "ready" or not evidence.get("production_ready"):
        return {"type": "command", "id": "release_evidence", "label": "Regenerate production release evidence."}
    return {"type": "command", "id": "release_handoff", "label": "Render the production handoff again."}


def _command_map(commands: object) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in commands if isinstance(commands, list) else []:
        if isinstance(item, dict) and item.get("id"):
            result[str(item["id"])] = dict(item)
    return result


def _command_phase(phase_id: str, title: str, commands: dict[str, dict[str, Any]], command_ids: tuple[str, ...]) -> dict[str, Any]:
    selected = _selected_phase_commands(commands, command_ids)
    return {"id": phase_id, "title": title, "type": "command", "commands": selected, "command_count": len(selected)}


def _selected_phase_commands(commands: dict[str, dict[str, Any]], command_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for command_id in command_ids:
        command = commands.get(command_id)
        if command is None:
            continue
        canonical_id = COMMAND_ID_ALIASES.get(command_id, command_id)
        if canonical_id in seen:
            continue
        selected.append(command)
        seen.add(canonical_id)
    return selected


def _manual_phase(phase_id: str, title: str, steps: list[str], settings: list[str]) -> dict[str, Any]:
    return {"id": phase_id, "title": title, "type": "manual", "manual_steps": steps, "settings": settings}


def _production_settings(handoff: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for item in handoff.get("production_env_flags") or []:
        if isinstance(item, dict) and item.get("name"):
            result.append(str(item["name"]))
    return result or list(DEFAULT_PRODUCTION_SETTINGS)
