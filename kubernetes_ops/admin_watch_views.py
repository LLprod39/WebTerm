from __future__ import annotations

from typing import Any

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from loguru import logger

from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAdminSession, K8sAuditEvent
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.admin_watch import get_admin_resource_watch_preview


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes admin watch API failed: %s", exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


def _error_response(error: AdminResourceError) -> JsonResponse:
    return JsonResponse(
        {"success": False, "error": str(error), "code": error.code, "payload": error.payload}, status=error.status
    )


def _query(request, name: str, default: str = "") -> str:
    return str(request.GET.get(name) or default).strip()


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


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_admin_resource_watch(request, cluster_id: str):
    def handler():
        try:
            payload = get_admin_resource_watch_preview(
                user=request.user,
                session_id=_query(request, "session_id"),
                cluster_id=cluster_id,
                api_version=_query(request, "api_version", "v1"),
                kind=_query(request, "kind"),
                namespace=_query(request, "namespace"),
                name=_query(request, "name"),
                resource=_query(request, "resource"),
                resource_version=_query(request, "resource_version"),
                limit=_query(request, "limit", "20"),
                timeout_seconds=_query(request, "timeout_seconds", "10"),
            )
        except AdminResourceError as exc:
            _audit(
                request,
                "k8s.admin_resource.watch_rejected",
                payload={"code": exc.code, "cluster_id": cluster_id, "kind": _query(request, "kind")},
            )
            return _error_response(exc)
        _audit(
            request,
            "k8s.admin_resource.watch",
            payload={
                "cluster_id": cluster_id,
                "target": payload["target"],
                "event_count": payload.get("event_count", 0),
                "truncated": bool(payload.get("truncated")),
                "source": payload.get("source", ""),
            },
        )
        return JsonResponse(payload)

    return _safe_json(handler)
