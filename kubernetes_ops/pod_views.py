from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from loguru import logger

from core_ui.api_errors import internal_error_response
from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAuditEvent, K8sCluster, K8sPodRef
from kubernetes_ops.serializers import serialize_cluster, serialize_pod_ref
from kubernetes_ops.services.pod_detail import build_pod_detail, pod_detail_audit_payload, pod_for_value


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes ops pods API failed: %s", exc)
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
def api_kubernetes_pod_detail(request, pod_id: str):
    def handler():
        pod = pod_for_value(pod_id)
        if pod is None:
            return JsonResponse({"success": False, "error": "Pod not found.", "code": "pod_not_found"}, status=404)
        payload = build_pod_detail(pod, user=request.user)
        K8sAuditEvent.objects.create(
            user=request.user,
            username_snapshot=getattr(request.user, "username", ""),
            action="k8s.pod.detail",
            provider="webterm",
            cluster=pod.cluster,
            payload=pod_detail_audit_payload(payload),
        )
        return JsonResponse(payload)

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_cluster_pods(request, cluster_id: str):
    def handler():
        cluster = _cluster_or_none(cluster_id)
        if cluster is None:
            return JsonResponse({"success": False, "error": "Cluster not found"}, status=404)
        pods = K8sPodRef.objects.filter(cluster=cluster).select_related("cluster")
        return JsonResponse(
            {
                "success": True,
                "cluster": serialize_cluster(cluster, user=request.user),
                "pods": [serialize_pod_ref(pod, user=request.user) for pod in pods],
            }
        )

    return _safe_json(handler)
