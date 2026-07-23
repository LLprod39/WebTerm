from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_resource_describe import get_cluster_resource_live_describe
from kubernetes_ops.services.admin_resource_detail import get_cluster_resource_detail
from kubernetes_ops.services.admin_resources import get_cluster_resource_yaml, list_cluster_resources
from kubernetes_ops.services.admin_watch import get_admin_resource_watch_preview


class KubernetesOpsAdminCustomResourceTests(TestCase):
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

    def test_custom_resource_list_and_yaml_use_explicit_crd_plural(self):
        user = self.create_user("k8s-admin-custom-resource")
        session = self.create_read_session(user)
        seen_urls = []

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen_urls.append(url)
            if url.endswith("/indices"):
                return {
                    "items": [
                        {
                            "apiVersion": "search.example.com/v1",
                            "kind": "Index",
                            "metadata": {"name": "catalog", "namespace": "search", "labels": {"token": "raw-token"}},
                            "status": {"phase": "Ready"},
                        }
                    ]
                }
            if url.endswith("/indices/catalog"):
                return {
                    "apiVersion": "search.example.com/v1",
                    "kind": "Index",
                    "metadata": {"name": "catalog", "namespace": "search"},
                    "spec": {"shards": 3},
                }
            raise AssertionError(f"unexpected url: {url}")

        listing = list_cluster_resources(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="search.example.com/v1",
            kind="Index",
            resource="indices",
            namespace="search",
            transport=transport,
        )
        resource_get = list_cluster_resources(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="search.example.com/v1",
            kind="Index",
            resource="indices",
            namespace="search",
            name="catalog",
            transport=transport,
        )
        yaml_payload = get_cluster_resource_yaml(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="search.example.com/v1",
            kind="Index",
            resource="indices",
            namespace="search",
            name="catalog",
            transport=transport,
        )

        self.assertEqual(listing["target"]["resource"], "indices")
        self.assertEqual(listing["path"], "/k8s/clusters/c-prod/apis/search.example.com/v1/namespaces/search/indices")
        self.assertEqual(resource_get["summary"]["name"], "catalog")
        self.assertEqual(resource_get["summary"]["kind"], "Index")
        self.assertEqual(resource_get["summary"]["replicas"]["desired"], None)
        self.assertEqual(yaml_payload["target"]["resource"], "indices")
        self.assertEqual(
            yaml_payload["path"], "/k8s/clusters/c-prod/apis/search.example.com/v1/namespaces/search/indices/catalog"
        )
        self.assertIn(
            "https://rancher.example.test/k8s/clusters/c-prod/apis/search.example.com/v1/namespaces/search/indices",
            seen_urls,
        )
        self.assertIn(
            "https://rancher.example.test/k8s/clusters/c-prod/apis/search.example.com/v1/namespaces/search/indices/catalog",
            seen_urls,
        )
        self.assertNotIn("/indexes", " ".join(seen_urls))
        self.assertNotIn("raw-token", str(listing))

    def test_custom_resource_detail_describe_and_watch_use_explicit_crd_plural(self):
        user = self.create_user("k8s-admin-custom-resource-detail")
        session = self.create_read_session(user)
        seen_urls = []

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen_urls.append(url)
            if "/indices/catalog" in url and "watch=1" not in url:
                return {
                    "apiVersion": "search.example.com/v1",
                    "kind": "Index",
                    "metadata": {"name": "catalog", "namespace": "search"},
                    "status": {"conditions": [{"type": "Ready", "status": "True"}]},
                }
            if "/indices/catalog" in url and "watch=1" in url:
                return {
                    "items": [
                        {
                            "type": "MODIFIED",
                            "object": {
                                "apiVersion": "search.example.com/v1",
                                "kind": "Index",
                                "metadata": {"name": "catalog", "namespace": "search", "resourceVersion": "42"},
                            },
                        }
                    ]
                }
            raise AssertionError(f"unexpected url: {url}")

        detail = get_cluster_resource_detail(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="search.example.com/v1",
            kind="Index",
            resource="indices",
            namespace="search",
            name="catalog",
            include_events=False,
            transport=transport,
        )
        describe = get_cluster_resource_live_describe(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="search.example.com/v1",
            kind="Index",
            resource="indices",
            namespace="search",
            name="catalog",
            include_events=False,
            include_related=False,
            transport=transport,
        )
        watch = get_admin_resource_watch_preview(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="search.example.com/v1",
            kind="Index",
            resource="indices",
            namespace="search",
            name="catalog",
            transport=transport,
        )

        self.assertEqual(detail["target"]["resource"], "indices")
        self.assertEqual(detail["summary"]["condition_count"], 1)
        self.assertEqual(detail["summary"]["condition_summary"]["ready"], "True")
        self.assertEqual(detail["summary"]["conditions"][0]["type"], "Ready")
        self.assertEqual(describe["target"]["resource"], "indices")
        self.assertEqual(watch["target"]["resource"], "indices")
        self.assertEqual(watch["latest_resource_version"], "42")
        self.assertTrue(all("/indices/catalog" in url for url in seen_urls))
        self.assertNotIn("/indexes/catalog", " ".join(seen_urls))
