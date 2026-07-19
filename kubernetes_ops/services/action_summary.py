from __future__ import annotations

from typing import Any

from django.db.models import Count, QuerySet

from kubernetes_ops.models import K8sActionRequest
from kubernetes_ops.services.action_sanitizers import reference_action_text, sanitize_action_value
from kubernetes_ops.services.admin_resources import cluster_for_value

DEFAULT_QUEUE_LIMIT = 5
MAX_QUEUE_LIMIT = 20
ATTENTION_STATUSES = {
    K8sActionRequest.STATUS_PENDING_APPROVAL,
    K8sActionRequest.STATUS_APPROVED_EXTERNAL,
    K8sActionRequest.STATUS_EXECUTED_NATIVE,
    K8sActionRequest.STATUS_EXECUTION_BLOCKED,
    K8sActionRequest.STATUS_VERIFICATION_FAILED,
}
TERMINAL_STATUSES = {
    K8sActionRequest.STATUS_VERIFIED_EXTERNAL,
    K8sActionRequest.STATUS_VERIFIED_NATIVE,
    K8sActionRequest.STATUS_REJECTED,
}


def build_action_request_summary(
    *,
    user,
    include_all: bool = False,
    status: str = "",
    action: str = "",
    risk_tier: str = "",
    cluster_id: str = "",
    queue_limit: int | str | None = None,
) -> dict[str, Any]:
    queryset = _visible_queryset(user, include_all=include_all)
    queryset = _apply_filters(queryset, status=status, action=action, risk_tier=risk_tier, cluster_id=cluster_id)
    limit = _bounded_queue_limit(queue_limit)
    status_counts = _counts(queryset, "status", [item[0] for item in K8sActionRequest.STATUS_CHOICES])
    action_counts = _counts(queryset, "action", [item[0] for item in K8sActionRequest.ACTION_CHOICES])
    risk_counts = _counts(queryset, "risk_tier", [item[0] for item in K8sActionRequest.RISK_CHOICES])
    needs_verification = queryset.filter(status=K8sActionRequest.STATUS_EXECUTED_NATIVE)
    pending_approval = queryset.filter(status=K8sActionRequest.STATUS_PENDING_APPROVAL)
    approved_external = queryset.filter(status=K8sActionRequest.STATUS_APPROVED_EXTERNAL)
    blocked = queryset.filter(status__in=[K8sActionRequest.STATUS_EXECUTION_BLOCKED, K8sActionRequest.STATUS_VERIFICATION_FAILED])
    attention = queryset.filter(status__in=sorted(ATTENTION_STATUSES))
    high_risk_attention = attention.filter(risk_tier=K8sActionRequest.RISK_HIGH)
    return {
        "success": True,
        "mode": "read_only",
        "operation": "action_request_summary",
        "visibility": "staff_all" if include_all and getattr(user, "is_staff", False) else "requester",
        "filters": {
            "status": reference_action_text(status, limit=80),
            "action": reference_action_text(action, limit=120),
            "risk_tier": reference_action_text(risk_tier, limit=40),
            "cluster_id": reference_action_text(cluster_id, limit=120),
        },
        "counts": {
            "total": queryset.count(),
            "attention": attention.count(),
            "terminal": queryset.filter(status__in=sorted(TERMINAL_STATUSES)).count(),
            "pending_approval": pending_approval.count(),
            "approved_external": approved_external.count(),
            "needs_verification": needs_verification.count(),
            "blocked": blocked.count(),
            "high_risk_attention": high_risk_attention.count(),
            "production_like_attention": _production_like_attention_count(attention),
            "by_status": status_counts,
            "by_action": action_counts,
            "by_risk": risk_counts,
        },
        "queues": {
            "pending_approval": _queue_items(pending_approval, limit=limit),
            "approved_external": _queue_items(approved_external, limit=limit),
            "needs_verification": _queue_items(needs_verification, limit=limit),
            "blocked": _queue_items(blocked, limit=limit),
            "high_risk_attention": _queue_items(high_risk_attention, limit=limit),
        },
        "policy": {
            "mutates_state": False,
            "native_execution": False,
            "external_execution": False,
            "payload": "metadata_only",
        },
    }


def _visible_queryset(user, *, include_all: bool) -> QuerySet[K8sActionRequest]:
    queryset = K8sActionRequest.objects.select_related("requested_by", "cluster")
    if include_all and getattr(user, "is_staff", False):
        return queryset
    return queryset.filter(requested_by=user)


def _apply_filters(
    queryset: QuerySet[K8sActionRequest],
    *,
    status: str,
    action: str,
    risk_tier: str,
    cluster_id: str,
) -> QuerySet[K8sActionRequest]:
    status = str(status or "").strip()
    if status:
        queryset = queryset.filter(status=status)
    action = str(action or "").strip()
    if action:
        queryset = queryset.filter(action=action)
    risk_tier = str(risk_tier or "").strip()
    if risk_tier:
        queryset = queryset.filter(risk_tier=risk_tier)
    cluster_id = str(cluster_id or "").strip()
    if cluster_id:
        cluster = cluster_for_value(cluster_id)
        queryset = queryset.filter(cluster=cluster) if cluster is not None else queryset.none()
    return queryset


def _counts(queryset: QuerySet[K8sActionRequest], field: str, known_values: list[str]) -> dict[str, int]:
    counts = dict.fromkeys(known_values, 0)
    for row in queryset.values(field).annotate(total=Count("id")):
        counts[str(row.get(field) or "")] = int(row.get("total") or 0)
    return counts


def _bounded_queue_limit(value: int | str | None) -> int:
    try:
        limit = int(value) if value not in (None, "") else DEFAULT_QUEUE_LIMIT
    except (TypeError, ValueError):
        return DEFAULT_QUEUE_LIMIT
    return max(1, min(limit, MAX_QUEUE_LIMIT))


def _queue_items(queryset: QuerySet[K8sActionRequest], *, limit: int) -> list[dict[str, Any]]:
    return [_summary_item(action_request) for action_request in queryset.order_by("-updated_at", "-created_at", "-id")[:limit]]


def _summary_item(action_request: K8sActionRequest) -> dict[str, Any]:
    target = action_request.target if isinstance(action_request.target, dict) else {}
    report = action_request.report if isinstance(action_request.report, dict) else {}
    execution_policy = action_request.execution_policy if isinstance(action_request.execution_policy, dict) else {}
    rollback_plan = action_request.preview.get("rollback_plan") if isinstance(action_request.preview, dict) and isinstance(action_request.preview.get("rollback_plan"), dict) else {}
    verification_plan = report.get("verification_plan") if isinstance(report.get("verification_plan"), dict) else {}
    return {
        "id": str(action_request.request_id),
        "action": action_request.action,
        "status": action_request.status,
        "risk_tier": action_request.risk_tier,
        "requested_by": action_request.username_snapshot or getattr(action_request.requested_by, "username", ""),
        "cluster_id": f"cluster_{action_request.cluster_id}" if action_request.cluster_id else reference_action_text(target.get("cluster_id") or "", limit=120),
        "cluster_name": action_request.cluster.name if action_request.cluster_id else reference_action_text(target.get("cluster_name") or "", limit=160),
        "target": _target_summary(target),
        "flags": {
            "needs_approval": action_request.status == K8sActionRequest.STATUS_PENDING_APPROVAL,
            "needs_external_execution": action_request.status == K8sActionRequest.STATUS_APPROVED_EXTERNAL,
            "needs_verification": action_request.status == K8sActionRequest.STATUS_EXECUTED_NATIVE,
            "blocked": action_request.status in {K8sActionRequest.STATUS_EXECUTION_BLOCKED, K8sActionRequest.STATUS_VERIFICATION_FAILED},
            "verified": action_request.status in {K8sActionRequest.STATUS_VERIFIED_EXTERNAL, K8sActionRequest.STATUS_VERIFIED_NATIVE},
            "native_execution_enabled": bool(execution_policy.get("native_execution_enabled")),
            "approval_ref_present": bool(action_request.approval_ref),
            "reason_present": bool(action_request.reason),
        },
        "rollback": {
            "status": reference_action_text(rollback_plan.get("status") or "", limit=80),
            "strategy": reference_action_text(rollback_plan.get("strategy") or "", limit=120),
            "payload_stored": bool(rollback_plan.get("payload_stored")),
            "sensitive_values_stored": bool(rollback_plan.get("sensitive_values_stored")),
        },
        "verification": {
            "status": reference_action_text(verification_plan.get("status") or report.get("status") or "", limit=80),
            "mode": reference_action_text(verification_plan.get("mode") or report.get("verification_mode") or "", limit=120),
            "required": bool(verification_plan.get("required") or report.get("requires_verification")),
            "check_ids": [reference_action_text(item, limit=120) for item in (verification_plan.get("check_ids") or [])[:10]],
            "payload_stored": bool(verification_plan.get("payload_stored")),
            "sensitive_values_stored": bool(verification_plan.get("sensitive_values_stored")),
        },
        "report_url": f"/api/kubernetes/actions/{action_request.request_id}/report/",
        "created_at": action_request.created_at.isoformat() if action_request.created_at else "",
        "updated_at": action_request.updated_at.isoformat() if action_request.updated_at else "",
    }


def _target_summary(target: dict[str, Any]) -> dict[str, Any]:
    safe = sanitize_action_value(target)
    return {
        "namespace": reference_action_text(safe.get("namespace") or "", limit=120),
        "kind": reference_action_text(safe.get("kind") or "", limit=80),
        "name": reference_action_text(safe.get("name") or safe.get("resource") or safe.get("bundle_name") or "", limit=180),
        "workload_id": reference_action_text(safe.get("workload_id") or "", limit=120),
        "app_id": reference_action_text(safe.get("app_id") or "", limit=120),
        "bundle_id": reference_action_text(safe.get("bundle_id") or "", limit=120),
    }


def _production_like_attention_count(queryset: QuerySet[K8sActionRequest]) -> int:
    return queryset.filter(cluster__environment__icontains="prod").count()
