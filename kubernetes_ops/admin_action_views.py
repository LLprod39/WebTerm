from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods
from loguru import logger

from app.egress_redaction import redact_egress_text
from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sAuditEvent
from kubernetes_ops.permissions import kubernetes_permission_policy
from kubernetes_ops.serializers import serialize_admin_action, serialize_admin_session
from kubernetes_ops.services.admin_recording_evidence import safe_recording_payload
from kubernetes_ops.services.admin_resources import cluster_for_value
from kubernetes_ops.services.describe import sanitize_metadata

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


class AdminActionReviewError(ValueError):
    def __init__(self, message: str, *, code: str, status: int = 400, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.payload = payload or {}


def _json_body(request) -> tuple[dict[str, Any], JsonResponse | None]:
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}, JsonResponse({"success": False, "error": "Invalid JSON body"}, status=400)
    if not isinstance(data, dict):
        return {}, JsonResponse({"success": False, "error": "JSON body must be an object"}, status=400)
    return data, None


def _error_response(error: AdminActionReviewError) -> JsonResponse:
    return JsonResponse(
        {
            "success": False,
            "error": str(error),
            "code": error.code,
            "payload": error.payload,
        },
        status=error.status,
    )


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes admin action API failed: %s", exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


def _visible_actions_for_user(user, *, include_all: bool = False):
    queryset = K8sAdminAction.objects.select_related("session", "user", "cluster")
    if include_all and getattr(user, "is_staff", False):
        return queryset
    return queryset.filter(Q(user=user) | Q(session__user=user))


def _bounded_limit(value: str | None) -> int:
    try:
        limit = int(value) if value not in (None, "") else 50
    except (TypeError, ValueError):
        return 50
    return max(1, min(limit, 100))


def _bounded_review_scan_limit(value: str | None) -> int:
    try:
        limit = int(value) if value not in (None, "") else DEFAULT_REVIEW_SCAN_LIMIT
    except (TypeError, ValueError):
        return DEFAULT_REVIEW_SCAN_LIMIT
    return max(1, min(limit, MAX_REVIEW_SCAN_LIMIT))


def _clean_review_text(value: Any, *, max_length: int) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return redact_egress_text(text).text.strip()[:max_length]


def _response_summary(action: K8sAdminAction) -> dict[str, Any]:
    if isinstance(action.response_summary, dict):
        return action.response_summary
    return {}


def _post_review_from_action(action: K8sAdminAction) -> dict[str, Any]:
    review = _response_summary(action).get("post_review")
    return sanitize_metadata(review) if isinstance(review, dict) else {}


def _action_needs_post_review(action: K8sAdminAction) -> bool:
    return action.session.mode == K8sAdminSession.MODE_BREAK_GLASS or action.verb in BREAK_GLASS_REVIEW_VERBS | WRITE_REVIEW_VERBS


def _post_review_state(action: K8sAdminAction) -> dict[str, Any]:
    review = _post_review_from_action(action)
    review_needed = _action_needs_post_review(action)
    if review:
        status = "completed"
    elif review_needed and action.status in FINAL_ACTION_STATUSES:
        status = "pending"
    elif review_needed:
        status = "not_ready"
    else:
        status = ""
    return {
        "post_review_required": bool(review_needed and not review),
        "post_review_status": status,
        "post_review": review,
    }


def _action_matches_review_filter(action: K8sAdminAction, review_filter: str) -> bool:
    state = _post_review_state(action)
    status = str(state.get("post_review_status") or "")
    if review_filter == "pending":
        return status == "pending"
    if review_filter == "completed":
        return status == "completed"
    if review_filter == "not_ready":
        return status == "not_ready"
    if review_filter == "required":
        return bool(state.get("post_review_required"))
    if review_filter == "any":
        return status in {"pending", "completed", "not_ready"}
    if review_filter == "none":
        return status == ""
    return True


def _review_summary(actions: list[K8sAdminAction]) -> dict[str, int]:
    summary = {"pending": 0, "completed": 0, "not_ready": 0, "none": 0}
    for action in actions:
        status = str(_post_review_state(action).get("post_review_status") or "")
        if status in {"pending", "completed", "not_ready"}:
            summary[status] += 1
        else:
            summary["none"] += 1
    return summary


def _actions_with_review_filter(queryset, *, review_filter: str, limit: int, scan_limit: int) -> tuple[list[K8sAdminAction], int, bool]:
    actions: list[K8sAdminAction] = []
    scanned = 0
    truncated = False
    for action in queryset[: scan_limit + 1]:
        if scanned >= scan_limit:
            truncated = True
            break
        scanned += 1
        if _action_matches_review_filter(action, review_filter):
            actions.append(action)
            if len(actions) >= limit:
                break
    return actions, scanned, truncated


def _safe_admin_action_payload(action: K8sAdminAction) -> dict[str, Any]:
    payload = serialize_admin_action(action)
    payload["request_payload_sanitized"] = sanitize_metadata(payload.get("request_payload_sanitized") or {})
    payload["diff_summary"] = sanitize_metadata(payload.get("diff_summary") or {})
    payload["response_summary"] = sanitize_metadata(payload.get("response_summary") or {})
    payload.update(_post_review_state(action))
    return payload


def _safe_admin_session_payload(action: K8sAdminAction) -> dict[str, Any]:
    payload = serialize_admin_session(action.session)
    payload["metadata"] = sanitize_metadata(payload.get("metadata") or {})
    return payload


def _safe_recording_payloads(action: K8sAdminAction) -> list[dict[str, Any]]:
    recordings = action.recordings.select_related("session", "action", "cluster").order_by("created_at", "id")
    payloads: list[dict[str, Any]] = []
    for recording in recordings:
        payloads.append(safe_recording_payload(recording, include_events=True, event_limit=100))
    return payloads


def _safe_timeline_event(event: K8sAuditEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "action": event.action,
        "username": event.username_snapshot,
        "provider": event.provider,
        "cluster": event.cluster.name if event.cluster_id else "",
        "payload": sanitize_metadata(event.payload or {}),
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def _apply_action_filters(queryset, request):
    session_id = str(request.GET.get("session_id") or "").strip()
    if session_id:
        queryset = queryset.filter(session__session_id=session_id)
    cluster_id = str(request.GET.get("cluster_id") or "").strip()
    if cluster_id:
        cluster = cluster_for_value(cluster_id)
        queryset = queryset.filter(cluster=cluster) if cluster is not None else queryset.none()
    verb = str(request.GET.get("verb") or "").strip()
    if verb:
        queryset = queryset.filter(verb=verb)
    status = str(request.GET.get("status") or "").strip()
    if status:
        queryset = queryset.filter(status=status)
    return queryset


def _action_for_user_or_none(user, action_id) -> K8sAdminAction | None:
    try:
        action = (
            K8sAdminAction.objects.select_related("session", "session__user", "user", "cluster")
            .filter(action_id=action_id)
            .first()
        )
    except (TypeError, ValueError):
        return None
    if action is None:
        return None
    if getattr(user, "is_staff", False):
        return action
    if action.user_id == getattr(user, "id", None) or action.session.user_id == getattr(user, "id", None):
        return action
    return None


def _action_timeline(action: K8sAdminAction) -> list[dict[str, Any]]:
    action_id = str(action.action_id)
    session_id = str(action.session.session_id)
    events = (
        K8sAuditEvent.objects.select_related("cluster")
        .filter(Q(payload__action_id=action_id) | (Q(payload__session_id=session_id) & Q(action__startswith="k8s.admin_session.")))
        .order_by("created_at", "id")[:50]
    )
    return [_safe_timeline_event(event) for event in events]


def _admin_action_report(action: K8sAdminAction) -> dict[str, Any]:
    timeline = _action_timeline(action)
    review_state = _post_review_state(action)
    return {
        "action": _safe_admin_action_payload(action),
        "session": _safe_admin_session_payload(action),
        "recordings": _safe_recording_payloads(action),
        "timeline": timeline,
        "summary": {
            "action_id": str(action.action_id),
            "session_id": str(action.session.session_id),
            "verb": action.verb,
            "status": action.status,
            "recording_count": action.recordings.count(),
            "timeline_event_count": len(timeline),
            "has_action_audit_event": any(str((event.get("payload") or {}).get("action_id") or "") == str(action.action_id) for event in timeline),
            "post_review_required": review_state["post_review_required"],
            "post_review_status": review_state["post_review_status"],
            "has_post_review": bool(review_state["post_review"]),
        },
    }


def _require_action_review_access(user, action: K8sAdminAction) -> None:
    if not getattr(user, "is_staff", False):
        raise AdminActionReviewError("Staff review is required.", code="staff_required", status=403)
    policy = kubernetes_permission_policy(user)
    break_glass_review = action.session.mode == K8sAdminSession.MODE_BREAK_GLASS or action.verb in BREAK_GLASS_REVIEW_VERBS
    if break_glass_review:
        if not policy.get("can_break_glass"):
            raise AdminActionReviewError("Kubernetes break-glass access is required.", code="break_glass_required", status=403)
        return
    if action.verb in WRITE_REVIEW_VERBS and not policy.get("can_admin_write"):
        raise AdminActionReviewError("Kubernetes admin write access is required.", code="admin_write_required", status=403)


def _build_post_review(user, data: dict[str, Any]) -> dict[str, Any]:
    outcome = _clean_review_text(data.get("outcome"), max_length=80)
    if outcome not in ACTION_REVIEW_OUTCOMES:
        raise AdminActionReviewError(
            "outcome must be accepted, verified, needs_followup, or incident_created.",
            code="post_review_outcome_invalid",
        )
    summary = _clean_review_text(data.get("summary") or data.get("notes"), max_length=2000)
    if not summary:
        raise AdminActionReviewError("summary is required for admin action post-review.", code="post_review_summary_required")
    current_time = timezone.now()
    return sanitize_metadata(
        {
            "outcome": outcome,
            "summary": summary,
            "evidence_ref": _clean_review_text(data.get("evidence_ref"), max_length=240),
            "follow_up_ref": _clean_review_text(data.get("follow_up_ref"), max_length=240),
            "reviewed_by": getattr(user, "username", ""),
            "reviewed_at": current_time.isoformat(),
        }
    )


def _audit_action_review(request, action: K8sAdminAction, audit_action: str, payload: dict[str, Any] | None = None) -> None:
    K8sAuditEvent.objects.create(
        user=request.user,
        username_snapshot=getattr(request.user, "username", ""),
        action=audit_action,
        provider="webterm",
        cluster=action.cluster,
        payload=sanitize_metadata(
            {
                "action_id": str(action.action_id),
                "session_id": str(action.session.session_id),
                "verb": action.verb,
                "status": action.status,
                **(payload or {}),
            }
        ),
    )


def _review_admin_action(*, action: K8sAdminAction, user, data: dict[str, Any]) -> K8sAdminAction:
    _require_action_review_access(user, action)
    if not _action_needs_post_review(action):
        raise AdminActionReviewError("Post-review is not required for this admin action.", code="post_review_not_required", status=409)
    if action.status not in FINAL_ACTION_STATUSES:
        raise AdminActionReviewError("Admin action can be reviewed only after it reaches a final status.", code="post_review_not_ready", status=409)

    post_review = _build_post_review(user, data)
    response_summary = sanitize_metadata(dict(_response_summary(action)))
    response_summary["post_review_status"] = "completed"
    response_summary["post_review"] = post_review
    action.response_summary = sanitize_metadata(response_summary)
    action.save(update_fields=["response_summary", "updated_at"])
    return action


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
            actions, scanned_count, truncated = _actions_with_review_filter(queryset, review_filter=review_filter, limit=limit, scan_limit=scan_limit)
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
            return JsonResponse({"success": False, "error": "Admin action not found.", "code": "admin_action_not_found"}, status=404)
        return JsonResponse({"success": True, "action": _safe_admin_action_payload(action)})

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_admin_action_report(request, action_id):
    def handler():
        action = _action_for_user_or_none(request.user, action_id)
        if action is None:
            return JsonResponse({"success": False, "error": "Admin action not found.", "code": "admin_action_not_found"}, status=404)
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
            return JsonResponse({"success": False, "error": "Admin action not found.", "code": "admin_action_not_found"}, status=404)
        try:
            action = _review_admin_action(action=action, user=request.user, data=data)
        except AdminActionReviewError as exc:
            _audit_action_review(request, action, "k8s.admin_action.post_review_rejected", {"code": exc.code, "error": str(exc)})
            return _error_response(exc)
        post_review = _post_review_from_action(action)
        _audit_action_review(request, action, "k8s.admin_action.post_review", {"post_review": post_review})
        return JsonResponse({"success": True, "action": _safe_admin_action_payload(action), "post_review": post_review})

    return _safe_json(handler)
