from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.models import (
    K8sAppRef,
    K8sAuditEvent,
    K8sCluster,
    K8sEvent,
    K8sNamespace,
    K8sNetworkRef,
    K8sPodRef,
    K8sWorkloadRef,
)


class KubernetesOpsInventoryTests(TestCase):
    def create_user(self, username: str) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        return user

    def test_cluster_related_endpoints_prefer_native_namespace_and_workload_inventory(self):
        user = self.create_user("k8s-native-inventory-reader")
        self.client.force_login(user)
        cluster = K8sCluster.objects.create(name="stage-webterm-ops", environment="stage")
        K8sAppRef.objects.create(
            name="demo-api-devtron",
            cluster=cluster,
            namespace="demo",
            environment="stage",
            owner=K8sAppRef.OWNER_DEVTRON,
            health=K8sCluster.HEALTH_HEALTHY,
        )
        K8sNamespace.objects.create(
            name="platform",
            cluster=cluster,
            environment="stage",
            health=K8sCluster.HEALTH_HEALTHY,
            workload_count=1,
            labels={"team": "platform"},
        )
        K8sWorkloadRef.objects.create(
            name="ingress-nginx",
            cluster=cluster,
            namespace="platform",
            kind=K8sWorkloadRef.KIND_DEPLOYMENT,
            environment="stage",
            owner="fleet",
            team="platform",
            health=K8sCluster.HEALTH_WARNING,
            ready=1,
            desired=2,
        )

        namespaces = self.client.get(reverse("api_kubernetes_cluster_namespaces", kwargs={"cluster_id": f"cluster_{cluster.id}"})).json()["namespaces"]
        workloads = self.client.get(reverse("api_kubernetes_cluster_workloads", kwargs={"cluster_id": f"cluster_{cluster.id}"})).json()["workloads"]

        self.assertEqual([item["name"] for item in namespaces], ["platform"])
        self.assertEqual(namespaces[0]["workloads"], 1)
        self.assertEqual(namespaces[0]["teams"], ["platform"])
        self.assertEqual([item["name"] for item in workloads], ["ingress-nginx"])
        self.assertEqual(workloads[0]["kind"], K8sWorkloadRef.KIND_DEPLOYMENT)
        self.assertEqual(workloads[0]["ready"], 1)
        self.assertEqual(workloads[0]["desired"], 2)

    def test_cluster_events_endpoint_prefers_native_kubernetes_events(self):
        user = self.create_user("k8s-native-event-reader")
        self.client.force_login(user)
        cluster = K8sCluster.objects.create(name="stage-webterm-ops")
        K8sAuditEvent.objects.create(user=user, username_snapshot=user.username, action="k8s.cluster.view", cluster=cluster)
        K8sEvent.objects.create(
            cluster=cluster,
            event_uid="event-1",
            source="rancher",
            severity=K8sEvent.SEVERITY_WARNING,
            reason="Unhealthy",
            message="Readiness probe failed",
            namespace="demo",
            involved_kind="Deployment",
            involved_name="demo-api",
            count=2,
        )

        response = self.client.get(reverse("api_kubernetes_cluster_events", kwargs={"cluster_id": f"cluster_{cluster.id}"}))

        self.assertEqual(response.status_code, 200)
        events = response.json()["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["source"], "rancher")
        self.assertEqual(events[0]["severity"], K8sEvent.SEVERITY_WARNING)
        self.assertEqual(events[0]["reason"], "Unhealthy")
        self.assertEqual(events[0]["namespace"], "demo")
        self.assertEqual(events[0]["count"], 2)

    def test_cluster_network_endpoint_returns_services_and_ingresses(self):
        user = self.create_user("k8s-network-reader")
        self.client.force_login(user)
        cluster = K8sCluster.objects.create(name="stage-webterm-ops", environment="stage")
        K8sNetworkRef.objects.create(
            cluster=cluster,
            namespace="demo",
            name="demo-api",
            kind=K8sNetworkRef.KIND_SERVICE,
            health=K8sCluster.HEALTH_HEALTHY,
            service_type="ClusterIP",
            ports=[{"port": 80, "targetPort": 8080}],
        )
        K8sNetworkRef.objects.create(
            cluster=cluster,
            namespace="demo",
            name="demo-api",
            kind=K8sNetworkRef.KIND_INGRESS,
            health=K8sCluster.HEALTH_HEALTHY,
            service_type="nginx",
            hosts=["demo.example.test"],
        )

        response = self.client.get(reverse("api_kubernetes_cluster_network", kwargs={"cluster_id": f"cluster_{cluster.id}"}))

        self.assertEqual(response.status_code, 200)
        rows = response.json()["network_refs"]
        self.assertEqual([item["kind"] for item in rows], [K8sNetworkRef.KIND_INGRESS, K8sNetworkRef.KIND_SERVICE])
        self.assertEqual(rows[0]["hosts"], ["demo.example.test"])
        self.assertEqual(rows[1]["ports"][0]["port"], 80)

    def test_cluster_pods_endpoint_returns_native_pod_inventory(self):
        user = self.create_user("k8s-pod-reader")
        self.client.force_login(user)
        cluster = K8sCluster.objects.create(name="stage-webterm-ops", environment="stage")
        K8sPodRef.objects.create(
            cluster=cluster,
            namespace="demo",
            name="demo-api-abc123",
            phase="Running",
            health=K8sCluster.HEALTH_WARNING,
            node_name="worker-a",
            pod_ip="10.42.0.12",
            owner_kind="ReplicaSet",
            owner_name="demo-api-abc",
            ready_containers=1,
            total_containers=2,
            restart_count=3,
            images=["demo-api:2026.06"],
        )

        response = self.client.get(reverse("api_kubernetes_cluster_pods", kwargs={"cluster_id": f"cluster_{cluster.id}"}))

        self.assertEqual(response.status_code, 200)
        pods = response.json()["pods"]
        self.assertEqual(pods[0]["name"], "demo-api-abc123")
        self.assertEqual(pods[0]["phase"], "Running")
        self.assertEqual(pods[0]["ready_containers"], 1)
        self.assertEqual(pods[0]["restart_count"], 3)
        self.assertEqual(pods[0]["images"], ["demo-api:2026.06"])
