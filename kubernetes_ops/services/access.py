"""Cluster / namespace visibility for personal connections and admin grants."""

from __future__ import annotations

from django.db.models import Q, QuerySet
from django.utils import timezone

from kubernetes_ops.models import K8sCluster, K8sClusterAccess, K8sNamespace, K8sProvider


def active_access_qs_for_user(user) -> QuerySet[K8sClusterAccess]:
    now = timezone.now()
    return K8sClusterAccess.objects.filter(user=user, is_revoked=False).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    )


def owned_kubeconfig_provider_ids(user) -> list[int]:
    return list(
        K8sProvider.objects.filter(
            kind=K8sProvider.KIND_KUBECONFIG,
            created_by=user,
            enabled=True,
        ).values_list("id", flat=True)
    )


def owned_rancher_provider_ids(user) -> list[int]:
    """Legacy personal Rancher connections (kept for visibility of already-synced clusters)."""
    return list(
        K8sProvider.objects.filter(
            kind=K8sProvider.KIND_RANCHER,
            created_by=user,
            enabled=True,
        ).values_list("id", flat=True)
    )


def visible_clusters_queryset(user) -> QuerySet[K8sCluster]:
    qs = K8sCluster.objects.all()
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()
    if getattr(user, "is_staff", False):
        return qs

    owned_kube = owned_kubeconfig_provider_ids(user)
    owned_rancher = owned_rancher_provider_ids(user)
    grant_ids = list(active_access_qs_for_user(user).values_list("cluster_id", flat=True))

    visibility = Q(pk__in=grant_ids)
    if owned_rancher:
        visibility |= Q(rancher_provider_id__in=owned_rancher)
    for provider_id in owned_kube:
        visibility |= Q(rancher_cluster_id=f"kubeconfig:{provider_id}")
        visibility |= Q(labels__provider_id=provider_id)

    return qs.filter(visibility).distinct()


def user_can_view_cluster(user, cluster: K8sCluster) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_staff", False):
        return True
    return visible_clusters_queryset(user).filter(pk=cluster.pk).exists()


def allowed_namespaces_for_cluster(user, cluster: K8sCluster) -> list[str] | None:
    """
    None = all namespaces in inventory (subject to kube RBAC).
    list = intersection allow-list from grants (empty list means no namespaces).
    """
    if not user or not getattr(user, "is_authenticated", False):
        return []
    if getattr(user, "is_staff", False):
        return None

    # Owner of personal connection → all ns returned by their credential.
    labels = cluster.labels if isinstance(cluster.labels, dict) else {}
    provider_id = labels.get("provider_id")
    if provider_id in owned_kubeconfig_provider_ids(user):
        return None
    if cluster.rancher_provider_id and cluster.rancher_provider_id in owned_rancher_provider_ids(user):
        return None

    grants = list(active_access_qs_for_user(user).filter(cluster=cluster))
    if not grants:
        return []

    # Empty namespaces on any grant = full cluster.
    if any(not (grant.namespaces or []) for grant in grants):
        return None

    allowed: set[str] = set()
    for grant in grants:
        for name in grant.namespaces or []:
            value = str(name or "").strip()
            if value:
                allowed.add(value)
    return sorted(allowed)


def filter_namespaces_queryset(user, cluster: K8sCluster) -> QuerySet[K8sNamespace]:
    qs = K8sNamespace.objects.filter(cluster=cluster)
    allowed = allowed_namespaces_for_cluster(user, cluster)
    if allowed is None:
        return qs
    if not allowed:
        return qs.none()
    return qs.filter(name__in=allowed)


def cluster_access_origin(user, cluster: K8sCluster) -> str:
    """owned | granted | platform (staff view)."""
    if getattr(user, "is_staff", False):
        labels = cluster.labels if isinstance(cluster.labels, dict) else {}
        if labels.get("source") == "kubeconfig" and labels.get("scope") == K8sProvider.SCOPE_PERSONAL:
            if labels.get("provider_id") in owned_kubeconfig_provider_ids(user):
                return "owned"
        if cluster.rancher_provider_id and cluster.rancher_provider_id in owned_rancher_provider_ids(user):
            return "owned"
        if active_access_qs_for_user(user).filter(cluster=cluster).exists():
            return "granted"
        return "platform"

    labels = cluster.labels if isinstance(cluster.labels, dict) else {}
    if labels.get("provider_id") in owned_kubeconfig_provider_ids(user):
        return "owned"
    if cluster.rancher_provider_id and cluster.rancher_provider_id in owned_rancher_provider_ids(user):
        return "owned"
    if active_access_qs_for_user(user).filter(cluster=cluster).exists():
        return "granted"
    return "none"


def serialize_access_grant(grant: K8sClusterAccess) -> dict:
    return {
        "id": grant.id,
        "cluster_id": f"cluster_{grant.cluster_id}",
        "cluster_name": grant.cluster.name,
        "user_id": grant.user_id,
        "username": grant.user.username,
        "email": grant.user.email or "",
        "namespaces": list(grant.namespaces or []),
        "can_view_logs": bool(grant.can_view_logs),
        "can_exec": bool(grant.can_exec),
        "expires_at": grant.expires_at.isoformat() if grant.expires_at else None,
        "is_revoked": bool(grant.is_revoked),
        "is_active": grant.is_active(),
        "granted_by_id": grant.granted_by_id,
        "granted_by_username": getattr(grant.granted_by, "username", "") if grant.granted_by_id else "",
        "created_at": grant.created_at.isoformat() if grant.created_at else None,
    }
