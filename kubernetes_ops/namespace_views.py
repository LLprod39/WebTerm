from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from loguru import logger

from core_ui.api_errors import internal_error_response
from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAuditEvent, K8sCluster
from kubernetes_ops.services.namespace_detail import build_namespace_detail, namespace_detail_audit_payload


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes namespace API failed: %s", exc)
        return internal_error_response(None, exc)


def _cluster_or_none(cluster_id: str) -> K8sCluster | None:
    value = str(cluster_id or "").strip()
    numeric = value.removeprefix("cluster_")
    query = Q(name=value) | Q(rancher_cluster_id=value) | Q(devtron_cluster_id=value)
    if numeric.isdigit():
        query |= Q(id=int(numeric))
    return K8sCluster.objects.filter(query).first()


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_namespace_detail(request, cluster_id: str, namespace_id: str):
    def handler():
        cluster = _cluster_or_none(cluster_id)
        if cluster is None:
            return JsonResponse(
                {"success": False, "error": "Cluster not found.", "code": "cluster_not_found"}, status=404
            )
        payload = build_namespace_detail(cluster, namespace_id, user=request.user)
        if payload is None:
            return JsonResponse(
                {"success": False, "error": "Namespace not found.", "code": "namespace_not_found"}, status=404
            )
        K8sAuditEvent.objects.create(
            user=request.user,
            username_snapshot=getattr(request.user, "username", ""),
            action="k8s.namespace.detail",
            provider="webterm",
            cluster=cluster,
            payload=namespace_detail_audit_payload(payload),
        )
        return JsonResponse(payload)

    return _safe_json(handler)
