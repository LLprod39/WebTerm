from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods
from loguru import logger

from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAdminSession, K8sAuditEvent
from kubernetes_ops.serializers import serialize_admin_session
from kubernetes_ops.services.admin_restricted_context import build_restricted_kube_context_for_session
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.admin_sessions import (
    AdminSessionValidationError,
    approve_admin_session,
    close_admin_session,
    create_admin_session,
    refresh_admin_session_state,
    review_break_glass_session,
    revoke_admin_session,
    visible_admin_sessions_for_user,
)


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
        logger.exception("kubernetes admin session API failed: %s", exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


def _error_response(error: AdminSessionValidationError) -> JsonResponse:
    return JsonResponse(
        {
            "success": False,
            "error": str(error),
            "code": error.code,
            "payload": error.payload,
        },
        status=error.status,
    )


def _resource_error_response(error: AdminResourceError) -> JsonResponse:
    return JsonResponse(
        {
            "success": False,
            "error": str(error),
            "code": error.code,
            "payload": error.payload,
        },
        status=error.status,
    )


def _audit(request, action: str, *, session: K8sAdminSession | None = None, payload: dict[str, Any] | None = None) -> None:
    K8sAuditEvent.objects.create(
        user=request.user,
        username_snapshot=getattr(request.user, "username", ""),
        action=action,
        provider="webterm",
        cluster=session.cluster if session else None,
        payload={
            "session_id": str(session.session_id) if session else "",
            "mode": session.mode if session else "",
            "status": session.status if session else "",
            **(payload or {}),
        },
    )


def _session_queryset_for_user(user, *, for_approval: bool = False):
    if for_approval and getattr(user, "is_staff", False):
        return K8sAdminSession.objects.select_related("user", "approved_by", "provider", "cluster")
    return visible_admin_sessions_for_user(user)


def _session_or_none(user, session_id, *, for_approval: bool = False) -> K8sAdminSession | None:
    return _session_queryset_for_user(user, for_approval=for_approval).filter(session_id=session_id).first()


@login_required
@require_feature("kubernetes")
@require_http_methods(["GET", "POST"])
def api_kubernetes_admin_sessions(request):
    def handler():
        if request.method == "GET":
            include_all = str(request.GET.get("all") or "").lower() in {"1", "true", "yes"}
            sessions = visible_admin_sessions_for_user(request.user, include_all=include_all).order_by("-created_at", "-id")[:100]
            refreshed = [refresh_admin_session_state(session) for session in sessions]
            return JsonResponse({"success": True, "sessions": [serialize_admin_session(session) for session in refreshed]})

        data, error_response = _json_body(request)
        if error_response:
            return error_response
        try:
            session = create_admin_session(user=request.user, data=data)
        except AdminSessionValidationError as exc:
            _audit(
                request,
                "k8s.admin_session.rejected",
                payload={"code": exc.code, "error": str(exc), "mode": str(data.get("mode") or "")},
            )
            return _error_response(exc)
        _audit(request, "k8s.admin_session.create", session=session)
        return JsonResponse({"success": True, "session": serialize_admin_session(session)}, status=201)

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_admin_session_detail(request, session_id):
    def handler():
        session = _session_or_none(request.user, session_id)
        if session is None:
            return JsonResponse({"success": False, "error": "Admin session not found.", "code": "admin_session_not_found"}, status=404)
        return JsonResponse({"success": True, "session": serialize_admin_session(refresh_admin_session_state(session))})

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_admin_session_approve(request, session_id):
    def handler():
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        session = _session_or_none(request.user, session_id, for_approval=True)
        if session is None:
            return JsonResponse({"success": False, "error": "Admin session not found.", "code": "admin_session_not_found"}, status=404)
        try:
            session = approve_admin_session(session=session, user=request.user, data=data)
        except AdminSessionValidationError as exc:
            _audit(request, "k8s.admin_session.approval_rejected", session=session, payload={"code": exc.code, "error": str(exc)})
            return _error_response(exc)
        _audit(request, "k8s.admin_session.approve", session=session, payload={"approval_ref": session.approval_ref})
        return JsonResponse({"success": True, "session": serialize_admin_session(session)})

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_admin_session_revoke(request, session_id):
    def handler():
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        session = _session_or_none(request.user, session_id, for_approval=True)
        if session is None:
            return JsonResponse({"success": False, "error": "Admin session not found.", "code": "admin_session_not_found"}, status=404)
        try:
            session = revoke_admin_session(session=session, user=request.user, reason=str(data.get("reason") or ""))
        except AdminSessionValidationError as exc:
            _audit(request, "k8s.admin_session.revoke_rejected", session=session, payload={"code": exc.code, "error": str(exc)})
            return _error_response(exc)
        _audit(request, "k8s.admin_session.revoke", session=session)
        return JsonResponse({"success": True, "session": serialize_admin_session(session)})

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_admin_session_close(request, session_id):
    def handler():
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        session = _session_or_none(request.user, session_id, for_approval=True)
        if session is None:
            return JsonResponse({"success": False, "error": "Admin session not found.", "code": "admin_session_not_found"}, status=404)
        try:
            session = close_admin_session(session=session, user=request.user, reason=str(data.get("reason") or ""))
        except AdminSessionValidationError as exc:
            _audit(request, "k8s.admin_session.close_rejected", session=session, payload={"code": exc.code, "error": str(exc)})
            return _error_response(exc)
        _audit(request, "k8s.admin_session.close", session=session)
        return JsonResponse({"success": True, "session": serialize_admin_session(session)})

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_admin_session_review(request, session_id):
    def handler():
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        session = _session_or_none(request.user, session_id, for_approval=True)
        if session is None:
            return JsonResponse({"success": False, "error": "Admin session not found.", "code": "admin_session_not_found"}, status=404)
        try:
            session = review_break_glass_session(session=session, user=request.user, data=data)
        except AdminSessionValidationError as exc:
            _audit(request, "k8s.admin_session.post_review_rejected", session=session, payload={"code": exc.code, "error": str(exc)})
            return _error_response(exc)
        _audit(request, "k8s.admin_session.post_review", session=session, payload=session.metadata.get("post_review", {}))
        return JsonResponse({"success": True, "session": serialize_admin_session(session)})

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_admin_session_restricted_context(request, session_id):
    def handler():
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        session = _session_or_none(request.user, session_id, for_approval=True)
        if session is None:
            return JsonResponse({"success": False, "error": "Admin session not found.", "code": "admin_session_not_found"}, status=404)
        try:
            context = build_restricted_kube_context_for_session(
                session=session,
                include_manifest=str(data.get("include_manifest") or "").lower() in {"1", "true", "yes"},
            )
        except AdminResourceError as exc:
            _audit(request, "k8s.admin_session.restricted_context_rejected", session=session, payload={"code": exc.code, "error": str(exc)})
            return _resource_error_response(exc)
        _audit(
            request,
            "k8s.admin_session.restricted_context",
            session=session,
            payload={
                "namespace": context["namespace"],
                "service_account_name": context["service_account_name"],
                "ttl_seconds": context["ttl_seconds"],
                "applies_manifest": False,
            },
        )
        return JsonResponse({"success": True, "restricted_context": context})

    return _safe_json(handler)
