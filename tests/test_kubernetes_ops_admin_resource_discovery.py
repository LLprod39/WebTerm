from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_resources import discover_cluster_resources


class KubernetesOpsAdminResourceDiscoveryTests(TestCase):
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

    def create_user(self, username: str) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        UserAppPermission.objects.create(user=user, feature="kubernetes_admin_read", allowed=True)
        return user

    def create_read_session(self, user: User, *, allowed_kinds: list[str] | None = None) -> K8sAdminSession:
        return K8sAdminSession.objects.create(
            user=user,
            username_snapshot=user.username,
            cluster=self.cluster,
            mode=K8sAdminSession.MODE_READ,
            status=K8sAdminSession.STATUS_ACTIVE,
            risk_tier=K8sAdminSession.RISK_LOW,
            allowed_verbs=["get", "list", "watch", "logs", "yaml"],
            allowed_kinds=allowed_kinds or ["*"],
            allowed_namespaces=["*"],
            expires_at=timezone.now() + timedelta(hours=1),
        )

    def test_discovery_includes_safe_crd_resources_without_raw_schema(self):
        user = self.create_user("k8s-admin-crd-discovery")
        session = self.create_read_session(user)
        seen_urls = []

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen_urls.append(url)
            if url.endswith("/api/v1"):
                return {
                    "kind": "APIResourceList",
                    "resources": [{"name": "pods", "kind": "Pod", "namespaced": True, "verbs": ["get", "list"]}],
                }
            if url.endswith("/apis"):
                return {"groups": [{"name": "example.com", "versions": [{"version": "v1"}]}]}
            if url.endswith("/apis/example.com/v1"):
                return {
                    "kind": "APIResourceList",
                    "resources": [
                        {
                            "name": "widgets",
                            "kind": "Widget",
                            "namespaced": True,
                            "verbs": ["get", "list", "watch"],
                            "shortNames": ["wdg"],
                            "categories": ["all"],
                            "singularName": "widget",
                            "token": "raw-api-token",
                        },
                        {"name": "widgets/status", "kind": "Widget", "namespaced": True, "verbs": ["get"]},
                    ],
                }
            if url.endswith("/customresourcedefinitions"):
                return {
                    "items": [
                        {
                            "metadata": {"name": "widgets.example.com", "annotations": {"token": "raw-token"}},
                            "spec": {
                                "group": "example.com",
                                "scope": "Namespaced",
                                "names": {
                                    "kind": "Widget",
                                    "plural": "widgets",
                                    "shortNames": ["wdg"],
                                    "categories": ["all"],
                                },
                                "versions": [
                                    {
                                        "name": "v1",
                                        "served": True,
                                        "storage": True,
                                        "schema": {"openAPIV3Schema": {"properties": {"password": {"type": "string"}}}},
                                    },
                                    {"name": "v2alpha1", "served": False, "storage": False},
                                ],
                            },
                        }
                    ]
                }
            raise AssertionError(f"unexpected url: {url}")

        payload = discover_cluster_resources(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            transport=transport,
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["api_resources"]["status"], "ready")
        self.assertFalse(payload["api_resources"]["raw_payload_included"])
        self.assertEqual(
            payload["api_resources"]["items"],
            [
                {
                    "api_version": "v1",
                    "group": "",
                    "version": "v1",
                    "kind": "Pod",
                    "resource": "pods",
                    "namespaced": True,
                    "verbs": ["get", "list"],
                    "short_names": [],
                    "categories": [],
                    "singular_name": "",
                    "source": "core",
                },
                {
                    "api_version": "example.com/v1",
                    "group": "example.com",
                    "version": "v1",
                    "kind": "Widget",
                    "resource": "widgets",
                    "namespaced": True,
                    "verbs": ["get", "list", "watch"],
                    "short_names": ["wdg"],
                    "categories": ["all"],
                    "singular_name": "widget",
                    "source": "group",
                },
            ],
        )
        catalog = {item["id"]: item for item in payload["resource_catalog"]["items"]}
        self.assertFalse(payload["resource_catalog"]["raw_payload_included"])
        self.assertEqual(payload["resource_catalog"]["status"], "ready")
        self.assertEqual(payload["resource_catalog"]["counts"]["custom"], 1)
        self.assertGreaterEqual(payload["resource_catalog"]["counts"]["cluster_available"], 2)
        catalog_groups = {item["id"]: item for item in payload["resource_catalog"]["groups"]}
        self.assertGreaterEqual(catalog_groups["workloads"]["item_count"], 1)
        self.assertEqual(catalog_groups["custom"]["custom_count"], 1)
        self.assertEqual(catalog["v1:pods"]["sources"], ["common", "api"])
        self.assertTrue(catalog["v1:pods"]["cluster_available"])
        self.assertEqual(catalog["v1:pods"]["query"], {"api_version": "v1", "kind": "Pod", "resource": "pods"})
        self.assertEqual(catalog["v1:pods"]["ui_group"], "workloads")
        self.assertEqual(catalog["v1:pods"]["safe_read_actions"], ["list", "detail", "yaml", "logs"])
        self.assertEqual(catalog["example.com/v1:widgets"]["sources"], ["api", "crd"])
        self.assertTrue(catalog["example.com/v1:widgets"]["custom"])
        self.assertEqual(catalog["example.com/v1:widgets"]["ui_group"], "custom")
        self.assertEqual(catalog["example.com/v1:widgets"]["safe_read_actions"], ["list", "detail", "yaml", "watch"])
        self.assertEqual(catalog["example.com/v1:widgets"]["verbs"], ["get", "list", "watch"])
        self.assertEqual(catalog["example.com/v1:widgets"]["short_names"], ["wdg"])
        self.assertEqual(catalog["example.com/v1:widgets"]["crd_name"], "widgets.example.com")
        self.assertEqual(
            payload["paths"]["crds"], "/k8s/clusters/c-prod/apis/apiextensions.k8s.io/v1/customresourcedefinitions"
        )
        self.assertEqual(payload["crd_resources"]["status"], "ready")
        self.assertFalse(payload["crd_resources"]["schema_included"])
        self.assertEqual(
            payload["crd_resources"]["items"],
            [
                {
                    "api_version": "example.com/v1",
                    "group": "example.com",
                    "version": "v1",
                    "kind": "Widget",
                    "resource": "widgets",
                    "namespaced": True,
                    "scope": "Namespaced",
                    "short_names": ["wdg"],
                    "categories": ["all"],
                    "storage": True,
                    "crd_name": "widgets.example.com",
                }
            ],
        )
        self.assertIn(
            "https://rancher.example.test/k8s/clusters/c-prod/apis/apiextensions.k8s.io/v1/customresourcedefinitions",
            seen_urls,
        )
        self.assertIn("https://rancher.example.test/k8s/clusters/c-prod/apis/example.com/v1", seen_urls)
        self.assertNotIn("raw-token", str(payload))
        self.assertNotIn("raw-api-token", str(payload))
        self.assertNotIn("openAPIV3Schema", str(payload))
        self.assertNotIn("password", str(payload))
        action = K8sAdminAction.objects.get()
        self.assertEqual(action.response_summary["api_resource_status"], "ready")
        self.assertEqual(action.response_summary["api_resource_count"], 2)
        self.assertGreaterEqual(action.response_summary["resource_catalog_count"], 2)
        self.assertGreaterEqual(action.response_summary["resource_catalog_group_count"], 2)
        self.assertEqual(action.response_summary["resource_catalog_custom_count"], 1)
        self.assertEqual(action.response_summary["crd_status"], "ready")
        self.assertEqual(action.response_summary["crd_count"], 1)

    def test_discovery_continues_when_session_scope_cannot_read_crds(self):
        user = self.create_user("k8s-admin-crd-denied")
        session = self.create_read_session(user, allowed_kinds=["Pod"])
        seen_urls = []

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen_urls.append(url)
            if url.endswith("/api/v1"):
                return {"kind": "APIResourceList", "resources": [{"name": "pods", "kind": "Pod"}]}
            if url.endswith("/apis"):
                return {"groups": []}
            raise AssertionError(f"CRD path should not be requested: {url}")

        payload = discover_cluster_resources(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            transport=transport,
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["crd_resources"]["status"], "unavailable")
        self.assertEqual(payload["crd_resources"]["reason"], "admin_session_kind_denied")
        self.assertEqual(payload["crd_resources"]["item_count"], 0)
        self.assertEqual(payload["resource_catalog"]["status"], "partial")
        self.assertEqual(payload["resource_catalog"]["counts"]["custom"], 0)
        catalog = {item["id"]: item for item in payload["resource_catalog"]["items"]}
        self.assertEqual(catalog["v1:pods"]["sources"], ["common", "api"])
        self.assertEqual(catalog["v1:pods"]["ui_group"], "workloads")
        self.assertFalse(any(item["custom"] for item in catalog.values()))
        self.assertEqual(len(seen_urls), 2)
        action = K8sAdminAction.objects.get()
        self.assertEqual(action.response_summary["crd_status"], "unavailable")
        self.assertEqual(action.response_summary["crd_count"], 0)
