from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAppRef, K8sAuditEvent, K8sCluster, K8sFleetBundle, K8sProvider, K8sWorkloadRef


class KubernetesOpsHelmOwnershipTests(TestCase):
    def create_user(self, username: str, *, grant_kubernetes: bool = True, is_staff: bool = False) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=is_staff)
        if grant_kubernetes:
            UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        return user

    def setUp(self):
        self.provider = K8sProvider.objects.create(
            name="rancher-main",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            auth_mode=K8sProvider.AUTH_NONE,
        )
        self.cluster = K8sCluster.objects.create(
            name="prod-kz-1",
            environment="prod",
            rancher_provider=self.provider,
            rancher_cluster_id="c-prod",
        )

    def test_reader_lists_helm_release_from_workload_labels_without_secret_leakage(self):
        user = self.create_user("k8s-helm-reader")
        self.client.force_login(user)
        K8sWorkloadRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            kind=K8sWorkloadRef.KIND_DEPLOYMENT,
            owner="rancher",
            health=K8sCluster.HEALTH_HEALTHY,
            ready=2,
            desired=2,
            version="1.2.3",
            labels={
                "app.kubernetes.io/managed-by": "Helm",
                "meta.helm.sh/release-name": "payments",
                "token": "raw-secret-token",
                "note": "password=raw-secret-value",
            },
            links={"rancher": "https://rancher.example.test/apps/payments?token=raw-secret-token"},
        )

        response = self.client.get(reverse("api_kubernetes_helm_releases"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["summary"]["release_count"], 1)
        release = payload["items"][0]
        self.assertEqual(release["release_name"], "payments")
        self.assertEqual(release["primary_owner"], "rancher")
        self.assertTrue(release["one_release_one_owner"])
        self.assertEqual(release["policy"]["change_path"], "webterm_admin_session")
        self.assertEqual(release["workloads"][0]["links"], {})
        self.assertNotIn("raw-secret-token", str(payload))
        self.assertNotIn("raw-secret-value", str(payload))
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.helm_releases.list").exists())

    def test_devtron_and_fleet_same_release_returns_owner_conflict(self):
        user = self.create_user("k8s-helm-conflict")
        self.client.force_login(user)
        K8sAppRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            owner=K8sAppRef.OWNER_DEVTRON,
            health=K8sCluster.HEALTH_WARNING,
            labels={"meta.helm.sh/release-name": "payments"},
        )
        K8sFleetBundle.objects.create(
            name="fleet-local/payments",
            source="https://git.example.test/platform/payments.git?token=fleet-secret-token",
            target="payments",
            status=K8sFleetBundle.STATUS_ROLLING,
            ready=1,
            desired=2,
            labels={"meta.helm.sh/release-name": "payments"},
            links={"fleet": "https://rancher.example.test/fleet/payments?token=fleet-secret-token"},
        )

        response = self.client.get(reverse("api_kubernetes_helm_releases"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        release = payload["items"][0]
        self.assertTrue(release["conflict"])
        self.assertEqual(set(release["owners"]), {K8sAppRef.OWNER_DEVTRON, K8sAppRef.OWNER_FLEET})
        self.assertFalse(release["one_release_one_owner"])
        self.assertEqual(release["policy"]["change_path"], "resolve_owner_before_mutation")
        self.assertEqual(release["policy"]["direct_mutation_policy"], "blocked_by_default")
        self.assertEqual(payload["summary"]["conflict_count"], 1)
        self.assertNotIn("fleet-secret-token", str(payload))

    def test_unknown_cluster_filter_returns_404(self):
        user = self.create_user("k8s-helm-missing-cluster")
        self.client.force_login(user)

        response = self.client.get(reverse("api_kubernetes_helm_releases"), {"cluster_id": "cluster_99999"})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "cluster_not_found")
