from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAppRef, K8sAuditEvent, K8sCluster, K8sEvent, K8sWorkloadRef


class KubernetesOpsDescribeTests(TestCase):
    def create_user(self, username: str, *, is_staff: bool = False) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=is_staff)
        UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        return user

    def test_workload_describe_returns_read_only_snapshot_and_related_events(self):
        user = self.create_user("k8s-describe-reader")
        self.client.force_login(user)
        cluster = K8sCluster.objects.create(name="prod-kz-1", environment="prod")
        workload = K8sWorkloadRef.objects.create(
            name="payments-api",
            cluster=cluster,
            namespace="payments",
            kind=K8sWorkloadRef.KIND_DEPLOYMENT,
            owner="rancher",
            team="payments",
            health=K8sCluster.HEALTH_WARNING,
            ready=1,
            desired=2,
            links={"logs": "https://devtron.example.test/apps/1/logs?token=raw-url-token#tail", "secret_link": "https://secret.example.test"},
            labels={"app": "payments-api", "token": "raw-token", "nested": {"password": "raw-password"}},
        )
        K8sEvent.objects.create(
            cluster=cluster,
            event_uid="event-1",
            severity=K8sEvent.SEVERITY_WARNING,
            reason="Unhealthy",
            message="Readiness probe failed for payments-api",
            namespace="payments",
            involved_kind="Deployment",
            involved_name="payments-api",
            count=2,
        )

        response = self.client.get(reverse("api_kubernetes_workload_describe", kwargs={"workload_id": f"workload_{workload.id}"}))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["target"]["id"], f"workload_{workload.id}")
        self.assertEqual(payload["target"]["source"], "workload")
        self.assertFalse(payload["policy"]["mutates_state"])
        self.assertIn("rollout_restart", payload["policy"]["blocked_actions"])
        self.assertEqual(payload["manifest_preview"]["kind"], "Deployment")
        self.assertEqual(payload["manifest_preview"]["metadata"]["labels"]["token"], "[redacted]")
        self.assertEqual(payload["manifest_preview"]["metadata"]["labels"]["nested"]["password"], "[redacted]")
        self.assertEqual(payload["target"]["links"], {})
        self.assertFalse(payload["target"]["external_links_policy"]["visible"])
        self.assertNotIn("raw-token", str(payload))
        self.assertNotIn("raw-password", str(payload))
        self.assertNotIn("raw-url-token", str(payload))
        self.assertEqual(payload["related_events"][0]["reason"], "Unhealthy")

    def test_staff_workload_describe_returns_sanitized_external_fallback_links(self):
        user = self.create_user("k8s-describe-staff", is_staff=True)
        self.client.force_login(user)
        cluster = K8sCluster.objects.create(name="prod-kz-1", environment="prod")
        workload = K8sWorkloadRef.objects.create(
            name="payments-api",
            cluster=cluster,
            namespace="payments",
            kind=K8sWorkloadRef.KIND_DEPLOYMENT,
            links={"logs": "https://devtron.example.test/apps/1/logs?token=raw-url-token#tail", "secret_link": "https://secret.example.test"},
        )

        response = self.client.get(reverse("api_kubernetes_workload_describe", kwargs={"workload_id": f"workload_{workload.id}"}))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["target"]["external_links_policy"]["visible"])
        self.assertEqual(payload["target"]["links"]["logs"], "https://devtron.example.test/apps/1/logs")
        self.assertEqual(payload["target"]["links"]["secret_link"], "[redacted]")
        self.assertNotIn("raw-url-token", str(payload))

    def test_workload_describe_supports_devtron_app_fallback(self):
        user = self.create_user("k8s-describe-app-reader")
        self.client.force_login(user)
        cluster = K8sCluster.objects.create(name="prod-kz-1", environment="prod")
        app = K8sAppRef.objects.create(
            name="payments-worker",
            cluster=cluster,
            namespace="payments",
            owner=K8sAppRef.OWNER_DEVTRON,
            team="payments",
            health=K8sCluster.HEALTH_DEGRADED,
        )
        K8sAuditEvent.objects.create(
            user=user,
            username_snapshot=user.username,
            action="k8s.deeplink.open",
            cluster=cluster,
            payload={"target_id": f"app_{app.id}", "target_name": "payments-worker"},
        )

        response = self.client.get(reverse("api_kubernetes_workload_describe", kwargs={"workload_id": f"app_{app.id}"}))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["target"]["source"], "app")
        self.assertEqual(payload["target"]["owner"], K8sAppRef.OWNER_DEVTRON)
        self.assertEqual(payload["manifest_preview"]["kind"], "ApplicationRef")
        self.assertEqual(payload["related_events"][0]["source"], "webterm_audit")

    def test_workload_describe_returns_404_for_missing_target(self):
        user = self.create_user("k8s-describe-missing-reader")
        self.client.force_login(user)

        response = self.client.get(reverse("api_kubernetes_workload_describe", kwargs={"workload_id": "workload_404"}))

        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()["success"])
