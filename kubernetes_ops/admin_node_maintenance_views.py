from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from loguru import logger

from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAdminSession, K8sAuditEvent
from kubernetes_ops.services.admin_node_maintenance import run_node_maintenance_action
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
        logger.exception("kubernetes admin node maintenance API failed: %s", exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


def _error_response(error: AdminResourceError) -> JsonResponse:
    return JsonResponse(
        {"success": False, "error": str(error), "code": error.code, "payload": error.payload}, status=error.status
    )


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_admin_node_cordon(request, cluster_id: str):
    return _node_action(request, cluster_id=cluster_id, action="cordon")


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_admin_node_uncordon(request, cluster_id: str):
    return _node_action(request, cluster_id=cluster_id, action="uncordon")


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_admin_node_drain(request, cluster_id: str):
    return _node_action(request, cluster_id=cluster_id, action="drain")


def _node_action(request, *, cluster_id: str, action: str):
    def handler():
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        session_id = str(data.get("session_id") or "")
        try:
            payload = run_node_maintenance_action(
                user=request.user,
                session_id=session_id,
                cluster_id=cluster_id,
                action=action,
                node_name=str(data.get("node_name") or data.get("node") or ""),
                reason=str(data.get("reason") or ""),
                confirmation=str(data.get("confirmation") or ""),
                options=data.get("options") if isinstance(data.get("options"), dict) else {},
            )
        except AdminResourceError as exc:
            _audit(
                request,
                f"k8s.admin_node_maintenance.{action}_rejected",
                payload={
                    "code": exc.code,
                    "cluster_id": cluster_id,
                    "node": str(data.get("node_name") or data.get("node") or "")[:253],
                },
                session_id=session_id,
            )
            return _error_response(exc)
        _audit(
            request,
            f"k8s.admin_node_maintenance.{action}",
            payload={
                "cluster_id": cluster_id,
                "target": payload["target"],
                "status": payload["status"],
                "action_id": payload.get("action", {}).get("id", ""),
                "blocked_reason": payload.get("blocked_reason", ""),
                "unschedulable": payload.get("unschedulable"),
            },
            session_id=session_id,
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
