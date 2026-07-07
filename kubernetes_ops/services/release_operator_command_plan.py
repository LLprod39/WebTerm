from __future__ import annotations

from typing import Any

from kubernetes_ops.services.release_command_plan import build_kubernetes_release_command_plan


def build_kubernetes_handoff_operator_command_plan(
    *,
    production_evidence_checklist: dict[str, Any],
    blocker_groups: list[dict[str, Any]],
    can_enable_sidebar: bool,
) -> dict[str, Any]:
    return build_kubernetes_release_command_plan(
        production_evidence_checklist=production_evidence_checklist,
        blocker_groups=blocker_groups,
        can_enable_sidebar=can_enable_sidebar,
    )


def build_kubernetes_handoff_production_checklist(release_scope: dict[str, Any]) -> dict[str, Any]:
    production_target = str(release_scope.get("target_environment") or "") == "production" or release_scope.get("status") == "ready"
    missing_refs = [item for item in release_scope.get("missing_required_references") or [] if isinstance(item, dict)]
    core_references = [
        {
            "id": str(item.get("id") or item.get("setting") or ""),
            "setting": str(item.get("setting") or ""),
            "required": True,
            "present": False,
            "expected": str(item.get("expected") or ""),
        }
        for item in missing_refs
    ]
    local_indicator_count = int(release_scope.get("local_indicator_count") or 0)
    if not production_target:
        status, next_gap, commands, count, external_bundle_status = "not_required", "select_production_environment", [], 1, "not_required"
    elif missing_refs:
        status, next_gap, commands, count, external_bundle_status = "missing_core_refs", "set_core_evidence_refs", [], len(missing_refs), "blocked"
    elif local_indicator_count:
        status, next_gap, commands, count, external_bundle_status = "blocked", "replace_local_evidence", ["external_evidence_bundle"], local_indicator_count, "blocked"
    else:
        status, next_gap, commands, count, external_bundle_status = "ready", "ready", ["release_evidence", "release_handoff"], 0, "ready"
    return {
        "status": status,
        "production_target": production_target,
        "core_references": core_references,
        "external_bundle": {"status": external_bundle_status},
        "gap_summary": {"next_gap_id": next_gap, "blocking_gap_count": count, "next_command_ids": commands},
    }


def render_kubernetes_operator_command_plan_markdown(plan: dict[str, Any]) -> list[str]:
    if not plan:
        return ["## Operator Command Plan", "- unavailable"]
    recommended = plan.get("recommended_next") if isinstance(plan.get("recommended_next"), dict) else {}
    lines = [
        "## Operator Command Plan",
        f"- Status: {plan.get('status') or 'unknown'}",
        f"- Recommended next: {recommended.get('id') or 'operator_review'} ({recommended.get('type') or 'unknown'})",
    ]
    manual_steps = plan.get("manual_steps") if isinstance(plan.get("manual_steps"), list) else []
    if manual_steps:
        lines.append("- Manual steps:")
        for step in manual_steps:
            if isinstance(step, dict):
                lines.append(f"  - {step.get('id')}: {step.get('label')}")
    phases = plan.get("phases") if isinstance(plan.get("phases"), list) else []
    if phases:
        lines.append("")
        lines.append("### Operator Command Phases")
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        lines.append(f"- {phase.get('title')} (`{phase.get('id')}`)")
        for command in phase.get("commands") or []:
            if isinstance(command, dict):
                lines.append(f"  - `{command.get('id')}`: `{command.get('command')}`")
    if not phases:
        lines.append("- No command phases.")
    return lines
