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


class KubernetesOpsNamespaceDetailTests(TestCase):
    def create_user(self, username: str, *, is_staff: bool = False, grant_kubernetes: bool = True) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=is_staff)
        if grant_kubernetes:
            UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        return user

    def setUp(self):
        self.cluster = K8sCluster.objects.create(name="prod-kz-1", environment="prod", health=K8sCluster.HEALTH_WARNING)

    def test_namespace_detail_returns_read_only_context_for_reader_without_external_links(self):
        user = self.create_user("k8s-namespace-detail-reader")
        self.client.force_login(user)
        namespace = K8sNamespace.objects.create(
            name="payments",
            cluster=self.cluster,
            environment="prod",
            health=K8sCluster.HEALTH_WARNING,
            app_count=1,
            workload_count=1,
            labels={"team": "payments", "token": "raw-namespace-token"},
            links={"rancher": "https://rancher.example.test/ns/payments?token=raw-link-token"},
        )
        K8sAppRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            owner=K8sAppRef.OWNER_DEVTRON,
            team="payments",
            health=K8sCluster.HEALTH_WARNING,
            labels={"secret": "raw-app-secret"},
            links={"devtron_app": "https://devtron.example.test/app/payments?token=raw-app-link-token"},
        )
        K8sWorkloadRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            kind=K8sWorkloadRef.KIND_DEPLOYMENT,
            owner=K8sAppRef.OWNER_DEVTRON,
            team="payments",
            health=K8sCluster.HEALTH_DEGRADED,
            ready=1,
            desired=2,
            labels={"password": "raw-workload-password"},
        )
        K8sPodRef.objects.create(
            name="payments-api-abc123",
            cluster=self.cluster,
            namespace="payments",
            health=K8sCluster.HEALTH_WARNING,
            phase="Running",
            owner_kind="Deployment",
            owner_name="payments-api",
            ready_containers=1,
            total_containers=2,
            restart_count=3,
            labels={"token": "raw-pod-token"},
        )
        K8sNetworkRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            kind=K8sNetworkRef.KIND_SERVICE,
            health=K8sCluster.HEALTH_HEALTHY,
            service_type="ClusterIP",
            ports=[{"port": 80, "targetPort": 8080}],
            links={"rancher": "https://rancher.example.test/service/payments?token=raw-network-link-token"},
        )
        K8sEvent.objects.create(
            cluster=self.cluster,
            event_uid="evt-payments-warning",
            severity=K8sEvent.SEVERITY_WARNING,
            reason="BackOff",
            message="payments-api waiting password=raw-event-secret",
            namespace="payments",
            involved_kind="Pod",
            involved_name="payments-api-abc123",
            last_seen_at=timezone.now(),
        )
        K8sEvent.objects.create(
            cluster=self.cluster,
            event_uid="evt-platform-warning",
            severity=K8sEvent.SEVERITY_WARNING,
            reason="BackOff",
            message="platform waiting password=other-secret",
            namespace="platform",
            involved_kind="Pod",
            involved_name="platform-api-abc123",
            last_seen_at=timezone.now(),
        )

        response = self.client.get(
            reverse(
                "api_kubernetes_namespace_detail",
                kwargs={"cluster_id": f"cluster_{self.cluster.id}", "namespace_id": f"namespace_{namespace.id}"},
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["operation"], "namespace_detail")
        self.assertEqual(payload["namespace"]["name"], "payments")
        self.assertEqual(payload["namespace"]["links"], {})
        self.assertEqual(payload["namespace"]["labels"]["token"], "[redacted]")
        self.assertEqual(payload["apps"][0]["links"], {})
        self.assertEqual(payload["workloads"][0]["labels"]["password"], "[redacted]")
        self.assertEqual(payload["pods"][0]["labels"]["token"], "[redacted]")
        self.assertEqual(payload["network_refs"][0]["links"], {})
        self.assertEqual(payload["summary"]["app_count"], 1)
        self.assertEqual(payload["summary"]["workload_count"], 1)
        self.assertEqual(payload["summary"]["pod_count"], 1)
        self.assertEqual(payload["summary"]["network_count"], 1)
        self.assertEqual(payload["summary"]["event_count"], 1)
        self.assertEqual(payload["summary"]["warning_event_count"], 1)
        self.assertEqual(payload["summary"]["health"], K8sCluster.HEALTH_DEGRADED)
        self.assertFalse(payload["policy"]["mutates_state"])
        self.assertIn("exec", payload["policy"]["blocked_actions"])
        self.assertIn("approval.request", payload["policy"]["requestable_actions"])
        self.assertEqual(payload["events"][0]["message"], "payments-api waiting password=[redacted]")
        self.assertNotIn("raw-namespace-token", str(payload))
        self.assertNotIn("raw-event-secret", str(payload))
        self.assertNotIn("other-secret", str(payload))
        audit = K8sAuditEvent.objects.get(action="k8s.namespace.detail")
        self.assertEqual(audit.payload["namespace"], "payments")
        self.assertEqual(audit.payload["workload_count"], 1)
        self.assertNotIn("raw-event-secret", str(audit.payload))

    def test_namespace_detail_staff_gets_sanitized_fallback_links(self):
        staff = self.create_user("k8s-namespace-detail-staff", is_staff=True)
        self.client.force_login(staff)
        K8sNamespace.objects.create(
            name="ingress-nginx",
            cluster=self.cluster,
            health=K8sCluster.HEALTH_HEALTHY,
            links={"rancher": "https://rancher.example.test/ns/ingress-nginx?token=raw-link-token#tail"},
        )
        K8sAppRef.objects.create(
            name="ingress-nginx",
            cluster=self.cluster,
            namespace="ingress-nginx",
            owner=K8sAppRef.OWNER_FLEET,
            health=K8sCluster.HEALTH_HEALTHY,
            links={"fleet": "https://rancher.example.test/fleet/ingress-nginx?token=raw-app-link-token#tail"},
        )

        response = self.client.get(
            reverse(
                "api_kubernetes_namespace_detail",
                kwargs={"cluster_id": f"cluster_{self.cluster.id}", "namespace_id": "ingress-nginx"},
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["namespace"]["links"]["rancher"], "https://rancher.example.test/ns/ingress-nginx")
        self.assertEqual(payload["apps"][0]["links"]["fleet"], "https://rancher.example.test/fleet/ingress-nginx")
        self.assertNotIn("raw-link-token", str(payload))
        self.assertNotIn("#tail", str(payload))

    def test_namespace_detail_supports_inferred_namespace_without_namespace_row(self):
        user = self.create_user("k8s-namespace-detail-fallback")
        self.client.force_login(user)
        K8sWorkloadRef.objects.create(
            name="worker",
            cluster=self.cluster,
            namespace="jobs",
            kind=K8sWorkloadRef.KIND_CRONJOB,
            owner="rancher",
            team="platform",
            health=K8sCluster.HEALTH_HEALTHY,
            ready=1,
            desired=1,
        )

        response = self.client.get(
            reverse(
                "api_kubernetes_namespace_detail",
                kwargs={"cluster_id": f"cluster_{self.cluster.id}", "namespace_id": "jobs"},
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["namespace"]["name"], "jobs")
        self.assertIsNone(payload["namespace"]["database_id"])
        self.assertEqual(payload["summary"]["workload_count"], 1)
        self.assertEqual(payload["summary"]["owners"], ["rancher"])
        self.assertEqual(payload["summary"]["teams"], ["platform"])

    def test_namespace_detail_returns_404_for_missing_namespace_without_audit(self):
        user = self.create_user("k8s-namespace-detail-missing")
        self.client.force_login(user)

        response = self.client.get(
            reverse(
                "api_kubernetes_namespace_detail",
                kwargs={"cluster_id": f"cluster_{self.cluster.id}", "namespace_id": "missing"},
            )
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "namespace_not_found")
        self.assertFalse(K8sAuditEvent.objects.exists())
