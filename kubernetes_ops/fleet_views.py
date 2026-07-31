from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from loguru import logger

from core_ui.api_errors import internal_error_response
from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAuditEvent
from kubernetes_ops.services.fleet_bundle_detail import (
    build_fleet_bundle_detail,
    fleet_bundle_audit_payload,
    fleet_bundle_for_value,
)


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes fleet API failed: %s", exc)
        return internal_error_response(None, exc)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_fleet_bundle_detail(request, bundle_id: str):
    def handler():
        bundle = fleet_bundle_for_value(bundle_id)
        if bundle is None:
            return JsonResponse(
                {"success": False, "error": "Fleet bundle not found.", "code": "bundle_not_found"}, status=404
            )
        payload = build_fleet_bundle_detail(bundle, user=request.user)
        K8sAuditEvent.objects.create(
            user=request.user,
            username_snapshot=getattr(request.user, "username", ""),
            action="k8s.fleet_bundle.detail",
            provider="webterm",
            cluster=None,
            payload=fleet_bundle_audit_payload(payload),
        )
        return JsonResponse(payload)

    return _safe_json(handler)
