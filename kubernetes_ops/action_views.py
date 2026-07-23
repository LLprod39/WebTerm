from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from loguru import logger

from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sActionRequest, K8sAuditEvent
from kubernetes_ops.serializers import serialize_action_request
from kubernetes_ops.services.action_execution import execute_approved_action_request
from kubernetes_ops.services.action_requests import (
    ActionRequestValidationError,
    approve_external_action_request,
    create_kubernetes_action_request,
    record_external_action_verification,
    sanitized_action_rejection_payload,
)
from kubernetes_ops.services.action_sanitizers import reference_action_text
from kubernetes_ops.services.action_summary import build_action_request_summary
from kubernetes_ops.services.admin_resources import cluster_for_value
from kubernetes_ops.services.describe import sanitize_metadata
from kubernetes_ops.studio_drafts import app_for_diagnosis, create_kubernetes_diagnosis_draft
from studio.views.common import STUDIO_FEATURE_PIPELINES, _user_has_feature

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
