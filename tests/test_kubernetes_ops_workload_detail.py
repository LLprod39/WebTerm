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


class KubernetesOpsWorkloadDetailTests(TestCase):
    def create_user(self, username: str, *, is_staff: bool = False, grant_kubernetes: bool = True) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=is_staff)
        if grant_kubernetes:
            UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        return user

    def setUp(self):
        self.cluster = K8sCluster.objects.create(name="prod-kz-1", environment="prod", health=K8sCluster.HEALTH_WARNING)

    def test_workload_detail_returns_runtime_context_for_reader_without_external_links(self):
        user = self.create_user("k8s-workload-detail-reader")
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
            links={"rancher": "https://rancher.example.test/workloads/payments-api?token=raw-workload-link-token"},
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
            restart_count=3,
            labels={"app.kubernetes.io/name": "payments-api", "token": "raw-pod-token"},
        )
        K8sPodRef.objects.create(
            name="other-api-abc123",
            cluster=self.cluster,
            namespace="payments",
            health=K8sCluster.HEALTH_HEALTHY,
            phase="Running",
            owner_kind="ReplicaSet",
            owner_name="other-api-abc123",
            labels={"app.kubernetes.io/name": "other-api"},
        )
        K8sNetworkRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            kind=K8sNetworkRef.KIND_SERVICE,
            health=K8sCluster.HEALTH_HEALTHY,
            service_type="ClusterIP",
            ports=[{"port": 80, "targetPort": 8080}],
            endpoints=[{"pod": "payments-api-abc123", "token": "raw-endpoint-token"}],
            labels={"app.kubernetes.io/name": "payments-api"},
            links={"rancher": "https://rancher.example.test/service/payments-api?token=raw-service-link-token"},
        )
        K8sEvent.objects.create(
            cluster=self.cluster,
            event_uid="evt-workload-warning",
            severity=K8sEvent.SEVERITY_WARNING,
            reason="BackOff",
            message="payments-api rollout waiting password=raw-event-password",
            namespace="payments",
            involved_kind="Deployment",
            involved_name="payments-api",
            last_seen_at=timezone.now(),
        )
        K8sEvent.objects.create(
            cluster=self.cluster,
            event_uid="evt-other-warning",
            severity=K8sEvent.SEVERITY_WARNING,
            reason="BackOff",
            message="other workload password=other-event-password",
            namespace="payments",
            involved_kind="Deployment",
            involved_name="other-api",
            last_seen_at=timezone.now(),
        )

        response = self.client.get(
            reverse("api_kubernetes_workload_detail", kwargs={"workload_id": f"workload_{workload.id}"})
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["operation"], "workload_detail")
        self.assertEqual(payload["workload"]["id"], f"workload_{workload.id}")
        self.assertEqual(payload["workload"]["links"], {})
        self.assertEqual(payload["workload"]["labels"]["password"], "[redacted]")
        self.assertEqual(payload["owner_apps"][0]["id"], f"app_{app.id}")
        self.assertEqual(payload["owner_apps"][0]["links"], {})
        self.assertEqual(payload["pods"][0]["name"], "payments-api-abc123")
        self.assertEqual(payload["pods"][0]["labels"]["token"], "[redacted]")
        self.assertEqual(payload["network_refs"][0]["links"], {})
        self.assertEqual(payload["network_refs"][0]["endpoints"][0]["token"], "[redacted]")
        self.assertEqual(payload["summary"]["owner_app_count"], 1)
        self.assertEqual(payload["summary"]["pod_count"], 1)
        self.assertEqual(payload["summary"]["network_count"], 1)
        self.assertEqual(payload["summary"]["event_count"], 1)
        self.assertEqual(payload["summary"]["warning_event_count"], 1)
        self.assertEqual(payload["summary"]["restart_count"], 3)
        self.assertFalse(payload["policy"]["mutates_state"])
        self.assertIn("scale", payload["policy"]["blocked_actions"])
        self.assertIn("gitops.create_merge_request", payload["policy"]["requestable_actions"])
        self.assertEqual(payload["events"][0]["message"], "payments-api rollout waiting password=[redacted]")
        self.assertNotIn("raw-workload-password", str(payload))
        self.assertNotIn("raw-event-password", str(payload))
        self.assertNotIn("other-event-password", str(payload))
        audit = K8sAuditEvent.objects.get(action="k8s.workload.detail")
        self.assertEqual(audit.payload["workload_id"], f"workload_{workload.id}")
        self.assertEqual(audit.payload["namespace"], "payments")
        self.assertEqual(audit.payload["pod_count"], 1)
        self.assertNotIn("raw-event-password", str(audit.payload))

    def test_workload_detail_staff_gets_sanitized_fallback_links(self):
        staff = self.create_user("k8s-workload-detail-staff", is_staff=True)
        self.client.force_login(staff)
        workload = K8sWorkloadRef.objects.create(
            name="ingress-nginx-controller",
            cluster=self.cluster,
            namespace="ingress-nginx",
            kind=K8sWorkloadRef.KIND_DEPLOYMENT,
            owner=K8sAppRef.OWNER_FLEET,
            health=K8sCluster.HEALTH_HEALTHY,
            links={
                "rancher": "https://rancher.example.test/workloads/ingress-nginx-controller?token=raw-link-token#tail"
            },
        )

        response = self.client.get(
            reverse("api_kubernetes_workload_detail", kwargs={"workload_id": f"workload_{workload.id}"})
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["workload"]["links"]["rancher"], "https://rancher.example.test/workloads/ingress-nginx-controller"
        )
        self.assertNotIn("raw-link-token", str(payload))
        self.assertNotIn("#tail", str(payload))

    def test_workload_detail_returns_404_for_missing_workload_without_audit(self):
        user = self.create_user("k8s-workload-detail-missing")
        self.client.force_login(user)

        response = self.client.get(reverse("api_kubernetes_workload_detail", kwargs={"workload_id": "workload_999999"}))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "workload_not_found")
        self.assertFalse(K8sAuditEvent.objects.exists())
