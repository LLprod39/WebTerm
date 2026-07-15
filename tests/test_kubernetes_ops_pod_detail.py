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
    K8sNetworkRef,
    K8sPodRef,
    K8sWorkloadRef,
)


class KubernetesOpsPodDetailTests(TestCase):
    def create_user(self, username: str, *, is_staff: bool = False, grant_kubernetes: bool = True) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=is_staff)
        if grant_kubernetes:
            UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        return user

    def setUp(self):
        self.cluster = K8sCluster.objects.create(name="prod-kz-1", environment="prod", health=K8sCluster.HEALTH_WARNING)

    def test_pod_detail_returns_owner_context_for_reader_without_external_links(self):
        user = self.create_user("k8s-pod-detail-reader")
        self.client.force_login(user)
        app = K8sAppRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            owner=K8sAppRef.OWNER_DEVTRON,
            team="payments",
            health=K8sCluster.HEALTH_WARNING,
            version="2026.07.01",
            labels={"app.kubernetes.io/name": "payments-api", "secret": "raw-app-secret"},
            links={"devtron_app": "https://devtron.example.test/app/payments?token=raw-app-link-token"},
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
            version="2026.07.01",
            labels={"app.kubernetes.io/name": "payments-api", "password": "raw-workload-password"},
        )
        pod = K8sPodRef.objects.create(
            name="payments-api-abc123",
            cluster=self.cluster,
            namespace="payments",
            health=K8sCluster.HEALTH_WARNING,
            phase="Running",
            node_name="worker-1",
            pod_ip="10.42.0.10",
            host_ip="10.0.0.10",
            owner_kind="ReplicaSet",
            owner_name="payments-api-abc123",
            ready_containers=1,
            total_containers=2,
            restart_count=3,
            images=["registry.example.test/payments-api:2026.07.01"],
            labels={"app.kubernetes.io/name": "payments-api", "token": "raw-pod-token"},
            links={"rancher": "https://rancher.example.test/pod/payments-api-abc123?token=raw-pod-link-token"},
        )
        K8sPodRef.objects.create(
            name="payments-api-def456",
            cluster=self.cluster,
            namespace="payments",
            health=K8sCluster.HEALTH_HEALTHY,
            phase="Running",
            owner_kind="ReplicaSet",
            owner_name="payments-api-def456",
            ready_containers=2,
            total_containers=2,
            restart_count=0,
            labels={"app.kubernetes.io/name": "payments-api"},
        )
        K8sNetworkRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            kind=K8sNetworkRef.KIND_SERVICE,
            health=K8sCluster.HEALTH_HEALTHY,
            service_type="ClusterIP",
            ports=[{"port": 80, "targetPort": 8080}],
            endpoints=[{"pod": "payments-api-abc123", "ip": "10.42.0.10", "token": "raw-endpoint-token"}],
            labels={"app.kubernetes.io/name": "payments-api"},
            links={"rancher": "https://rancher.example.test/service/payments-api?token=raw-service-link-token"},
        )
        K8sEvent.objects.create(
            cluster=self.cluster,
            event_uid="evt-payments-pod",
            severity=K8sEvent.SEVERITY_WARNING,
            reason="BackOff",
            message="payments-api-abc123 waiting token=raw-event-token",
            namespace="payments",
            involved_kind="Pod",
            involved_name="payments-api-abc123",
            last_seen_at=timezone.now(),
        )
        K8sEvent.objects.create(
            cluster=self.cluster,
            event_uid="evt-other-pod",
            severity=K8sEvent.SEVERITY_WARNING,
            reason="BackOff",
            message="other pod token=other-event-token",
            namespace="payments",
            involved_kind="Pod",
            involved_name="other-api-abc123",
            last_seen_at=timezone.now(),
        )

        response = self.client.get(reverse("api_kubernetes_pod_detail", kwargs={"pod_id": f"pod_{pod.id}"}))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["operation"], "pod_detail")
        self.assertEqual(payload["pod"]["name"], pod.name)
        self.assertEqual(payload["pod"]["links"], {})
        self.assertEqual(payload["pod"]["labels"]["token"], "[redacted]")
        self.assertEqual(payload["owner_apps"][0]["id"], f"app_{app.id}")
        self.assertEqual(payload["owner_apps"][0]["links"], {})
        self.assertEqual(payload["owner_workloads"][0]["id"], f"workload_{workload.id}")
        self.assertEqual(payload["owner_workloads"][0]["labels"]["password"], "[redacted]")
        self.assertEqual(payload["sibling_pods"][0]["name"], "payments-api-def456")
        self.assertEqual(payload["network_refs"][0]["links"], {})
        self.assertEqual(payload["network_refs"][0]["endpoints"][0]["token"], "[redacted]")
        self.assertEqual(payload["summary"]["owner_workload_count"], 1)
        self.assertEqual(payload["summary"]["owner_app_count"], 1)
        self.assertEqual(payload["summary"]["sibling_pod_count"], 1)
        self.assertEqual(payload["summary"]["network_count"], 1)
        self.assertEqual(payload["summary"]["event_count"], 1)
        self.assertEqual(payload["summary"]["warning_event_count"], 1)
        self.assertEqual(payload["summary"]["related_restart_count"], 3)
        self.assertFalse(payload["policy"]["mutates_state"])
        self.assertIn("exec", payload["policy"]["blocked_actions"])
        self.assertIn("logs.snapshot", payload["policy"]["requestable_actions"])
        self.assertEqual(payload["policy"]["logs"]["snapshot_endpoint"], f"/api/kubernetes/pods/pod_{pod.id}/logs/")
        self.assertEqual(payload["events"][0]["message"], "payments-api-abc123 waiting token=[redacted]")
        self.assertNotIn("raw-pod-token", str(payload))
        self.assertNotIn("raw-event-token", str(payload))
        self.assertNotIn("other-event-token", str(payload))
        audit = K8sAuditEvent.objects.get(action="k8s.pod.detail")
        self.assertEqual(audit.payload["pod_id"], f"pod_{pod.id}")
        self.assertEqual(audit.payload["namespace"], "payments")
        self.assertEqual(audit.payload["owner_workload_count"], 1)
        self.assertNotIn("raw-event-token", str(audit.payload))

    def test_pod_detail_staff_gets_sanitized_fallback_links(self):
        staff = self.create_user("k8s-pod-detail-staff", is_staff=True)
        self.client.force_login(staff)
        pod = K8sPodRef.objects.create(
            name="ingress-nginx-controller-abc123",
            cluster=self.cluster,
            namespace="ingress-nginx",
            health=K8sCluster.HEALTH_HEALTHY,
            phase="Running",
            owner_kind="ReplicaSet",
            owner_name="ingress-nginx-controller-abc123",
            links={"rancher": "https://rancher.example.test/pod/ingress-nginx-controller-abc123?token=raw-link-token#tail"},
        )

        response = self.client.get(reverse("api_kubernetes_pod_detail", kwargs={"pod_id": f"pod_{pod.id}"}))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["pod"]["links"]["rancher"], "https://rancher.example.test/pod/ingress-nginx-controller-abc123")
        self.assertNotIn("raw-link-token", str(payload))
        self.assertNotIn("#tail", str(payload))

    def test_pod_detail_returns_404_for_missing_pod_without_audit(self):
        user = self.create_user("k8s-pod-detail-missing")
        self.client.force_login(user)

        response = self.client.get(reverse("api_kubernetes_pod_detail", kwargs={"pod_id": "pod_999999"}))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "pod_not_found")
        self.assertFalse(K8sAuditEvent.objects.exists())
