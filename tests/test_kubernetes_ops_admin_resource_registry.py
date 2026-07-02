from kubernetes_ops.models import K8sCluster, K8sProvider
from kubernetes_ops.services.admin_resources import build_resource_ref, rancher_resource_path
from kubernetes_ops.services.admin_resource_registry import common_resource_payload


def _provider() -> K8sProvider:
    return K8sProvider(
        name="rancher-main",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://rancher.example.test",
        auth_mode=K8sProvider.AUTH_NONE,
    )


def _cluster(provider: K8sProvider) -> K8sCluster:
    return K8sCluster(name="prod-kz-1", rancher_provider=provider, rancher_cluster_id="c-prod")


def test_common_resource_payload_exposes_freelens_admin_kinds():
    resources = {(item["api_version"], item["kind"]): item for item in common_resource_payload()}

    assert resources[("v1", "PersistentVolumeClaim")] == {
        "api_version": "v1",
        "kind": "PersistentVolumeClaim",
        "resource": "persistentvolumeclaims",
        "namespaced": True,
    }
    assert resources[("autoscaling/v2", "HorizontalPodAutoscaler")]["resource"] == "horizontalpodautoscalers"
    assert resources[("storage.k8s.io/v1", "StorageClass")]["namespaced"] is False
    assert resources[("rbac.authorization.k8s.io/v1", "ClusterRoleBinding")]["resource"] == "clusterrolebindings"


def test_resource_ref_accepts_common_kubectl_aliases():
    pvc = build_resource_ref(api_version="v1", kind="pvc", namespace="payments", name="data-db")
    hpa = build_resource_ref(api_version="autoscaling/v2", kind="hpa", namespace="payments", name="payments-api")
    pdb = build_resource_ref(api_version="policy/v1", kind="pdb", namespace="payments", name="payments-api")
    service_account = build_resource_ref(api_version="v1", kind="sa", namespace="payments", name="payments-api")
    network_policy = build_resource_ref(api_version="networking.k8s.io/v1", kind="netpol", namespace="payments", name="deny-all")

    assert (pvc.kind, pvc.resource) == ("PersistentVolumeClaim", "persistentvolumeclaims")
    assert (hpa.kind, hpa.resource) == ("HorizontalPodAutoscaler", "horizontalpodautoscalers")
    assert (pdb.kind, pdb.resource) == ("PodDisruptionBudget", "poddisruptionbudgets")
    assert (service_account.kind, service_account.resource) == ("ServiceAccount", "serviceaccounts")
    assert (network_policy.kind, network_policy.resource) == ("NetworkPolicy", "networkpolicies")


def test_rancher_resource_path_handles_new_namespaced_and_cluster_scoped_resources():
    provider = _provider()
    cluster = _cluster(provider)

    pvc = build_resource_ref(api_version="v1", kind="pvc", namespace="payments", name="data-db")
    hpa = build_resource_ref(api_version="autoscaling/v2", kind="hpa", namespace="payments", name="payments-api")
    storage_class = build_resource_ref(api_version="storage.k8s.io/v1", kind="sc", name="fast")
    cluster_role_binding = build_resource_ref(api_version="rbac.authorization.k8s.io/v1", kind="clusterrolebinding", name="readers")

    assert rancher_resource_path(provider, cluster, pvc) == "/k8s/clusters/c-prod/api/v1/namespaces/payments/persistentvolumeclaims/data-db"
    assert rancher_resource_path(provider, cluster, hpa) == "/k8s/clusters/c-prod/apis/autoscaling/v2/namespaces/payments/horizontalpodautoscalers/payments-api"
    assert rancher_resource_path(provider, cluster, storage_class) == "/k8s/clusters/c-prod/apis/storage.k8s.io/v1/storageclasses/fast"
    assert rancher_resource_path(provider, cluster, cluster_role_binding) == "/k8s/clusters/c-prod/apis/rbac.authorization.k8s.io/v1/clusterrolebindings/readers"
