from __future__ import annotations

from typing import Any

from django.db.models import Q

from kubernetes_ops.models import K8sAppRef, K8sCluster, K8sFleetBundle


def _cluster_or_none(cluster_id: str) -> K8sCluster | None:
    value = str(cluster_id or "").strip()
    numeric = value.removeprefix("cluster_")
    query = Q(name=value) | Q(rancher_cluster_id=value) | Q(devtron_cluster_id=value)
    if numeric.isdigit():
        query |= Q(id=int(numeric))
    return K8sCluster.objects.filter(query).first()


def _app_from_target(target: dict[str, Any]) -> K8sAppRef | None:
    app_id = str(target.get("app_id") or "").strip()
    numeric = app_id.removeprefix("app_")
    if numeric.isdigit():
        return K8sAppRef.objects.filter(id=int(numeric)).select_related("cluster").first()
    return None


def _fleet_bundle_from_target(target: dict[str, Any]) -> K8sFleetBundle | None:
    bundle_id = str(target.get("bundle_id") or "").strip()
    numeric = bundle_id.removeprefix("fleet_")
    if numeric.isdigit():
        return K8sFleetBundle.objects.filter(id=int(numeric)).first()
    bundle_name = str(target.get("bundle_name") or target.get("name") or "").strip()
    if bundle_name:
        return K8sFleetBundle.objects.filter(name=bundle_name).first()
    return None
