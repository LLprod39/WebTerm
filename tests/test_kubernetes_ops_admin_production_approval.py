from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_apply import apply_kubernetes_resource
from kubernetes_ops.services.admin_delete import delete_kubernetes_resource
from kubernetes_ops.services.admin_patch import patch_kubernetes_resource
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.admin_workload_actions import restart_kubernetes_workload, scale_kubernetes_workload


class KubernetesOpsAdminProductionApprovalTests(TestCase):
    def create_user(self, username: str) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        UserAppPermission.objects.create(user=user, feature="kubernetes_admin_write", allowed=True)
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

    def create_write_session(self, user: User, **kwargs) -> K8sAdminSession:
        defaults = {
            "user": user,
            "username_snapshot": user.username,
            "cluster": self.cluster,
            "mode": K8sAdminSession.MODE_WRITE,
            "status": K8sAdminSession.STATUS_ACTIVE,
            "risk_tier": K8sAdminSession.RISK_HIGH,
            "allowed_verbs": ["get", "list", "watch", "logs", "yaml", "dry_run_apply", "apply", "patch", "scale", "restart", "delete"],
            "allowed_kinds": ["Deployment", "Service", "Ingress"],
            "allowed_namespaces": ["payments", "payments-prod"],
            "reason": "missing approval evidence regression",
            "approval_ref": "CHG-MISSING-EVIDENCE",
            "expires_at": timezone.now() + timedelta(minutes=30),
        }
        defaults.update(kwargs)
        return K8sAdminSession.objects.create(**defaults)

    def deployment_manifest(self, *, namespace: str = "payments") -> dict:
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "payments-api", "namespace": namespace},
            "spec": {"replicas": 2},
        }

    def fail_transport(self, *args, **kwargs):
        self.fail("provider transport must not be called without production approval")

    @override_settings(
        KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_SCALE_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED=True,
    )
    def test_prod_cluster_mutations_require_approved_session_evidence_before_provider_call(self):
        user = self.create_user("k8s-prod-approval-required")

        operations = [
            (
                "apply",
                lambda session: apply_kubernetes_resource(
                    user=user,
                    session_id=str(session.session_id),
                    cluster_id=f"cluster_{self.cluster.id}",
                    dry_run_action_id="",
                    reason="apply deployment",
                    manifest=self.deployment_manifest(),
                    transport=self.fail_transport,
                ),
            ),
            (
                "patch",
                lambda session: patch_kubernetes_resource(
                    user=user,
                    session_id=str(session.session_id),
                    cluster_id=f"cluster_{self.cluster.id}",
                    api_version="apps/v1",
                    kind="Deployment",
                    namespace="payments",
                    name="payments-api",
                    patch_body={"metadata": {"labels": {"patched": "true"}}},
                    reason="patch deployment",
                    transport=self.fail_transport,
                ),
            ),
            (
                "scale",
                lambda session: scale_kubernetes_workload(
                    user=user,
                    session_id=str(session.session_id),
                    cluster_id=f"cluster_{self.cluster.id}",
                    api_version="apps/v1",
                    kind="Deployment",
                    namespace="payments",
                    name="payments-api",
                    replicas=3,
                    reason="scale deployment",
                    transport=self.fail_transport,
                ),
            ),
            (
                "restart",
                lambda session: restart_kubernetes_workload(
                    user=user,
                    session_id=str(session.session_id),
                    cluster_id=f"cluster_{self.cluster.id}",
                    api_version="apps/v1",
                    kind="Deployment",
                    namespace="payments",
                    name="payments-api",
                    reason="restart deployment",
                    transport=self.fail_transport,
                ),
            ),
            (
                "delete",
                lambda session: delete_kubernetes_resource(
                    user=user,
                    session_id=str(session.session_id),
                    cluster_id=f"cluster_{self.cluster.id}",
                    api_version="apps/v1",
                    kind="Deployment",
                    namespace="payments",
                    name="payments-api",
                    confirmation="delete Deployment payments/payments-api",
                    reason="delete deployment",
                    transport=self.fail_transport,
                ),
            ),
        ]

        for action, call in operations:
            with self.subTest(action=action):
                session = self.create_write_session(user)
                with self.assertRaises(AdminResourceError) as raised:
                    call(session)
                self.assertEqual(raised.exception.code, "production_approval_required")
                self.assertEqual(raised.exception.payload["action"], action)
                self.assertEqual(raised.exception.payload["environment"], "prod")

        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED=True)
    def test_prod_like_namespace_requires_approval_even_outside_prod_cluster(self):
        user = self.create_user("k8s-prod-namespace-approval")
        self.cluster.environment = "staging"
        self.cluster.save(update_fields=["environment"])
        session = self.create_write_session(user)

        with self.assertRaises(AdminResourceError) as raised:
            patch_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="apps/v1",
                kind="Deployment",
                namespace="payments-prod",
                name="payments-api",
                patch_body={"metadata": {"labels": {"patched": "true"}}},
                reason="patch production namespace",
                transport=self.fail_transport,
            )

        self.assertEqual(raised.exception.code, "production_approval_required")
        self.assertEqual(raised.exception.payload["namespace"], "payments-prod")
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF="",
        KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED=True,
    )
    def test_production_release_writes_require_restricted_credential_evidence_before_provider_call(self):
        user = self.create_user("k8s-prod-restricted-credentials")
        session = self.create_write_session(user, approved_by=user, approved_at=timezone.now())

        with self.assertRaises(AdminResourceError) as raised:
            patch_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="apps/v1",
                kind="Deployment",
                namespace="payments",
                name="payments-api",
                patch_body={"metadata": {"labels": {"patched": "true"}}},
                reason="patch production deployment",
                transport=self.fail_transport,
            )

        self.assertEqual(raised.exception.code, "restricted_credential_evidence_required")
        self.assertEqual(raised.exception.payload["target_environment"], "production")
        self.assertEqual(
            raised.exception.payload["requires"],
            ["KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF"],
        )
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF="artifact:restricted-sa-proof-123",
        KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED=True,
    )
    def test_production_release_writes_continue_when_restricted_credential_evidence_is_present(self):
        user = self.create_user("k8s-prod-restricted-credentials-present")
        session = self.create_write_session(user, approved_by=user, approved_at=timezone.now())

        def transport(url: str, headers: dict[str, str], timeout: int, *, method: str = "GET", body=None):
            return {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "payments-api", "namespace": "payments"},
                "spec": {"replicas": 2},
            }

        payload = patch_kubernetes_resource(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="apps/v1",
            kind="Deployment",
            namespace="payments",
            name="payments-api",
            patch_body={"metadata": {"labels": {"patched": "true"}}},
            reason="patch production deployment",
            transport=transport,
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["operation"], "patch")
        self.assertEqual(K8sAdminAction.objects.get().status, K8sAdminAction.STATUS_COMPLETED)
