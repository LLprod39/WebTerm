from __future__ import annotations

import json
from typing import Any

from django.http import JsonResponse
from loguru import logger

from kubernetes_ops.models import K8sActionRequest, K8sAuditEvent
from kubernetes_ops.serializers import serialize_action_request
from kubernetes_ops.services.action_requests import (
    ActionRequestValidationError,
)
from kubernetes_ops.services.action_sanitizers import reference_action_text
from kubernetes_ops.services.admin_resources import cluster_for_value
from kubernetes_ops.services.describe import sanitize_metadata

ACTION_TIMELINE_LIMIT = 50
ACTION_TEXT_LIMIT = 1_000


def _json_body(request) -> tuple[dict[str, Any], JsonResponse | None]:
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}, JsonResponse({"success": False, "error": "Invalid JSON body"}, status=400)
    if not isinstance(data, dict):
        return {}, JsonResponse({"success": False, "error": "JSON body must be an object"}, status=400)
    return data, None


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes ops action API failed: %s", exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


def _staff_required(request) -> JsonResponse | None:
    if not getattr(request.user, "is_staff", False):
        return JsonResponse(
            {"success": False, "error": "Admin access is required.", "code": "admin_required"}, status=403
        )
    return None


def _can_read_action_request(user, action_request: K8sActionRequest) -> bool:
    if getattr(user, "is_staff", False):
        return True
    return bool(action_request.requested_by_id and action_request.requested_by_id == getattr(user, "id", None))


def _action_request_not_found() -> JsonResponse:
    return JsonResponse(
        {"success": False, "error": "Action request not found.", "code": "request_not_found"}, status=404
    )


def _action_error_status(error: ActionRequestValidationError) -> int:
    return 409 if error.code in {"action_request_not_pending", "action_request_not_approved"} else 400


def _audit_action_request(
    request, action: str, *, action_request: K8sActionRequest | None = None, payload: dict[str, Any] | None = None
) -> None:
    K8sAuditEvent.objects.create(
        user=request.user,
        username_snapshot=getattr(request.user, "username", ""),
        action=action,
        provider="webterm",
        cluster=action_request.cluster if action_request else None,
        payload=_safe_action_metadata(payload or {}),
    )


def _safe_action_request_payload(action_request: K8sActionRequest) -> dict[str, Any]:
    payload = serialize_action_request(action_request)
    for key in ("target", "preview", "execution_policy", "report"):
        payload[key] = _safe_action_metadata(payload.get(key) or {})
    payload["reason"] = _safe_action_text(payload.get("reason") or "")
    payload["approval_ref"] = _safe_action_text(payload.get("approval_ref") or "", limit=240)
    return payload


def _visible_action_requests_for_user(user, *, include_all: bool = False):
    queryset = K8sActionRequest.objects.select_related("requested_by", "cluster")
    if include_all and getattr(user, "is_staff", False):
        return queryset
    return queryset.filter(requested_by=user)


def _bounded_limit(value: str | None) -> int:
    try:
        limit = int(value) if value not in (None, "") else 50
    except (TypeError, ValueError):
        return 50
    return max(1, min(limit, 100))


def _apply_action_request_filters(queryset, request):
    status = str(request.GET.get("status") or "").strip()
    if status:
        queryset = queryset.filter(status=status)
    action = str(request.GET.get("action") or "").strip()
    if action:
        queryset = queryset.filter(action=action)
    risk_tier = str(request.GET.get("risk_tier") or "").strip()
    if risk_tier:
        queryset = queryset.filter(risk_tier=risk_tier)
    cluster_id = str(request.GET.get("cluster_id") or "").strip()
    if cluster_id:
        cluster = cluster_for_value(cluster_id)
        queryset = queryset.filter(cluster=cluster) if cluster is not None else queryset.none()
    return queryset


def _safe_action_request_timeline_event(event: K8sAuditEvent) -> dict[str, Any]:
    return {
        "action": event.action,
        "username": event.username_snapshot,
        "created_at": event.created_at.isoformat() if event.created_at else "",
        "payload": _safe_action_metadata(event.payload or {}),
    }


def _safe_action_metadata(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return "[truncated]"
    value = sanitize_metadata(value)
    if isinstance(value, dict):
        return {str(key)[:80]: _safe_action_metadata(item, depth=depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_action_metadata(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str):
        return _safe_action_text(value)
    return value


def _safe_action_text(value: Any, *, limit: int = ACTION_TEXT_LIMIT) -> str:
    return reference_action_text(value, limit=limit)


def _action_request_timeline(action_request: K8sActionRequest) -> list[dict[str, Any]]:
    events = K8sAuditEvent.objects.filter(
        action__startswith="k8s.action_request.",
        payload__request_id=str(action_request.request_id),
    ).order_by("created_at", "id")[:ACTION_TIMELINE_LIMIT]
    return [_safe_action_request_timeline_event(event) for event in events]


def _action_request_report_payload(action_request: K8sActionRequest) -> dict[str, Any]:
    request_payload = _safe_action_request_payload(action_request)
    timeline = _action_request_timeline(action_request)
    return {
        "success": True,
        "request_id": str(action_request.request_id),
        "status": action_request.status,
        "request": request_payload,
        "report": request_payload["report"],
        "execution_policy": request_payload["execution_policy"],
        "timeline": timeline,
        "summary": {
            "request_id": str(action_request.request_id),
            "action": action_request.action,
            "status": action_request.status,
            "risk_tier": action_request.risk_tier,
            "timeline_event_count": len(timeline),
            "verified": bool((action_request.report or {}).get("verified")),
            "native_execution_enabled": bool((action_request.execution_policy or {}).get("native_execution_enabled")),
        },
    }
