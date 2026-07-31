from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from loguru import logger

from core_ui.api_errors import internal_error_response
from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAdminRecording
from kubernetes_ops.services.admin_recording_evidence import safe_recording_payload
from kubernetes_ops.services.admin_resources import cluster_for_value


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes admin recording API failed: %s", exc)
        return internal_error_response(None, exc)


def _visible_recordings_for_user(user, *, include_all: bool = False):
    queryset = K8sAdminRecording.objects.select_related(
        "session", "session__user", "action", "action__user", "user", "cluster"
    )
    if include_all and getattr(user, "is_staff", False):
        return queryset
    user_id = getattr(user, "id", None)
    return queryset.filter(Q(user_id=user_id) | Q(session__user_id=user_id) | Q(action__user_id=user_id))


def _bounded_limit(value: str | None, *, default: int = 50, maximum: int = 100) -> int:
    try:
        limit = int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default
    return max(1, min(limit, maximum))


def _apply_recording_filters(queryset, request):
    session_id = str(request.GET.get("session_id") or "").strip()
    if session_id:
        queryset = queryset.filter(session__session_id=session_id)
    action_id = str(request.GET.get("action_id") or "").strip()
    if action_id:
        queryset = queryset.filter(action__action_id=action_id)
    cluster_id = str(request.GET.get("cluster_id") or "").strip()
    if cluster_id:
        cluster = cluster_for_value(cluster_id)
        queryset = queryset.filter(cluster=cluster) if cluster is not None else queryset.none()
    operation = str(request.GET.get("operation") or "").strip()
    if operation:
        queryset = queryset.filter(operation=operation)
    status = str(request.GET.get("status") or "").strip()
    if status:
        queryset = queryset.filter(status=status)
    return queryset


def _recording_for_user_or_none(user, recording_id) -> K8sAdminRecording | None:
    try:
        recording = (
            K8sAdminRecording.objects.select_related(
                "session", "session__user", "action", "action__user", "user", "cluster"
            )
            .filter(recording_id=recording_id)
            .first()
        )
    except (TypeError, ValueError):
        return None
    if recording is None:
        return None
    if getattr(user, "is_staff", False):
        return recording
    user_id = getattr(user, "id", None)
    if (
        recording.user_id == user_id
        or recording.session.user_id == user_id
        or (recording.action_id and recording.action.user_id == user_id)
    ):
        return recording
    return None


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_admin_recordings(request):
    def handler():
        include_all = str(request.GET.get("all") or "").lower() in {"1", "true", "yes"}
        queryset = _visible_recordings_for_user(request.user, include_all=include_all)
        queryset = _apply_recording_filters(queryset, request).order_by("-created_at", "-id")
        limit = _bounded_limit(request.GET.get("limit"))
        recordings = list(queryset[:limit])
        return JsonResponse(
            {
                "success": True,
                "recordings": [safe_recording_payload(recording, include_events=False) for recording in recordings],
                "count": len(recordings),
                "limit": limit,
            }
        )

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_admin_recording_detail(request, recording_id):
    def handler():
        recording = _recording_for_user_or_none(request.user, recording_id)
        if recording is None:
            return JsonResponse(
                {"success": False, "error": "Admin recording not found.", "code": "admin_recording_not_found"},
                status=404,
            )
        event_limit = _bounded_limit(request.GET.get("event_limit"), default=100, maximum=500)
        return JsonResponse(
            {
                "success": True,
                "recording": safe_recording_payload(recording, include_events=True, event_limit=event_limit),
                "event_limit": event_limit,
            }
        )

    return _safe_json(handler)
