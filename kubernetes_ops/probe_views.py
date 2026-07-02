from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from loguru import logger

from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAuditEvent, K8sProvider
from kubernetes_ops.services.provider_probe import probe_kubernetes_provider, probe_result_payload


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes ops provider probe API failed: %s", exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


def _staff_required(request) -> JsonResponse | None:
    if not getattr(request.user, "is_staff", False):
        return JsonResponse({"success": False, "error": "Admin access is required.", "code": "admin_required"}, status=403)
    return None


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_provider_probe(request, provider_id: int):
    def handler():
        denied = _staff_required(request)
        if denied:
            return denied
        provider = K8sProvider.objects.filter(id=provider_id).first()
        if provider is None:
            return JsonResponse({"success": False, "error": "Provider not found"}, status=404)
        result = probe_kubernetes_provider(provider)
        payload = probe_result_payload(result)
        K8sAuditEvent.objects.create(
            user=request.user,
            username_snapshot=getattr(request.user, "username", ""),
            action="k8s.provider.probe",
            provider=provider.name,
            payload={
                "provider_id": provider.id,
                "kind": provider.kind,
                "status": result.status,
                "success": result.success,
                "path": result.path,
                "item_count": result.item_count,
                "duration_ms": result.duration_ms,
            },
        )
        return JsonResponse({"success": result.success, "probe": payload})

    return _safe_json(handler)
