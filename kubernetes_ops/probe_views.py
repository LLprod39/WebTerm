from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from loguru import logger

from core_ui.api_errors import internal_error_response
from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAuditEvent, K8sProvider
from kubernetes_ops.services.kubeconfig import probe_kubeconfig_provider
from kubernetes_ops.services.provider_probe import probe_kubernetes_provider, probe_result_payload
from kubernetes_ops.views_helpers import _provider_manage_denied


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes ops provider probe API failed: %s", exc)
        return internal_error_response(None, exc)


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_provider_probe(request, provider_id: int):
    def handler():
        provider = K8sProvider.objects.filter(id=provider_id).first()
        if provider is None:
            return JsonResponse({"success": False, "error": "Provider not found"}, status=404)
        denied = _provider_manage_denied(request, provider)
        if denied:
            return denied
        if provider.kind == K8sProvider.KIND_KUBECONFIG:
            kc = probe_kubeconfig_provider(provider)
            payload = {
                "provider_id": provider.id,
                "provider_name": provider.name,
                "provider_kind": provider.kind,
                "success": kc.success,
                "status": kc.status,
                "path": "/api/v1/namespaces",
                "item_count": kc.namespace_count,
                "payload_keys": [],
                "duration_ms": kc.duration_ms,
                "checked_at": kc.checked_at,
                "error": kc.error,
                "server": kc.server,
                "context": kc.context,
            }
            success = kc.success
            status = kc.status
        else:
            result = probe_kubernetes_provider(provider)
            payload = probe_result_payload(result)
            success = result.success
            status = result.status
        K8sAuditEvent.objects.create(
            user=request.user,
            username_snapshot=getattr(request.user, "username", ""),
            action="k8s.provider.probe",
            provider=provider.name,
            payload={
                "provider_id": provider.id,
                "kind": provider.kind,
                "status": status,
                "success": success,
            },
        )
        return JsonResponse({"success": success, "probe": payload})

    return _safe_json(handler)
