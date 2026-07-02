from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sAppRef, K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_resource_detail import get_cluster_resource_detail


class KubernetesOpsAdminResourceDetailTests(TestCase):
    def create_user(
        self,
        username: str,
        *,
        grant_kubernetes: bool = True,
        grant_admin_read: bool = False,
        grant_secret_read: bool = False,
    ) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        if grant_kubernetes:
            UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        if grant_admin_read:
            UserAppPermission.objects.create(user=user, feature="kubernetes_admin_read", allowed=True)
        if grant_secret_read:
            UserAppPermission.objects.create(user=user, feature="kubernetes_secret_read", allowed=True)
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

    def test_admin_resource_detail_combines_resource_describe_ownership_and_events_without_raw_audit_body(self):
        user = self.create_user("k8s-admin-detail", grant_admin_read=True)
        session = self.create_read_session(user)
        K8sAppRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            owner=K8sAppRef.OWNER_DEVTRON,
            team="payments",
            health=K8sCluster.HEALTH_HEALTHY,
            labels={"token": "raw-app-token"},
        )
        seen_urls = []

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen_urls.append(url)
            if "/events?" in url:
                return {
                    "items": [
                        {
                            "metadata": {"name": "payments-api.17a", "namespace": "payments"},
                            "type": "Warning",
                            "reason": "FailedScheduling",
                            "message": "scheduler password=raw-event-secret",
                            "source": {"component": "scheduler", "token": "raw-source-token"},
                            "involvedObject": {
                                "apiVersion": "apps/v1",
                                "kind": "Deployment",
                                "namespace": "payments",
                                "name": "payments-api",
                            },
                        }
                    ]
                }
            return {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {
                    "name": "payments-api",
                    "namespace": "payments",
                    "uid": "uid-1",
                    "resourceVersion": "42",
                    "labels": {"app": "payments", "token": "raw-label-token"},
                    "annotations": {"checksum/config": "abc"},
                    "managedFields": [{"manager": "kubectl"}],
                },
                "spec": {"replicas": 2, "template": {"spec": {"containers": [{"name": "api"}]}}},
                "status": {
                    "message": "token=raw-detail-token",
                    "replicas": 2,
                    "readyReplicas": 1,
                    "conditions": [
                        {
                            "type": "Available",
                            "status": "False",
                            "reason": "MinimumReplicasUnavailable",
                            "message": "password=raw-status-secret",
                        }
                    ],
                },
            }

        payload = get_cluster_resource_detail(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="apps/v1",
            kind="Deployment",
            namespace="payments",
            name="payments-api",
            event_limit=5,
            transport=transport,
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["operation"], "resource_detail")
        self.assertEqual(payload["paths"]["resource"], "/k8s/clusters/c-prod/apis/apps/v1/namespaces/payments/deployments/payments-api")
        self.assertEqual(payload["paths"]["events"], "/k8s/clusters/c-prod/api/v1/namespaces/payments/events")
        self.assertEqual(payload["resource"]["metadata"]["labels"]["token"], "[redacted]")
        self.assertEqual(payload["resource"]["metadata"]["managedFields"], "[redacted]")
        self.assertEqual(payload["summary"]["name"], "payments-api")
        self.assertEqual(payload["summary"]["replicas"]["desired"], 2)
        self.assertEqual(payload["summary"]["replicas"]["ready"], 1)
        self.assertFalse(payload["summary"]["ready"])
        self.assertEqual(payload["summary"]["containers"]["count"], 1)
        self.assertEqual(payload["summary"]["condition_summary"]["available"], "False")
        self.assertEqual(payload["summary"]["condition_summary"]["failing_count"], 1)
        self.assertEqual(payload["summary"]["conditions"][0]["reason"], "MinimumReplicasUnavailable")
        self.assertEqual(payload["summary"]["conditions"][0]["message"], "password=[redacted]")
        self.assertEqual(payload["describe"]["health"]["ready_replicas"], 1)
        self.assertEqual(payload["describe"]["health"]["conditions"][0]["message"], "password=[redacted]")
        self.assertEqual(payload["describe"]["shape"]["container_count"], 1)
        self.assertEqual(payload["ownership"]["owner"], "devtron")
        self.assertEqual(payload["ownership"]["app"]["labels"]["token"], "[redacted]")
        self.assertTrue(payload["events"]["available"])
        self.assertEqual(payload["events"]["event_count"], 1)
        self.assertEqual(payload["events"]["events"][0]["message"], "scheduler password=[redacted]")
        self.assertEqual(payload["events"]["events"][0]["source"]["token"], "[redacted]")
        self.assertTrue(payload["redacted"])
        self.assertIn("fieldSelector=", seen_urls[1])
        self.assertNotIn("raw-label-token", str(payload))
        self.assertNotIn("raw-detail-token", str(payload))
        self.assertNotIn("raw-status-secret", str(payload))
        self.assertNotIn("raw-event-secret", str(payload))
        self.assertNotIn("raw-source-token", str(payload))
        self.assertNotIn("raw-app-token", str(payload))

        action = K8sAdminAction.objects.get()
        self.assertEqual(action.verb, K8sAdminAction.VERB_GET)
        self.assertEqual(action.resource_kind, "Deployment")
        self.assertEqual(action.resource_name, "payments-api")
        self.assertTrue(action.response_summary["detail"])
        self.assertEqual(action.response_summary["event_count"], 1)
        self.assertTrue(action.response_summary["redacted"])
        self.assertNotIn("raw-label-token", str(action.response_summary))
        self.assertNotIn("raw-event-secret", str(action.response_summary))

    def test_admin_resource_detail_api_is_session_gated_and_audits_metadata(self):
        user = self.create_user("k8s-admin-detail-api", grant_admin_read=True)
        session = self.create_read_session(user)
        self.client.force_login(user)

        with (
            patch("kubernetes_ops.services.admin_resource_detail.ProviderJsonClient") as detail_client,
            patch("kubernetes_ops.services.admin_resource_events.ProviderJsonClient") as events_client,
        ):
            detail_client.return_value.get.return_value = {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {"name": "payments-api-abc123", "namespace": "payments"},
                "status": {"phase": "Running"},
            }
            events_client.return_value.get.return_value = {"items": [{"metadata": {"name": "event-1"}, "reason": "Pulled"}]}
            response = self.client.get(
                reverse("api_kubernetes_admin_resource_detail", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
                {
                    "session_id": str(session.session_id),
                    "api_version": "v1",
                    "kind": "Pod",
                    "namespace": "payments",
                    "name": "payments-api-abc123",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["operation"], "resource_detail")
        self.assertEqual(response.json()["events"]["event_count"], 1)
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_resource.detail").exists())
        audit = K8sAuditEvent.objects.get(action="k8s.admin_resource.detail")
        self.assertEqual(audit.payload["event_count"], 1)
        self.assertNotIn("Pulled", str(audit.payload))

    def test_regular_kubernetes_user_cannot_read_admin_resource_detail(self):
        user = self.create_user("k8s-regular-detail")
        session = self.create_read_session(user)
        self.client.force_login(user)

        response = self.client.get(
            reverse("api_kubernetes_admin_resource_detail", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
            {
                "session_id": str(session.session_id),
                "api_version": "apps/v1",
                "kind": "Deployment",
                "namespace": "payments",
                "name": "payments-api",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_read_required")
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_resource.detail_rejected").exists())

    @override_settings(KUBERNETES_ADMIN_SECRET_READ_ENABLED=True)
    def test_admin_resource_detail_can_reveal_secret_values_with_explicit_grant(self):
        user = self.create_user("k8s-admin-detail-secret-visible", grant_admin_read=True, grant_secret_read=True)
        session = self.create_read_session(user)

        def transport(url: str, headers: dict[str, str], timeout: int):
            if "/events?" in url:
                return {"items": []}
            return {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": "db-creds", "namespace": "payments"},
                "data": {"password": "cGFzc3dvcmQ="},
            }

        payload = get_cluster_resource_detail(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="v1",
            kind="Secret",
            namespace="payments",
            name="db-creds",
            include_secret_values=True,
            transport=transport,
        )

        self.assertTrue(payload["secret_values"]["visible"])
        self.assertEqual(payload["resource"]["data"]["password"], "cGFzc3dvcmQ=")
        action = K8sAdminAction.objects.get()
        self.assertTrue(action.response_summary["secret_values_requested"])
        self.assertTrue(action.response_summary["secret_values_visible"])
        self.assertNotIn("cGFzc3dvcmQ=", str(action.response_summary))
