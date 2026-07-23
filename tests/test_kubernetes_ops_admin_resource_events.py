from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_resource_events import list_cluster_resource_events


class KubernetesOpsAdminResourceEventsTests(TestCase):
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

    def test_admin_resource_events_uses_selector_redacts_payload_and_records_action(self):
        user = self.create_user("k8s-admin-events", grant_admin_read=True)
        session = self.create_read_session(user)
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen["url"] = url
            return {
                "items": [
                    {
                        "metadata": {"name": "payments-api.17a", "namespace": "payments", "resourceVersion": "91"},
                        "type": "Warning",
                        "reason": "Failed",
                        "message": "pull failed password=raw-secret",
                        "source": {"component": "kubelet", "token": "raw-source-token"},
                        "involvedObject": {
                            "apiVersion": "apps/v1",
                            "kind": "Deployment",
                            "namespace": "payments",
                            "name": "payments-api",
                            "uid": "uid-1",
                        },
                        "count": 2,
                        "lastTimestamp": "2026-07-01T01:02:03Z",
                    }
                ]
            }

        payload = list_cluster_resource_events(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="apps/v1",
            kind="Deployment",
            namespace="payments",
            name="payments-api",
            limit=10,
            transport=transport,
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["operation"], "resource_events")
        self.assertEqual(payload["path"], "/k8s/clusters/c-prod/api/v1/namespaces/payments/events")
        self.assertEqual(
            payload["field_selector"],
            "involvedObject.apiVersion=apps/v1,involvedObject.kind=Deployment,involvedObject.name=payments-api,involvedObject.namespace=payments",
        )
        self.assertEqual(payload["event_count"], 1)
        self.assertTrue(payload["redacted"])
        self.assertEqual(payload["events"][0]["message"], "pull failed password=[redacted]")
        self.assertEqual(payload["events"][0]["source"]["token"], "[redacted]")
        self.assertEqual(payload["events"][0]["involved_object"]["name"], "payments-api")
        self.assertEqual(payload["events"][0]["count"], 2)
        self.assertNotIn("raw-secret", str(payload))
        self.assertNotIn("raw-source-token", str(payload))
        self.assertIn("fieldSelector=", seen["url"])
        self.assertIn("involvedObject.apiVersion%3Dapps%2Fv1", seen["url"])
        self.assertIn("involvedObject.kind%3DDeployment", seen["url"])
        self.assertIn("involvedObject.namespace%3Dpayments", seen["url"])
        action = K8sAdminAction.objects.get()
        self.assertEqual(action.verb, K8sAdminAction.VERB_LIST)
        self.assertEqual(action.resource_kind, "Deployment")
        self.assertEqual(action.resource_name, "payments-api")
        self.assertEqual(action.response_summary["event_count"], 1)
        self.assertNotIn("raw-secret", str(action.response_summary))

    def test_admin_resource_events_api_is_session_gated_and_audits_metadata(self):
        user = self.create_user("k8s-admin-events-api", grant_admin_read=True)
        session = self.create_read_session(user)
        self.client.force_login(user)

        with patch("kubernetes_ops.services.admin_resource_events.ProviderJsonClient") as client_cls:
            client_cls.return_value.get.return_value = {
                "items": [{"metadata": {"name": "event-1"}, "reason": "Pulled"}]
            }
            response = self.client.get(
                reverse("api_kubernetes_admin_resource_events", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
                {
                    "session_id": str(session.session_id),
                    "api_version": "apps/v1",
                    "kind": "Deployment",
                    "namespace": "payments",
                    "name": "payments-api",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["event_count"], 1)
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_resource.events").exists())

    def test_regular_kubernetes_user_cannot_read_admin_resource_events(self):
        user = self.create_user("k8s-regular-events")
        session = self.create_read_session(user)
        self.client.force_login(user)

        response = self.client.get(
            reverse("api_kubernetes_admin_resource_events", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
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
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_resource.events_rejected").exists())
