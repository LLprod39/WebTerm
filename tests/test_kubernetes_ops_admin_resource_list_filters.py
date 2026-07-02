from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_resources import list_cluster_resources


class KubernetesOpsAdminResourceListFilterTests(TestCase):
    def create_user(self, username: str) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
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

    def create_read_session(self, user: User) -> K8sAdminSession:
        return K8sAdminSession.objects.create(
            user=user,
            username_snapshot=user.username,
            cluster=self.cluster,
            mode=K8sAdminSession.MODE_READ,
            status=K8sAdminSession.STATUS_ACTIVE,
            risk_tier=K8sAdminSession.RISK_LOW,
            allowed_verbs=["get", "list", "watch", "logs", "yaml"],
            allowed_kinds=["*"],
            allowed_namespaces=["*"],
            expires_at=timezone.now() + timedelta(hours=1),
        )

    def test_admin_resource_list_filters_are_bounded_and_passed_to_provider(self):
        user = self.create_user("k8s-admin-list-filter")
        session = self.create_read_session(user)
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen["url"] = url
            return {
                "metadata": {"continue": "next-page-token"},
                "items": [
                    {
                        "apiVersion": "v1",
                        "kind": "Pod",
                        "metadata": {
                            "name": "payments-api-1",
                            "namespace": "payments",
                            "managedFields": [{"manager": "kubectl", "token": "raw-managed-token"}],
                        },
                    },
                    {
                        "apiVersion": "v1",
                        "kind": "Pod",
                        "metadata": {"name": "payments-api-2", "namespace": "payments"},
                    },
                ],
            }

        payload = list_cluster_resources(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="v1",
            kind="Pod",
            namespace="payments",
            label_selector="app=payments,tier=api",
            field_selector="status.phase=Running",
            limit=1,
            continue_token="old-page-token",
            include_managed_fields=True,
            transport=transport,
        )

        self.assertEqual(payload["item_count"], 1)
        self.assertTrue(payload["truncated"])
        self.assertEqual(payload["continue_token"], "next-page-token")
        self.assertEqual(payload["list_query"]["limit"], 1)
        self.assertTrue(payload["list_query"]["label_selector_present"])
        self.assertTrue(payload["list_query"]["field_selector_present"])
        self.assertTrue(payload["list_query"]["continue_present"])
        self.assertTrue(payload["list_query"]["include_managed_fields"])
        self.assertEqual(payload["items"][0]["metadata"]["managedFields"][0]["manager"], "kubectl")
        self.assertEqual(payload["items"][0]["metadata"]["managedFields"][0]["token"], "[redacted]")
        self.assertNotIn("raw-managed-token", str(payload))
        self.assertIn("labelSelector=app%3Dpayments%2Ctier%3Dapi", seen["url"])
        self.assertIn("fieldSelector=status.phase%3DRunning", seen["url"])
        self.assertIn("limit=1", seen["url"])
        self.assertIn("continue=old-page-token", seen["url"])
        action = K8sAdminAction.objects.get()
        self.assertEqual(action.response_summary["item_count"], 1)
        self.assertTrue(action.response_summary["label_selector_present"])
        self.assertTrue(action.response_summary["field_selector_present"])
        self.assertTrue(action.response_summary["continue_present"])
        self.assertTrue(action.response_summary["include_managed_fields"])
        self.assertNotIn("app=payments", str(action.response_summary))
        self.assertNotIn("old-page-token", str(action.response_summary))

    def test_admin_resource_list_search_filters_sanitized_items_without_provider_query_or_audit_body(self):
        user = self.create_user("k8s-admin-list-search")
        session = self.create_read_session(user)
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen["url"] = url
            return {
                "items": [
                    {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "metadata": {
                            "name": "billing-api",
                            "namespace": "payments",
                            "labels": {"app": "billing", "token": "raw-token"},
                        },
                    },
                    {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "metadata": {
                            "name": "payments-worker",
                            "namespace": "payments",
                            "labels": {"app": "payments-worker", "team": "checkout"},
                        },
                    },
                ]
            }

        payload = list_cluster_resources(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="apps/v1",
            kind="Deployment",
            namespace="payments",
            search="checkout",
            transport=transport,
        )

        self.assertEqual(payload["item_count"], 1)
        self.assertFalse(payload["truncated"])
        self.assertTrue(payload["list_query"]["search_present"])
        self.assertEqual(payload["items"][0]["metadata"]["name"], "payments-worker")
        self.assertNotIn("billing-api", str(payload["items"]))
        self.assertNotIn("raw-token", str(payload))
        self.assertNotIn("search=", seen["url"])
        self.assertNotIn("checkout", seen["url"])
        action = K8sAdminAction.objects.get()
        self.assertTrue(action.response_summary["search_present"])
        self.assertEqual(action.response_summary["item_count"], 1)
        self.assertNotIn("checkout", str(action.response_summary))
