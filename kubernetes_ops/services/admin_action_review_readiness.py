from __future__ import annotations

from typing import Any

from django.db import OperationalError, ProgrammingError

from kubernetes_ops.models import K8sAdminAction, K8sAdminSession
from kubernetes_ops.services.describe import sanitize_metadata

BREAK_GLASS_REVIEW_VERBS = {
    K8sAdminAction.VERB_EXEC,
    K8sAdminAction.VERB_PORT_FORWARD,
    K8sAdminAction.VERB_CLUSTER_TERMINAL,
    K8sAdminAction.VERB_NODE_DEBUG,
    K8sAdminAction.VERB_CORDON,
    K8sAdminAction.VERB_UNCORDON,
    K8sAdminAction.VERB_DRAIN,
}
WRITE_REVIEW_VERBS = {
    K8sAdminAction.VERB_DRY_RUN_APPLY,
    K8sAdminAction.VERB_APPLY,
    K8sAdminAction.VERB_PATCH,
    K8sAdminAction.VERB_SCALE,
    K8sAdminAction.VERB_RESTART,
    K8sAdminAction.VERB_DELETE,
}
FINAL_ACTION_STATUSES = {
    K8sAdminAction.STATUS_DRY_RUN,
    K8sAdminAction.STATUS_EXECUTION_BLOCKED,
    K8sAdminAction.STATUS_COMPLETED,
    K8sAdminAction.STATUS_FAILED,
}
DEFAULT_SCAN_LIMIT = 1000
PENDING_PREVIEW_LIMIT = 20


def _action_needs_post_review(action: K8sAdminAction) -> bool:
    return action.session.mode == K8sAdminSession.MODE_BREAK_GLASS or action.verb in BREAK_GLASS_REVIEW_VERBS | WRITE_REVIEW_VERBS


def _has_post_review(action: K8sAdminAction) -> bool:
    response_summary = action.response_summary if isinstance(action.response_summary, dict) else {}
    return isinstance(response_summary.get("post_review"), dict)


def _post_review_status(action: K8sAdminAction) -> str:
    if _has_post_review(action):
        return "completed"
    if not _action_needs_post_review(action):
        return "none"
    if action.status in FINAL_ACTION_STATUSES:
        return "pending"
    return "not_ready"


def _pending_action_payload(action: K8sAdminAction) -> dict[str, Any]:
    return sanitize_metadata(
        {
            "action_id": str(action.action_id),
            "session_id": str(action.session.session_id),
            "verb": action.verb,
            "status": action.status,
            "cluster": action.cluster.name if action.cluster_id else "",
            "namespace": action.namespace,
            "resource_kind": action.resource_kind,
            "resource_name": action.resource_name,
            "created_at": action.created_at.isoformat() if action.created_at else None,
        }
    )


def build_admin_action_post_review_report(*, scan_limit: int = DEFAULT_SCAN_LIMIT) -> dict[str, Any]:
    try:
        queryset = K8sAdminAction.objects.select_related("session", "cluster").order_by("-created_at", "-id")
        summary = {"pending": 0, "completed": 0, "not_ready": 0, "none": 0, "scanned": 0}
        pending_actions: list[dict[str, Any]] = []
        truncated = False
        bounded_scan_limit = max(1, min(int(scan_limit or DEFAULT_SCAN_LIMIT), DEFAULT_SCAN_LIMIT))
        for action in queryset[: bounded_scan_limit + 1]:
            if summary["scanned"] >= bounded_scan_limit:
                truncated = True
                break
            summary["scanned"] += 1
            status = _post_review_status(action)
            summary[status] += 1
            if status == "pending" and len(pending_actions) < PENDING_PREVIEW_LIMIT:
                pending_actions.append(_pending_action_payload(action))
    except (OperationalError, ProgrammingError):
        return {
            "status": "missing",
            "available": False,
            "summary": {},
            "pending_actions": [],
            "detail": "Kubernetes Admin Mode action tables are not ready.",
        }

    status = "manual" if summary["pending"] or truncated else "ready"
    if summary["pending"]:
        detail = f"Admin action post-review has pending items: {summary['pending']}."
    elif truncated:
        detail = f"Admin action post-review scan reached {bounded_scan_limit} rows; review the action queue manually."
    else:
        detail = "No pending Admin action post-review items."
    return {
        "status": status,
        "available": True,
        "summary": summary,
        "pending_actions": pending_actions,
        "pending_url": "/api/kubernetes/admin/actions/?all=1&post_review_status=pending",
        "scan_limit": bounded_scan_limit,
        "truncated": truncated,
        "detail": detail,
    }


def kubernetes_admin_action_post_review_check() -> dict[str, Any]:
    report = build_admin_action_post_review_report()
    return {
        "id": "admin_action_post_review",
        "status": report["status"],
        "detail": report["detail"],
        "required": False,
    }
