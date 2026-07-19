from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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


class KubernetesOpsDiagnosticsSummaryTests(TestCase):
    def create_user(self, username: str, *, grant_kubernetes: bool = True) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        if grant_kubernetes:
            UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        return user

    def setUp(self):
        self.cluster = K8sCluster.objects.create(name="prod-kz-1", environment="prod", health=K8sCluster.HEALTH_WARNING)

    def test_workload_diagnostics_returns_read_only_triage_without_secrets(self):
        user = self.create_user("k8s-diagnostics-workload")
        self.client.force_login(user)
        K8sAppRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            owner=K8sAppRef.OWNER_DEVTRON,
            team="payments",
            health=K8sCluster.HEALTH_WARNING,
            labels={"app.kubernetes.io/name": "payments-api", "secret": "raw-app-secret"},
            links={"devtron_app": "https://devtron.example.test/app/payments?token=raw-app-token"},
        )
        workload = K8sWorkloadRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            kind=K8sWorkloadRef.KIND_DEPLOYMENT,
            owner=K8sAppRef.OWNER_DEVTRON,
            team="payments",
            health=K8sCluster.HEALTH_WARNING,
            ready=1,
            desired=2,
            labels={"app.kubernetes.io/name": "payments-api", "password": "raw-workload-password"},
            links={"rancher": "https://rancher.example.test/workloads/payments?token=raw-workload-token"},
        )
        K8sPodRef.objects.create(
            name="payments-api-abc123",
            cluster=self.cluster,
            namespace="payments",
            health=K8sCluster.HEALTH_WARNING,
            phase="Running",
            owner_kind="ReplicaSet",
            owner_name="payments-api-abc123",
            ready_containers=1,
            total_containers=2,
            restart_count=4,
            labels={"app.kubernetes.io/name": "payments-api", "token": "raw-pod-token"},
        )
        K8sEvent.objects.create(
            cluster=self.cluster,
            event_uid="evt-payments-warning",
            severity=K8sEvent.SEVERITY_WARNING,
            reason="BackOff",
            message="payments-api waiting password=raw-event-secret",
            namespace="payments",
            involved_kind="Deployment",
            involved_name="payments-api",
            last_seen_at=timezone.now(),
        )

        response = self.client.get(
            reverse("api_kubernetes_diagnostics_summary"),
            {"scope": "workload", "workload_id": f"workload_{workload.id}"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["operation"], "diagnostics_summary")
        self.assertEqual(payload["scope"]["type"], "workload")
        self.assertEqual(payload["scope"]["target_id"], f"workload_{workload.id}")
        self.assertEqual(payload["owner_context"]["primary_owner"], "devtron")
        self.assertEqual(payload["owner_context"]["change_path"], "devtron_rollback_or_deploy")
        self.assertEqual(payload["signals"]["restart_count"], 4)
        self.assertEqual(payload["signals"]["warning_event_count"], 1)
        self.assertFalse(payload["policy"]["mutates_state"])
        self.assertFalse(payload["policy"]["external_links_included"])
        self.assertIn("devtron.open_rollback", payload["policy"]["requestable_actions"])
        self.assertIn("logs_snapshot", [step["id"] for step in payload["safe_next_steps"]])
        self.assertIn("readiness_gap", [item["id"] for item in payload["findings"]])
        self.assertIn("pod_restarts", [item["id"] for item in payload["findings"]])
        self.assertIn("warning_events", [item["id"] for item in payload["findings"]])
        self.assertNotIn("raw-app-secret", str(payload))
        self.assertNotIn("raw-workload-password", str(payload))
        self.assertNotIn("raw-pod-token", str(payload))
        self.assertNotIn("raw-event-secret", str(payload))
        self.assertNotIn("raw-workload-token", str(payload))
        audit = K8sAuditEvent.objects.get(action="k8s.diagnostics.summary")
        self.assertEqual(audit.payload["scope_type"], "workload")
        self.assertEqual(audit.payload["target_id"], f"workload_{workload.id}")
        self.assertEqual(audit.payload["warning_event_count"], 1)
        self.assertEqual(audit.payload["restart_count"], 4)
        self.assertNotIn("raw-event-secret", str(audit.payload))

    def test_pod_diagnostics_exposes_logs_endpoint_and_blocks_mutations(self):
        user = self.create_user("k8s-diagnostics-pod")
        self.client.force_login(user)
        pod = K8sPodRef.objects.create(
            name="worker-abc123",
            cluster=self.cluster,
            namespace="jobs",
            health=K8sCluster.HEALTH_DEGRADED,
            phase="CrashLoopBackOff",
            ready_containers=0,
            total_containers=1,
            restart_count=7,
            labels={"token": "raw-pod-token"},
        )

        response = self.client.get(reverse("api_kubernetes_diagnostics_summary"), {"scope": "pod", "pod_id": f"pod_{pod.id}"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["scope"]["type"], "pod")
        self.assertEqual(payload["health"]["severity"], "critical")
        self.assertEqual(payload["webterm_endpoints"]["logs"], f"/api/kubernetes/pods/pod_{pod.id}/logs/")
        self.assertIn("exec", payload["policy"]["blocked_actions"])
        self.assertIn("container_readiness_gap", [item["id"] for item in payload["findings"]])
        self.assertNotIn("raw-pod-token", str(payload))

    def test_namespace_diagnostics_supports_namespace_scope(self):
        user = self.create_user("k8s-diagnostics-namespace")
        self.client.force_login(user)
        namespace = K8sNamespace.objects.create(name="platform", cluster=self.cluster, health=K8sCluster.HEALTH_HEALTHY)
        K8sWorkloadRef.objects.create(
            name="controller",
            cluster=self.cluster,
            namespace="platform",
            kind=K8sWorkloadRef.KIND_DEPLOYMENT,
            health=K8sCluster.HEALTH_HEALTHY,
            ready=1,
            desired=1,
        )

        response = self.client.get(
            reverse("api_kubernetes_diagnostics_summary"),
            {"scope": "namespace", "cluster_id": f"cluster_{self.cluster.id}", "namespace_id": f"namespace_{namespace.id}"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["scope"]["type"], "namespace")
        self.assertEqual(payload["scope"]["namespace"], "platform")
        self.assertEqual(payload["health"]["severity"], "ok")
        self.assertIn("no_immediate_issue", [item["id"] for item in payload["findings"]])

    def test_network_diagnostics_supports_service_or_ingress_scope(self):
        user = self.create_user("k8s-diagnostics-network")
        self.client.force_login(user)
        K8sAppRef.objects.create(
            name="edge-api",
            cluster=self.cluster,
            namespace="edge",
            owner=K8sAppRef.OWNER_FLEET,
            team="platform",
            labels={"app.kubernetes.io/name": "edge-api", "token": "raw-network-app-token"},
        )
        K8sWorkloadRef.objects.create(
            name="edge-api",
            cluster=self.cluster,
            namespace="edge",
            kind=K8sWorkloadRef.KIND_DEPLOYMENT,
            owner=K8sAppRef.OWNER_FLEET,
            team="platform",
            health=K8sCluster.HEALTH_WARNING,
            labels={"app.kubernetes.io/name": "edge-api"},
        )
        K8sPodRef.objects.create(
            name="edge-api-abc123",
            cluster=self.cluster,
            namespace="edge",
            health=K8sCluster.HEALTH_WARNING,
            ready_containers=1,
            total_containers=2,
            restart_count=3,
            labels={"app.kubernetes.io/name": "edge-api", "password": "raw-network-pod-password"},
        )
        network = K8sNetworkRef.objects.create(
            name="edge-api",
            cluster=self.cluster,
            namespace="edge",
            kind=K8sNetworkRef.KIND_SERVICE,
            health=K8sCluster.HEALTH_WARNING,
            service_type="ClusterIP",
            endpoints=[{"pod": "edge-api-abc123", "token": "raw-network-endpoint-token"}],
            labels={"app.kubernetes.io/name": "edge-api"},
            links={"rancher": "https://rancher.example.test/service/edge-api?token=raw-network-link-token"},
        )
        K8sEvent.objects.create(
            cluster=self.cluster,
            event_uid="evt-edge-warning",
            severity=K8sEvent.SEVERITY_WARNING,
            reason="EndpointSliceNotReady",
            message="edge-api endpoint password=raw-network-event-secret",
            namespace="edge",
            involved_kind="Service",
            involved_name="edge-api",
            last_seen_at=timezone.now(),
        )

        response = self.client.get(
            reverse("api_kubernetes_diagnostics_summary"),
            {"scope": "network", "network_id": f"network_{network.id}"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["scope"]["type"], "network")
        self.assertEqual(payload["scope"]["target_id"], f"network_{network.id}")
        self.assertEqual(payload["scope"]["target_kind"], K8sNetworkRef.KIND_SERVICE)
        self.assertEqual(payload["owner_context"]["primary_owner"], K8sAppRef.OWNER_FLEET)
        self.assertEqual(payload["signals"]["restart_count"], 3)
        self.assertEqual(payload["signals"]["warning_event_count"], 1)
        self.assertEqual(payload["webterm_endpoints"]["detail"], f"/api/kubernetes/network/network_{network.id}/")
        self.assertIn("fleet_context", [step["id"] for step in payload["safe_next_steps"]])
        self.assertIn("fleet_gitops_or_mr", payload["owner_context"]["change_path"])
        self.assertIn("warning_events", [item["id"] for item in payload["findings"]])
        self.assertNotIn("raw-network-app-token", str(payload))
        self.assertNotIn("raw-network-pod-password", str(payload))
        self.assertNotIn("raw-network-endpoint-token", str(payload))
        self.assertNotIn("raw-network-event-secret", str(payload))
        self.assertNotIn("raw-network-link-token", str(payload))
        audit = K8sAuditEvent.objects.get(action="k8s.diagnostics.summary")
        self.assertEqual(audit.payload["scope_type"], "network")
        self.assertEqual(audit.payload["target_id"], f"network_{network.id}")

    def test_cluster_diagnostics_summarizes_inventory_health_without_provider_links(self):
        user = self.create_user("k8s-diagnostics-cluster")
        self.client.force_login(user)
        self.cluster.nodes_ready = 2
        self.cluster.nodes_total = 3
        self.cluster.namespace_count = 2
        self.cluster.workload_count = 2
        self.cluster.labels = {"credential": "raw-cluster-credential"}
        self.cluster.links = {"rancher": "https://rancher.example.test/c/prod?token=raw-cluster-link-token"}
        self.cluster.save(update_fields=["nodes_ready", "nodes_total", "namespace_count", "workload_count", "labels", "links"])
        K8sNamespace.objects.create(name="payments", cluster=self.cluster, health=K8sCluster.HEALTH_WARNING)
        K8sWorkloadRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            kind=K8sWorkloadRef.KIND_DEPLOYMENT,
            owner=K8sAppRef.OWNER_FLEET,
            team="payments",
            health=K8sCluster.HEALTH_DEGRADED,
            ready=0,
            desired=2,
        )
        K8sPodRef.objects.create(
            name="payments-api-abc123",
            cluster=self.cluster,
            namespace="payments",
            health=K8sCluster.HEALTH_DEGRADED,
            ready_containers=0,
            total_containers=1,
            restart_count=6,
        )
        K8sNetworkRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            kind=K8sNetworkRef.KIND_SERVICE,
            health=K8sCluster.HEALTH_WARNING,
        )
        K8sEvent.objects.create(
            cluster=self.cluster,
            event_uid="evt-cluster-warning",
            severity=K8sEvent.SEVERITY_WARNING,
            reason="FailedScheduling",
            message="scheduler token=raw-cluster-event-token",
            namespace="payments",
            involved_kind="Pod",
            involved_name="payments-api-abc123",
            last_seen_at=timezone.now(),
        )

        response = self.client.get(
            reverse("api_kubernetes_diagnostics_summary"),
            {"scope": "cluster", "cluster_id": f"cluster_{self.cluster.id}"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["scope"]["type"], "cluster")
        self.assertEqual(payload["scope"]["target_id"], f"cluster_{self.cluster.id}")
        self.assertEqual(payload["scope"]["target_kind"], "Cluster")
        self.assertEqual(payload["signals"]["nodes_ready"], 2)
        self.assertEqual(payload["signals"]["nodes_total"], 3)
        self.assertEqual(payload["signals"]["namespace_count"], 1)
        self.assertEqual(payload["signals"]["workload_count"], 1)
        self.assertEqual(payload["signals"]["network_count"], 1)
        self.assertEqual(payload["signals"]["restart_count"], 6)
        self.assertEqual(payload["signals"]["unhealthy_namespace_count"], 1)
        self.assertEqual(payload["signals"]["unhealthy_workload_count"], 1)
        self.assertEqual(payload["signals"]["unhealthy_pod_count"], 1)
        self.assertEqual(payload["webterm_endpoints"]["events"], f"/api/kubernetes/clusters/cluster_{self.cluster.id}/events/")
        self.assertIn("node_readiness_gap", [item["id"] for item in payload["findings"]])
        self.assertIn("unhealthy_namespaces", [item["id"] for item in payload["findings"]])
        self.assertIn("unhealthy_workloads", [item["id"] for item in payload["findings"]])
        self.assertIn("unhealthy_pods", [item["id"] for item in payload["findings"]])
        self.assertIn("review_cluster_inventory", [step["id"] for step in payload["safe_next_steps"]])
        self.assertFalse(payload["policy"]["mutates_state"])
        self.assertFalse(payload["policy"]["external_links_included"])
        self.assertNotIn("raw-cluster-credential", str(payload))
        self.assertNotIn("raw-cluster-link-token", str(payload))
        self.assertNotIn("raw-cluster-event-token", str(payload))
        audit = K8sAuditEvent.objects.get(action="k8s.diagnostics.summary")
        self.assertEqual(audit.payload["scope_type"], "cluster")
        self.assertEqual(audit.payload["cluster_id"], f"cluster_{self.cluster.id}")

    def test_diagnostics_rejects_invalid_scope_without_audit(self):
        user = self.create_user("k8s-diagnostics-invalid")
        self.client.force_login(user)

        response = self.client.get(reverse("api_kubernetes_diagnostics_summary"), {"scope": "invalid"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_scope")
        self.assertFalse(K8sAuditEvent.objects.exists())
