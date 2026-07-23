from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from loguru import logger

from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAuditEvent, K8sCluster, K8sNetworkRef
from kubernetes_ops.serializers import serialize_cluster, serialize_network_ref
from kubernetes_ops.services.network_detail import build_network_detail, network_detail_audit_payload, network_for_value


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes ops network API failed: %s", exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


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
def api_kubernetes_network_detail(request, network_id: str):
    def handler():
        network_ref = network_for_value(network_id)
        if network_ref is None:
            return JsonResponse(
                {"success": False, "error": "Network reference not found.", "code": "network_not_found"}, status=404
            )
        payload = build_network_detail(network_ref, user=request.user)
        K8sAuditEvent.objects.create(
            user=request.user,
            username_snapshot=getattr(request.user, "username", ""),
            action="k8s.network.detail",
            provider="webterm",
            cluster=network_ref.cluster,
            payload=network_detail_audit_payload(payload),
        )
        return JsonResponse(payload)

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_cluster_network(request, cluster_id: str):
    def handler():
        cluster = _cluster_or_none(cluster_id)
        if cluster is None:
            return JsonResponse({"success": False, "error": "Cluster not found"}, status=404)
        items = K8sNetworkRef.objects.filter(cluster=cluster).select_related("cluster")
        return JsonResponse(
            {
                "success": True,
                "cluster": serialize_cluster(cluster, user=request.user),
                "network_refs": [serialize_network_ref(item, user=request.user) for item in items],
            }
        )

    return _safe_json(handler)
