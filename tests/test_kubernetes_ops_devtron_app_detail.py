from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAppRef, K8sAuditEvent, K8sCluster, K8sEvent, K8sPodRef, K8sWorkloadRef


class KubernetesOpsDevtronAppDetailTests(TestCase):
    def create_user(self, username: str, *, is_staff: bool = False, grant_kubernetes: bool = True) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=is_staff)
        if grant_kubernetes:
            UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        return user

    def setUp(self):
        self.cluster = K8sCluster.objects.create(name="prod-kz-1", environment="prod", health=K8sCluster.HEALTH_WARNING)

    def test_devtron_app_detail_returns_related_inventory_for_reader_without_external_links(self):
        user = self.create_user("k8s-devtron-detail-reader")
        self.client.force_login(user)
        app = K8sAppRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            environment="prod",
            owner=K8sAppRef.OWNER_DEVTRON,
            team="payments",
            health=K8sCluster.HEALTH_WARNING,
            version="2026.07.01-1",
            links={
                "rollback": "https://devtron.example.test/app/rollback?token=raw-link-token",
                "history": "https://devtron.example.test/app/history?token=raw-link-token",
                "values": "https://devtron.example.test/app/values?token=raw-link-token",
                "logs": "https://devtron.example.test/app/logs?token=raw-link-token",
            },
            labels={
                "app.kubernetes.io/name": "payments-api",
                "meta.helm.sh/release-name": "payments",
                "helm.sh/chart": "payments-chart",
                "app.kubernetes.io/version": "1.2.3",
                "devtron.ai/deployment-id": "deploy-42",
                "helm_values": {"image": {"tag": "2026.07.01-1"}, "password": "raw-values-secret"},
                "token": "raw-label-token",
            },
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
            version="2026.07.01-1",
            labels={"app.kubernetes.io/name": "payments-api"},
        )
        K8sPodRef.objects.create(
            name="payments-api-abc123",
            cluster=self.cluster,
            namespace="payments",
            health=K8sCluster.HEALTH_DEGRADED,
            phase="Running",
            owner_kind="ReplicaSet",
            owner_name="payments-api",
            ready_containers=1,
            total_containers=2,
            restart_count=3,
            labels={"app.kubernetes.io/name": "payments-api"},
        )
        K8sEvent.objects.create(
            cluster=self.cluster,
            event_uid="evt-payments-api",
            severity=K8sEvent.SEVERITY_WARNING,
            reason="BackOff",
            message="Back-off restarting failed container password=raw-event-secret",
            namespace="payments",
            involved_kind="Pod",
            involved_name="payments-api-abc123",
            last_seen_at=timezone.now(),
        )

        response = self.client.get(reverse("api_kubernetes_devtron_app_detail", kwargs={"app_id": f"app_{app.id}"}))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["operation"], "devtron_app_detail")
        self.assertEqual(payload["app"]["name"], "payments-api")
        self.assertEqual(payload["app"]["links"], {})
        self.assertEqual(payload["app"]["labels"]["token"], "[redacted]")
        self.assertEqual(payload["summary"]["workload_count"], 1)
        self.assertEqual(payload["summary"]["pod_count"], 1)
        self.assertEqual(payload["summary"]["event_count"], 1)
        self.assertEqual(payload["summary"]["restart_count"], 3)
        self.assertEqual(payload["summary"]["ready_containers"], 1)
        self.assertEqual(payload["summary"]["total_containers"], 2)
        self.assertEqual(payload["summary"]["delivery_capabilities"], ["deployment_history", "helm_values", "rollback_context", "logs"])
        self.assertTrue(payload["summary"]["values_context_available"])
        self.assertEqual(payload["delivery_context"]["chart"]["name"], "payments-chart")
        self.assertEqual(payload["delivery_context"]["chart"]["release"], "payments")
        self.assertEqual(payload["delivery_context"]["links"], {})
        self.assertTrue(payload["delivery_context"]["values"]["available"])
        self.assertFalse(payload["delivery_context"]["values"]["body_returned"])
        self.assertEqual(payload["delivery_context"]["values"]["preview"]["password"], "[redacted]")
        self.assertEqual(payload["delivery_context"]["rollback"]["strategy"], "devtron_previous_deployment")
        self.assertTrue(payload["delivery_context"]["rollback"]["requires_approval"])
        self.assertFalse(payload["policy"]["mutates_state"])
        self.assertEqual(payload["policy"]["change_path"], "devtron_rollback_or_deploy")
        self.assertIn("devtron.open_rollback", payload["policy"]["requestable_actions"])
        self.assertIn("devtron_rollback", payload["policy"]["blocked_actions"])
        self.assertEqual(payload["events"][0]["message"], "Back-off restarting failed container password=[redacted]")
        self.assertNotIn("raw-link-token", str(payload))
        self.assertNotIn("raw-label-token", str(payload))
        self.assertNotIn("raw-event-secret", str(payload))
        self.assertNotIn("raw-values-secret", str(payload))
        audit = K8sAuditEvent.objects.get(action="k8s.devtron_app.detail")
        self.assertEqual(audit.cluster, self.cluster)
        self.assertEqual(audit.payload["app_id"], f"app_{app.id}")
        self.assertEqual(audit.payload["workload_count"], 1)
        self.assertEqual(audit.payload["delivery_capabilities"], ["deployment_history", "helm_values", "rollback_context", "logs"])
        self.assertTrue(audit.payload["values_visible"])
        self.assertNotIn("raw-event-secret", str(audit.payload))
        self.assertNotIn("raw-values-secret", str(audit.payload))

    def test_devtron_app_detail_staff_gets_sanitized_external_links_and_namespace_scope(self):
        staff = self.create_user("k8s-devtron-detail-staff", is_staff=True)
        self.client.force_login(staff)
        app = K8sAppRef.objects.create(
            name="billing-api",
            cluster=self.cluster,
            namespace="billing",
            owner=K8sAppRef.OWNER_DEVTRON,
            health=K8sCluster.HEALTH_HEALTHY,
            links={
                "history": "https://devtron.example.test/app/history?token=raw-link-token#tail",
                "values": "https://devtron.example.test/app/values?token=raw-link-token#tail",
            },
            labels={"app.kubernetes.io/instance": "billing-api"},
        )
        K8sPodRef.objects.create(
            name="billing-api-abc123",
            cluster=self.cluster,
            namespace="other",
            health=K8sCluster.HEALTH_DEGRADED,
            labels={"app.kubernetes.io/instance": "billing-api"},
        )

        response = self.client.get(reverse("api_kubernetes_devtron_app_detail", kwargs={"app_id": f"app_{app.id}"}))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["app"]["links"]["history"], "https://devtron.example.test/app/history")
        self.assertEqual(payload["delivery_context"]["links"]["history"], "https://devtron.example.test/app/history")
        self.assertEqual(payload["delivery_context"]["links"]["values"], "https://devtron.example.test/app/values")
        self.assertEqual(payload["summary"]["pod_count"], 0)
        self.assertNotIn("raw-link-token", str(payload))

    def test_devtron_app_detail_hides_missing_or_non_devtron_app(self):
        user = self.create_user("k8s-devtron-detail-missing")
        self.client.force_login(user)
        non_devtron = K8sAppRef.objects.create(
            name="external-api",
            cluster=self.cluster,
            namespace="external",
            owner=K8sAppRef.OWNER_EXTERNAL,
            health=K8sCluster.HEALTH_HEALTHY,
        )

        missing = self.client.get(reverse("api_kubernetes_devtron_app_detail", kwargs={"app_id": "app_999999"}))
        wrong_owner = self.client.get(reverse("api_kubernetes_devtron_app_detail", kwargs={"app_id": f"app_{non_devtron.id}"}))

        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["code"], "app_not_found")
        self.assertEqual(wrong_owner.status_code, 404)
        self.assertFalse(K8sAuditEvent.objects.exists())
