from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_resources import AdminResourceError, get_cluster_resource_yaml


class KubernetesOpsAdminSecretValueTests(TestCase):
    def create_user(
        self,
        username: str,
        *,
        grant_admin_read: bool = False,
        grant_secret_read: bool = False,
    ) -> User:
        user = User.objects.create_user(username=username, password="password-123")
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

    def test_secret_yaml_is_redacted_and_does_not_store_secret_in_audit(self):
        user = self.create_user("k8s-admin-secret-yaml", grant_admin_read=True)
        session = self.create_read_session(user)

        def transport(url: str, headers: dict[str, str], timeout: int):
            return {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": "db-creds", "namespace": "payments"},
                "data": {"password": "cGFzc3dvcmQ=", "token": "cmF3"},
                "stringData": {"dsn": "postgres://raw-secret"},
            }

        payload = get_cluster_resource_yaml(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="v1",
            kind="Secret",
            namespace="payments",
            name="db-creds",
            transport=transport,
        )

        self.assertTrue(payload["redacted"])
        self.assertEqual(payload["resource"]["data"]["password"], "[redacted]")
        self.assertEqual(payload["resource"]["data"]["token"], "[redacted]")
        self.assertEqual(payload["resource"]["stringData"]["dsn"], "[redacted]")
        self.assertNotIn("cGFzc3dvcmQ=", str(payload))
        self.assertNotIn("postgres://raw-secret", str(payload))
        action = K8sAdminAction.objects.get()
        self.assertEqual(action.verb, K8sAdminAction.VERB_YAML)
        self.assertTrue(action.response_summary["redacted"])
        self.assertNotIn("postgres://raw-secret", str(action.request_payload_sanitized))
        self.assertNotIn("postgres://raw-secret", str(action.response_summary))

    @override_settings(KUBERNETES_ADMIN_SECRET_READ_ENABLED=True)
    def test_secret_yaml_rejects_value_reveal_without_secret_read_grant(self):
        user = self.create_user("k8s-admin-secret-denied", grant_admin_read=True)
        session = self.create_read_session(user)

        def transport(url: str, headers: dict[str, str], timeout: int):
            return {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": "db-creds", "namespace": "payments"},
                "data": {"password": "cGFzc3dvcmQ="},
            }

        with self.assertRaises(AdminResourceError) as raised:
            get_cluster_resource_yaml(
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

        self.assertEqual(raised.exception.code, "secret_read_required")
        self.assertEqual(raised.exception.status, 403)
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(KUBERNETES_ADMIN_SECRET_READ_ENABLED=True)
    def test_secret_yaml_can_reveal_values_with_grant_without_audit_body(self):
        user = self.create_user("k8s-admin-secret-visible", grant_admin_read=True, grant_secret_read=True)
        session = self.create_read_session(user)
        self.client.force_login(user)

        with patch("kubernetes_ops.services.admin_resources_helpers.ProviderJsonClient") as client_cls:
            client_cls.return_value.get.return_value = {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {
                    "name": "db-creds",
                    "namespace": "payments",
                    "annotations": {"token": "raw-annotation-token"},
                },
                "data": {"password": "cGFzc3dvcmQ=", "token": "cmF3"},
                "stringData": {"dsn": "postgres://raw-secret"},
            }
            response = self.client.get(
                reverse("api_kubernetes_admin_resource_yaml", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
                {
                    "session_id": str(session.session_id),
                    "api_version": "v1",
                    "kind": "Secret",
                    "namespace": "payments",
                    "name": "db-creds",
                    "include_secret_values": "1",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["secret_values"]["requested"])
        self.assertTrue(payload["secret_values"]["visible"])
        self.assertEqual(payload["resource"]["data"]["password"], "cGFzc3dvcmQ=")
        self.assertEqual(payload["resource"]["data"]["token"], "cmF3")
        self.assertEqual(payload["resource"]["stringData"]["dsn"], "postgres://raw-secret")
        self.assertEqual(payload["resource"]["metadata"]["annotations"]["token"], "[redacted]")
        self.assertIn("postgres://raw-secret", str(payload))
        self.assertNotIn("raw-annotation-token", str(payload))
        action = K8sAdminAction.objects.get()
        self.assertTrue(action.response_summary["redacted"])
        self.assertTrue(action.response_summary["secret_values_requested"])
        self.assertTrue(action.response_summary["secret_values_visible"])
        self.assertNotIn("cGFzc3dvcmQ=", str(action.request_payload_sanitized))
        self.assertNotIn("postgres://raw-secret", str(action.response_summary))
        audit = K8sAuditEvent.objects.get(action="k8s.admin_resource.yaml")
        self.assertTrue(audit.payload["secret_values_requested"])
        self.assertTrue(audit.payload["secret_values_visible"])
        self.assertNotIn("cGFzc3dvcmQ=", str(audit.payload))
        self.assertNotIn("postgres://raw-secret", str(audit.payload))
