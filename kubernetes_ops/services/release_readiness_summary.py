from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings

from kubernetes_ops.services.readiness import build_kubernetes_readiness_report
from kubernetes_ops.services.release_artifact import build_kubernetes_release_evidence_artifact_report
from kubernetes_ops.services.release_backend_workstream import (
    build_kubernetes_release_backend_workstream,
    can_enable_kubernetes_release_sidebar,
)
from kubernetes_ops.services.release_command_plan import COMMANDS, build_kubernetes_release_command_plan
from kubernetes_ops.services.release_completion_audit import PRODUCTION_SCOPE_READINESS_CHECK_IDS, build_kubernetes_release_completion_audit
from kubernetes_ops.services.release_evidence_checklist import build_kubernetes_production_evidence_checklist
from kubernetes_ops.services.release_handoff_plan import build_kubernetes_handoff_execution_plan
from kubernetes_ops.services.release_summary import build_kubernetes_release_summary


RELEASE_SUMMARY_COMMANDS = tuple(dict(item) for item in COMMANDS.values())


def build_kubernetes_release_readiness_summary(*, user=None) -> dict[str, Any]:
    readiness = build_kubernetes_readiness_report(user=user)
    sidebar_env_enabled = _bool_setting("KUBERNETES_OPS_READY_FOR_SIDEBAR")
    artifact_report = build_kubernetes_release_evidence_artifact_report(require_ready=sidebar_env_enabled)
    artifact_summary = _release_summary_from_artifact(artifact_report)
    production_gate = readiness.get("production_gate") if isinstance(readiness.get("production_gate"), dict) else {}
    readiness_checks = readiness.get("checks") if isinstance(readiness.get("checks"), list) else []
    blocker_groups = _blocker_groups(
        readiness_checks=readiness_checks,
        production_gate=production_gate,
        artifact_report=artifact_report,
        artifact_summary=artifact_summary,
    )
    next_steps = _dedupe(
        [
            *list(artifact_summary.get("next_steps") or []),
            *[group["next_step"] for group in blocker_groups if group.get("next_step")],
        ]
    )
    release_gate_ready = (
        bool(readiness.get("ready_for_sidebar"))
        and bool(artifact_report.get("production_ready"))
        and bool(artifact_report.get("ready_for_sidebar"))
        and artifact_report.get("status") == "ready"
    )
    production_evidence_checklist = build_kubernetes_production_evidence_checklist(production_gate=production_gate)
    artifact_payload = _artifact_payload(artifact_report)
    completion_audit = build_kubernetes_release_completion_audit(
        artifact_summary=artifact_summary,
        readiness_checks=readiness_checks,
        production_gate=production_gate,
        artifact_report=artifact_report,
        can_enable_sidebar=release_gate_ready,
    )
    can_enable_sidebar = can_enable_kubernetes_release_sidebar(
        production_ready=bool(artifact_report.get("production_ready")),
        ready_for_sidebar=bool(readiness.get("ready_for_sidebar")) and bool(artifact_report.get("ready_for_sidebar")),
        completion_audit=completion_audit,
        artifact_ready=artifact_report.get("status") == "ready",
    )
    if can_enable_sidebar != release_gate_ready:
        completion_audit = build_kubernetes_release_completion_audit(
            artifact_summary=artifact_summary,
            readiness_checks=readiness_checks,
            production_gate=production_gate,
            artifact_report=artifact_report,
            can_enable_sidebar=can_enable_sidebar,
        )
    operator_command_plan = build_kubernetes_release_command_plan(
        production_evidence_checklist=production_evidence_checklist,
        blocker_groups=blocker_groups,
        can_enable_sidebar=can_enable_sidebar,
    )
    summary_payload = {
        "success": True,
        "operation": "release_readiness_summary",
        "policy": {
            "staff_only": True,
            "mutates_state": False,
            "runs_live_checks": False,
            "source": "readiness_state_and_release_artifact",
        },
        "status": "ready" if can_enable_sidebar else "blocked",
        "can_enable_sidebar": can_enable_sidebar,
        "sidebar_env_enabled": sidebar_env_enabled,
        "target_environment": str(production_gate.get("target_environment") or "local"),
        "production_target": bool(production_gate.get("production_target")),
        "readiness": {
            "status": str(readiness.get("status") or ""),
            "ready_for_sidebar": bool(readiness.get("ready_for_sidebar")),
            "summary": readiness.get("summary") if isinstance(readiness.get("summary"), dict) else {},
        },
        "artifact": artifact_payload,
        "proofs": _proof_statuses(artifact_summary),
        "progress": _progress_payload(
            readiness=readiness,
            artifact_summary=artifact_summary,
            can_enable_sidebar=can_enable_sidebar,
            blocker_groups=blocker_groups,
        ),
        "completion_audit": completion_audit,
        "backend_workstream": build_kubernetes_release_backend_workstream(
            completion_audit=completion_audit,
            blocker_groups=blocker_groups,
            production_evidence_checklist=production_evidence_checklist,
            can_enable_sidebar=can_enable_sidebar,
        ),
        "production_evidence_checklist": production_evidence_checklist,
        "operator_command_plan": operator_command_plan,
        "missing_required_references": _missing_refs(production_gate),
        "blocker_groups": blocker_groups,
        "top_blockers": _top_blockers(blocker_groups),
        "next_steps": next_steps[:8],
        "required_commands": list(RELEASE_SUMMARY_COMMANDS),
    }
    summary_payload["production_execution_plan"] = build_kubernetes_handoff_execution_plan(
        _handoff_like_payload(
            summary_payload=summary_payload,
            production_gate=production_gate,
            artifact_payload=artifact_payload,
            completion_audit=completion_audit,
        )
    )
    return summary_payload


def _handoff_like_payload(
    *,
    summary_payload: dict[str, Any],
    production_gate: dict[str, Any],
    artifact_payload: dict[str, Any],
    completion_audit: dict[str, Any],
) -> dict[str, Any]:
    return {
        "can_enable_sidebar": bool(summary_payload.get("can_enable_sidebar")),
        "release_scope": {
            "status": str(production_gate.get("status") or ""),
            "target_environment": str(production_gate.get("target_environment") or "local"),
            "approval_ref_present": bool(production_gate.get("approval_ref_present")),
            "missing_reference_count": len(_missing_refs(production_gate)),
            "missing_required_references": _missing_refs(production_gate),
            "local_indicator_count": int(production_gate.get("local_indicator_count") or 0),
            "reason": str(production_gate.get("reason") or ""),
        },
        "evidence": {
            "artifact_status": str(artifact_payload.get("status") or ""),
            "production_ready": bool(artifact_payload.get("production_ready")),
            "ready_for_sidebar": bool(artifact_payload.get("ready_for_sidebar")),
        },
        "completion_audit": completion_audit,
        "required_commands": list(RELEASE_SUMMARY_COMMANDS),
        "production_env_flags": [],
    }


def _release_summary_from_artifact(artifact_report: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(artifact_report.get("path") or ""))
    payload: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if isinstance(loaded, dict):
            payload = loaded
    summary = payload.get("release_summary") if isinstance(payload.get("release_summary"), dict) else {}
    if summary:
        return _safe_release_summary(summary)
    synthetic = {
        "production_ready": bool(artifact_report.get("production_ready")),
        "ready_for_sidebar": bool(artifact_report.get("ready_for_sidebar")),
        "blockers": list(artifact_report.get("blockers") or []),
        "release_scope": {"status": artifact_report.get("release_scope_status") or ""},
        "artifact_safety": {
            "status": artifact_report.get("artifact_safety_status") or "",
            "issue_count": artifact_report.get("artifact_safety_issue_count") or 0,
        },
    }
    return _safe_release_summary(build_kubernetes_release_summary(synthetic))


def _safe_release_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": str(summary.get("status") or ""),
        "production_ready": bool(summary.get("production_ready")),
        "ready_for_sidebar": bool(summary.get("ready_for_sidebar")),
        "blocker_count": int(summary.get("blocker_count") or 0),
        "top_blockers": [str(item) for item in list(summary.get("top_blockers") or [])[:8]],
        "next_steps": [str(item) for item in list(summary.get("next_steps") or [])[:8]],
        "release_scope_status": str(summary.get("release_scope_status") or ""),
        "preflight_status": str(summary.get("preflight_status") or ""),
        "artifact_safety_status": str(summary.get("artifact_safety_status") or ""),
        "artifact_safety_issue_count": int(summary.get("artifact_safety_issue_count") or 0),
        "normal_user_surface_status": str(summary.get("normal_user_surface_status") or ""),
        "definition_of_done_status": str(summary.get("definition_of_done_status") or ""),
        "definition_of_done_ready": int(summary.get("definition_of_done_ready") or 0),
        "definition_of_done_total": int(summary.get("definition_of_done_total") or 0),
        "frontend_payload_scan_status": str(summary.get("frontend_payload_scan_status") or ""),
        "sensitive_value_controls_status": str(summary.get("sensitive_value_controls_status") or ""),
        "provider_lifecycle_status": str(summary.get("provider_lifecycle_status") or ""),
        "audit_redaction_status": str(summary.get("audit_redaction_status") or ""),
        "production_action_evidence_status": str(summary.get("production_action_evidence_status") or ""),
        "production_action_blocked_action_class_count": int(summary.get("production_action_blocked_action_class_count") or 0),
    }


def _artifact_payload(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": str(report.get("status") or ""),
        "detail": str(report.get("detail") or ""),
        "generated_at": str(report.get("generated_at") or ""),
        "age_seconds": report.get("age_seconds"),
        "max_age_seconds": report.get("max_age_seconds"),
        "production_ready": bool(report.get("production_ready")),
        "ready_for_sidebar": bool(report.get("ready_for_sidebar")),
        "schema_version": str(report.get("schema_version") or ""),
        "expected_schema_version": str(report.get("expected_schema_version") or ""),
        "release_scope_status": str(report.get("release_scope_status") or ""),
        "artifact_safety_status": str(report.get("artifact_safety_status") or ""),
        "artifact_safety_issue_count": int(report.get("artifact_safety_issue_count") or 0),
        "completion_audit_status": str(report.get("completion_audit_status") or ""),
        "production_evidence_complete": bool(report.get("production_evidence_complete")),
        "sidebar_enablement_complete": bool(report.get("sidebar_enablement_complete")),
        "error_count": len(report.get("errors") or []),
        "errors": [str(item) for item in list(report.get("errors") or [])[:8]],
        "blocker_count": len(report.get("blockers") or []),
    }


def _proof_statuses(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "preflight": str(summary.get("preflight_status") or ""),
        "artifact_safety": str(summary.get("artifact_safety_status") or ""),
        "release_scope": str(summary.get("release_scope_status") or ""),
        "definition_of_done": {
            "status": str(summary.get("definition_of_done_status") or ""),
            "ready": int(summary.get("definition_of_done_ready") or 0),
            "total": int(summary.get("definition_of_done_total") or 0),
        },
        "normal_user_surface": str(summary.get("normal_user_surface_status") or ""),
        "frontend_payload_scan": str(summary.get("frontend_payload_scan_status") or ""),
        "secret_read_controls": str(summary.get("sensitive_value_controls_status") or ""),
        "provider_secret_lifecycle": str(summary.get("provider_lifecycle_status") or ""),
        "audit_redaction": str(summary.get("audit_redaction_status") or ""),
        "production_action_evidence": {
            "status": str(summary.get("production_action_evidence_status") or ""),
            "blocked_action_class_count": int(summary.get("production_action_blocked_action_class_count") or 0),
        },
    }


def _progress_payload(
    *,
    readiness: dict[str, Any],
    artifact_summary: dict[str, Any],
    can_enable_sidebar: bool,
    blocker_groups: list[dict[str, Any]],
) -> dict[str, Any]:
    readiness_summary = readiness.get("summary") if isinstance(readiness.get("summary"), dict) else {}
    readiness_ready = int(readiness_summary.get("ready") or 0)
    readiness_total = int(readiness_summary.get("total") or 0)
    dod_ready = int(artifact_summary.get("definition_of_done_ready") or 0)
    dod_total = int(artifact_summary.get("definition_of_done_total") or 0)
    remaining_categories = [str(group.get("id") or "") for group in blocker_groups if group.get("count")]
    runtime_blocker_count = sum(int(group.get("count") or 0) for group in blocker_groups if group.get("id") == "runtime_readiness")
    stage = _progress_stage(
        can_enable_sidebar=can_enable_sidebar,
        dod_ready=dod_ready,
        dod_total=dod_total,
        readiness_ready=readiness_ready,
        readiness_total=readiness_total,
        runtime_blocker_count=runtime_blocker_count,
        artifact_summary=artifact_summary,
    )
    return {
        "stage": stage,
        "plain_status": _plain_progress_status(stage),
        "backend_definition_of_done": {
            "ready": dod_ready,
            "total": dod_total,
            "percent": _percent(dod_ready, dod_total),
            "status": str(artifact_summary.get("definition_of_done_status") or ""),
        },
        "runtime_readiness": {
            "ready": readiness_ready,
            "missing": int(readiness_summary.get("missing") or 0),
            "manual": int(readiness_summary.get("manual") or 0),
            "total": readiness_total,
            "percent": _percent(readiness_ready, readiness_total),
            "status": str(readiness.get("status") or ""),
        },
        "release_surface": {
            "normal_user_surface": str(artifact_summary.get("normal_user_surface_status") or ""),
            "frontend_payload_scan": str(artifact_summary.get("frontend_payload_scan_status") or ""),
            "secret_read_controls": str(artifact_summary.get("sensitive_value_controls_status") or ""),
            "audit_redaction": str(artifact_summary.get("audit_redaction_status") or ""),
            "production_action_evidence": str(artifact_summary.get("production_action_evidence_status") or ""),
            "production_ready": bool(artifact_summary.get("production_ready")),
            "ready_for_sidebar": bool(artifact_summary.get("ready_for_sidebar")),
        },
        "remaining_categories": remaining_categories[:8],
        "remaining_category_count": len(remaining_categories),
    }


def _progress_stage(
    *,
    can_enable_sidebar: bool,
    dod_ready: int,
    dod_total: int,
    readiness_ready: int,
    readiness_total: int,
    runtime_blocker_count: int,
    artifact_summary: dict[str, Any],
) -> str:
    if can_enable_sidebar:
        return "production_sidebar_ready"
    if dod_total and dod_ready < dod_total:
        return "backend_definition_of_done_incomplete"
    if readiness_total and readiness_ready < readiness_total and runtime_blocker_count:
        return "runtime_readiness_incomplete"
    if str(artifact_summary.get("normal_user_surface_status") or "") != "ready":
        return "normal_user_surface_incomplete"
    if str(artifact_summary.get("frontend_payload_scan_status") or "") != "ready":
        return "frontend_payload_scan_incomplete"
    if str(artifact_summary.get("sensitive_value_controls_status") or "") != "ready":
        return "secret_read_controls_incomplete"
    if str(artifact_summary.get("audit_redaction_status") or "") != "ready":
        return "audit_redaction_incomplete"
    if str(artifact_summary.get("production_action_evidence_status") or "") != "ready":
        return "production_action_evidence_incomplete"
    if not artifact_summary.get("production_ready"):
        return "core_backend_ready_production_blocked"
    return "release_artifact_incomplete"


def _plain_progress_status(stage: str) -> str:
    return {
        "production_sidebar_ready": "Production sidebar can be enabled after the approved operator change.",
        "backend_definition_of_done_incomplete": "Core backend Definition of Done is still incomplete.",
        "runtime_readiness_incomplete": "Runtime readiness still has required gaps.",
        "normal_user_surface_incomplete": "Normal-user WebTerm-only surface proof is incomplete.",
        "frontend_payload_scan_incomplete": "Frontend payload credential scan is incomplete.",
        "secret_read_controls_incomplete": "Secret redaction/reveal controls proof is incomplete.",
        "audit_redaction_incomplete": "Audit/log redaction proof is incomplete.",
        "production_action_evidence_incomplete": "Production action safety proof is incomplete.",
        "core_backend_ready_production_blocked": "Core backend proof is ready, but production/sidebar enablement is still blocked by release scope or evidence.",
        "release_artifact_incomplete": "Release artifact is incomplete or stale.",
    }.get(stage, "Kubernetes release progress requires operator review.")


def _percent(ready: int, total: int) -> int | None:
    if total <= 0:
        return None
    return int(round((ready / total) * 100))


def _blocker_groups(
    *,
    readiness_checks: list[dict[str, Any]],
    production_gate: dict[str, Any],
    artifact_report: dict[str, Any],
    artifact_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    readiness_blockers = [
        {
            "id": str(item.get("id") or ""),
            "status": str(item.get("status") or ""),
            "detail": str(item.get("detail") or ""),
            "required": bool(item.get("required", True)),
        }
        for item in readiness_checks
        if item.get("required", True) and item.get("status") != "ready"
    ]
    runtime_readiness_blockers = [
        item for item in readiness_blockers if item["id"] not in PRODUCTION_SCOPE_READINESS_CHECK_IDS
    ]
    if runtime_readiness_blockers:
        groups.append(
            _group(
                "runtime_readiness",
                "Runtime readiness",
                runtime_readiness_blockers,
                "Fix missing required readiness checks, then rerun release evidence.",
            )
        )

    missing_refs = _missing_refs(production_gate)
    if missing_refs or not production_gate.get("production_target") or production_gate.get("local_indicator_count"):
        blockers: list[dict[str, Any]] = []
        if not production_gate.get("production_target"):
            blockers.append({"id": "target_environment", "status": "missing", "detail": "Production release environment is not selected."})
        if production_gate.get("local_indicator_count"):
            blockers.append({"id": "local_evidence", "status": "missing", "detail": "Configured evidence still contains local/test markers."})
        blockers.extend({"id": item["id"], "status": "missing", "detail": f"{item['setting']} is required."} for item in missing_refs)
        groups.append(
            _group(
                "production_scope",
                "Production scope",
                blockers,
                "Set production environment, approval ref and all required non-local evidence refs.",
            )
        )

    artifact_blockers = []
    if artifact_report.get("status") != "ready" or not artifact_report.get("production_ready") or not artifact_report.get("ready_for_sidebar"):
        artifact_blockers.append(
            {
                "id": "release_artifact",
                "status": str(artifact_report.get("status") or "missing"),
                "detail": str(artifact_report.get("detail") or "Release evidence artifact is not production-ready."),
            }
        )
    artifact_blockers.extend({"id": f"artifact_error_{index + 1}", "status": "missing", "detail": str(item)} for index, item in enumerate(artifact_report.get("errors") or []))
    if artifact_blockers:
        groups.append(
            _group(
                "release_artifact",
                "Release artifact",
                artifact_blockers,
                "Regenerate fresh production release evidence and render the handoff.",
            )
        )

    evidence_blockers = [{"id": str(item), "status": "blocked", "detail": str(item)} for item in artifact_summary.get("top_blockers") or []]
    if evidence_blockers:
        groups.append(
            _group(
                "release_evidence",
                "Release evidence blockers",
                evidence_blockers,
                "Follow release summary next steps and rerun verify_kubernetes_ops_release.",
            )
        )
    return groups


def _group(group_id: str, title: str, blockers: list[dict[str, Any]], next_step: str) -> dict[str, Any]:
    return {
        "id": group_id,
        "title": title,
        "status": "ready" if not blockers else "blocked",
        "count": len(blockers),
        "blockers": blockers[:12],
        "next_step": next_step,
    }


def _missing_refs(production_gate: dict[str, Any]) -> list[dict[str, str]]:
    refs = production_gate.get("missing_required_references") if isinstance(production_gate.get("missing_required_references"), list) else []
    result: list[dict[str, str]] = []
    for item in refs:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "id": str(item.get("id") or ""),
                "setting": str(item.get("setting") or ""),
                "expected": str(item.get("expected") or ""),
            }
        )
    return result


def _top_blockers(groups: list[dict[str, Any]]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    for group in groups:
        for item in group.get("blockers") or []:
            blockers.append(
                {
                    "group": str(group.get("id") or ""),
                    "id": str(item.get("id") or ""),
                    "status": str(item.get("status") or ""),
                    "detail": str(item.get("detail") or ""),
                }
            )
            if len(blockers) >= 8:
                return blockers
    return blockers


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _bool_setting(name: str) -> bool:
    return str(getattr(settings, name, "") or "").strip().lower() in {"1", "true", "yes", "on"}
