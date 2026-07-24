from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from core_ui.decorators import require_feature
from kubernetes_ops.admin_action_views_helpers import (
    AdminActionReviewError,
    _action_for_user_or_none,
    _actions_with_review_filter,
    _admin_action_report,
    _apply_action_filters,
    _audit_action_review,
    _bounded_limit,
    _bounded_review_scan_limit,
    _error_response,
    _json_body,
    _post_review_from_action,
    _review_admin_action,
    _review_summary,
    _safe_admin_action_payload,
    _safe_json,
    _visible_actions_for_user,
)
from kubernetes_ops.models import K8sAdminAction

ACTION_REVIEW_OUTCOMES = {"accepted", "verified", "needs_followup", "incident_created"}
BREAK_GLASS_REVIEW_VERBS = {
    K8sAdminAction.VERB_EXEC,
    K8sAdminAction.VERB_PORT_FORWARD,
    K8sAdminAction.VERB_CLUSTER_TERMINAL,
    K8sAdminAction.VERB_NODE_DEBUG,
    K8sAdminAction.VERB_CORDON,
    K8sAdminAction.VERB_UNCORDON,
    K8sAdminAction.VERB_DRAIN,
}
WRITE_REVIEW_VERBS = {
    K8sAdminAction.VERB_DRY_RUN_APPLY,
    K8sAdminAction.VERB_APPLY,
    K8sAdminAction.VERB_PATCH,
    K8sAdminAction.VERB_SCALE,
    K8sAdminAction.VERB_RESTART,
    K8sAdminAction.VERB_DELETE,
}
FINAL_ACTION_STATUSES = {
    K8sAdminAction.STATUS_DRY_RUN,
    K8sAdminAction.STATUS_EXECUTION_BLOCKED,
    K8sAdminAction.STATUS_COMPLETED,
    K8sAdminAction.STATUS_FAILED,
}
ACTION_REVIEW_FILTERS = {"pending", "completed", "not_ready", "required", "any", "none"}
DEFAULT_REVIEW_SCAN_LIMIT = 500
MAX_REVIEW_SCAN_LIMIT = 1000


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_admin_actions(request):
    def handler():
        include_all = str(request.GET.get("all") or "").lower() in {"1", "true", "yes"}
        queryset = _visible_actions_for_user(request.user, include_all=include_all)
        queryset = _apply_action_filters(queryset, request).order_by("-created_at", "-id")
        limit = _bounded_limit(request.GET.get("limit"))
        review_filter = str(request.GET.get("post_review_status") or "").strip()
        if review_filter and review_filter not in ACTION_REVIEW_FILTERS:
            return JsonResponse(
                {
                    "success": False,
                    "error": "post_review_status must be pending, completed, not_ready, required, any, or none.",
                    "code": "post_review_status_invalid",
                },
                status=400,
            )
        if review_filter:
            scan_limit = _bounded_review_scan_limit(request.GET.get("review_scan_limit"))
            actions, scanned_count, truncated = _actions_with_review_filter(
                queryset, review_filter=review_filter, limit=limit, scan_limit=scan_limit
            )
        else:
            scan_limit = 0
            scanned_count = 0
            truncated = False
            actions = list(queryset[:limit])
        payload = {
            "success": True,
            "actions": [_safe_admin_action_payload(action) for action in actions],
            "count": len(actions),
            "limit": limit,
            "review_summary": _review_summary(actions),
        }
        if review_filter:
            payload.update(
                {
                    "post_review_status": review_filter,
                    "review_scan_limit": scan_limit,
                    "review_scanned_count": scanned_count,
                    "review_scan_truncated": truncated,
                }
            )
        return JsonResponse(payload)

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_admin_action_detail(request, action_id):
    def handler():
        action = _action_for_user_or_none(request.user, action_id)
        if action is None:
            return JsonResponse(
                {"success": False, "error": "Admin action not found.", "code": "admin_action_not_found"}, status=404
            )
        return JsonResponse({"success": True, "action": _safe_admin_action_payload(action)})

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_admin_action_report(request, action_id):
    def handler():
        action = _action_for_user_or_none(request.user, action_id)
        if action is None:
            return JsonResponse(
                {"success": False, "error": "Admin action not found.", "code": "admin_action_not_found"}, status=404
            )
        return JsonResponse({"success": True, "report": _admin_action_report(action)})

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_admin_action_review(request, action_id):
    def handler():
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        action = _action_for_user_or_none(request.user, action_id)
        if action is None:
            return JsonResponse(
                {"success": False, "error": "Admin action not found.", "code": "admin_action_not_found"}, status=404
            )
        try:
            action = _review_admin_action(action=action, user=request.user, data=data)
        except AdminActionReviewError as exc:
            _audit_action_review(
                request, action, "k8s.admin_action.post_review_rejected", {"code": exc.code, "error": str(exc)}
            )
            return _error_response(exc)
        post_review = _post_review_from_action(action)
        _audit_action_review(request, action, "k8s.admin_action.post_review", {"post_review": post_review})
        return JsonResponse({"success": True, "action": _safe_admin_action_payload(action), "post_review": post_review})

    return _safe_json(handler)
