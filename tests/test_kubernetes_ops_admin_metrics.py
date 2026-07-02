from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_metrics import get_cluster_metrics_snapshot, parse_cpu_millicores, parse_memory_bytes


class KubernetesOpsAdminMetricsTests(TestCase):
    def create_user(self, username: str, *, grant_kubernetes: bool = True, grant_admin_read: bool = False) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        if grant_kubernetes:
            UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        if grant_admin_read:
            UserAppPermission.objects.create(user=user, feature="kubernetes_admin_read", allowed=True)
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

    def create_read_session(self, user: User, **kwargs) -> K8sAdminSession:
        defaults = {
            "user": user,
            "username_snapshot": user.username,
            "cluster": self.cluster,
            "mode": K8sAdminSession.MODE_READ,
            "status": K8sAdminSession.STATUS_ACTIVE,
            "risk_tier": K8sAdminSession.RISK_LOW,
            "allowed_verbs": ["get", "list", "watch", "logs", "yaml"],
            "allowed_kinds": ["*"],
            "allowed_namespaces": ["*"],
            "expires_at": timezone.now() + timedelta(hours=1),
        }
        defaults.update(kwargs)
        return K8sAdminSession.objects.create(**defaults)

    def test_admin_node_metrics_summarizes_usage_without_raw_audit_body(self):
        user = self.create_user("k8s-admin-node-metrics", grant_admin_read=True)
        session = self.create_read_session(user)
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen["url"] = url
            return {
                "items": [
                    {"metadata": {"name": "worker-1"}, "timestamp": "2026-07-02T00:00:00Z", "window": "30s", "usage": {"cpu": "125m", "memory": "256Mi"}},
                    {"metadata": {"name": "worker-2"}, "timestamp": "2026-07-02T00:00:01Z", "window": "30s", "usage": {"cpu": "250000000n", "memory": "1Gi"}},
                ]
            }

        payload = get_cluster_metrics_snapshot(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            scope="nodes",
            transport=transport,
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["operation"], "metrics_snapshot")
        self.assertEqual(payload["path"], "/k8s/clusters/c-prod/apis/metrics.k8s.io/v1beta1/nodes")
        self.assertEqual(seen["url"], "https://rancher.example.test/k8s/clusters/c-prod/apis/metrics.k8s.io/v1beta1/nodes")
        self.assertEqual(payload["items"][0]["usage_normalized"]["cpu_millicores"], 125)
        self.assertEqual(payload["items"][0]["usage_normalized"]["memory_bytes"], 268435456)
        self.assertEqual(payload["items"][1]["usage_normalized"]["cpu_millicores"], 250)
        self.assertEqual(payload["summary"]["item_count"], 2)
        self.assertEqual(payload["summary"]["total_cpu_millicores"], 375)
        self.assertEqual(payload["summary"]["total_memory_bytes"], 1342177280)
        self.assertFalse(payload["policy"]["mutates_state"])
        self.assertTrue(payload["policy"]["metrics_only"])

        action = K8sAdminAction.objects.get()
        self.assertEqual(action.verb, K8sAdminAction.VERB_LIST)
        self.assertEqual(action.resource_kind, "NodeMetrics")
        self.assertEqual(action.response_summary["item_count"], 2)
        self.assertEqual(action.response_summary["total_cpu_millicores"], 375)
        self.assertNotIn("worker-1", str(action.response_summary))

    def test_admin_pod_metrics_api_summarizes_container_usage_and_audits_counts_only(self):
        user = self.create_user("k8s-admin-pod-metrics", grant_admin_read=True)
        session = self.create_read_session(user)
        self.client.force_login(user)

        with patch("kubernetes_ops.services.admin_metrics.ProviderJsonClient") as client_cls:
            client_cls.return_value.get.return_value = {
                "items": [
                    {
                        "metadata": {"name": "payments-api-abc123", "namespace": "payments"},
                        "timestamp": "2026-07-02T00:00:00Z",
                        "window": "30s",
                        "containers": [
                            {"name": "api", "usage": {"cpu": "50m", "memory": "64Mi"}},
                            {"name": "sidecar", "usage": {"cpu": "100m", "memory": "128Mi"}},
                        ],
                    }
                ]
            }
            response = self.client.get(
                reverse("api_kubernetes_admin_metrics", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
                {"session_id": str(session.session_id), "scope": "pods", "namespace": "payments"},
            )
            client_cls.return_value.get.assert_called_with("/k8s/clusters/c-prod/apis/metrics.k8s.io/v1beta1/namespaces/payments/pods")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["target"]["kind"], "PodMetrics")
        self.assertEqual(payload["summary"]["item_count"], 1)
        self.assertEqual(payload["summary"]["container_count"], 2)
        self.assertEqual(payload["summary"]["total_cpu_millicores"], 150)
        self.assertEqual(payload["summary"]["total_memory_bytes"], 201326592)
        self.assertEqual(payload["items"][0]["usage_normalized"]["memory_bytes"], 201326592)
        audit = K8sAuditEvent.objects.get(action="k8s.admin_resource.metrics")
        self.assertEqual(audit.payload["item_count"], 1)
        self.assertEqual(audit.payload["container_count"], 2)
        self.assertNotIn("payments-api-abc123", str(audit.payload))
        self.assertNotIn("sidecar", str(audit.payload))

    def test_regular_kubernetes_user_cannot_read_admin_metrics_without_admin_read(self):
        user = self.create_user("k8s-regular-metrics")
        session = self.create_read_session(user)
        self.client.force_login(user)

        response = self.client.get(
            reverse("api_kubernetes_admin_metrics", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
            {"session_id": str(session.session_id), "scope": "nodes"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_read_required")
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_resource.metrics_rejected").exists())

    @override_settings(KUBERNETES_ADMIN_MODE_ENABLED=False)
    def test_global_admin_mode_kill_switch_blocks_existing_session_before_provider_call(self):
        user = self.create_user("k8s-admin-metrics-disabled", grant_admin_read=True)
        session = self.create_read_session(user)
        self.client.force_login(user)

        with patch("kubernetes_ops.services.admin_metrics.ProviderJsonClient") as client_cls:
            response = self.client.get(
                reverse("api_kubernetes_admin_metrics", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
                {"session_id": str(session.session_id), "scope": "nodes"},
            )
            client_cls.assert_not_called()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_mode_disabled")
        self.assertFalse(K8sAdminAction.objects.exists())
        session.refresh_from_db()
        self.assertEqual(session.status, K8sAdminSession.STATUS_ACTIVE)
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_resource.metrics_rejected").exists())

    def test_pod_metrics_all_namespaces_requires_all_namespace_session(self):
        user = self.create_user("k8s-admin-pod-metrics-scope", grant_admin_read=True)
        session = self.create_read_session(user, allowed_namespaces=["payments"])

        with self.assertRaisesMessage(Exception, "all-namespaces Admin session"):
            get_cluster_metrics_snapshot(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                scope="pods",
            )


def test_metric_quantity_parsers():
    assert parse_cpu_millicores("250m") == 250
    assert parse_cpu_millicores("250000000n") == 250
    assert parse_cpu_millicores("2") == 2000
    assert parse_memory_bytes("256Mi") == 268435456
    assert parse_memory_bytes("1Gi") == 1073741824
