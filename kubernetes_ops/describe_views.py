from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from loguru import logger

from core_ui.api_errors import internal_error_response
from core_ui.decorators import require_feature
from kubernetes_ops.services.describe import build_workload_describe


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes ops describe API failed: %s", exc)
        return internal_error_response(None, exc)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_workload_describe(request, workload_id: str):
    def handler():
        payload = build_workload_describe(workload_id, user=request.user)
        if payload is None:
            return JsonResponse({"success": False, "error": "Workload not found"}, status=404)
        return JsonResponse(payload)

    return _safe_json(handler)
