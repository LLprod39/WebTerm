"""Operator review API for exhausted pipeline node attempts."""

from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core_ui.projects import active_project_for_user
from studio.pipeline.pipeline_dead_letter import dead_letter_to_dict, resolve_node_dead_letter
from studio.retry_models import PipelineNodeDeadLetter
from studio.views.studio_access import require_studio_access

STUDIO_FEATURE_RUNS = "studio_runs"


def _queryset_for_user(user):
    project = active_project_for_user(user)
    queryset = PipelineNodeDeadLetter.objects.select_related(
        "run",
        "run__pipeline",
        "run__pipeline__owner",
        "resolved_by",
    )
    queryset = queryset.filter(run__project=project) if project else queryset.none()
    if getattr(user, "is_staff", False):
        return queryset
    return queryset.filter(run__pipeline__owner=user)


@require_studio_access(STUDIO_FEATURE_RUNS)
@require_http_methods(["GET"])
def api_dead_letters(request):
    requested_status = str(request.GET.get("status") or PipelineNodeDeadLetter.STATUS_OPEN).strip().lower()
    queryset = _queryset_for_user(request.user)
    if requested_status in {PipelineNodeDeadLetter.STATUS_OPEN, PipelineNodeDeadLetter.STATUS_RESOLVED}:
        queryset = queryset.filter(status=requested_status)
    elif requested_status != "all":
        return JsonResponse({"error": "status must be open, resolved or all"}, status=400)
    return JsonResponse([dead_letter_to_dict(item) for item in queryset[:200]], safe=False)


@require_studio_access(STUDIO_FEATURE_RUNS)
@require_http_methods(["POST"])
def api_dead_letter_resolve(request, item_id: int):
    item = _queryset_for_user(request.user).filter(pk=item_id).first()
    if item is None:
        return JsonResponse({"error": "Dead-letter item not found"}, status=404)
    try:
        body = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = {}
    resolved = resolve_node_dead_letter(
        item.pk,
        actor=request.user,
        note=str(body.get("note") or "") if isinstance(body, dict) else "",
    )
    return JsonResponse({"ok": True, "item": dead_letter_to_dict(resolved)})
