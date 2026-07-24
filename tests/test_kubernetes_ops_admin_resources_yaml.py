from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import (
    K8sAdminSession,
    K8sAuditEvent,
    K8sCluster,
    K8sFleetBundle,
    K8sProvider,
)
from kubernetes_ops.services.admin_resources import (
    AdminResourceError,
    get_cluster_resource_yaml,
    list_cluster_resources,
)


class KubernetesOpsAdminResourceYamlAndErrorTests(TestCase):
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

        with patch("kubernetes_ops.services.admin_resources_helpers.ProviderJsonClient") as client_cls:
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
