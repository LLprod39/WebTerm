from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from loguru import logger

from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAuditEvent
from kubernetes_ops.services.devtron_app_detail import (
    build_devtron_app_detail,
    devtron_app_audit_payload,
    devtron_app_for_value,
)


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes devtron API failed: %s", exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_devtron_app_detail(request, app_id: str):
    def handler():
        app = devtron_app_for_value(app_id)
        if app is None:
            return JsonResponse({"success": False, "error": "Devtron app not found.", "code": "app_not_found"}, status=404)
        payload = build_devtron_app_detail(app, user=request.user)
        K8sAuditEvent.objects.create(
            user=request.user,
            username_snapshot=getattr(request.user, "username", ""),
            action="k8s.devtron_app.detail",
            provider="webterm",
            cluster=app.cluster,
            payload=devtron_app_audit_payload(payload),
        )
        return JsonResponse(payload)

    return _safe_json(handler)
