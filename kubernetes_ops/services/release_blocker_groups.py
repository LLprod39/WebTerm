"""Blocker grouping/formatting helpers for the release readiness summary.

Extracted from release_readiness_summary.py to keep modules under the size limit.
"""
from __future__ import annotations

from typing import Any

from django.conf import settings

from kubernetes_ops.services.release_completion_audit import PRODUCTION_SCOPE_READINESS_CHECK_IDS

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
