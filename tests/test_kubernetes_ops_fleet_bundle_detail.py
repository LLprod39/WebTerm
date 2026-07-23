from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAppRef, K8sAuditEvent, K8sCluster, K8sEvent, K8sFleetBundle, K8sWorkloadRef


class KubernetesOpsFleetBundleDetailTests(TestCase):
    def create_user(self, username: str, *, is_staff: bool = False, grant_kubernetes: bool = True) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=is_staff)
        if grant_kubernetes:
            UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        return user

    def setUp(self):
        self.cluster = K8sCluster.objects.create(name="prod-kz-1", environment="prod", health=K8sCluster.HEALTH_WARNING)

    def test_fleet_bundle_detail_returns_gitops_context_for_reader_without_external_links(self):
        user = self.create_user("k8s-fleet-detail-reader")
        self.client.force_login(user)
        bundle = K8sFleetBundle.objects.create(
            name="fleet-local/payments-rollout",
            source="gitrepo/platform",
            target="payments",
            status=K8sFleetBundle.STATUS_ROLLING,
            ready=1,
            desired=2,
            partitions=[{"name": "prod", "ready": 1, "desired": 2}],
            links={"rancher_fleet": "https://rancher.example.test/fleet/payments?token=raw-link-token"},
            labels={"fleet.cattle.io/bundle-id": "fleet-local/payments-rollout", "token": "raw-label-token"},
        )
        K8sAppRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            owner=K8sAppRef.OWNER_FLEET,
            health=K8sCluster.HEALTH_WARNING,
            labels={"fleet.cattle.io/bundle-id": "fleet-local/payments-rollout"},
        )
        K8sWorkloadRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            kind=K8sWorkloadRef.KIND_DEPLOYMENT,
            owner=K8sAppRef.OWNER_FLEET,
            health=K8sCluster.HEALTH_DEGRADED,
            ready=1,
            desired=2,
            labels={"fleet.cattle.io/bundle-id": "fleet-local/payments-rollout"},
        )
        K8sEvent.objects.create(
            cluster=self.cluster,
            event_uid="evt-fleet-payments",
            severity=K8sEvent.SEVERITY_WARNING,
            reason="Modified",
            message="Fleet bundle payments-rollout waiting password=raw-event-secret",
            namespace="payments",
            involved_kind="Deployment",
            involved_name="payments-api",
            last_seen_at=timezone.now(),
        )
        other_cluster = K8sCluster.objects.create(
            name="other-prod", environment="prod", health=K8sCluster.HEALTH_HEALTHY
        )
        K8sEvent.objects.create(
            cluster=other_cluster,
            event_uid="evt-fleet-payments-other",
            severity=K8sEvent.SEVERITY_WARNING,
            reason="Modified",
            message="Fleet bundle payments-rollout from wrong cluster password=other-secret",
            namespace="payments",
            involved_kind="Deployment",
            involved_name="payments-api",
            last_seen_at=timezone.now(),
        )

        response = self.client.get(
            reverse("api_kubernetes_fleet_bundle_detail", kwargs={"bundle_id": f"fleet_{bundle.id}"})
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["operation"], "fleet_bundle_detail")
        self.assertEqual(payload["bundle"]["name"], "fleet-local/payments-rollout")
        self.assertEqual(payload["bundle"]["links"], {})
        self.assertEqual(payload["bundle"]["labels"]["token"], "[redacted]")
        self.assertEqual(payload["summary"]["app_count"], 1)
        self.assertEqual(payload["summary"]["workload_count"], 1)
        self.assertEqual(payload["summary"]["event_count"], 1)
        self.assertEqual(payload["summary"]["partition_count"], 1)
        self.assertEqual(payload["summary"]["unhealthy_workload_count"], 1)
        self.assertFalse(payload["policy"]["mutates_state"])
        self.assertEqual(payload["policy"]["change_path"], "fleet_gitops_or_mr")
        self.assertIn("fleet.rollout.pause", payload["policy"]["requestable_actions"])
        self.assertIn("direct_apply", payload["policy"]["blocked_actions"])
        self.assertEqual(payload["events"][0]["message"], "Fleet bundle payments-rollout waiting password=[redacted]")
        self.assertNotIn("raw-link-token", str(payload))
        self.assertNotIn("raw-label-token", str(payload))
        self.assertNotIn("raw-event-secret", str(payload))
        audit = K8sAuditEvent.objects.get(action="k8s.fleet_bundle.detail")
        self.assertEqual(audit.payload["bundle_id"], f"fleet_{bundle.id}")
        self.assertEqual(audit.payload["workload_count"], 1)
        self.assertNotIn("raw-event-secret", str(audit.payload))

    def test_fleet_bundle_detail_staff_gets_sanitized_fallback_link_and_target_match(self):
        staff = self.create_user("k8s-fleet-detail-staff", is_staff=True)
        self.client.force_login(staff)
        bundle = K8sFleetBundle.objects.create(
            name="fleet-default/ingress-nginx",
            source="gitrepo/platform",
            target="ingress-nginx",
            status=K8sFleetBundle.STATUS_READY,
            ready=2,
            desired=2,
            links={"rancher_fleet": "https://rancher.example.test/fleet/ingress-nginx?token=raw-link-token#tail"},
        )
        K8sWorkloadRef.objects.create(
            name="controller",
            cluster=self.cluster,
            namespace="ingress-nginx",
            kind=K8sWorkloadRef.KIND_DEPLOYMENT,
            owner=K8sAppRef.OWNER_FLEET,
            health=K8sCluster.HEALTH_HEALTHY,
            ready=1,
            desired=1,
            labels={"app.kubernetes.io/managed-by": "fleet"},
        )

        response = self.client.get(
            reverse("api_kubernetes_fleet_bundle_detail", kwargs={"bundle_id": f"fleet_{bundle.id}"})
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["bundle"]["links"]["rancher_fleet"], "https://rancher.example.test/fleet/ingress-nginx"
        )
        self.assertEqual(payload["summary"]["workload_count"], 1)
        self.assertEqual(payload["summary"]["namespaces"], ["ingress-nginx"])
        self.assertNotIn("raw-link-token", str(payload))

    def test_fleet_bundle_detail_returns_404_for_missing_bundle_without_audit(self):
        user = self.create_user("k8s-fleet-detail-missing")
        self.client.force_login(user)

        response = self.client.get(reverse("api_kubernetes_fleet_bundle_detail", kwargs={"bundle_id": "fleet_999999"}))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "bundle_not_found")
        self.assertFalse(K8sAuditEvent.objects.exists())
