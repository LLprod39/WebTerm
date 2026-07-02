from types import SimpleNamespace

from kubernetes_ops.services.admin_resource_sanitizer import sanitize_kubernetes_resource
from kubernetes_ops.services.admin_resource_summary import build_resource_row_summary


def test_resource_summary_includes_bounded_redacted_condition_context():
    conditions = [
        {
            "type": "Available",
            "status": "False",
            "reason": "MinimumReplicasUnavailable",
            "message": "password=raw-condition-secret",
        },
        *({"type": f"Extra{i}", "status": "True"} for i in range(8)),
    ]
    resource = sanitize_kubernetes_resource(
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "payments-api",
                "namespace": "payments",
                "generation": 3,
                "resourceVersion": "99",
                "ownerReferences": [{"apiVersion": "apps/v1", "kind": "ReplicaSet", "name": "payments-api-7d9", "controller": True}],
            },
            "spec": {
                "replicas": 2,
                "selector": {"matchLabels": {"app": "payments", "token": "raw-selector-token"}},
                "strategy": {"type": "RollingUpdate"},
                "template": {
                    "spec": {
                        "initContainers": [{"name": "migrate", "image": "registry.example/migrate:1"}],
                        "containers": [{"name": "api", "image": "registry.example/api:1-token=raw-image-secret"}],
                    }
                },
            },
            "status": {
                "replicas": 2,
                "readyReplicas": 1,
                "observedGeneration": 3,
                "conditions": conditions,
            },
        }
    )
    ref = SimpleNamespace(api_version="apps/v1", kind="Deployment", resource="deployments", namespace="payments", name="")

    summary = build_resource_row_summary(resource, ref=ref)

    assert summary["condition_count"] == 9
    assert len(summary["conditions"]) == 8
    assert summary["conditions_truncated"] is True
    assert summary["condition_summary"]["available"] == "False"
    assert summary["condition_summary"]["failing_count"] == 1
    assert summary["condition_summary"]["failing"][0]["message"] == "password=[redacted]"
    assert summary["generation"] == 3
    assert summary["resource_version"] == "99"
    assert summary["owner_references"] == [{"api_version": "apps/v1", "kind": "ReplicaSet", "name": "payments-api-7d9", "controller": True}]
    assert summary["containers"]["init_count"] == 1
    assert summary["containers"]["images"] == ["registry.example/api:1-token=[redacted]", "registry.example/migrate:1"]
    assert summary["workload"]["selector_keys"] == ["[redacted]", "app"]
    assert summary["workload"]["strategy"] == "RollingUpdate"
    assert summary["workload"]["observed_generation"] == 3
    assert "raw-condition-secret" not in str(summary)
    assert "raw-image-secret" not in str(summary)
    assert "raw-selector-token" not in str(summary)


def test_resource_summary_includes_storage_ingress_and_config_context():
    pvc = build_resource_row_summary(
        {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {"name": "data", "namespace": "payments"},
            "spec": {
                "storageClassName": "fast",
                "volumeName": "pvc-123",
                "volumeMode": "Filesystem",
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": "20Gi"}},
            },
            "status": {"phase": "Bound", "capacity": {"storage": "20Gi"}},
        },
        ref=SimpleNamespace(api_version="v1", kind="PersistentVolumeClaim", resource="persistentvolumeclaims", namespace="payments", name="data"),
    )
    ingress = build_resource_row_summary(
        sanitize_kubernetes_resource(
            {
                "apiVersion": "networking.k8s.io/v1",
                "kind": "Ingress",
                "metadata": {"name": "payments", "namespace": "payments"},
                "spec": {
                    "ingressClassName": "nginx",
                    "rules": [
                        {
                            "host": "payments.example.test",
                            "http": {"paths": [{"backend": {"service": {"name": "payments-api"}}}]},
                        }
                    ],
                    "tls": [{"hosts": ["payments.example.test"]}],
                },
            }
        ),
        ref=SimpleNamespace(api_version="networking.k8s.io/v1", kind="Ingress", resource="ingresses", namespace="payments", name="payments"),
    )
    secret = build_resource_row_summary(
        sanitize_kubernetes_resource(
            {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": "db", "namespace": "payments"},
                "type": "Opaque",
                "data": {"password": "raw-secret", "username": "user"},
                "binaryData": {"token.bin": "raw-token"},
            }
        ),
        ref=SimpleNamespace(api_version="v1", kind="Secret", resource="secrets", namespace="payments", name="db"),
    )

    assert pvc["storage"]["storage_class"] == "fast"
    assert pvc["storage"]["requested"] == "20Gi"
    assert pvc["storage"]["capacity"] == "20Gi"
    assert pvc["storage"]["access_modes"] == ["ReadWriteOnce"]
    assert ingress["ingress"]["hosts"] == ["payments.example.test"]
    assert ingress["ingress"]["backend_services"] == ["payments-api"]
    assert ingress["ingress"]["tls_host_count"] == 1
    assert secret["config"]["type"] == "Opaque"
    assert secret["config"]["data_key_count"] == 2
    assert secret["config"]["data_keys"] == ["[redacted]", "username"]
    assert secret["config"]["binary_data_keys"] == ["[redacted]"]
    assert "raw-secret" not in str(secret)
    assert "raw-token" not in str(secret)


def test_resource_summary_includes_batch_autoscaling_and_policy_context():
    job = build_resource_row_summary(
        {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {"name": "backfill", "namespace": "payments"},
            "spec": {"completions": 3, "parallelism": 1, "backoffLimit": 2},
            "status": {"active": 0, "succeeded": 3, "failed": 1, "completionTime": "2026-07-02T10:00:00Z"},
        },
        ref=SimpleNamespace(api_version="batch/v1", kind="Job", resource="jobs", namespace="payments", name="backfill"),
    )
    cronjob = build_resource_row_summary(
        {
            "apiVersion": "batch/v1",
            "kind": "CronJob",
            "metadata": {"name": "nightly", "namespace": "payments"},
            "spec": {
                "schedule": "0 1 * * *",
                "concurrencyPolicy": "Forbid",
                "jobTemplate": {"spec": {"parallelism": 2}},
            },
            "status": {"active": [{"name": "nightly-1"}], "lastScheduleTime": "2026-07-02T01:00:00Z"},
        },
        ref=SimpleNamespace(api_version="batch/v1", kind="CronJob", resource="cronjobs", namespace="payments", name="nightly"),
    )
    hpa = build_resource_row_summary(
        {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {"name": "payments-api", "namespace": "payments"},
            "spec": {
                "scaleTargetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": "payments-api"},
                "minReplicas": 2,
                "maxReplicas": 10,
                "metrics": [{"type": "Resource", "resource": {"name": "cpu", "target": {"type": "Utilization", "averageUtilization": 70}}}],
            },
            "status": {"currentReplicas": 3, "desiredReplicas": 4},
        },
        ref=SimpleNamespace(api_version="autoscaling/v2", kind="HorizontalPodAutoscaler", resource="horizontalpodautoscalers", namespace="payments", name="payments-api"),
    )
    pdb = build_resource_row_summary(
        {
            "apiVersion": "policy/v1",
            "kind": "PodDisruptionBudget",
            "metadata": {"name": "payments-api", "namespace": "payments"},
            "spec": {"minAvailable": "50%", "selector": {"matchLabels": {"app": "payments", "token": "raw-token"}}},
            "status": {"currentHealthy": 2, "desiredHealthy": 2, "disruptionsAllowed": 0, "expectedPods": 3},
        },
        ref=SimpleNamespace(api_version="policy/v1", kind="PodDisruptionBudget", resource="poddisruptionbudgets", namespace="payments", name="payments-api"),
    )
    netpol = build_resource_row_summary(
        {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {"name": "payments-api", "namespace": "payments"},
            "spec": {"podSelector": {"matchLabels": {"app": "payments"}}, "policyTypes": ["Ingress", "Egress"], "ingress": [{}], "egress": [{}, {}]},
        },
        ref=SimpleNamespace(api_version="networking.k8s.io/v1", kind="NetworkPolicy", resource="networkpolicies", namespace="payments", name="payments-api"),
    )

    assert job["batch"]["succeeded"] == 3
    assert job["batch"]["backoff_limit"] == 2
    assert cronjob["batch"]["schedule"] == "0 1 * * *"
    assert cronjob["batch"]["active_count"] == 1
    assert hpa["autoscaling"]["target"]["kind"] == "Deployment"
    assert hpa["autoscaling"]["desired_replicas"] == 4
    assert hpa["autoscaling"]["metrics"][0]["average_utilization"] == 70
    assert pdb["policy"]["min_available"] == "50%"
    assert pdb["policy"]["selector_keys"] == ["[redacted]", "app"]
    assert pdb["policy"]["disruptions_allowed"] == 0
    assert netpol["policy"]["policy_types"] == ["Ingress", "Egress"]
    assert netpol["policy"]["ingress_rule_count"] == 1
    assert netpol["policy"]["egress_rule_count"] == 2
    assert "raw-token" not in str(pdb)


def test_resource_summary_includes_rbac_endpoint_quota_and_service_account_context():
    role = build_resource_row_summary(
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "Role",
            "metadata": {"name": "operator", "namespace": "payments"},
            "rules": [{"apiGroups": [""], "resources": ["pods", "secrets"], "verbs": ["get", "list", "patch"]}],
        },
        ref=SimpleNamespace(api_version="rbac.authorization.k8s.io/v1", kind="Role", resource="roles", namespace="payments", name="operator"),
    )
    binding = build_resource_row_summary(
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "RoleBinding",
            "metadata": {"name": "operator", "namespace": "payments"},
            "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "Role", "name": "operator"},
            "subjects": [{"kind": "User", "name": "raw-user@example.test"}, {"kind": "ServiceAccount", "name": "operator"}],
        },
        ref=SimpleNamespace(api_version="rbac.authorization.k8s.io/v1", kind="RoleBinding", resource="rolebindings", namespace="payments", name="operator"),
    )
    endpoint_slice = build_resource_row_summary(
        {
            "apiVersion": "discovery.k8s.io/v1",
            "kind": "EndpointSlice",
            "metadata": {"name": "payments-api", "namespace": "payments"},
            "addressType": "IPv4",
            "endpoints": [
                {"addresses": ["10.0.0.1"], "conditions": {"ready": True, "serving": True}},
                {"addresses": ["10.0.0.2"], "conditions": {"ready": False, "terminating": True}},
            ],
            "ports": [{"name": "http", "port": 8080, "protocol": "TCP"}],
        },
        ref=SimpleNamespace(api_version="discovery.k8s.io/v1", kind="EndpointSlice", resource="endpointslices", namespace="payments", name="payments-api"),
    )
    quota = build_resource_row_summary(
        {
            "apiVersion": "v1",
            "kind": "ResourceQuota",
            "metadata": {"name": "payments", "namespace": "payments"},
            "spec": {"scopes": ["NotTerminating"]},
            "status": {"hard": {"requests.cpu": "4", "secrets": "10"}, "used": {"requests.cpu": "2", "secrets": "4"}},
        },
        ref=SimpleNamespace(api_version="v1", kind="ResourceQuota", resource="resourcequotas", namespace="payments", name="payments"),
    )
    service_account = build_resource_row_summary(
        {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {"name": "operator", "namespace": "payments"},
            "secrets": [{"name": "raw-token-secret"}],
            "imagePullSecrets": [{"name": "raw-pull-secret"}],
            "automountServiceAccountToken": False,
        },
        ref=SimpleNamespace(api_version="v1", kind="ServiceAccount", resource="serviceaccounts", namespace="payments", name="operator"),
    )

    assert role["rbac"]["rule_count"] == 1
    assert role["rbac"]["grants_write"] is True
    assert role["rbac"]["grants_secret_access"] is True
    assert binding["rbac"]["subject_count"] == 2
    assert binding["rbac"]["has_service_account_subject"] is True
    assert "raw-user@example.test" not in str(binding["rbac"])
    assert endpoint_slice["endpoints"]["endpoint_count"] == 2
    assert endpoint_slice["endpoints"]["ready_count"] == 1
    assert endpoint_slice["endpoints"]["terminating_count"] == 1
    assert "10.0.0.1" not in str(endpoint_slice["endpoints"])
    assert quota["quota"]["scopes"] == ["NotTerminating"]
    assert quota["quota"]["hard"]["requests.cpu"] == "4"
    assert quota["quota"]["used"]["[redacted]"] == "4"
    assert service_account["service_account"]["secret_ref_count"] == 1
    assert service_account["service_account"]["automount_service_account_token"] is False
    assert "raw-token-secret" not in str(service_account["service_account"])
