from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import (
    K8sAdminAction,
    K8sAdminSession,
    K8sAppRef,
    K8sAuditEvent,
    K8sCluster,
    K8sFleetBundle,
    K8sProvider,
)
from kubernetes_ops.services.admin_logs import get_admin_pod_log_snapshot
from kubernetes_ops.services.admin_resources import (
    AdminResourceError,
    get_cluster_resource_yaml,
    list_cluster_resources,
)
from kubernetes_ops.services.admin_watch import get_admin_resource_watch_preview


class KubernetesOpsAdminResourceTests(TestCase):
    def create_user(
        self,
        username: str,
        *,
        grant_kubernetes: bool = True,
        grant_admin_read: bool = False,
    ) -> User:
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

    def test_regular_kubernetes_user_cannot_list_admin_resources_without_admin_read(self):
        user = self.create_user("k8s-regular")
        session = self.create_read_session(user)
        self.client.force_login(user)

        response = self.client.get(
            reverse("api_kubernetes_admin_resource_list", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
            {"session_id": str(session.session_id), "api_version": "apps/v1", "kind": "Deployment", "namespace": "payments"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_read_required")
        self.assertFalse(K8sAdminAction.objects.exists())

    def test_admin_read_session_lists_deployments_through_rancher_proxy_and_audits_metadata(self):
        user = self.create_user("k8s-admin-reader", grant_admin_read=True)
        session = self.create_read_session(user)
        K8sAppRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            owner=K8sAppRef.OWNER_DEVTRON,
            team="payments",
            health=K8sCluster.HEALTH_HEALTHY,
            version="1.2.3",
            labels={"token": "raw-app-token"},
        )
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen["url"] = url
            return {
                "items": [
                    {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "metadata": {
                            "name": "payments-api",
                            "namespace": "payments",
                            "labels": {"app": "payments", "token": "raw-token"},
                            "managedFields": [{"manager": "kubectl"}],
                        },
                        "spec": {"replicas": 2, "template": {"spec": {"containers": [{"name": "api"}]}}},
                        "status": {"replicas": 2, "readyReplicas": 1, "message": "token=raw-status-token"},
                    }
                ]
            }

        payload = list_cluster_resources(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="apps/v1",
            kind="Deployment",
            namespace="payments",
            transport=transport,
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["operation"], "resource_list")
        self.assertEqual(payload["path"], "/k8s/clusters/c-prod/apis/apps/v1/namespaces/payments/deployments")
        self.assertEqual(seen["url"], "https://rancher.example.test/k8s/clusters/c-prod/apis/apps/v1/namespaces/payments/deployments")
        self.assertEqual(payload["items"][0]["metadata"]["labels"]["token"], "[redacted]")
        self.assertEqual(payload["items"][0]["metadata"]["managedFields"], "[redacted]")
        self.assertEqual(payload["items"][0]["summary"]["name"], "payments-api")
        self.assertEqual(payload["items"][0]["summary"]["replicas"]["desired"], 2)
        self.assertEqual(payload["items"][0]["summary"]["replicas"]["ready"], 1)
        self.assertEqual(payload["items"][0]["summary"]["containers"]["count"], 1)
        self.assertIn("status", payload["items"][0]["summary"]["keys"])
        ownership = payload["items"][0]["webterm_ownership"]
        self.assertEqual(ownership["owner"], "devtron")
        self.assertEqual(ownership["change_path"], "devtron_app_flow")
        self.assertEqual(ownership["direct_apply_policy"], "blocked_by_default")
        self.assertEqual(ownership["app"]["name"], "payments-api")
        self.assertEqual(ownership["app"]["labels"]["token"], "[redacted]")
        self.assertEqual(payload["ownership_summary"]["owners"], {"devtron": 1})
        self.assertEqual(payload["ownership_summary"]["guarded_items"], 1)
        self.assertNotIn("raw-token", str(payload))
        self.assertNotIn("raw-app-token", str(payload))
        self.assertNotIn("raw-status-token", str(payload))
        action = K8sAdminAction.objects.get()
        self.assertEqual(action.verb, K8sAdminAction.VERB_LIST)
        self.assertEqual(action.resource_kind, "Deployment")
        self.assertEqual(action.namespace, "payments")

    def test_secret_list_is_metadata_only_even_when_secret_values_are_requested(self):
        user = self.create_user("k8s-admin-secret-list", grant_admin_read=True)
        session = self.create_read_session(user)
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen["url"] = url
            return {
                "items": [
                    {
                        "apiVersion": "v1",
                        "kind": "Secret",
                        "metadata": {"name": "db-creds", "namespace": "payments", "annotations": {"token": "raw-annotation-token"}},
                        "data": {"password": "cGFzc3dvcmQ=", "token": "cmF3"},
                        "stringData": {"dsn": "postgres://raw-secret"},
                    }
                ]
            }

        payload = list_cluster_resources(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="v1",
            kind="Secret",
            namespace="payments",
            include_secret_values=True,
            transport=transport,
        )

        self.assertEqual(payload["path"], "/k8s/clusters/c-prod/api/v1/namespaces/payments/secrets")
        self.assertEqual(seen["url"], "https://rancher.example.test/k8s/clusters/c-prod/api/v1/namespaces/payments/secrets")
        self.assertTrue(payload["secret_values"]["requested"])
        self.assertFalse(payload["secret_values"]["visible"])
        self.assertEqual(payload["secret_values"]["mode"], "list_metadata_only")
        self.assertEqual(payload["items"][0]["metadata"]["annotations"]["token"], "[redacted]")
        self.assertEqual(payload["items"][0]["data"]["password"], "[redacted]")
        self.assertEqual(payload["items"][0]["stringData"]["dsn"], "[redacted]")
        self.assertNotIn("cGFzc3dvcmQ=", str(payload))
        self.assertNotIn("postgres://raw-secret", str(payload))
        self.assertNotIn("raw-annotation-token", str(payload))

        action = K8sAdminAction.objects.get()
        self.assertEqual(action.verb, K8sAdminAction.VERB_LIST)
        self.assertEqual(action.resource_kind, "Secret")
        self.assertTrue(action.response_summary["secret_values_requested"])
        self.assertFalse(action.response_summary["secret_values_visible"])
        self.assertNotIn("cGFzc3dvcmQ=", str(action.response_summary))
        self.assertNotIn("postgres://raw-secret", str(action.response_summary))

    def test_admin_resource_api_requires_active_session(self):
        user = self.create_user("k8s-admin-no-session", grant_admin_read=True)
        self.client.force_login(user)

        response = self.client.get(
            reverse("api_kubernetes_admin_resource_list", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
            {"api_version": "apps/v1", "kind": "Deployment", "namespace": "payments"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_session_required")
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_resource.read_rejected").exists())

    def test_regular_kubernetes_user_cannot_read_admin_pod_logs_without_admin_read(self):
        user = self.create_user("k8s-regular-logs")
        session = self.create_read_session(user)
        self.client.force_login(user)

        response = self.client.get(
            reverse("api_kubernetes_admin_pod_logs", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
            {"session_id": str(session.session_id), "namespace": "payments", "pod": "payments-api-abc123"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_read_required")
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_resource.logs_rejected").exists())

    def test_regular_kubernetes_user_cannot_watch_admin_resources_without_admin_read(self):
        user = self.create_user("k8s-regular-watch")
        session = self.create_read_session(user)
        self.client.force_login(user)

        response = self.client.get(
            reverse("api_kubernetes_admin_resource_watch", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
            {"session_id": str(session.session_id), "api_version": "v1", "kind": "Pod", "namespace": "payments"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_read_required")
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_resource.watch_rejected").exists())

    def test_admin_pod_logs_snapshot_is_session_gated_bounded_redacted_and_audited(self):
        self.provider.labels = {"pod_logs_path_template": "/v3/pods/{namespace}:{pod_name}/logs?tail={tail}&cluster={cluster_id}"}
        self.provider.save(update_fields=["labels"])
        user = self.create_user("k8s-admin-logs", grant_admin_read=True)
        session = self.create_read_session(user)
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen["url"] = url
            return {"logs": "line one\npassword=super-secret\nAuthorization: Bearer abc.def\nlast line"}

        payload = get_admin_pod_log_snapshot(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            namespace="payments",
            pod_name="payments-api-abc123",
            tail_lines=3,
            transport=transport,
        )

        self.assertTrue(payload["success"])
        self.assertTrue(payload["available"])
        self.assertEqual(payload["operation"], "pod_logs_snapshot")
        self.assertEqual(payload["mode"], "admin_read_only")
        self.assertEqual(payload["source"], "provider_snapshot")
        self.assertEqual(payload["line_count"], 3)
        self.assertTrue(payload["truncated"])
        self.assertFalse(payload["policy"]["mutates_state"])
        self.assertFalse(payload["policy"]["streaming"])
        self.assertIn("exec", payload["policy"]["blocked_actions"])
        self.assertEqual(payload["path"], "/v3/pods/payments:payments-api-abc123/logs")
        self.assertEqual(seen["url"], "https://rancher.example.test/v3/pods/payments:payments-api-abc123/logs?tail=3&cluster=c-prod")
        self.assertEqual(payload["lines"][0], "password=[redacted]")
        self.assertEqual(payload["lines"][1], "Authorization: Bearer [redacted]")
        self.assertEqual(payload["lines"][2], "last line")
        self.assertNotIn("super-secret", str(payload))
        self.assertNotIn("abc.def", str(payload))
        action = K8sAdminAction.objects.get()
        self.assertEqual(action.verb, K8sAdminAction.VERB_LOGS)
        self.assertEqual(action.resource_kind, "Pod")
        self.assertEqual(action.resource_name, "payments-api-abc123")
        self.assertEqual(action.response_summary["line_count"], 3)
        self.assertNotIn("line one", str(action.response_summary))
        self.assertNotIn("super-secret", str(action.response_summary))

    def test_admin_resource_watch_preview_is_bounded_redacted_and_audited_without_body(self):
        user = self.create_user("k8s-admin-watch", grant_admin_read=True)
        session = self.create_read_session(user)
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen["url"] = url
            seen["timeout"] = timeout
            return {
                "events": [
                    {
                        "type": "ADDED",
                        "object": {
                            "apiVersion": "v1",
                            "kind": "Pod",
                            "metadata": {
                                "name": "payments-api-abc123",
                                "namespace": "payments",
                                "resourceVersion": "10",
                                "labels": {"token": "raw-token"},
                            },
                            "spec": {"serviceAccountName": "payments"},
                        },
                    },
                    {
                        "type": "MODIFIED",
                        "object": {
                            "apiVersion": "v1",
                            "kind": "Pod",
                            "metadata": {"name": "payments-api-abc123", "namespace": "payments", "resourceVersion": "11"},
                            "status": {"phase": "Running"},
                        },
                    },
                    {
                        "type": "DELETED",
                        "object": {
                            "apiVersion": "v1",
                            "kind": "Pod",
                            "metadata": {"name": "old-pod", "namespace": "payments", "resourceVersion": "12"},
                        },
                    },
                ]
            }

        payload = get_admin_resource_watch_preview(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="v1",
            kind="Pod",
            namespace="payments",
            resource_version="9",
            limit=2,
            timeout_seconds=6,
            transport=transport,
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["operation"], "resource_watch_preview")
        self.assertEqual(payload["path"], "/k8s/clusters/c-prod/api/v1/namespaces/payments/pods")
        self.assertEqual(payload["event_count"], 2)
        self.assertTrue(payload["truncated"])
        self.assertFalse(payload["policy"]["mutates_state"])
        self.assertFalse(payload["policy"]["streaming"])
        self.assertEqual(payload["latest_resource_version"], "11")
        self.assertEqual(payload["events"][0]["object"]["metadata"]["labels"]["token"], "[redacted]")
        self.assertEqual(payload["events"][0]["resource_version"], "10")
        self.assertNotIn("raw-token", str(payload))
        self.assertIn("watch=1", seen["url"])
        self.assertIn("resourceVersion=9", seen["url"])
        self.assertIn("timeoutSeconds=6", seen["url"])
        self.assertEqual(seen["timeout"], 11)
        action = K8sAdminAction.objects.get()
        self.assertEqual(action.verb, K8sAdminAction.VERB_WATCH)
        self.assertEqual(action.resource_kind, "Pod")
        self.assertEqual(action.namespace, "payments")
        self.assertEqual(action.response_summary["event_count"], 2)
        self.assertEqual(action.response_summary["latest_resource_version"], "11")
        self.assertNotIn("payments-api-abc123", str(action.response_summary))
        self.assertNotIn("raw-token", str(action.response_summary))

    def test_admin_resource_watch_preview_uses_bookmark_for_latest_resource_version(self):
        user = self.create_user("k8s-admin-watch-bookmark", grant_admin_read=True)
        session = self.create_read_session(user)

        def transport(url: str, headers: dict[str, str], timeout: int):
            return {
                "items": [
                    {
                        "type": "ADDED",
                        "object": {
                            "apiVersion": "apps/v1",
                            "kind": "Deployment",
                            "metadata": {"name": "payments-api", "namespace": "payments", "resourceVersion": "14"},
                        },
                    },
                    {
                        "type": "BOOKMARK",
                        "object": {"metadata": {"resourceVersion": "15"}},
                    },
                ]
            }

        payload = get_admin_resource_watch_preview(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="apps/v1",
            kind="Deployment",
            namespace="payments",
            resource_version="13",
            limit=5,
            transport=transport,
        )

        self.assertEqual(payload["event_count"], 1)
        self.assertEqual(payload["events"][0]["type"], "ADDED")
        self.assertEqual(payload["events"][0]["resource_version"], "14")
        self.assertEqual(payload["latest_resource_version"], "15")
        self.assertNotIn("BOOKMARK", str(payload["events"]))
        action = K8sAdminAction.objects.get()
        self.assertEqual(action.response_summary["latest_resource_version"], "15")

    def test_yaml_includes_fleet_ownership_context_without_mutating_manifest(self):
        user = self.create_user("k8s-admin-fleet-yaml", grant_admin_read=True)
        session = self.create_read_session(user)
        K8sFleetBundle.objects.create(
            name="fleet-local/payments-rollout",
            source="https://git.example.test/platform.git",
            target="payments",
            status=K8sFleetBundle.STATUS_ROLLING,
            labels={"token": "raw-fleet-token"},
        )

        def transport(url: str, headers: dict[str, str], timeout: int):
            return {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {
                    "name": "payments-api",
                    "namespace": "payments",
                    "labels": {"fleet.cattle.io/bundle-id": "fleet-local/payments-rollout"},
                },
                "spec": {"replicas": 2},
            }

        payload = get_cluster_resource_yaml(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="apps/v1",
            kind="Deployment",
            namespace="payments",
            name="payments-api",
            transport=transport,
        )

        self.assertEqual(payload["ownership"]["owner"], "fleet")
        self.assertEqual(payload["ownership"]["change_path"], "fleet_gitops_or_mr")
        self.assertEqual(payload["ownership"]["direct_apply_policy"], "blocked_by_default")
        self.assertEqual(payload["ownership"]["fleet_bundle"]["name"], "fleet-local/payments-rollout")
        self.assertEqual(payload["ownership"]["fleet_bundle"]["labels"]["token"], "[redacted]")
        self.assertNotIn("webterm_ownership", payload["resource"])
        self.assertNotIn("raw-fleet-token", str(payload))

    def test_admin_crds_api_uses_cluster_proxy_path(self):
        user = self.create_user("k8s-admin-crds", grant_admin_read=True)
        session = self.create_read_session(user)
        self.client.force_login(user)

        def transport(url: str, headers: dict[str, str], timeout: int):
            return {
                "items": [
                    {
                        "apiVersion": "apiextensions.k8s.io/v1",
                        "kind": "CustomResourceDefinition",
                        "metadata": {"name": "widgets.example.com"},
                    }
                ]
            }

        with patch("kubernetes_ops.services.admin_resources.ProviderJsonClient") as client_cls:
            client_cls.return_value.get.side_effect = lambda path: transport(f"{self.provider.base_url}{path}", {}, 20)
            response = self.client.get(
                reverse("api_kubernetes_admin_crds", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
                {"session_id": str(session.session_id)},
            )
            client_cls.return_value.get.assert_called_with(
                "/k8s/clusters/c-prod/apis/apiextensions.k8s.io/v1/customresourcedefinitions"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["metadata"]["name"], "widgets.example.com")
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_resource.crds").exists())

    def test_provider_error_returns_controlled_json(self):
        user = self.create_user("k8s-admin-provider-error", grant_admin_read=True)
        session = self.create_read_session(user)

        def transport(url: str, headers: dict[str, str], timeout: int):
            raise OSError("connection refused")

        with self.assertRaises(AdminResourceError) as raised:
            list_cluster_resources(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="apps/v1",
                kind="Deployment",
                namespace="payments",
                transport=transport,
            )
        self.assertEqual(raised.exception.code, "provider_request_failed")
        self.assertEqual(raised.exception.status, 502)
