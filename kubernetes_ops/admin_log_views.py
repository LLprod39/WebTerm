from __future__ import annotations

from typing import Any

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from loguru import logger

from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAdminSession, K8sAuditEvent
from kubernetes_ops.services.admin_logs import get_admin_pod_log_snapshot
from kubernetes_ops.services.admin_resources import AdminResourceError


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes admin logs API failed: %s", exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


def _error_response(error: AdminResourceError) -> JsonResponse:
    return JsonResponse(
        {
            "success": False,
            "error": str(error),
            "code": error.code,
            "payload": error.payload,
        },
        status=error.status,
    )


def _query(request, name: str, default: str = "") -> str:
    return str(request.GET.get(name) or default).strip()


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_admin_pod_logs(request, cluster_id: str):
    def handler():
        try:
            payload = get_admin_pod_log_snapshot(
                user=request.user,
                session_id=_query(request, "session_id"),
                cluster_id=cluster_id,
                namespace=_query(request, "namespace"),
                pod_name=_query(request, "pod") or _query(request, "name"),
                container=_query(request, "container"),
                tail_lines=_query(request, "tail", "120"),
            )
        except AdminResourceError as exc:
            _audit(
                request,
                "k8s.admin_resource.logs_rejected",
                payload={"code": exc.code, "cluster_id": cluster_id, "namespace": _query(request, "namespace"), "pod": _query(request, "pod") or _query(request, "name")},
            )
            return _error_response(exc)
        _audit(
            request,
            "k8s.admin_resource.logs",
            payload={
                "cluster_id": cluster_id,
                "target": payload["target"],
                "source": payload.get("source", ""),
                "available": bool(payload.get("available")),
                "line_count": payload.get("line_count", 0),
                "truncated": bool(payload.get("truncated")),
            },
        )
        return JsonResponse(payload)

    return _safe_json(handler)


def _audit(request, action: str, *, payload: dict[str, Any]) -> None:
    session = _session_for_audit(_query(request, "session_id"))
    K8sAuditEvent.objects.create(
        user=request.user,
        username_snapshot=getattr(request.user, "username", ""),
        action=action,
        provider="webterm",
        cluster=session.cluster if session and session.cluster_id else None,
        payload={"session_id": str(session.session_id) if session else _query(request, "session_id")[:80], **payload},
    )


def _session_for_audit(session_id: str) -> K8sAdminSession | None:
    if not session_id:
        return None
    try:
        return K8sAdminSession.objects.select_related("cluster").filter(session_id=session_id).first()
    except (TypeError, ValueError, ValidationError):
        return None
