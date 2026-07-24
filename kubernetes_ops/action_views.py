from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from kubernetes_ops.action_views_helpers import (
    _action_error_status,
    _action_request_not_found,
    _action_request_report_payload,
    _apply_action_request_filters,
    _audit_action_request,
    _bounded_limit,
    _can_read_action_request,
    _json_body,
    _safe_action_request_payload,
    _safe_json,
    _staff_required,
    _visible_action_requests_for_user,
)
from kubernetes_ops.models import K8sActionRequest, K8sAuditEvent
from kubernetes_ops.services.action_execution import execute_approved_action_request
from kubernetes_ops.services.action_requests import (
    ActionRequestValidationError,
    approve_external_action_request,
    create_kubernetes_action_request,
    record_external_action_verification,
    sanitized_action_rejection_payload,
)
from kubernetes_ops.services.action_summary import build_action_request_summary
from kubernetes_ops.studio_drafts import app_for_diagnosis, create_kubernetes_diagnosis_draft
from studio.views.common import STUDIO_FEATURE_PIPELINES, _user_has_feature

ACTION_TIMELINE_LIMIT = 50
ACTION_TEXT_LIMIT = 1_000


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_diagnose_action(request):
    def handler():
        if not _user_has_feature(request.user, STUDIO_FEATURE_PIPELINES):
            return JsonResponse(
                {
                    "success": False,
                    "error": "Studio pipelines access is required.",
                    "code": "studio_required",
                },
                status=403,
            )
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        app = app_for_diagnosis(str(data.get("app_id") or ""))
        if app is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "app_id is required and must reference a known Kubernetes app.",
                    "code": "app_required",
                },
                status=400,
            )

        session = create_kubernetes_diagnosis_draft(user=request.user, app=app)
        K8sAuditEvent.objects.create(
            user=request.user,
            username_snapshot=getattr(request.user, "username", ""),
            action="k8s.diagnosis_draft.create",
            provider="webterm",
            cluster=app.cluster,
            payload={
                "draft_id": session.id,
                "app_id": app.id,
                "app_name": app.name,
                "namespace": app.namespace,
                "status": session.status,
            },
        )
        return JsonResponse(
            {
                "success": True,
                "draft": session.to_dict(include_latest=True),
                "target_url": f"/studio/drafts?draft={session.id}",
            },
            status=201,
        )

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_action_request_approval(request):
    def handler():
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        try:
            action_request = create_kubernetes_action_request(user=request.user, data=data)
        except ActionRequestValidationError as exc:
            payload = sanitized_action_rejection_payload(exc)
            _audit_action_request(
                request,
                "k8s.action_request.rejected",
                payload={"code": exc.code, "error": str(exc), **payload},
            )
            return JsonResponse({"success": False, "error": str(exc), "code": exc.code, "payload": payload}, status=400)
        _audit_action_request(
            request,
            "k8s.action_request.create",
            action_request=action_request,
            payload={
                "request_id": str(action_request.request_id),
                "action": action_request.action,
                "status": action_request.status,
                "target": action_request.target,
                "approval_ref": action_request.approval_ref,
            },
        )
        return JsonResponse({"success": True, "request": _safe_action_request_payload(action_request)}, status=201)

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["GET"])
def api_kubernetes_action_summary(request):
    def handler():
        include_all = str(request.GET.get("all") or "").lower() in {"1", "true", "yes"}
        payload = build_action_request_summary(
            user=request.user,
            include_all=include_all,
            status=request.GET.get("status", ""),
            action=request.GET.get("action", ""),
            risk_tier=request.GET.get("risk_tier", ""),
            cluster_id=request.GET.get("cluster_id", ""),
            queue_limit=request.GET.get("queue_limit"),
        )
        return JsonResponse(payload)

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["GET"])
def api_kubernetes_action_requests(request):
    def handler():
        include_all = str(request.GET.get("all") or "").lower() in {"1", "true", "yes"}
        queryset = _visible_action_requests_for_user(request.user, include_all=include_all)
        queryset = _apply_action_request_filters(queryset, request).order_by("-created_at", "-id")
        limit = _bounded_limit(request.GET.get("limit"))
        requests = list(queryset[:limit])
        return JsonResponse(
            {
                "success": True,
                "requests": [_safe_action_request_payload(action_request) for action_request in requests],
                "count": len(requests),
                "limit": limit,
            }
        )

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_action_approve_external(request, request_id):
    def handler():
        denied = _staff_required(request)
        if denied:
            return denied
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        action_request = K8sActionRequest.objects.filter(request_id=request_id).select_related("cluster").first()
        if action_request is None:
            return _action_request_not_found()
        try:
            action_request = approve_external_action_request(
                action_request=action_request, user=request.user, data=data
            )
        except ActionRequestValidationError as exc:
            payload = sanitized_action_rejection_payload(exc)
            _audit_action_request(
                request,
                "k8s.action_request.approval_rejected",
                action_request=action_request,
                payload={"request_id": str(action_request.request_id), "code": exc.code, "error": str(exc), **payload},
            )
            return JsonResponse(
                {"success": False, "error": str(exc), "code": exc.code, "payload": payload},
                status=_action_error_status(exc),
            )
        _audit_action_request(
            request,
            "k8s.action_request.approve_external",
            action_request=action_request,
            payload={
                "request_id": str(action_request.request_id),
                "action": action_request.action,
                "status": action_request.status,
                "approval_ref": action_request.approval_ref,
            },
        )
        return JsonResponse({"success": True, "request": _safe_action_request_payload(action_request)})

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_action_execute_approved(request):
    def handler():
        denied = _staff_required(request)
        if denied:
            return denied
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        request_id = str(data.get("request_id") or "").strip()
        if not request_id:
            return JsonResponse(
                {"success": False, "error": "request_id is required.", "code": "request_id_required"}, status=400
            )
        action_request = K8sActionRequest.objects.filter(request_id=request_id).select_related("cluster").first()
        if action_request is None:
            return _action_request_not_found()
        try:
            action_request = execute_approved_action_request(
                action_request=action_request, user=request.user, data=data
            )
        except ActionRequestValidationError as exc:
            payload = sanitized_action_rejection_payload(exc)
            _audit_action_request(
                request,
                "k8s.action_request.execute_rejected",
                action_request=action_request,
                payload={"request_id": str(action_request.request_id), "code": exc.code, "error": str(exc), **payload},
            )
            return JsonResponse(
                {"success": False, "error": str(exc), "code": exc.code, "payload": payload},
                status=_action_error_status(exc),
            )
        if action_request.status == K8sActionRequest.STATUS_EXECUTED_NATIVE:
            _audit_action_request(
                request,
                "k8s.action_request.execute_native",
                action_request=action_request,
                payload={
                    "request_id": str(action_request.request_id),
                    "action": action_request.action,
                    "status": action_request.status,
                    "admin_action_id": action_request.report.get("admin_action_id", ""),
                    "target": action_request.report.get("target", {}),
                },
            )
            return JsonResponse({"success": True, "request": _safe_action_request_payload(action_request)})
        _audit_action_request(
            request,
            "k8s.action_request.execute_blocked",
            action_request=action_request,
            payload={
                "request_id": str(action_request.request_id),
                "action": action_request.action,
                "status": action_request.status,
                "reason": action_request.report.get("blocked_reason", ""),
            },
        )
        return JsonResponse(
            {
                "success": False,
                "error": action_request.report.get("blocked_reason", "Execution is disabled."),
                "code": "execution_disabled_by_policy",
                "request": _safe_action_request_payload(action_request),
            },
            status=403,
        )

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["GET"])
def api_kubernetes_action_status(request, request_id):
    def handler():
        action_request = K8sActionRequest.objects.filter(request_id=request_id).select_related("cluster").first()
        if action_request is None or not _can_read_action_request(request.user, action_request):
            return _action_request_not_found()
        return JsonResponse({"success": True, "request": _safe_action_request_payload(action_request)})

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["GET"])
def api_kubernetes_action_report(request, request_id):
    def handler():
        action_request = K8sActionRequest.objects.filter(request_id=request_id).select_related("cluster").first()
        if action_request is None or not _can_read_action_request(request.user, action_request):
            return _action_request_not_found()
        return JsonResponse(_action_request_report_payload(action_request))

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_action_verify_external(request, request_id):
    def handler():
        denied = _staff_required(request)
        if denied:
            return denied
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        action_request = K8sActionRequest.objects.filter(request_id=request_id).select_related("cluster").first()
        if action_request is None:
            return _action_request_not_found()
        try:
            action_request = record_external_action_verification(
                action_request=action_request, user=request.user, data=data
            )
        except ActionRequestValidationError as exc:
            payload = sanitized_action_rejection_payload(exc)
            _audit_action_request(
                request,
                "k8s.action_request.verification_rejected",
                action_request=action_request,
                payload={"request_id": str(action_request.request_id), "code": exc.code, "error": str(exc), **payload},
            )
            return JsonResponse(
                {"success": False, "error": str(exc), "code": exc.code, "payload": payload},
                status=_action_error_status(exc),
            )
        audit_action = (
            "k8s.action_request.verify_native"
            if action_request.report.get("verification_mode") == "native_post_action"
            else "k8s.action_request.verify_external"
        )
        _audit_action_request(
            request,
            audit_action,
            action_request=action_request,
            payload={
                "request_id": str(action_request.request_id),
                "action": action_request.action,
                "status": action_request.status,
                "verified": bool(action_request.report.get("verified")),
                "external_ref": action_request.report.get("external_ref", ""),
            },
        )
        return JsonResponse({"success": True, "request": _safe_action_request_payload(action_request)})

    return _safe_json(handler)
