from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from loguru import logger

from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAdminSession
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.admin_terminal import prepare_cluster_terminal_start, reject_cluster_terminal_stop


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
        logger.exception("kubernetes admin terminal API failed: %s", exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


def _error_response(error: AdminResourceError) -> JsonResponse:
    return JsonResponse(
        {"success": False, "error": str(error), "code": error.code, "payload": error.payload}, status=error.status
    )


def _session_for_user(user, session_id) -> K8sAdminSession | None:
    return (
        K8sAdminSession.objects.select_related("user", "approved_by", "provider", "cluster")
        .filter(session_id=session_id, user=user)
        .first()
    )


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_admin_terminal_start(request, session_id):
    def handler():
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        session = _session_for_user(request.user, session_id)
        if session is None:
            return JsonResponse(
                {"success": False, "error": "Admin session not found.", "code": "admin_session_not_found"}, status=404
            )
        try:
            envelope = prepare_cluster_terminal_start(
                user=request.user,
                session=session,
                reason=str(data.get("reason") or ""),
                include_restricted_context=str(data.get("include_restricted_context") or "").lower()
                in {"1", "true", "yes"},
            )
        except AdminResourceError as exc:
            return _error_response(exc)
        return JsonResponse({"success": True, "terminal": envelope})

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_admin_terminal_stop(request, session_id):
    def handler():
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        session = _session_for_user(request.user, session_id)
        if session is None:
            return JsonResponse(
                {"success": False, "error": "Admin session not found.", "code": "admin_session_not_found"}, status=404
            )
        try:
            reject_cluster_terminal_stop(
                user=request.user,
                session=session,
                action_id=str(data.get("action_id") or ""),
                reason=str(data.get("reason") or ""),
            )
        except AdminResourceError as exc:
            return _error_response(exc)
        return JsonResponse({"success": True})

    return _safe_json(handler)
