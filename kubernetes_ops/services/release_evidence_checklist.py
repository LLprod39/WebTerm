from __future__ import annotations

from typing import Any

from kubernetes_ops.services.release_external_evidence_bundle import load_kubernetes_external_evidence_bundle_artifact
from kubernetes_ops.services.release_scope import production_core_reference_checks


def build_kubernetes_production_evidence_checklist(*, production_gate: dict[str, Any]) -> dict[str, Any]:
    production_target = bool(production_gate.get("production_target"))
    core_references = _core_references(production_gate, production_target=production_target)
    external_bundle = _external_bundle_payload(load_kubernetes_external_evidence_bundle_artifact())
    core_missing = [item for item in core_references if item["required"] and not item["present"]]
    external_missing = [
        item
        for item in external_bundle["references"]
        if item["required"] and not item["present"]
    ]
    artifact_missing = [
        item
        for item in external_bundle["artifact_checks"]
        if item["status"] != "ready"
    ]
    blockers = []
    blockers.extend(f"core_ref:{item['id']}" for item in core_missing)
    blockers.extend(f"external_ref:{item['id']}" for item in external_missing)
    blockers.extend(f"external_artifact:{item['id']}" for item in artifact_missing)
    if external_bundle["local_indicator_count"]:
        blockers.append("external_bundle:local_indicators")
    if production_target and external_bundle["status"] != "ready":
        blockers.append("external_bundle:not_ready")
    status = _checklist_status(
        production_target=production_target,
        core_missing=core_missing,
        external_bundle=external_bundle,
        blockers=blockers,
    )
    return {
        "status": status,
        "production_target": production_target,
        "target_environment": str(production_gate.get("target_environment") or "local"),
        "approval_ref_present": bool(production_gate.get("approval_ref_present")),
        "core_reference_count": len(core_references),
        "core_missing_required_count": len(core_missing),
        "core_references": core_references,
        "external_bundle": external_bundle,
        "blockers": blockers[:12],
        "gap_summary": _gap_summary(
            status=status,
            production_target=production_target,
            core_missing=core_missing,
            external_missing=external_missing,
            artifact_missing=artifact_missing,
            external_bundle=external_bundle,
            blockers=blockers,
        ),
        "next_step": _next_step(status, core_missing=core_missing, external_bundle=external_bundle),
    }


def _core_references(production_gate: dict[str, Any], *, production_target: bool) -> list[dict[str, Any]]:
    raw = production_gate.get("required_references")
    if not isinstance(raw, list):
        raw = production_core_reference_checks(production_required=production_target)
    return [_reference_item(item) for item in raw if isinstance(item, dict)]


def _reference_item(item: dict[str, Any]) -> dict[str, Any]:
    required = bool(item.get("required"))
    present = bool(item.get("present"))
    return {
        "id": str(item.get("id") or ""),
        "setting": str(item.get("setting") or ""),
        "expected": str(item.get("expected") or ""),
        "required": required,
        "present": present,
        "status": "ready" if present else ("missing" if required else "not_required"),
    }


def _external_bundle_payload(bundle: dict[str, Any]) -> dict[str, Any]:
    summary = bundle.get("summary") if isinstance(bundle.get("summary"), dict) else {}
    references = [
        _reference_item(item)
        for item in bundle.get("references") or []
        if isinstance(item, dict)
    ]
    artifact_checks = [
        _artifact_check_item(item)
        for item in bundle.get("artifact_checks") or []
        if isinstance(item, dict)
    ]
    local_indicator_count = int(summary.get("local_indicator_count") or 0)
    if not local_indicator_count:
        local_indicator_count = sum(int(item.get("local_indicator_count") or 0) for item in artifact_checks)
    return {
        "status": str(bundle.get("status") or "missing"),
        "success": bool(bundle.get("success")),
        "checked_at": str(bundle.get("checked_at") or ""),
        "age_seconds": bundle.get("age_seconds"),
        "max_age_seconds": bundle.get("max_age_seconds"),
        "required_ref_count": int(summary.get("required_ref_count") or sum(1 for item in references if item["required"])),
        "missing_required_ref_count": int(summary.get("missing_required_ref_count") or sum(1 for item in references if item["required"] and not item["present"])),
        "artifact_check_count": int(summary.get("artifact_check_count") or len(artifact_checks)),
        "artifact_ready_count": int(summary.get("artifact_ready_count") or sum(1 for item in artifact_checks if item["status"] == "ready")),
        "local_indicator_count": local_indicator_count,
        "error_count": len(bundle.get("errors") or []),
        "references": references,
        "artifact_checks": artifact_checks,
    }


def _artifact_check_item(item: dict[str, Any]) -> dict[str, Any]:
    local_indicators = item.get("local_indicators") if isinstance(item.get("local_indicators"), list) else []
    return {
        "id": str(item.get("id") or ""),
        "status": str(item.get("status") or "missing"),
        "success": bool(item.get("success")),
        "checked_at": str(item.get("checked_at") or ""),
        "schema_version": str(item.get("schema_version") or ""),
        "local_indicator_count": len(local_indicators),
        "error_count": len(item.get("errors") or []),
    }


def _checklist_status(
    *,
    production_target: bool,
    core_missing: list[dict[str, Any]],
    external_bundle: dict[str, Any],
    blockers: list[str],
) -> str:
    if not production_target:
        return "not_required"
    if core_missing:
        return "missing_core_refs"
    if external_bundle["status"] != "ready":
        return "missing_external_bundle"
    if blockers:
        return "blocked"
    return "ready"


def _gap_summary(
    *,
    status: str,
    production_target: bool,
    core_missing: list[dict[str, Any]],
    external_missing: list[dict[str, Any]],
    artifact_missing: list[dict[str, Any]],
    external_bundle: dict[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    next_gap_id, next_manual_step_id, next_command_ids = _next_gap(
        status=status,
        production_target=production_target,
        core_missing=core_missing,
        external_missing=external_missing,
        artifact_missing=artifact_missing,
        external_bundle=external_bundle,
    )
    missing_settings = _unique(
        [
            *[item["setting"] for item in core_missing],
            *[item["setting"] for item in external_missing],
        ]
    )
    production_target_gap = 0 if production_target else 1
    return {
        "status": status,
        "production_target": production_target,
        "ready_for_release_evidence": status == "ready",
        "blocking_gap_count": production_target_gap + len(blockers),
        "missing_core_ref_count": len(core_missing),
        "missing_external_ref_count": len(external_missing),
        "missing_external_artifact_count": len(artifact_missing),
        "local_indicator_count": int(external_bundle.get("local_indicator_count") or 0),
        "external_bundle_status": str(external_bundle.get("status") or "missing"),
        "next_gap_id": next_gap_id,
        "next_manual_step_id": next_manual_step_id,
        "next_command_ids": next_command_ids,
        "missing_settings": missing_settings[:12],
        "external_artifact_ids": [str(item.get("id") or "") for item in artifact_missing[:12]],
    }


def _next_gap(
    *,
    status: str,
    production_target: bool,
    core_missing: list[dict[str, Any]],
    external_missing: list[dict[str, Any]],
    artifact_missing: list[dict[str, Any]],
    external_bundle: dict[str, Any],
) -> tuple[str, str, list[str]]:
    if not production_target:
        return "select_production_environment", "select_production_environment", []
    if core_missing:
        return "set_core_evidence_refs", "set_production_evidence_refs", []
    if external_missing:
        return "set_external_bundle_refs", "set_external_evidence_refs", ["external_evidence_bundle"]
    if artifact_missing or external_bundle.get("status") != "ready":
        return "refresh_external_evidence_bundle", "", ["external_evidence_bundle"]
    if external_bundle.get("local_indicator_count"):
        return "replace_local_evidence", "", ["external_evidence_bundle"]
    if status == "ready":
        return "ready", "", ["release_evidence", "release_handoff"]
    return "fix_production_evidence_blockers", "", ["external_evidence_bundle"]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _next_step(status: str, *, core_missing: list[dict[str, Any]], external_bundle: dict[str, Any]) -> str:
    if status == "not_required":
        return "Select production release environment only when production evidence refs are available."
    if status == "missing_core_refs":
        missing = ", ".join(item["setting"] for item in core_missing[:6])
        return f"Set required production evidence refs: {missing}."
    if status == "missing_external_bundle":
        return "Run verify_kubernetes_ops_external_evidence_bundle with production refs and non-local artifacts."
    if external_bundle["local_indicator_count"]:
        return "Replace local/test external evidence artifacts with production evidence and rerun the external bundle verifier."
    if status == "ready":
        return "Production evidence checklist is ready; rerun release evidence and handoff before enabling sidebar."
    return "Fix listed production evidence blockers and rerun the release summary."
