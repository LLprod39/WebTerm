from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_resources import get_cluster_resource_yaml


class KubernetesOpsAdminManifestContractTests(TestCase):
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

    def test_yaml_response_exposes_safe_json_manifest_contract(self):
        user = self.create_user("k8s-admin-manifest-contract")
        session = self.create_read_session(user)

        def transport(url: str, headers: dict[str, str], timeout: int):
            return {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {
                    "name": "payments-api",
                    "namespace": "payments",
                    "managedFields": [{"manager": "kubectl"}],
                    "annotations": {"token": "raw-annotation-token"},
                },
                "spec": {"replicas": 2},
                "status": {"availableReplicas": 2},
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

        manifest = payload["manifest"]
        self.assertTrue(manifest["resource_json_available"])
        self.assertTrue(manifest["client_yaml_render_available"])
        self.assertFalse(manifest["server_yaml_body_stored"])
        self.assertFalse(manifest["raw_provider_body_stored"])
        self.assertTrue(manifest["apply_requires_dry_run"])
        self.assertFalse(manifest["copy_for_apply_recommended"])
        self.assertTrue(manifest["redacted"])
        self.assertEqual(manifest["api_version"], "apps/v1")
        self.assertEqual(manifest["kind"], "Deployment")
        self.assertEqual(manifest["namespace"], "payments")
        self.assertEqual(manifest["name"], "payments-api")
        self.assertEqual(manifest["top_level_keys"], ["apiVersion", "kind", "metadata", "spec", "status"])
        self.assertIn("managedFields", manifest["metadata_keys"])
        self.assertTrue(manifest["managed_fields_redacted"])
        self.assertTrue(manifest["spec_present"])
        self.assertTrue(manifest["status_present"])
        self.assertEqual(manifest["secret_payload_keys"], [])
        self.assertNotIn("raw-annotation-token", str(payload))

        action = K8sAdminAction.objects.get()
        self.assertNotIn("raw-annotation-token", str(action.request_payload_sanitized))
        self.assertNotIn("raw-annotation-token", str(action.response_summary))

    def test_secret_manifest_contract_marks_redacted_secret_payload(self):
        user = self.create_user("k8s-admin-secret-manifest-contract")
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

        manifest = payload["manifest"]
        self.assertEqual(manifest["secret_payload_keys"], ["data", "stringData"])
        self.assertTrue(manifest["secret_payload_redacted"])
        self.assertTrue(manifest["redacted"])
        self.assertTrue(payload["secret_values"]["visible"] is False)
        self.assertNotIn("cGFzc3dvcmQ=", str(payload))
        self.assertNotIn("postgres://raw-secret", str(payload))
