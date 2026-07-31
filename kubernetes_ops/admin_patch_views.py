from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from loguru import logger

from core_ui.api_errors import internal_error_response
from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAdminSession, K8sAuditEvent
from kubernetes_ops.services.admin_patch import patch_kubernetes_resource
from kubernetes_ops.services.admin_resources import AdminResourceError


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
        logger.exception("kubernetes admin patch API failed: %s", exc)
        return internal_error_response(None, exc)


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


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_admin_patch(request, cluster_id: str):
    def handler():
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        try:
            payload = patch_kubernetes_resource(
                user=request.user,
                session_id=str(data.get("session_id") or ""),
                cluster_id=cluster_id,
                api_version=str(data.get("api_version") or "v1"),
                kind=str(data.get("kind") or ""),
                namespace=str(data.get("namespace") or ""),
                name=str(data.get("name") or ""),
                resource=str(data.get("resource") or ""),
                patch_type=str(data.get("patch_type") or "merge"),
                patch_body=data.get("patch"),
                reason=str(data.get("reason") or ""),
            )
        except AdminResourceError as exc:
            _audit(
                request,
                "k8s.admin_resource.patch_rejected",
                payload={"code": exc.code, "cluster_id": cluster_id},
                session_id=str(data.get("session_id") or ""),
            )
            return _error_response(exc)
        _audit(
            request,
            "k8s.admin_resource.patch",
            payload={
                "cluster_id": cluster_id,
                "target": payload["target"],
                "patch_type": payload.get("patch_type"),
                "redacted": bool(payload.get("redacted")),
                "action_id": payload.get("action", {}).get("id", ""),
            },
            session_id=str(data.get("session_id") or ""),
        )
        return JsonResponse(payload)

    return _safe_json(handler)


def _audit(request, action: str, *, payload: dict[str, Any], session_id: str) -> None:
    session = _session_for_audit(session_id)
    K8sAuditEvent.objects.create(
        user=request.user,
        username_snapshot=getattr(request.user, "username", ""),
        action=action,
        provider="webterm",
        cluster=session.cluster if session and session.cluster_id else None,
        payload={"session_id": str(session.session_id) if session else session_id[:80], **payload},
    )


def _session_for_audit(session_id: str) -> K8sAdminSession | None:
    if not session_id:
        return None
    try:
        return K8sAdminSession.objects.select_related("cluster").filter(session_id=session_id).first()
    except (TypeError, ValueError, ValidationError):
        return None
