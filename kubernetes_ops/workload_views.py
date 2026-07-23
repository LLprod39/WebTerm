from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from loguru import logger

from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAuditEvent
from kubernetes_ops.services.workload_detail import (
    build_workload_detail,
    workload_detail_audit_payload,
    workload_for_value,
)


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes workload API failed: %s", exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_workload_detail(request, workload_id: str):
    def handler():
        workload = workload_for_value(workload_id)
        if workload is None:
            return JsonResponse(
                {"success": False, "error": "Workload not found.", "code": "workload_not_found"}, status=404
            )
        payload = build_workload_detail(workload, user=request.user)
        K8sAuditEvent.objects.create(
            user=request.user,
            username_snapshot=getattr(request.user, "username", ""),
            action="k8s.workload.detail",
            provider="webterm",
            cluster=workload.cluster,
            payload=workload_detail_audit_payload(payload),
        )
        return JsonResponse(payload)

    return _safe_json(handler)
