from __future__ import annotations

from typing import Any

PRODUCTION_SCOPE_READINESS_CHECK_IDS = {"sidebar_release_scope", "release_evidence_artifact"}


def build_kubernetes_release_completion_audit(
    *,
    artifact_summary: dict[str, Any],
    readiness_checks: list[dict[str, Any]] | None = None,
    production_gate: dict[str, Any] | None = None,
    artifact_report: dict[str, Any] | None = None,
    can_enable_sidebar: bool = False,
) -> dict[str, Any]:
    readiness_checks = readiness_checks or []
    production_gate = production_gate or {}
    artifact_report = artifact_report or {"status": "ready"}
    core_proofs = _core_backend_proofs(artifact_summary)
    readiness_missing = [str(item.get("id") or "") for item in readiness_checks if item.get("required", True) and item.get("status") != "ready"]
    runtime_missing = [item for item in readiness_missing if item not in PRODUCTION_SCOPE_READINESS_CHECK_IDS]
    production_scope_missing = [item for item in readiness_missing if item in PRODUCTION_SCOPE_READINESS_CHECK_IDS]
    production_checks = _production_evidence_checks(production_gate, artifact_report, artifact_summary)
    remaining = []
    if not all(item["complete"] for item in core_proofs):
        remaining.append("core_backend")
    if runtime_missing:
        remaining.append("runtime_readiness")
    if not all(item["complete"] for item in production_checks):
        remaining.append("production_evidence")
    if not can_enable_sidebar:
        remaining.append("sidebar_enablement")
    return {
        "status": "complete" if can_enable_sidebar else "incomplete",
        "core_backend_complete": all(item["complete"] for item in core_proofs),
        "runtime_readiness_complete": not runtime_missing,
        "production_evidence_complete": all(item["complete"] for item in production_checks),
        "sidebar_enablement_complete": can_enable_sidebar,
        "core_backend_proofs": core_proofs,
        "runtime_missing_required_checks": runtime_missing[:12],
        "production_scope_readiness_checks": production_scope_missing[:12],
        "production_evidence_checks": production_checks,
        "remaining": remaining,
    }


def _core_backend_proofs(summary: dict[str, Any]) -> list[dict[str, Any]]:
    dod_ready = int(summary.get("definition_of_done_ready") or 0)
    dod_total = int(summary.get("definition_of_done_total") or 0)
    return [
        {
            "id": "definition_of_done",
            "status": str(summary.get("definition_of_done_status") or ""),
            "complete": bool(dod_total and dod_ready == dod_total and summary.get("definition_of_done_status") == "ready"),
        },
        {
            "id": "normal_user_surface",
            "status": str(summary.get("normal_user_surface_status") or ""),
            "complete": str(summary.get("normal_user_surface_status") or "") == "ready",
        },
        {
            "id": "frontend_payload_scan",
            "status": str(summary.get("frontend_payload_scan_status") or ""),
            "complete": str(summary.get("frontend_payload_scan_status") or "") == "ready",
        },
        {
            "id": "secret_read_controls",
            "status": str(summary.get("sensitive_value_controls_status") or ""),
            "complete": str(summary.get("sensitive_value_controls_status") or "") == "ready",
        },
        {
            "id": "provider_secret_lifecycle",
            "status": str(summary.get("provider_lifecycle_status") or ""),
            "complete": str(summary.get("provider_lifecycle_status") or "") == "ready",
        },
        {
            "id": "audit_redaction",
            "status": str(summary.get("audit_redaction_status") or ""),
            "complete": str(summary.get("audit_redaction_status") or "") == "ready",
        },
        {
            "id": "production_action_evidence",
            "status": str(summary.get("production_action_evidence_status") or ""),
            "complete": str(summary.get("production_action_evidence_status") or "") == "ready"
            and int(summary.get("production_action_blocked_action_class_count") or 0) > 0,
        },
    ]


def _production_evidence_checks(
    production_gate: dict[str, Any],
    artifact_report: dict[str, Any],
    artifact_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    missing_refs = _missing_refs(production_gate)
    local_indicator_count = int(production_gate.get("local_indicator_count") or 0)
    return [
        {
            "id": "target_environment",
            "complete": bool(production_gate.get("production_target") or production_gate.get("status") == "ready"),
            "detail": str(production_gate.get("target_environment") or production_gate.get("status") or "local"),
        },
        {
            "id": "required_references",
            "complete": not missing_refs,
            "detail": str(len(missing_refs)),
        },
        {
            "id": "no_local_indicators",
            "complete": local_indicator_count == 0,
            "detail": str(local_indicator_count),
        },
        {
            "id": "release_artifact",
            "complete": artifact_report.get("status") == "ready"
            and bool(artifact_summary.get("production_ready"))
            and (
                "production_evidence_complete" not in artifact_report
                or artifact_report.get("production_evidence_complete") is True
            ),
            "detail": str(artifact_report.get("status") or ""),
        },
    ]


def _missing_refs(production_gate: dict[str, Any]) -> list[dict[str, str]]:
    refs = production_gate.get("missing_required_references") if isinstance(production_gate.get("missing_required_references"), list) else []
    return [item for item in refs if isinstance(item, dict)]
