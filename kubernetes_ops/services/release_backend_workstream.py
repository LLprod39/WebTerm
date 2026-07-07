from __future__ import annotations

from typing import Any


EXTERNAL_RELEASE_BLOCKER_PREFIXES = (
    "release_scope:",
    "external_evidence_bundle:",
    "readonly_rbac_live:",
    "readiness:sidebar_release_scope",
    "readiness:release_evidence_artifact",
)


def can_enable_kubernetes_release_sidebar(
    *,
    production_ready: bool,
    ready_for_sidebar: bool,
    completion_audit: dict[str, Any],
    artifact_ready: bool = True,
    release_scope_ready: bool = True,
) -> bool:
    return bool(
        production_ready
        and ready_for_sidebar
        and artifact_ready
        and release_scope_ready
        and completion_audit.get("production_evidence_complete") is True
        and completion_audit.get("sidebar_enablement_complete") is True
    )


def build_kubernetes_release_backend_workstream(
    *,
    completion_audit: dict[str, Any],
    blocker_groups: list[dict[str, Any]],
    production_evidence_checklist: dict[str, Any],
    can_enable_sidebar: bool,
) -> dict[str, Any]:
    core_proofs = completion_audit.get("core_backend_proofs") if isinstance(completion_audit.get("core_backend_proofs"), list) else []
    completed_proofs = sum(1 for item in core_proofs if isinstance(item, dict) and item.get("complete"))
    runtime_missing = [str(item) for item in completion_audit.get("runtime_missing_required_checks") or []][:12]
    remaining_backend_gaps = _remaining_backend_gaps(core_proofs, runtime_missing)
    external_blockers = _external_production_blockers(
        completion_audit=completion_audit,
        blocker_groups=blocker_groups,
        production_evidence_checklist=production_evidence_checklist,
    )
    backend_complete = bool(completion_audit.get("core_backend_complete")) and bool(completion_audit.get("runtime_readiness_complete"))
    status = _status(can_enable_sidebar=can_enable_sidebar, backend_complete=backend_complete)
    return {
        "status": status,
        "plain_status": _plain_status(status),
        "backend_complete": backend_complete,
        "core_backend_complete": bool(completion_audit.get("core_backend_complete")),
        "runtime_readiness_complete": bool(completion_audit.get("runtime_readiness_complete")),
        "core_backend_proof_count": len(core_proofs),
        "core_backend_proof_ready_count": completed_proofs,
        "core_backend_percent": _percent(completed_proofs, len(core_proofs)),
        "remaining_backend_gap_count": len(remaining_backend_gaps),
        "remaining_backend_gaps": remaining_backend_gaps[:12],
        "external_production_blocker_count": len(external_blockers),
        "external_production_blockers": external_blockers[:12],
        "external_production_blocker_summary": _external_blocker_summary(external_blockers),
        "safe_to_continue_frontend": backend_complete,
        "next_backend_step": _next_step(
            status=status,
            remaining_backend_gaps=remaining_backend_gaps,
            production_evidence_checklist=production_evidence_checklist,
        ),
    }


def build_kubernetes_release_backend_workstream_blocker_groups(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    release_scope = evidence.get("release_scope") if isinstance(evidence.get("release_scope"), dict) else {}
    artifact_safety = evidence.get("artifact_safety") if isinstance(evidence.get("artifact_safety"), dict) else {}
    groups: list[dict[str, Any]] = []
    if _release_scope_blocked(release_scope):
        groups.append({"id": "production_scope", "status": str(release_scope.get("status") or "blocked"), "count": 1})
    if artifact_safety.get("status") != "ready" or not evidence.get("production_ready"):
        status = str(artifact_safety.get("status") or "blocked")
        if status == "ready" and not evidence.get("production_ready"):
            status = "not_production_ready"
        groups.append({"id": "release_artifact", "status": status, "count": 1})
    external_blocker_count = _external_release_blocker_count(evidence.get("blockers"))
    if external_blocker_count:
        groups.append({"id": "release_evidence", "status": "blocked", "count": external_blocker_count})
    return groups


def _status(*, can_enable_sidebar: bool, backend_complete: bool) -> str:
    if can_enable_sidebar:
        return "ready_for_sidebar"
    if backend_complete:
        return "backend_ready_production_blocked"
    return "backend_incomplete"


def _remaining_backend_gaps(core_proofs: list[Any], runtime_missing: list[str]) -> list[dict[str, str]]:
    gaps = [
        {"id": str(item.get("id") or ""), "type": "core_backend_proof", "status": str(item.get("status") or "")}
        for item in core_proofs
        if isinstance(item, dict) and not item.get("complete")
    ]
    gaps.extend({"id": item, "type": "runtime_readiness", "status": "missing"} for item in runtime_missing)
    return gaps


def _external_production_blockers(
    *,
    completion_audit: dict[str, Any],
    blocker_groups: list[dict[str, Any]],
    production_evidence_checklist: dict[str, Any],
) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    for item in completion_audit.get("production_scope_readiness_checks") or []:
        blockers.append({"id": str(item), "type": "production_scope_readiness", "status": "missing"})
    for item in completion_audit.get("production_evidence_checks") or []:
        if isinstance(item, dict) and not item.get("complete"):
            blockers.append({"id": str(item.get("id") or ""), "type": "production_evidence", "status": str(item.get("detail") or "blocked")})
    gap_summary = production_evidence_checklist.get("gap_summary") if isinstance(production_evidence_checklist.get("gap_summary"), dict) else {}
    next_gap = str(gap_summary.get("next_gap_id") or "")
    if next_gap and next_gap != "ready":
        blockers.append({"id": next_gap, "type": "production_evidence_checklist", "status": str(production_evidence_checklist.get("status") or "blocked")})
    for group in blocker_groups:
        if group.get("id") in {"production_scope", "release_artifact", "release_evidence"}:
            blockers.append({"id": str(group.get("id") or ""), "type": "blocker_group", "status": str(group.get("status") or "blocked")})
    return _unique_blockers(blockers)


def _unique_blockers(blockers: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for blocker in blockers:
        key = (blocker["id"], blocker["type"])
        if blocker["id"] and key not in seen:
            seen.add(key)
            result.append(blocker)
    return result


def _external_blocker_summary(blockers: list[dict[str, str]]) -> dict[str, Any]:
    category_rows: dict[str, dict[str, Any]] = {}
    for blocker in blockers:
        category = _external_blocker_category(blocker)
        row = category_rows.setdefault(
            category,
            {
                "id": category,
                "label": _external_blocker_category_label(category),
                "count": 0,
                "blocker_ids": [],
            },
        )
        row["count"] += 1
        if len(row["blocker_ids"]) < 8:
            row["blocker_ids"].append(blocker["id"])
    categories = [category_rows[item] for item in _external_blocker_category_order() if item in category_rows]
    categories.extend(row for key, row in category_rows.items() if key not in _external_blocker_category_order())
    primary = categories[0]["id"] if categories else "none"
    return {
        "count": len(blockers),
        "category_count": len(categories),
        "primary_category": primary,
        "plain_status": _external_blocker_summary_status(primary),
        "categories": categories,
    }


def _external_blocker_category(blocker: dict[str, str]) -> str:
    blocker_id = str(blocker.get("id") or "")
    blocker_type = str(blocker.get("type") or "")
    if blocker_id in {"target_environment", "no_local_indicators", "select_production_environment", "production_scope"}:
        return "production_scope"
    if blocker_id in {"required_references", "set_core_evidence_refs", "set_external_bundle_refs"}:
        return "production_refs"
    if blocker_id in {"refresh_external_evidence_bundle", "replace_local_evidence", "external_evidence_bundle", "release_evidence"}:
        return "external_bundle"
    if blocker_id == "release_artifact":
        return "release_artifact"
    if blocker_id in {"sidebar_release_scope", "release_evidence_artifact"} or blocker_type == "production_scope_readiness":
        return "readiness_gate"
    if blocker_type == "production_evidence_checklist":
        return "external_bundle"
    return "other"


def _external_blocker_category_order() -> tuple[str, ...]:
    return ("production_scope", "production_refs", "external_bundle", "release_artifact", "readiness_gate", "other")


def _external_blocker_category_label(category: str) -> str:
    return {
        "production_scope": "Production scope",
        "production_refs": "Production evidence refs",
        "external_bundle": "External evidence bundle",
        "release_artifact": "Release artifact",
        "readiness_gate": "Readiness gate",
        "other": "Other production blocker",
    }.get(category, category)


def _external_blocker_summary_status(primary_category: str) -> str:
    return {
        "none": "No external production blockers.",
        "production_scope": "Select production release scope and remove local/demo evidence first.",
        "production_refs": "Set the required production evidence references.",
        "external_bundle": "Refresh or fix the reviewed external production evidence bundle.",
        "release_artifact": "Regenerate the release evidence artifact after production evidence is ready.",
        "readiness_gate": "Fix the production readiness gate before sidebar enablement.",
        "other": "Review remaining production blockers.",
    }.get(primary_category, "Review remaining production blockers.")


def _plain_status(status: str) -> str:
    return {
        "ready_for_sidebar": "Backend and production/sidebar gates are complete.",
        "backend_ready_production_blocked": "Backend scope is complete; remaining work is production evidence/sidebar enablement.",
        "backend_incomplete": "Backend still has implementation or runtime-readiness gaps.",
    }.get(status, "Backend workstream requires operator review.")


def _next_step(
    *,
    status: str,
    remaining_backend_gaps: list[dict[str, str]],
    production_evidence_checklist: dict[str, Any],
) -> dict[str, Any]:
    if status == "backend_incomplete":
        return {"id": "close_backend_gaps", "type": "backend", "gap_count": len(remaining_backend_gaps)}
    if status == "ready_for_sidebar":
        return {"id": "none", "type": "complete", "gap_count": 0}
    gap_summary = production_evidence_checklist.get("gap_summary") if isinstance(production_evidence_checklist.get("gap_summary"), dict) else {}
    return {
        "id": str(gap_summary.get("next_gap_id") or "collect_production_evidence"),
        "type": "production_evidence",
        "gap_count": int(gap_summary.get("blocking_gap_count") or 0),
        "command_ids": [str(item) for item in gap_summary.get("next_command_ids") or []],
    }


def _percent(ready: int, total: int) -> int | None:
    if total <= 0:
        return None
    return int(round((ready / total) * 100))


def _release_scope_blocked(release_scope: dict[str, Any]) -> bool:
    if release_scope.get("status") != "ready":
        return True
    if str(release_scope.get("target_environment") or "") != "production":
        return True
    if int(release_scope.get("local_indicator_count") or 0):
        return True
    return bool(release_scope.get("missing_required_references"))


def _external_release_blocker_count(blockers: object) -> int:
    rows = blockers if isinstance(blockers, list) else []
    return sum(1 for item in rows if str(item).startswith(EXTERNAL_RELEASE_BLOCKER_PREFIXES))
