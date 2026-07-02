from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from loguru import logger

from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAuditEvent
from kubernetes_ops.services.helm_ownership import build_helm_ownership_payload, helm_ownership_audit_payload


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes helm API failed: %s", exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_helm_releases(request):
    def handler():
        payload = build_helm_ownership_payload(
            user=request.user,
            cluster_id=str(request.GET.get("cluster_id") or ""),
            namespace=str(request.GET.get("namespace") or ""),
            owner=str(request.GET.get("owner") or ""),
            limit=request.GET.get("limit"),
        )
        status = 404 if payload.get("code") == "cluster_not_found" else 200
        if payload.get("success"):
            K8sAuditEvent.objects.create(
                user=request.user,
                username_snapshot=getattr(request.user, "username", ""),
                action="k8s.helm_releases.list",
                provider="webterm",
                cluster=None,
                payload=helm_ownership_audit_payload(payload),
            )
        return JsonResponse(payload, status=status)

    return _safe_json(handler)
