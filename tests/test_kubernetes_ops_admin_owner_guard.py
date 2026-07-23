from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sAppRef, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_apply import apply_kubernetes_resource
from kubernetes_ops.services.admin_delete import delete_kubernetes_resource
from kubernetes_ops.services.admin_dry_run import dry_run_apply_kubernetes_resource
from kubernetes_ops.services.admin_patch import patch_kubernetes_resource
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.admin_workload_actions import restart_kubernetes_workload, scale_kubernetes_workload


class KubernetesOpsAdminOwnerGuardTests(TestCase):
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

    def create_write_session(self, user: User) -> K8sAdminSession:
        return K8sAdminSession.objects.create(
            user=user,
            username_snapshot=user.username,
            cluster=self.cluster,
            mode=K8sAdminSession.MODE_WRITE,
            status=K8sAdminSession.STATUS_ACTIVE,
            risk_tier=K8sAdminSession.RISK_HIGH,
            allowed_verbs=[
                "get",
                "list",
                "watch",
                "logs",
                "yaml",
                "dry_run_apply",
                "apply",
                "patch",
                "scale",
                "restart",
                "delete",
            ],
            allowed_kinds=["Deployment", "Service", "Ingress"],
            allowed_namespaces=["payments"],
            reason="owner guard regression",
            approval_ref="CHG-OWNER-GUARD",
            approved_by=user,
            approved_at=timezone.now(),
            expires_at=timezone.now() + timedelta(minutes=30),
        )

    def create_devtron_app(self):
        return K8sAppRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            environment="prod",
            owner=K8sAppRef.OWNER_DEVTRON,
            team="payments",
        )

    def deployment_manifest(self) -> dict:
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "payments-api",
                "namespace": "payments",
                "labels": {"app.kubernetes.io/managed-by": "devtron"},
            },
            "spec": {"replicas": 2},
        }

    def fail_transport(self, *args, **kwargs):
        self.fail("provider transport must not be called for owner-blocked direct mutations")

    @override_settings(KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=True)
    def test_apply_blocks_devtron_owned_resource_after_dry_run_proof_before_provider_call(self):
        user = self.create_user("k8s-owner-apply")
        session = self.create_write_session(user)
        manifest = self.deployment_manifest()
        dry_run_apply_kubernetes_resource(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            manifest=manifest,
            transport=lambda *args, **kwargs: manifest,
        )
        proof = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_DRY_RUN_APPLY)

        with self.assertRaises(AdminResourceError) as raised:
            apply_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                dry_run_action_id=str(proof.action_id),
                reason="apply devtron-owned resource",
                manifest=manifest,
                transport=self.fail_transport,
            )

        self.assertEqual(raised.exception.code, "owner_direct_mutation_blocked")
        self.assertEqual(raised.exception.payload["owner"], K8sAppRef.OWNER_DEVTRON)
        self.assertEqual(raised.exception.payload["change_path"], "devtron_app_flow")
        self.assertEqual(K8sAdminAction.objects.filter(verb=K8sAdminAction.VERB_APPLY).count(), 0)

    @override_settings(KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED=True)
    def test_patch_blocks_devtron_owned_resource_before_provider_call(self):
        user = self.create_user("k8s-owner-patch")
        session = self.create_write_session(user)
        self.create_devtron_app()

        with self.assertRaises(AdminResourceError) as raised:
            patch_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="apps/v1",
                kind="Deployment",
                namespace="payments",
                name="payments-api",
                patch_body={"spec": {"replicas": 3}},
                reason="patch devtron-owned resource",
                transport=self.fail_transport,
            )

        self.assertEqual(raised.exception.code, "owner_direct_mutation_blocked")
        self.assertEqual(raised.exception.payload["owner"], K8sAppRef.OWNER_DEVTRON)
        self.assertEqual(K8sAdminAction.objects.count(), 0)

    @override_settings(KUBERNETES_ADMIN_NATIVE_SCALE_ENABLED=True)
    def test_scale_blocks_devtron_owned_resource_before_provider_call(self):
        user = self.create_user("k8s-owner-scale")
        session = self.create_write_session(user)
        self.create_devtron_app()

        with self.assertRaises(AdminResourceError) as raised:
            scale_kubernetes_workload(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="apps/v1",
                kind="Deployment",
                namespace="payments",
                name="payments-api",
                replicas=4,
                reason="scale devtron-owned resource",
                transport=self.fail_transport,
            )

        self.assertEqual(raised.exception.code, "owner_direct_mutation_blocked")
        self.assertEqual(raised.exception.payload["owner"], K8sAppRef.OWNER_DEVTRON)
        self.assertEqual(K8sAdminAction.objects.count(), 0)

    @override_settings(KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED=True)
    def test_restart_blocks_devtron_owned_resource_before_provider_call(self):
        user = self.create_user("k8s-owner-restart")
        session = self.create_write_session(user)
        self.create_devtron_app()

        with self.assertRaises(AdminResourceError) as raised:
            restart_kubernetes_workload(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="apps/v1",
                kind="Deployment",
                namespace="payments",
                name="payments-api",
                reason="restart devtron-owned resource",
                transport=self.fail_transport,
            )

        self.assertEqual(raised.exception.code, "owner_direct_mutation_blocked")
        self.assertEqual(raised.exception.payload["owner"], K8sAppRef.OWNER_DEVTRON)
        self.assertEqual(K8sAdminAction.objects.count(), 0)

    @override_settings(KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED=True)
    def test_delete_blocks_devtron_owned_resource_before_provider_call(self):
        user = self.create_user("k8s-owner-delete")
        session = self.create_write_session(user)
        self.create_devtron_app()

        with self.assertRaises(AdminResourceError) as raised:
            delete_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="apps/v1",
                kind="Deployment",
                namespace="payments",
                name="payments-api",
                confirmation="delete Deployment payments/payments-api",
                reason="delete devtron-owned resource",
                transport=self.fail_transport,
            )

        self.assertEqual(raised.exception.code, "owner_direct_mutation_blocked")
        self.assertEqual(raised.exception.payload["owner"], K8sAppRef.OWNER_DEVTRON)
        self.assertEqual(K8sAdminAction.objects.count(), 0)
