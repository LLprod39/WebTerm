from __future__ import annotations

from typing import Any


def safe_release_handoff_backend_workstream(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": str(payload.get("status") or ""),
        "plain_status": str(payload.get("plain_status") or ""),
        "backend_complete": bool(payload.get("backend_complete")),
        "core_backend_complete": bool(payload.get("core_backend_complete")),
        "runtime_readiness_complete": bool(payload.get("runtime_readiness_complete")),
        "core_backend_proof_count": int(payload.get("core_backend_proof_count") or 0),
        "core_backend_proof_ready_count": int(payload.get("core_backend_proof_ready_count") or 0),
        "core_backend_percent": payload.get("core_backend_percent"),
        "remaining_backend_gap_count": int(payload.get("remaining_backend_gap_count") or 0),
        "remaining_backend_gaps": _safe_workstream_items(payload.get("remaining_backend_gaps")),
        "external_production_blocker_count": int(payload.get("external_production_blocker_count") or 0),
        "external_production_blockers": _safe_workstream_items(payload.get("external_production_blockers")),
        "external_production_blocker_summary": _safe_external_blocker_summary(payload.get("external_production_blocker_summary")),
        "safe_to_continue_frontend": bool(payload.get("safe_to_continue_frontend")),
        "next_backend_step": _safe_next_step(payload.get("next_backend_step")),
    }


def backend_workstream_primary_blocker_category(backend_workstream: dict[str, Any]) -> str:
    summary = backend_workstream.get("external_production_blocker_summary")
    if not isinstance(summary, dict):
        return "unknown"
    return str(summary.get("primary_category") or "unknown")


def _safe_external_blocker_summary(value: object) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    categories = data.get("categories") if isinstance(data.get("categories"), list) else []
    return {
        "count": int(data.get("count") or 0),
        "category_count": int(data.get("category_count") or 0),
        "primary_category": str(data.get("primary_category") or "none"),
        "plain_status": str(data.get("plain_status") or ""),
        "categories": [_safe_external_blocker_category(item) for item in categories[:8] if isinstance(item, dict)],
    }


def _safe_external_blocker_category(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "label": str(item.get("label") or ""),
        "count": int(item.get("count") or 0),
        "blocker_ids": [str(value) for value in item.get("blocker_ids") or []][:8],
    }


def _safe_workstream_items(value: object) -> list[dict[str, str]]:
    rows = value if isinstance(value, list) else []
    return [
        {"id": str(item.get("id") or ""), "type": str(item.get("type") or ""), "status": str(item.get("status") or "")}
        for item in rows[:12]
        if isinstance(item, dict)
    ]


def _safe_next_step(value: object) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    return {
        "id": str(data.get("id") or ""),
        "type": str(data.get("type") or ""),
        "gap_count": int(data.get("gap_count") or 0),
        "command_ids": [str(item) for item in data.get("command_ids") or []][:8],
    }
