from __future__ import annotations

from typing import Any

COMMON_RESOURCE_SPECS = (
    ("v1", "Namespace", "namespaces", False, ("ns", "namespace", "namespaces")),
    ("v1", "Node", "nodes", False, ("node", "nodes")),
    ("v1", "Pod", "pods", True, ("po", "pod", "pods")),
    ("v1", "Service", "services", True, ("svc", "service", "services")),
    ("v1", "ConfigMap", "configmaps", True, ("cm", "configmap", "configmaps")),
    ("v1", "Secret", "secrets", True, ("secret", "secrets")),
    ("v1", "ServiceAccount", "serviceaccounts", True, ("sa", "serviceaccount", "serviceaccounts")),
    (
        "v1",
        "PersistentVolumeClaim",
        "persistentvolumeclaims",
        True,
        ("pvc", "pvcs", "persistentvolumeclaim", "persistentvolumeclaims"),
    ),
    ("v1", "PersistentVolume", "persistentvolumes", False, ("pv", "pvs", "persistentvolume", "persistentvolumes")),
    ("v1", "Endpoints", "endpoints", True, ("ep", "endpoints")),
    ("v1", "LimitRange", "limitranges", True, ("limitrange", "limitranges")),
    ("v1", "ResourceQuota", "resourcequotas", True, ("quota", "resourcequota", "resourcequotas")),
    ("apps/v1", "Deployment", "deployments", True, ("deploy", "deployment", "deployments")),
    ("apps/v1", "StatefulSet", "statefulsets", True, ("sts", "statefulset", "statefulsets")),
    ("apps/v1", "DaemonSet", "daemonsets", True, ("ds", "daemonset", "daemonsets")),
    ("apps/v1", "ReplicaSet", "replicasets", True, ("rs", "replicaset", "replicasets")),
    ("batch/v1", "Job", "jobs", True, ("job", "jobs")),
    ("batch/v1", "CronJob", "cronjobs", True, ("cj", "cronjob", "cronjobs")),
    (
        "autoscaling/v2",
        "HorizontalPodAutoscaler",
        "horizontalpodautoscalers",
        True,
        ("hpa", "hpas", "horizontalpodautoscaler", "horizontalpodautoscalers"),
    ),
    (
        "policy/v1",
        "PodDisruptionBudget",
        "poddisruptionbudgets",
        True,
        ("pdb", "pdbs", "poddisruptionbudget", "poddisruptionbudgets"),
    ),
    ("networking.k8s.io/v1", "Ingress", "ingresses", True, ("ing", "ingress", "ingresses")),
    ("networking.k8s.io/v1", "NetworkPolicy", "networkpolicies", True, ("netpol", "networkpolicy", "networkpolicies")),
    ("discovery.k8s.io/v1", "EndpointSlice", "endpointslices", True, ("endpointslice", "endpointslices")),
    ("storage.k8s.io/v1", "StorageClass", "storageclasses", False, ("sc", "storageclass", "storageclasses")),
    ("rbac.authorization.k8s.io/v1", "Role", "roles", True, ("role", "roles")),
    ("rbac.authorization.k8s.io/v1", "RoleBinding", "rolebindings", True, ("rolebinding", "rolebindings")),
    ("rbac.authorization.k8s.io/v1", "ClusterRole", "clusterroles", False, ("clusterrole", "clusterroles")),
    (
        "rbac.authorization.k8s.io/v1",
        "ClusterRoleBinding",
        "clusterrolebindings",
        False,
        ("clusterrolebinding", "clusterrolebindings"),
    ),
    (
        "apiextensions.k8s.io/v1",
        "CustomResourceDefinition",
        "customresourcedefinitions",
        False,
        ("crd", "crds", "customresourcedefinition", "customresourcedefinitions"),
    ),
)

COMMON_RESOURCES: dict[tuple[str, str], dict[str, Any]] = {
    (api_version, kind): {"resource": resource, "namespaced": namespaced}
    for api_version, kind, resource, namespaced, _aliases in COMMON_RESOURCE_SPECS
}

KIND_ALIASES: dict[str, str] = {
    alias: kind
    for _api_version, kind, _resource, _namespaced, aliases in COMMON_RESOURCE_SPECS
    for alias in {kind.lower(), *aliases}
}


def common_resource_payload() -> list[dict[str, Any]]:
    return [
        {
            "api_version": api_version,
            "kind": kind,
            "resource": metadata["resource"],
            "namespaced": bool(metadata["namespaced"]),
        }
        for (api_version, kind), metadata in sorted(COMMON_RESOURCES.items())
    ]


def display_kind(kind: str) -> str:
    value = str(kind or "").strip()
    return KIND_ALIASES.get(value.lower(), value[:80])


def pluralize_kind(kind: str) -> str:
    lower = kind.lower()
    return lower if lower.endswith("s") else lower[:-1] + "ies" if lower.endswith("y") else lower + "s"
