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
        payload = ROUTES.get(path)
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
