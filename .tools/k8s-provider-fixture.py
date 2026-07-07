from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


CLUSTER_ID = "c-webterm"
CLUSTER_NAME = "webterm-k8s"
NODE_NAME = "webterm-k8s-control-plane"
NOW = "2026-06-30T07:30:00Z"
BASE_LINK = "http://fixture.local"


def rancher_link(path: str) -> str:
    return f"{BASE_LINK}{path}"


def data(items: list[dict]) -> dict:
    return {"data": items}


def k8s_meta(name: str, namespace: str = "", labels: dict | None = None) -> dict:
    payload = {
        "name": name,
        "labels": labels or {},
        "creationTimestamp": NOW,
        "resourceVersion": "fixture",
    }
    if namespace:
        payload["namespace"] = namespace
    return payload


def k8s_list(api_version: str, kind: str, items: list[dict]) -> dict:
    return {
        "apiVersion": api_version,
        "kind": f"{kind}List",
        "metadata": {"resourceVersion": "fixture"},
        "items": items,
    }


def k8s_api_resource(name: str, kind: str, namespaced: bool, verbs: list[str], short_names: list[str] | None = None) -> dict:
    return {
        "name": name,
        "singularName": "",
        "namespaced": namespaced,
        "kind": kind,
        "verbs": verbs,
        "shortNames": short_names or [],
    }


K8S_CORE_RESOURCES = [
    k8s_api_resource("namespaces", "Namespace", False, ["get", "list", "watch"], ["ns"]),
    k8s_api_resource("nodes", "Node", False, ["get", "list", "watch"]),
    k8s_api_resource("pods", "Pod", True, ["get", "list", "watch"], ["po"]),
    k8s_api_resource("services", "Service", True, ["get", "list", "watch"], ["svc"]),
    k8s_api_resource("configmaps", "ConfigMap", True, ["get", "list", "watch"], ["cm"]),
    k8s_api_resource("secrets", "Secret", True, ["get", "list", "watch"]),
    k8s_api_resource("serviceaccounts", "ServiceAccount", True, ["get", "list", "watch"], ["sa"]),
]

K8S_GROUP_RESOURCES = {
    "apps/v1": [
        k8s_api_resource("deployments", "Deployment", True, ["get", "list", "watch", "patch"], ["deploy"]),
        k8s_api_resource("replicasets", "ReplicaSet", True, ["get", "list", "watch"], ["rs"]),
        k8s_api_resource("daemonsets", "DaemonSet", True, ["get", "list", "watch"], ["ds"]),
        k8s_api_resource("statefulsets", "StatefulSet", True, ["get", "list", "watch"], ["sts"]),
    ],
    "networking.k8s.io/v1": [
        k8s_api_resource("ingresses", "Ingress", True, ["get", "list", "watch"], ["ing"]),
        k8s_api_resource("networkpolicies", "NetworkPolicy", True, ["get", "list", "watch"], ["netpol"]),
    ],
    "apiextensions.k8s.io/v1": [
        k8s_api_resource("customresourcedefinitions", "CustomResourceDefinition", False, ["get", "list", "watch"], ["crd"]),
    ],
}

K8S_NAMESPACES = [
    {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": k8s_meta("payments", labels={"webterm.io/team": "payments"}),
        "status": {"phase": "Active"},
    },
    {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": k8s_meta("platform", labels={"webterm.io/team": "platform"}),
        "status": {"phase": "Active"},
    },
    {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": k8s_meta("observability", labels={"webterm.io/team": "sre"}),
        "status": {"phase": "Active"},
    },
]

K8S_NODES = [
    {
        "apiVersion": "v1",
        "kind": "Node",
        "metadata": k8s_meta("worker-1", labels={"node-role.kubernetes.io/worker": "true"}),
        "status": {"phase": "Ready", "conditions": [{"type": "Ready", "status": "True"}]},
    },
    {
        "apiVersion": "v1",
        "kind": "Node",
        "metadata": k8s_meta("worker-2", labels={"node-role.kubernetes.io/worker": "true"}),
        "status": {"phase": "Ready", "conditions": [{"type": "Ready", "status": "True"}]},
    },
    {
        "apiVersion": "v1",
        "kind": "Node",
        "metadata": k8s_meta("worker-3", labels={"node-role.kubernetes.io/worker": "true"}),
        "status": {"phase": "Ready", "conditions": [{"type": "Ready", "status": "True"}]},
    },
]

K8S_DEPLOYMENTS = [
    {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": k8s_meta("payments-api", "payments", {"app.kubernetes.io/name": "payments-api", "webterm.io/team": "payments"}),
        "spec": {"replicas": 3, "selector": {"matchLabels": {"app.kubernetes.io/name": "payments-api"}}},
        "status": {"readyReplicas": 3, "replicas": 3, "availableReplicas": 3},
    },
    {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": k8s_meta("broken-worker", "payments", {"app.kubernetes.io/name": "broken-worker", "webterm.io/team": "payments"}),
        "spec": {"replicas": 2, "selector": {"matchLabels": {"app.kubernetes.io/name": "broken-worker"}}},
        "status": {"readyReplicas": 0, "replicas": 2, "unavailableReplicas": 2, "reason": "ErrImagePull"},
    },
    {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": k8s_meta("demo-api", "platform", {"app.kubernetes.io/name": "demo-api", "webterm.io/team": "platform"}),
        "spec": {"replicas": 2, "selector": {"matchLabels": {"app.kubernetes.io/name": "demo-api"}}},
        "status": {"readyReplicas": 2, "replicas": 2, "availableReplicas": 2},
    },
]

K8S_PODS = [
    {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": k8s_meta("payments-api-7c76d8fdd9-4h2ks", "payments", {"app.kubernetes.io/name": "payments-api"}),
        "spec": {"nodeName": "worker-1", "containers": [{"name": "payments-api", "image": "payments-api:1.18.0-demo"}]},
        "status": {"phase": "Running", "podIP": "10.42.0.10", "containerStatuses": [{"name": "payments-api", "ready": True, "restartCount": 0}]},
    },
    {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": k8s_meta("payments-api-7c76d8fdd9-9n8pp", "payments", {"app.kubernetes.io/name": "payments-api"}),
        "spec": {"nodeName": "worker-2", "containers": [{"name": "payments-api", "image": "payments-api:1.18.0-demo"}]},
        "status": {"phase": "Running", "podIP": "10.42.0.11", "containerStatuses": [{"name": "payments-api", "ready": True, "restartCount": 0}]},
    },
    {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": k8s_meta("broken-worker-5dbb6df98c-jx2kf", "payments", {"app.kubernetes.io/name": "broken-worker"}),
        "spec": {"nodeName": "worker-3", "containers": [{"name": "broken-worker", "image": "broken-worker:1.18.0-demo"}]},
        "status": {"phase": "CrashLoopBackOff", "containerStatuses": [{"name": "broken-worker", "ready": False, "restartCount": 8}]},
    },
    {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": k8s_meta("demo-api-67b6f5d48c-qc82l", "platform", {"app.kubernetes.io/name": "demo-api"}),
        "spec": {"nodeName": "worker-1", "containers": [{"name": "demo-api", "image": "demo-api:0.9.4-demo"}]},
        "status": {"phase": "Running", "podIP": "10.42.1.10", "containerStatuses": [{"name": "demo-api", "ready": True, "restartCount": 0}]},
    },
]

K8S_SERVICES = [
    {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": k8s_meta("payments-api", "payments", {"app.kubernetes.io/name": "payments-api"}),
        "spec": {"type": "ClusterIP", "ports": [{"port": 8080, "targetPort": 8080}], "clusterIP": "10.43.0.10"},
        "status": {},
    },
    {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": k8s_meta("demo-api", "platform", {"app.kubernetes.io/name": "demo-api"}),
        "spec": {"type": "ClusterIP", "ports": [{"port": 9000, "targetPort": 9000}], "clusterIP": "10.43.1.10"},
        "status": {},
    },
]

K8S_INGRESSES = [
    {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": k8s_meta("payments-api-ingress", "payments", {"app.kubernetes.io/name": "payments-api"}),
        "spec": {"rules": [{"host": "payments.demo.local"}]},
        "status": {"loadBalancer": {"ingress": [{"hostname": "localhost"}]}},
    }
]

K8S_CRDS = [
    {
        "apiVersion": "apiextensions.k8s.io/v1",
        "kind": "CustomResourceDefinition",
        "metadata": k8s_meta("widgets.webterm.local"),
        "spec": {
            "group": "webterm.local",
            "names": {"kind": "Widget", "plural": "widgets", "singular": "widget"},
            "scope": "Namespaced",
            "versions": [{"name": "v1", "served": True, "storage": True}],
        },
        "status": {"conditions": [{"type": "Established", "status": "True"}]},
    }
]

K8S_OBJECTS = {
    ("v1", "namespaces"): K8S_NAMESPACES,
    ("v1", "nodes"): K8S_NODES,
    ("v1", "pods"): K8S_PODS,
    ("v1", "services"): K8S_SERVICES,
    ("v1", "configmaps"): [],
    ("v1", "secrets"): [],
    ("v1", "serviceaccounts"): [],
    ("apps/v1", "deployments"): K8S_DEPLOYMENTS,
    ("apps/v1", "replicasets"): [],
    ("apps/v1", "daemonsets"): [],
    ("apps/v1", "statefulsets"): [],
    ("networking.k8s.io/v1", "ingresses"): K8S_INGRESSES,
    ("networking.k8s.io/v1", "networkpolicies"): [],
    ("apiextensions.k8s.io/v1", "customresourcedefinitions"): K8S_CRDS,
}

K8S_KIND_BY_RESOURCE = {
    resource["name"]: resource["kind"]
    for resources in [K8S_CORE_RESOURCES, *K8S_GROUP_RESOURCES.values()]
    for resource in resources
}


def k8s_payload_for_path(path: str) -> dict | None:
    marker = "/k8s/clusters/"
    if marker not in path:
        return None
    _, _, tail = path.partition(marker)
    if "/" not in tail:
        return None
    suffix = tail.split("/", 1)[1].strip("/")
    if suffix == "api/v1":
        return {"apiVersion": "v1", "kind": "APIResourceList", "groupVersion": "v1", "resources": K8S_CORE_RESOURCES}
    if suffix == "apis":
        return {
            "apiVersion": "v1",
            "kind": "APIGroupList",
            "groups": [
                {
                    "name": api_version.rsplit("/", 1)[0],
                    "versions": [{"groupVersion": api_version, "version": api_version.rsplit("/", 1)[1]}],
                    "preferredVersion": {"groupVersion": api_version, "version": api_version.rsplit("/", 1)[1]},
                }
                for api_version in K8S_GROUP_RESOURCES
            ],
        }
    if suffix.startswith("apis/") and len(suffix.split("/")) == 3:
        _, group, version = suffix.split("/")
        api_version = f"{group}/{version}"
        return {
            "apiVersion": "v1",
            "kind": "APIResourceList",
            "groupVersion": api_version,
            "resources": K8S_GROUP_RESOURCES.get(api_version, []),
        }
    parsed = _parse_k8s_resource_suffix(suffix)
    if not parsed:
        return None
    api_version, namespace, resource, name, log_requested = parsed
    if log_requested:
        return {"lines": [f"{name}: demo log line 1", f"{name}: demo log line 2"], "message": ""}
    items = _namespace_items(K8S_OBJECTS.get((api_version, resource), []), namespace)
    kind = K8S_KIND_BY_RESOURCE.get(resource, resource.title())
    if name:
        for item in items:
            if item.get("metadata", {}).get("name") == name:
                return item
        return {"kind": "Status", "status": "Failure", "reason": "NotFound", "message": f"{kind} {name} not found"}
    return k8s_list(api_version, kind, items)


def _parse_k8s_resource_suffix(suffix: str) -> tuple[str, str, str, str, bool] | None:
    parts = suffix.split("/")
    if parts[:2] == ["api", "v1"]:
        api_version = "v1"
        rest = parts[2:]
    elif parts[:1] == ["apis"] and len(parts) >= 3:
        api_version = f"{parts[1]}/{parts[2]}"
        rest = parts[3:]
    else:
        return None
    namespace = ""
    if rest[:1] == ["namespaces"]:
        if len(rest) == 1:
            return api_version, namespace, "namespaces", "", False
        namespace = rest[1]
        rest = rest[2:]
    if not rest:
        return None
    resource = rest[0]
    name = rest[1] if len(rest) > 1 else ""
    log_requested = len(rest) > 2 and rest[2] == "log"
    return api_version, namespace, resource, name, log_requested


def _namespace_items(items: list[dict], namespace: str) -> list[dict]:
    if not namespace:
        return items
    effective_namespace = "platform" if namespace == "default" else namespace
    return [item for item in items if item.get("metadata", {}).get("namespace") == effective_namespace]


ROUTES = {
    "/v3/clusters": data(
        [
            {
                "id": CLUSTER_ID,
                "name": CLUSTER_NAME,
                "state": "active",
                "nodeCount": 1,
                "readyNodes": 1,
                "namespaceCount": 2,
                "workloadCount": 3,
                "labels": {
                    "webterm.io/environment": "test",
                    "webterm.io/team": "platform",
                },
                "links": {"self": rancher_link(f"/dashboard/c/{CLUSTER_ID}")},
            }
        ]
    ),
    "/v3/projectnamespaces": data(
        [
            {
                "id": f"{CLUSTER_ID}:webterm-stage",
                "name": "webterm-stage",
                "clusterId": CLUSTER_ID,
                "clusterName": CLUSTER_NAME,
                "state": "active",
                "workloadCount": 1,
                "appCount": 1,
                "labels": {
                    "webterm.io/environment": "stage",
                    "webterm.io/team": "platform",
                },
                "links": {"self": rancher_link(f"/dashboard/c/{CLUSTER_ID}/explorer/namespace/webterm-stage")},
            },
            {
                "id": f"{CLUSTER_ID}:webterm-prod",
                "name": "webterm-prod",
                "clusterId": CLUSTER_ID,
                "clusterName": CLUSTER_NAME,
                "state": "active",
                "workloadCount": 2,
                "appCount": 1,
                "labels": {
                    "webterm.io/environment": "prod",
                    "webterm.io/team": "payments",
                },
                "links": {"self": rancher_link(f"/dashboard/c/{CLUSTER_ID}/explorer/namespace/webterm-prod")},
            },
        ]
    ),
    "/v3/workloads": data(
        [
            {
                "id": f"deployment:{CLUSTER_ID}:webterm-stage:demo-api",
                "name": "demo-api",
                "clusterId": CLUSTER_ID,
                "clusterName": CLUSTER_NAME,
                "namespace": "webterm-stage",
                "kind": "deployment",
                "state": "active",
                "scale": 2,
                "readyReplicas": 2,
                "image": "nginx:1.27-alpine",
                "labels": {
                    "app.kubernetes.io/name": "demo-api",
                    "app.kubernetes.io/managed-by": "rancher",
                    "webterm.io/environment": "stage",
                    "webterm.io/team": "platform",
                },
                "links": {"self": rancher_link(f"/dashboard/c/{CLUSTER_ID}/explorer/apps.deployment/webterm-stage/demo-api")},
            },
            {
                "id": f"deployment:{CLUSTER_ID}:webterm-prod:payments-api",
                "name": "payments-api",
                "clusterId": CLUSTER_ID,
                "clusterName": CLUSTER_NAME,
                "namespace": "webterm-prod",
                "kind": "deployment",
                "state": "active",
                "scale": 1,
                "readyReplicas": 1,
                "image": "registry.k8s.io/e2e-test-images/agnhost:2.53",
                "labels": {
                    "app.kubernetes.io/name": "payments-api",
                    "app.kubernetes.io/managed-by": "rancher",
                    "webterm.io/environment": "prod",
                    "webterm.io/team": "payments",
                },
                "links": {"self": rancher_link(f"/dashboard/c/{CLUSTER_ID}/explorer/apps.deployment/webterm-prod/payments-api")},
            },
            {
                "id": f"deployment:{CLUSTER_ID}:webterm-prod:broken-worker",
                "name": "broken-worker",
                "clusterId": CLUSTER_ID,
                "clusterName": CLUSTER_NAME,
                "namespace": "webterm-prod",
                "kind": "deployment",
                "state": "degraded",
                "scale": 1,
                "readyReplicas": 0,
                "image": "registry.invalid/webterm/broken-worker:missing",
                "labels": {
                    "app.kubernetes.io/name": "broken-worker",
                    "app.kubernetes.io/managed-by": "rancher",
                    "webterm.io/environment": "prod",
                    "webterm.io/team": "payments",
                },
                "links": {"self": rancher_link(f"/dashboard/c/{CLUSTER_ID}/explorer/apps.deployment/webterm-prod/broken-worker")},
            },
        ]
    ),
    "/v3/pods": data(
        [
            {
                "id": f"{CLUSTER_ID}:webterm-stage:demo-api-7f79b858fb-a1111",
                "name": "demo-api-7f79b858fb-a1111",
                "clusterId": CLUSTER_ID,
                "clusterName": CLUSTER_NAME,
                "namespace": "webterm-stage",
                "state": "Running",
                "nodeName": NODE_NAME,
                "podIP": "10.244.0.21",
                "hostIP": "172.18.0.2",
                "ownerReferences": [{"kind": "ReplicaSet", "name": "demo-api-7f79b858fb"}],
                "containerStatuses": [
                    {
                        "name": "demo-api",
                        "ready": True,
                        "restartCount": 0,
                        "image": "nginx:1.27-alpine",
                        "state": {"running": {"startedAt": NOW}},
                    }
                ],
                "labels": {
                    "app.kubernetes.io/name": "demo-api",
                    "webterm.io/environment": "stage",
                    "webterm.io/team": "platform",
                },
                "links": {
                    "self": rancher_link(f"/dashboard/c/{CLUSTER_ID}/explorer/pod/webterm-stage/demo-api-7f79b858fb-a1111"),
                    "logs": rancher_link(f"/k8s/clusters/{CLUSTER_ID}/api/v1/namespaces/webterm-stage/pods/demo-api-7f79b858fb-a1111/log"),
                },
            },
            {
                "id": f"{CLUSTER_ID}:webterm-stage:demo-api-7f79b858fb-b2222",
                "name": "demo-api-7f79b858fb-b2222",
                "clusterId": CLUSTER_ID,
                "clusterName": CLUSTER_NAME,
                "namespace": "webterm-stage",
                "state": "Running",
                "nodeName": NODE_NAME,
                "podIP": "10.244.0.22",
                "hostIP": "172.18.0.2",
                "ownerReferences": [{"kind": "ReplicaSet", "name": "demo-api-7f79b858fb"}],
                "containerStatuses": [
                    {
                        "name": "demo-api",
                        "ready": True,
                        "restartCount": 0,
                        "image": "nginx:1.27-alpine",
                        "state": {"running": {"startedAt": NOW}},
                    }
                ],
                "labels": {
                    "app.kubernetes.io/name": "demo-api",
                    "webterm.io/environment": "stage",
                    "webterm.io/team": "platform",
                },
                "links": {
                    "self": rancher_link(f"/dashboard/c/{CLUSTER_ID}/explorer/pod/webterm-stage/demo-api-7f79b858fb-b2222"),
                    "logs": rancher_link(f"/k8s/clusters/{CLUSTER_ID}/api/v1/namespaces/webterm-stage/pods/demo-api-7f79b858fb-b2222/log"),
                },
            },
            {
                "id": f"{CLUSTER_ID}:webterm-prod:payments-api-6d46fb69c7-c3333",
                "name": "payments-api-6d46fb69c7-c3333",
                "clusterId": CLUSTER_ID,
                "clusterName": CLUSTER_NAME,
                "namespace": "webterm-prod",
                "state": "Running",
                "nodeName": NODE_NAME,
                "podIP": "10.244.0.31",
                "hostIP": "172.18.0.2",
                "ownerReferences": [{"kind": "ReplicaSet", "name": "payments-api-6d46fb69c7"}],
                "containerStatuses": [
                    {
                        "name": "payments-api",
                        "ready": True,
                        "restartCount": 0,
                        "image": "registry.k8s.io/e2e-test-images/agnhost:2.53",
                        "state": {"running": {"startedAt": NOW}},
                    }
                ],
                "labels": {
                    "app.kubernetes.io/name": "payments-api",
                    "webterm.io/environment": "prod",
                    "webterm.io/team": "payments",
                },
                "links": {
                    "self": rancher_link(f"/dashboard/c/{CLUSTER_ID}/explorer/pod/webterm-prod/payments-api-6d46fb69c7-c3333"),
                    "logs": rancher_link(f"/k8s/clusters/{CLUSTER_ID}/api/v1/namespaces/webterm-prod/pods/payments-api-6d46fb69c7-c3333/log"),
                },
            },
            {
                "id": f"{CLUSTER_ID}:webterm-prod:broken-worker-5df475b77f-d4444",
                "name": "broken-worker-5df475b77f-d4444",
                "clusterId": CLUSTER_ID,
                "clusterName": CLUSTER_NAME,
                "namespace": "webterm-prod",
                "state": "Pending",
                "nodeName": NODE_NAME,
                "podIP": "",
                "hostIP": "172.18.0.2",
                "ownerReferences": [{"kind": "ReplicaSet", "name": "broken-worker-5df475b77f"}],
                "containerStatuses": [
                    {
                        "name": "broken-worker",
                        "ready": False,
                        "restartCount": 0,
                        "image": "registry.invalid/webterm/broken-worker:missing",
                        "state": {"waiting": {"reason": "ErrImagePull", "message": "failed to pull image"}},
                    }
                ],
                "labels": {
                    "app.kubernetes.io/name": "broken-worker",
                    "webterm.io/environment": "prod",
                    "webterm.io/team": "payments",
                },
                "links": {
                    "self": rancher_link(f"/dashboard/c/{CLUSTER_ID}/explorer/pod/webterm-prod/broken-worker-5df475b77f-d4444"),
                    "logs": rancher_link(f"/k8s/clusters/{CLUSTER_ID}/api/v1/namespaces/webterm-prod/pods/broken-worker-5df475b77f-d4444/log"),
                },
            },
        ]
    ),
    "/v3/services": data(
        [
            {
                "id": f"{CLUSTER_ID}:webterm-stage:demo-api",
                "name": "demo-api",
                "clusterId": CLUSTER_ID,
                "clusterName": CLUSTER_NAME,
                "namespace": "webterm-stage",
                "state": "active",
                "serviceType": "ClusterIP",
                "ports": [{"name": "http", "port": 80, "protocol": "TCP", "targetPort": 80}],
                "labels": {"webterm.io/environment": "stage", "webterm.io/team": "platform"},
                "links": {"self": rancher_link(f"/dashboard/c/{CLUSTER_ID}/explorer/service/webterm-stage/demo-api")},
            },
            {
                "id": f"{CLUSTER_ID}:webterm-prod:payments-api",
                "name": "payments-api",
                "clusterId": CLUSTER_ID,
                "clusterName": CLUSTER_NAME,
                "namespace": "webterm-prod",
                "state": "active",
                "serviceType": "ClusterIP",
                "ports": [{"name": "http", "port": 80, "protocol": "TCP", "targetPort": 8080}],
                "labels": {"webterm.io/environment": "prod", "webterm.io/team": "payments"},
                "links": {"self": rancher_link(f"/dashboard/c/{CLUSTER_ID}/explorer/service/webterm-prod/payments-api")},
            },
        ]
    ),
    "/v3/ingresses": data(
        [
            {
                "id": f"{CLUSTER_ID}:webterm-stage:demo-api",
                "name": "demo-api",
                "clusterId": CLUSTER_ID,
                "clusterName": CLUSTER_NAME,
                "namespace": "webterm-stage",
                "state": "active",
                "ingressClassName": "nginx",
                "rules": [{"host": "demo.webterm.local"}],
                "publicEndpoints": [{"addresses": ["localhost"], "port": 8081, "protocol": "HTTP"}],
                "labels": {"webterm.io/environment": "stage", "webterm.io/team": "platform"},
                "links": {"self": rancher_link(f"/dashboard/c/{CLUSTER_ID}/explorer/ingress/webterm-stage/demo-api")},
            },
            {
                "id": f"{CLUSTER_ID}:webterm-prod:payments-api",
                "name": "payments-api",
                "clusterId": CLUSTER_ID,
                "clusterName": CLUSTER_NAME,
                "namespace": "webterm-prod",
                "state": "active",
                "ingressClassName": "nginx",
                "rules": [{"host": "payments.webterm.local"}],
                "publicEndpoints": [{"addresses": ["localhost"], "port": 8081, "protocol": "HTTP"}],
                "labels": {"webterm.io/environment": "prod", "webterm.io/team": "payments"},
                "links": {"self": rancher_link(f"/dashboard/c/{CLUSTER_ID}/explorer/ingress/webterm-prod/payments-api")},
            },
        ]
    ),
    "/v3/events": data(
        [
            {
                "id": f"{CLUSTER_ID}:webterm-prod:broken-worker:ErrImagePull",
                "uid": f"{CLUSTER_ID}:webterm-prod:broken-worker:ErrImagePull",
                "clusterId": CLUSTER_ID,
                "clusterName": CLUSTER_NAME,
                "namespace": "webterm-prod",
                "type": "Warning",
                "reason": "ErrImagePull",
                "message": "Failed to pull image registry.invalid/webterm/broken-worker:missing",
                "involvedObject": {"kind": "Pod", "name": "broken-worker-5df475b77f-d4444", "namespace": "webterm-prod"},
                "count": 4,
                "firstTimestamp": NOW,
                "lastTimestamp": NOW,
            },
            {
                "id": f"{CLUSTER_ID}:webterm-stage:demo-api:Scheduled",
                "uid": f"{CLUSTER_ID}:webterm-stage:demo-api:Scheduled",
                "clusterId": CLUSTER_ID,
                "clusterName": CLUSTER_NAME,
                "namespace": "webterm-stage",
                "type": "Normal",
                "reason": "Scheduled",
                "message": "Successfully assigned webterm-stage/demo-api pod to webterm-k8s-control-plane",
                "involvedObject": {"kind": "Pod", "name": "demo-api-7f79b858fb-a1111", "namespace": "webterm-stage"},
                "count": 1,
                "firstTimestamp": NOW,
                "lastTimestamp": NOW,
            },
        ]
    ),
    "/v1/fleet.cattle.io.bundles": data(
        [
            {
                "metadata": {
                    "name": "platform-demo",
                    "namespace": "fleet-local",
                    "labels": {"webterm.io/team": "platform"},
                },
                "spec": {
                    "repo": "https://example.invalid/webterm/platform-gitops.git",
                    "targetNamespace": "webterm-stage",
                },
                "status": {
                    "state": "ready",
                    "summary": {"ready": 1, "desiredReady": 1, "notReady": 0},
                },
                "links": {"self": rancher_link("/dashboard/c/local/fleet/bundles/fleet-local/platform-demo")},
            },
            {
                "metadata": {
                    "name": "payments-rollout",
                    "namespace": "fleet-local",
                    "labels": {"webterm.io/team": "payments"},
                },
                "spec": {
                    "repo": "https://example.invalid/webterm/payments-gitops.git",
                    "targetNamespace": "webterm-prod",
                },
                "status": {
                    "state": "rolling",
                    "summary": {"ready": 1, "desiredReady": 2, "notReady": 1},
                },
                "links": {"self": rancher_link("/dashboard/c/local/fleet/bundles/fleet-local/payments-rollout")},
            },
        ]
    ),
    "/orchestrator/app/list": {
        "apps": [
            {
                "appName": "demo-api",
                "clusterName": CLUSTER_NAME,
                "clusterId": CLUSTER_ID,
                "namespace": "webterm-stage",
                "environmentName": "stage",
                "teamName": "platform",
                "health": "healthy",
                "releaseVersion": "demo-api-1.0.0",
                "url": "http://devtron.fixture.local/app/demo-api",
                "logsUrl": "http://devtron.fixture.local/app/demo-api/logs",
                "historyUrl": "http://devtron.fixture.local/app/demo-api/history",
                "valuesUrl": "http://devtron.fixture.local/app/demo-api/values",
                "labels": {"webterm.io/team": "platform"},
            },
            {
                "appName": "payments-api",
                "clusterName": CLUSTER_NAME,
                "clusterId": CLUSTER_ID,
                "namespace": "webterm-prod",
                "environmentName": "prod",
                "teamName": "payments",
                "health": "healthy",
                "releaseVersion": "payments-api-2.4.0",
                "url": "http://devtron.fixture.local/app/payments-api",
                "logsUrl": "http://devtron.fixture.local/app/payments-api/logs",
                "historyUrl": "http://devtron.fixture.local/app/payments-api/history",
                "valuesUrl": "http://devtron.fixture.local/app/payments-api/values",
                "labels": {"webterm.io/team": "payments"},
            },
            {
                "appName": "broken-worker",
                "clusterName": CLUSTER_NAME,
                "clusterId": CLUSTER_ID,
                "namespace": "webterm-prod",
                "environmentName": "prod",
                "teamName": "payments",
                "health": "degraded",
                "releaseVersion": "broken-worker-0.1.0",
                "url": "http://devtron.fixture.local/app/broken-worker",
                "logsUrl": "http://devtron.fixture.local/app/broken-worker/logs",
                "historyUrl": "http://devtron.fixture.local/app/broken-worker/history",
                "valuesUrl": "http://devtron.fixture.local/app/broken-worker/values",
                "labels": {"webterm.io/team": "payments"},
            },
        ]
    },
}


class FixtureHandler(BaseHTTPRequestHandler):
    server_version = "WebTermK8sFixture/1.0"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        payload = k8s_payload_for_path(path) or ROUTES.get(path)
        if payload is None:
            self._send_json(404, {"error": "not found", "path": path, "routes": sorted(ROUTES)})
            return
        self._send_json(200, payload)

    def log_message(self, format: str, *args) -> None:
        return

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18090)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), FixtureHandler)
    print(f"Serving Kubernetes provider fixture on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
