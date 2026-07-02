import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core_ui.managed_secrets import KUBERNETES_PROVIDER_TOKEN_NAMESPACE, get_kubernetes_provider_token
from core_ui.models import UserAppPermission
from core_ui.models import ManagedSecret
from kubernetes_ops.background_workers import KUBERNETES_OPS_SYNC_WORKER
from kubernetes_ops.models import K8sAppRef, K8sAuditEvent, K8sCluster, K8sFleetBundle, K8sProvider, K8sWorkloadRef
from kubernetes_ops.services.secrets import resolve_provider_token
from kubernetes_ops.services.sync import KubernetesSyncResult
from servers.models import BackgroundWorkerState


class KubernetesOpsApiTests(TestCase):
    def create_user(self, username: str, *, grant_kubernetes: bool = True, is_staff: bool = False) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=is_staff)
        if grant_kubernetes:
            UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        return user

    def test_kubernetes_api_requires_explicit_feature_access(self):
        user = self.create_user("staff-without-k8s", grant_kubernetes=False, is_staff=True)
        self.client.force_login(user)

        response = self.client.get(reverse("api_kubernetes_readiness"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "Forbidden")

    def test_readiness_reports_missing_providers_and_stays_sidebar_locked(self):
        user = self.create_user("k8s-reader")
        self.client.force_login(user)

        response = self.client.get(reverse("api_kubernetes_readiness"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertFalse(payload["ready_for_sidebar"])
        checks = {item["id"]: item for item in payload["checks"]}
        self.assertEqual(checks["architecture_guard"]["status"], "ready")
        self.assertEqual(checks["rancher_provider"]["status"], "missing")
        self.assertEqual(checks["devtron_provider"]["status"], "missing")
        self.assertEqual(checks["read_only_sync"]["status"], "missing")
        self.assertEqual(checks["sync_worker"]["status"], "missing")
        self.assertEqual(checks["sidebar_release_scope"]["status"], "missing")
        self.assertEqual(checks["studio_automation"]["status"], "missing")
        self.assertFalse(checks["studio_automation"]["required"])
        self.assertEqual(payload["worker_state"]["worker_kind"], "kubernetes_ops_sync")

    def test_readiness_detects_running_sync_worker_with_non_default_key(self):
        user = self.create_user("k8s-reader-compose-worker")
        self.client.force_login(user)
        now = timezone.now()
        BackgroundWorkerState.objects.create(
            worker_kind=KUBERNETES_OPS_SYNC_WORKER,
            worker_key="compose",
            status=BackgroundWorkerState.STATUS_RUNNING,
            heartbeat_at=now,
            lease_expires_at=now + timedelta(minutes=5),
            last_cycle_finished_at=now,
        )

        response = self.client.get(reverse("api_kubernetes_readiness"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        checks = {item["id"]: item for item in payload["checks"]}
        self.assertEqual(checks["sync_worker"]["status"], "ready")
        self.assertEqual(payload["worker_state"]["worker_key"], "compose")

    def test_overview_returns_normalized_inventory_without_secret_refs(self):
        user = self.create_user("k8s-overview")
        self.client.force_login(user)
        rancher = K8sProvider.objects.create(
            name="rancher-main",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            secret_ref="vault://rancher/token",
        )
        K8sProvider.objects.create(
            name="devtron-main",
            kind=K8sProvider.KIND_DEVTRON,
            base_url="https://devtron.example.test",
            secret_ref="vault://devtron/token",
        )
        cluster = K8sCluster.objects.create(
            name="stage-webterm-ops",
            environment="stage",
            health=K8sCluster.HEALTH_DEGRADED,
            rancher_provider=rancher,
            rancher_cluster_id="c-stage",
            nodes_ready=2,
            nodes_total=3,
            namespace_count=4,
            workload_count=9,
            links={"rancher": "https://rancher.example.test/c/c-stage"},
        )
        K8sAppRef.objects.create(
            name="demo-api",
            cluster=cluster,
            namespace="demo",
            environment="stage",
            owner=K8sAppRef.OWNER_DEVTRON,
            health=K8sCluster.HEALTH_HEALTHY,
            team="platform",
            version="2026.06.29-1",
        )
        K8sWorkloadRef.objects.create(
            name="demo-worker",
            cluster=cluster,
            namespace="demo",
            kind=K8sWorkloadRef.KIND_DEPLOYMENT,
            health=K8sCluster.HEALTH_HEALTHY,
            ready=1,
            desired=1,
        )
        K8sFleetBundle.objects.create(
            name="ingress-nginx",
            source="gitrepo/platform",
            target="stage",
            status=K8sFleetBundle.STATUS_ROLLING,
            ready=1,
            desired=2,
            partitions=[{"name": "stage", "status": "rolling", "ready": 1, "desired": 2}],
        )

        response = self.client.get(reverse("api_kubernetes_overview"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["clusters"], 1)
        self.assertEqual(payload["summary"]["apps"], 1)
        self.assertEqual(payload["summary"]["fleet_rollouts"], 1)
        self.assertEqual(payload["summary"]["incidents"], 1)
        self.assertEqual(payload["clusters"][0]["name"], "stage-webterm-ops")
        self.assertEqual(payload["workloads"][0]["name"], "demo-worker")
        self.assertEqual(payload["apps"][0]["name"], "demo-api")
        self.assertEqual(payload["fleet_rollouts"][0]["name"], "ingress-nginx")
        self.assertTrue(payload["providers"][0]["has_secret_ref"])
        self.assertEqual(payload["providers"][0]["provider_health"], "missing")
        self.assertTrue(payload["providers"][0]["is_stale"])
        self.assertEqual(payload["summary"]["provider_issues"], 2)
        self.assertNotIn("secret_ref", payload["providers"][0])
        self.assertNotIn("vault://", str(payload))

    @override_settings(KUBERNETES_OPS_STALE_AFTER_SECONDS=60)
    def test_readiness_reports_stale_provider_health_as_blocking_gate(self):
        user = self.create_user("k8s-stale-provider")
        self.client.force_login(user)
        stale_sync = timezone.now() - timedelta(seconds=120)
        fresh_sync = timezone.now()
        rancher = K8sProvider.objects.create(
            name="rancher-main",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            secret_ref="env:RANCHER_TOKEN",
            last_sync_at=stale_sync,
        )
        K8sProvider.objects.create(
            name="devtron-main",
            kind=K8sProvider.KIND_DEVTRON,
            base_url="https://devtron.example.test",
            secret_ref="env:DEVTRON_TOKEN",
            last_sync_at=fresh_sync,
        )
        K8sCluster.objects.create(
            name="stage-webterm-ops",
            rancher_provider=rancher,
            rancher_cluster_id="c-stage",
            last_sync_at=fresh_sync,
        )

        response = self.client.get(reverse("api_kubernetes_readiness"))

        self.assertEqual(response.status_code, 200)
        checks = {item["id"]: item for item in response.json()["checks"]}
        self.assertEqual(checks["provider_health"]["status"], "missing")
        self.assertIn("rancher:rancher-main", checks["provider_health"]["detail"])

    @override_settings(KUBERNETES_OPS_STALE_AFTER_SECONDS=60)
    def test_overview_returns_freshness_metadata_and_stale_summary(self):
        user = self.create_user("k8s-freshness")
        self.client.force_login(user)
        stale_sync = timezone.now() - timedelta(seconds=120)
        provider = K8sProvider.objects.create(
            name="rancher-main",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            secret_ref="env:RANCHER_TOKEN",
            last_sync_at=stale_sync,
        )
        K8sCluster.objects.create(
            name="stale-cluster",
            rancher_provider=provider,
            rancher_cluster_id="c-stale",
            last_sync_at=stale_sync,
        )

        response = self.client.get(reverse("api_kubernetes_overview"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["providers"][0]["provider_health"], "stale")
        self.assertEqual(payload["providers"][0]["sync_status"], "stale")
        self.assertTrue(payload["providers"][0]["is_stale"])
        self.assertEqual(payload["clusters"][0]["sync_status"], "stale")
        self.assertTrue(payload["clusters"][0]["is_stale"])
        self.assertEqual(payload["summary"]["stale"], 1)
        self.assertEqual(payload["summary"]["provider_issues"], 1)

    def test_cluster_related_endpoints_return_read_only_shapes(self):
        user = self.create_user("k8s-cluster-reader")
        self.client.force_login(user)
        cluster = K8sCluster.objects.create(name="prod-kz-1", environment="prod")
        K8sAppRef.objects.create(
            name="payments-api",
            cluster=cluster,
            namespace="payments",
            environment="prod",
            owner=K8sAppRef.OWNER_DEVTRON,
            team="payments",
            health=K8sCluster.HEALTH_WARNING,
        )
        K8sAuditEvent.objects.create(
            user=user,
            username_snapshot=user.username,
            action="k8s.cluster.view",
            cluster=cluster,
            payload={"cluster": cluster.name},
        )

        for route_name in (
            "api_kubernetes_cluster_detail",
            "api_kubernetes_cluster_namespaces",
            "api_kubernetes_cluster_workloads",
            "api_kubernetes_cluster_pods",
            "api_kubernetes_cluster_network",
            "api_kubernetes_cluster_events",
        ):
            response = self.client.get(reverse(route_name, kwargs={"cluster_id": f"cluster_{cluster.id}"}))
            self.assertEqual(response.status_code, 200, route_name)
            self.assertTrue(response.json()["success"])

        namespaces = self.client.get(reverse("api_kubernetes_cluster_namespaces", kwargs={"cluster_id": f"cluster_{cluster.id}"})).json()["namespaces"]
        self.assertEqual(namespaces[0]["name"], "payments")
        self.assertEqual(namespaces[0]["apps"], 1)
        self.assertEqual(namespaces[0]["warning"], 1)
        self.assertEqual(namespaces[0]["owners"], [K8sAppRef.OWNER_DEVTRON])
        events = self.client.get(reverse("api_kubernetes_cluster_events", kwargs={"cluster_id": f"cluster_{cluster.id}"})).json()["events"]
        self.assertEqual(events[0]["source"], "webterm_audit")
        self.assertEqual(events[0]["reason"], "k8s.cluster.view")

    def test_provider_config_write_requires_staff_even_with_kubernetes_feature(self):
        user = self.create_user("k8s-non-admin")
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_providers"),
            data=json.dumps(
                {
                    "name": "rancher-main",
                    "kind": K8sProvider.KIND_RANCHER,
                    "base_url": "https://rancher.example.test",
                    "secret_ref": "env:RANCHER_TOKEN",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_required")
        self.assertFalse(K8sProvider.objects.exists())

    def test_staff_can_create_provider_without_secret_ref_leakage(self):
        user = self.create_user("k8s-admin", is_staff=True)
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_providers"),
            data=json.dumps(
                {
                    "name": "rancher-main",
                    "kind": K8sProvider.KIND_RANCHER,
                    "base_url": "https://rancher.example.test/",
                    "secret_ref": "env:RANCHER_TOKEN",
                    "labels": {"clusters_path": "/v3/clusters"},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["provider"]["has_secret_ref"])
        self.assertNotIn("secret_ref", payload["provider"])
        self.assertNotIn("RANCHER_TOKEN", str(payload))
        provider = K8sProvider.objects.get(name="rancher-main")
        self.assertEqual(provider.secret_ref, "env:RANCHER_TOKEN")
        self.assertEqual(provider.base_url, "https://rancher.example.test")
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.provider.create", provider="rancher-main").exists())

    def test_provider_config_rejects_raw_token_secret_ref(self):
        user = self.create_user("k8s-admin-raw-token", is_staff=True)
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_providers"),
            data=json.dumps(
                {
                    "name": "devtron-main",
                    "kind": K8sProvider.KIND_DEVTRON,
                    "base_url": "https://devtron.example.test",
                    "secret_ref": "raw-token-value",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("external secret reference", response.json()["error"])
        self.assertFalse(K8sProvider.objects.exists())

    def test_staff_can_create_provider_with_managed_secret_value_without_leakage(self):
        user = self.create_user("k8s-admin-managed-secret", is_staff=True)
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_providers"),
            data=json.dumps(
                {
                    "name": "rancher-main",
                    "kind": K8sProvider.KIND_RANCHER,
                    "base_url": "https://rancher.example.test/",
                    "secret_value": "super-secret-rancher-token",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["provider"]["has_secret_ref"])
        self.assertEqual(payload["provider"]["secret_storage"], "managed")
        self.assertNotIn("secret_ref", payload["provider"])
        self.assertNotIn("super-secret-rancher-token", str(payload))
        provider = K8sProvider.objects.get(name="rancher-main")
        self.assertEqual(provider.secret_ref, f"managed:kubernetes-provider-token:{provider.id}")
        self.assertEqual(resolve_provider_token(provider), "super-secret-rancher-token")
        secret = ManagedSecret.objects.get(namespace=KUBERNETES_PROVIDER_TOKEN_NAMESPACE, object_id=provider.id)
        self.assertNotIn("super-secret-rancher-token", secret.ciphertext)

    def test_staff_can_rotate_and_delete_managed_provider_token(self):
        user = self.create_user("k8s-admin-managed-rotate", is_staff=True)
        self.client.force_login(user)
        provider = K8sProvider.objects.create(
            name="devtron-main",
            kind=K8sProvider.KIND_DEVTRON,
            base_url="https://devtron.example.test",
            secret_ref="env:DEVTRON_TOKEN",
        )

        update_response = self.client.patch(
            reverse("api_kubernetes_provider_detail", kwargs={"provider_id": provider.id}),
            data=json.dumps({"secret_value": "rotated-devtron-token"}),
            content_type="application/json",
        )

        self.assertEqual(update_response.status_code, 200)
        provider.refresh_from_db()
        self.assertEqual(provider.secret_ref, f"managed:kubernetes-provider-token:{provider.id}")
        self.assertEqual(get_kubernetes_provider_token(provider.id), "rotated-devtron-token")
        self.assertNotIn("rotated-devtron-token", str(update_response.json()))

        delete_response = self.client.delete(reverse("api_kubernetes_provider_detail", kwargs={"provider_id": provider.id}))

        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(ManagedSecret.objects.filter(namespace=KUBERNETES_PROVIDER_TOKEN_NAMESPACE, object_id=provider.id).exists())

    def test_staff_can_update_and_delete_provider_config(self):
        user = self.create_user("k8s-admin-update", is_staff=True)
        self.client.force_login(user)
        provider = K8sProvider.objects.create(
            name="rancher-main",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            secret_ref="env:RANCHER_TOKEN",
        )

        update_response = self.client.patch(
            reverse("api_kubernetes_provider_detail", kwargs={"provider_id": provider.id}),
            data=json.dumps({"name": "rancher-stage", "enabled": False}),
            content_type="application/json",
        )

        self.assertEqual(update_response.status_code, 200)
        provider.refresh_from_db()
        self.assertEqual(provider.name, "rancher-stage")
        self.assertFalse(provider.enabled)
        self.assertEqual(provider.secret_ref, "env:RANCHER_TOKEN")

        delete_response = self.client.delete(reverse("api_kubernetes_provider_detail", kwargs={"provider_id": provider.id}))

        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(K8sProvider.objects.exists())
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.provider.delete", provider="rancher-stage").exists())

    def test_provider_sync_endpoint_is_admin_only_and_audited(self):
        user = self.create_user("k8s-admin-sync", is_staff=True)
        self.client.force_login(user)
        provider = K8sProvider.objects.create(
            name="rancher-main",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            secret_ref="env:RANCHER_TOKEN",
        )

        with patch("kubernetes_ops.views.sync_kubernetes_providers") as sync_mock:
            sync_mock.return_value = [
                KubernetesSyncResult(
                    provider_id=provider.id,
                    provider_name=provider.name,
                    provider_kind=provider.kind,
                    success=True,
                    clusters=2,
                    fleet_bundles=3,
                    dry_run=True,
                )
            ]
            response = self.client.post(
                reverse("api_kubernetes_provider_sync", kwargs={"provider_id": provider.id}),
                data=json.dumps({"dry_run": True}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertEqual(response.json()["results"][0]["clusters"], 2)
        self.assertEqual(response.json()["results"][0]["namespaces"], 0)
        self.assertEqual(response.json()["results"][0]["workloads"], 0)
        self.assertEqual(response.json()["results"][0]["pods"], 0)
        self.assertEqual(response.json()["results"][0]["services"], 0)
        self.assertEqual(response.json()["results"][0]["ingresses"], 0)
        self.assertEqual(response.json()["results"][0]["events"], 0)
        sync_mock.assert_called_once_with(provider_id=provider.id, dry_run=True)
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.provider.sync", provider="rancher-main").exists())

    def test_provider_sync_rejects_non_staff_user(self):
        user = self.create_user("k8s-sync-non-admin")
        self.client.force_login(user)
        provider = K8sProvider.objects.create(
            name="rancher-main",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            secret_ref="env:RANCHER_TOKEN",
        )

        response = self.client.post(
            reverse("api_kubernetes_provider_sync", kwargs={"provider_id": provider.id}),
            data=json.dumps({"dry_run": True}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_required")
