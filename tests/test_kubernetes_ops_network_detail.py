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


class KubernetesOpsNetworkDetailTests(TestCase):
    def create_user(self, username: str, *, is_staff: bool = False, grant_kubernetes: bool = True) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=is_staff)
        if grant_kubernetes:
            UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        return user

    def setUp(self):
        self.cluster = K8sCluster.objects.create(name="prod-kz-1", environment="prod", health=K8sCluster.HEALTH_WARNING)

    def test_network_detail_returns_service_runtime_context_without_external_links(self):
        user = self.create_user("k8s-network-detail-reader")
        self.client.force_login(user)
        app = K8sAppRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            owner=K8sAppRef.OWNER_DEVTRON,
            team="payments",
            health=K8sCluster.HEALTH_WARNING,
            labels={"app.kubernetes.io/name": "payments-api", "secret": "raw-app-secret"},
            links={"devtron": "https://devtron.example.test/app/payments?token=raw-app-link-token"},
        )
        K8sWorkloadRef.objects.create(
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
        )
        K8sPodRef.objects.create(
            name="payments-api-abc123",
            cluster=self.cluster,
            namespace="payments",
            health=K8sCluster.HEALTH_WARNING,
            phase="Running",
            owner_kind="ReplicaSet",
            owner_name="payments-api-abc123",
            pod_ip="10.42.0.15",
            ready_containers=1,
            total_containers=2,
            restart_count=4,
            labels={"app.kubernetes.io/name": "payments-api", "token": "raw-pod-token"},
        )
        K8sPodRef.objects.create(
            name="other-api-abc123",
            cluster=self.cluster,
            namespace="payments",
            health=K8sCluster.HEALTH_HEALTHY,
            phase="Running",
            labels={"app.kubernetes.io/name": "other-api"},
        )
        service = K8sNetworkRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            kind=K8sNetworkRef.KIND_SERVICE,
            health=K8sCluster.HEALTH_HEALTHY,
            service_type="ClusterIP",
            ports=[{"name": "http", "port": 80, "targetPort": 8080}],
            endpoints=[{"pod": "payments-api-abc123", "ip": "10.42.0.15", "token": "raw-endpoint-token"}],
            labels={"app.kubernetes.io/name": "payments-api", "secret": "raw-service-secret"},
            links={"rancher": "https://rancher.example.test/service/payments-api?token=raw-service-link-token"},
        )
        K8sNetworkRef.objects.create(
            name="payments-web",
            cluster=self.cluster,
            namespace="payments",
            kind=K8sNetworkRef.KIND_INGRESS,
            health=K8sCluster.HEALTH_HEALTHY,
            service_type="nginx",
            hosts=["payments.example.test"],
            endpoints=[{"serviceName": "payments-api", "secret": "raw-ingress-secret"}],
            labels={"app.kubernetes.io/name": "payments-api"},
        )
        K8sEvent.objects.create(
            cluster=self.cluster,
            event_uid="evt-service-warning",
            severity=K8sEvent.SEVERITY_WARNING,
            reason="EndpointSliceUpdate",
            message="payments-api endpoint update password=raw-event-password",
            namespace="payments",
            involved_kind="Service",
            involved_name="payments-api",
            last_seen_at=timezone.now(),
        )
        K8sEvent.objects.create(
            cluster=self.cluster,
            event_uid="evt-other-service",
            severity=K8sEvent.SEVERITY_WARNING,
            reason="Unrelated",
            message="other-api password=other-event-password",
            namespace="payments",
            involved_kind="Service",
            involved_name="other-api",
            last_seen_at=timezone.now(),
        )

        response = self.client.get(reverse("api_kubernetes_network_detail", kwargs={"network_id": f"network_{service.id}"}))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["operation"], "network_detail")
        self.assertEqual(payload["network_ref"]["id"], f"network_{service.id}")
        self.assertEqual(payload["network_ref"]["links"], {})
        self.assertEqual(payload["network_ref"]["labels"]["secret"], "[redacted]")
        self.assertEqual(payload["network_ref"]["endpoints"][0]["token"], "[redacted]")
        self.assertEqual(payload["owner_apps"][0]["id"], f"app_{app.id}")
        self.assertEqual(payload["owner_apps"][0]["links"], {})
        self.assertEqual(payload["workloads"][0]["name"], "payments-api")
        self.assertEqual(payload["workloads"][0]["labels"]["password"], "[redacted]")
        self.assertEqual(payload["pods"][0]["name"], "payments-api-abc123")
        self.assertEqual(payload["pods"][0]["labels"]["token"], "[redacted]")
        self.assertEqual(payload["related_network_refs"][0]["name"], "payments-web")
        self.assertEqual(payload["related_network_refs"][0]["endpoints"][0]["secret"], "[redacted]")
        self.assertEqual(payload["summary"]["owner_app_count"], 1)
        self.assertEqual(payload["summary"]["workload_count"], 1)
        self.assertEqual(payload["summary"]["pod_count"], 1)
        self.assertEqual(payload["summary"]["related_network_count"], 1)
        self.assertEqual(payload["summary"]["event_count"], 1)
        self.assertEqual(payload["summary"]["warning_event_count"], 1)
        self.assertEqual(payload["summary"]["restart_count"], 4)
        self.assertFalse(payload["policy"]["mutates_state"])
        self.assertIn("port_forward", payload["policy"]["blocked_actions"])
        self.assertEqual(payload["events"][0]["message"], "payments-api endpoint update password=[redacted]")
        self.assertNotIn("raw-service-secret", str(payload))
        self.assertNotIn("raw-event-password", str(payload))
        self.assertNotIn("other-event-password", str(payload))
        audit = K8sAuditEvent.objects.get(action="k8s.network.detail")
        self.assertEqual(audit.payload["network_id"], f"network_{service.id}")
        self.assertEqual(audit.payload["network_kind"], K8sNetworkRef.KIND_SERVICE)
        self.assertEqual(audit.payload["pod_count"], 1)
        self.assertEqual(audit.payload["related_network_count"], 1)
        self.assertNotIn("raw-event-password", str(audit.payload))

    def test_network_detail_staff_gets_sanitized_fallback_links(self):
        staff = self.create_user("k8s-network-detail-staff", is_staff=True)
        self.client.force_login(staff)
        ingress = K8sNetworkRef.objects.create(
            name="ingress-nginx",
            cluster=self.cluster,
            namespace="ingress-nginx",
            kind=K8sNetworkRef.KIND_INGRESS,
            health=K8sCluster.HEALTH_HEALTHY,
            hosts=["edge.example.test"],
            links={"rancher": "https://rancher.example.test/ingress/ingress-nginx?token=raw-link-token#rules"},
        )

        response = self.client.get(reverse("api_kubernetes_network_detail", kwargs={"network_id": f"network_{ingress.id}"}))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["network_ref"]["links"]["rancher"], "https://rancher.example.test/ingress/ingress-nginx")
        self.assertNotIn("raw-link-token", str(payload))
        self.assertNotIn("#rules", str(payload))

    def test_network_detail_returns_404_for_missing_network_without_audit(self):
        user = self.create_user("k8s-network-detail-missing")
        self.client.force_login(user)

        response = self.client.get(reverse("api_kubernetes_network_detail", kwargs={"network_id": "network_999999"}))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "network_not_found")
        self.assertFalse(K8sAuditEvent.objects.exists())
