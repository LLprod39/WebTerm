from __future__ import annotations

from typing import Any

from django.db.models import Count, Q

from kubernetes_ops.models import K8sAppRef, K8sCluster, K8sEvent, K8sFleetBundle, K8sProvider, K8sWorkloadRef
from kubernetes_ops.serializers import (
    serialize_app,
    serialize_cluster,
    serialize_fleet_bundle,
    serialize_provider,
    serialize_workload,
)
from kubernetes_ops.services.readiness import build_kubernetes_readiness_report


def build_overview_payload(user=None) -> dict[str, Any]:
    from kubernetes_ops.services.access import visible_clusters_queryset
    from kubernetes_ops.views_helpers import _providers_queryset_for_user

    visible_clusters = visible_clusters_queryset(user) if user is not None else K8sCluster.objects.none()
    clusters = list(visible_clusters.order_by("environment", "name"))
    cluster_ids = [cluster.id for cluster in clusters]
    apps = list(
        K8sAppRef.objects.select_related("cluster")
        .filter(cluster_id__in=cluster_ids)
        .order_by("cluster__name", "namespace", "name")[:50]
    )
    bundles = list(K8sFleetBundle.objects.all().order_by("name")[:50]) if getattr(user, "is_staff", False) else []
    workloads = list(
        K8sWorkloadRef.objects.select_related("cluster")
        .filter(cluster_id__in=cluster_ids)
        .order_by("cluster__name", "namespace", "kind", "name")[:50]
    )
    provider_rows = list(_providers_queryset_for_user(user).order_by("kind", "name")) if user is not None else []
    app_counts = K8sAppRef.objects.filter(cluster_id__in=cluster_ids).aggregate(
        total=Count("id"),
        degraded=Count("id", filter=Q(health=K8sCluster.HEALTH_DEGRADED)),
        warning=Count("id", filter=Q(health=K8sCluster.HEALTH_WARNING)),
    )
    cluster_counts = visible_clusters.aggregate(
        total=Count("id"),
        degraded=Count("id", filter=Q(health=K8sCluster.HEALTH_DEGRADED)),
        warning=Count("id", filter=Q(health=K8sCluster.HEALTH_WARNING)),
    )
    fleet_counts = (
        K8sFleetBundle.objects.aggregate(
            total=Count("id"),
            degraded=Count("id", filter=Q(status=K8sFleetBundle.STATUS_DEGRADED)),
            rolling=Count("id", filter=Q(status=K8sFleetBundle.STATUS_ROLLING)),
            paused=Count("id", filter=Q(status=K8sFleetBundle.STATUS_PAUSED)),
        )
        if getattr(user, "is_staff", False)
        else {"total": 0, "degraded": 0, "rolling": 0, "paused": 0}
    )
    workload_counts = K8sWorkloadRef.objects.filter(cluster_id__in=cluster_ids).aggregate(
        total=Count("id"),
        degraded=Count("id", filter=Q(health=K8sCluster.HEALTH_DEGRADED)),
        warning=Count("id", filter=Q(health=K8sCluster.HEALTH_WARNING)),
    )
    event_counts = K8sEvent.objects.filter(cluster_id__in=cluster_ids).aggregate(
        error=Count("id", filter=Q(severity=K8sEvent.SEVERITY_ERROR)),
        warning=Count("id", filter=Q(severity=K8sEvent.SEVERITY_WARNING)),
    )
    incidents = (
        int(cluster_counts.get("degraded") or 0)
        + int(app_counts.get("degraded") or 0)
        + int(workload_counts.get("degraded") or 0)
        + int(event_counts.get("error") or 0)
        + int(fleet_counts.get("degraded") or 0)
    )
    serialized_providers = [serialize_provider(provider, user=user) for provider in provider_rows]
    serialized_clusters = [serialize_cluster(cluster, user=user) for cluster in clusters]
    serialized_apps = [serialize_app(app, user=user) for app in apps]
    serialized_workloads = [serialize_workload(workload, user=user) for workload in workloads]
    serialized_bundles = [serialize_fleet_bundle(bundle, user=user) for bundle in bundles]
    stale_resources = sum(
        1
        for item in [*serialized_clusters, *serialized_apps, *serialized_workloads, *serialized_bundles]
        if item.get("is_stale")
    )
    provider_issues = sum(
        1 for item in serialized_providers if item.get("provider_health") in {"error", "missing", "stale"}
    )
    readiness = build_kubernetes_readiness_report(user=user)
    return {
        "success": True,
        "readiness": readiness,
        "access_policy": readiness["access_policy"],
        "summary": {
            "clusters": int(cluster_counts.get("total") or 0),
            "apps": int(app_counts.get("total") or 0),
            "fleet_rollouts": int(fleet_counts.get("total") or 0),
            "incidents": incidents,
            "warnings": int(cluster_counts.get("warning") or 0)
            + int(app_counts.get("warning") or 0)
            + int(workload_counts.get("warning") or 0)
            + int(event_counts.get("warning") or 0),
            "rolling": int(fleet_counts.get("rolling") or 0),
            "paused": int(fleet_counts.get("paused") or 0),
            "stale": stale_resources,
            "provider_issues": provider_issues,
        },
        "providers": serialized_providers,
        "clusters": serialized_clusters,
        "workloads": serialized_workloads,
        "apps": serialized_apps,
        "fleet_rollouts": serialized_bundles,
    }
