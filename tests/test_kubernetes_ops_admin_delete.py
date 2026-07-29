import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_delete import delete_kubernetes_resource
from kubernetes_ops.services.admin_resources import AdminResourceError


class KubernetesOpsAdminDeleteTests(TestCase):
    def create_user(self, username: str, *, grant_kubernetes: bool = True, grant_admin_write: bool = False) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        if grant_kubernetes:
            UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        if grant_admin_write:
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
            "allowed_verbs": ["get", "list", "watch", "logs", "yaml", "dry_run_apply", "apply", "patch", "delete"],
            "allowed_kinds": ["Deployment", "Service", "Ingress"],
            "allowed_namespaces": ["payments"],
            "reason": "delete after approval",
            "approval_ref": "CHG-2026-DELETE",
            "approved_by": user,
            "approved_at": timezone.now(),
            "expires_at": timezone.now() + timedelta(minutes=30),
        }
        defaults.update(kwargs)
        return K8sAdminSession.objects.create(**defaults)

    def test_delete_is_disabled_by_default_before_provider_call(self):
        user = self.create_user("k8s-delete-disabled", grant_admin_write=True)
        session = self.create_write_session(user)

        with self.assertRaises(AdminResourceError) as denied:
            delete_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="apps/v1",
                kind="Deployment",
                namespace="payments",
                name="payments-api",
                confirmation="delete Deployment payments/payments-api",
                reason="delete failed deployment",
                transport=lambda *args, **kwargs: self.fail("provider must not be called"),
            )

        self.assertEqual(denied.exception.code, "native_delete_disabled")
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED=True)
    def test_delete_requires_exact_confirmation_before_provider_call(self):
        user = self.create_user("k8s-delete-confirmation", grant_admin_write=True)
        session = self.create_write_session(user)

        with self.assertRaises(AdminResourceError) as denied:
            delete_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="apps/v1",
                kind="Deployment",
                namespace="payments",
                name="payments-api",
                confirmation="delete payments-api",
                reason="delete failed deployment",
                transport=lambda *args, **kwargs: self.fail("provider must not be called"),
            )

        self.assertEqual(denied.exception.code, "delete_confirmation_mismatch")
        self.assertEqual(denied.exception.payload["expected_confirmation"], "delete Deployment payments/payments-api")
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED=True)
    def test_delete_blocks_namespace_and_system_namespace(self):
        user = self.create_user("k8s-delete-guards", grant_admin_write=True)
        session = self.create_write_session(
            user, allowed_namespaces=["payments", "kube-system"], allowed_kinds=["Deployment", "Namespace"]
        )

        with self.assertRaises(AdminResourceError) as namespace_denied:
            delete_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="v1",
                kind="Namespace",
                namespace="",
                name="payments",
                confirmation="delete Namespace payments",
                reason="delete namespace",
                transport=lambda *args, **kwargs: self.fail("provider must not be called"),
            )
        with self.assertRaises(AdminResourceError) as system_denied:
            delete_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="apps/v1",
                kind="Deployment",
                namespace="kube-system",
                name="coredns",
                confirmation="delete Deployment kube-system/coredns",
                reason="delete system deployment",
                transport=lambda *args, **kwargs: self.fail("provider must not be called"),
            )

        self.assertEqual(namespace_denied.exception.code, "delete_kind_blocked")
        self.assertEqual(system_denied.exception.code, "delete_namespace_protected")
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED=True)
    def test_delete_api_calls_provider_with_delete_options_and_audits_result(self):
        user = self.create_user("k8s-delete-api", grant_admin_write=True)
        session = self.create_write_session(user)
        self.client.force_login(user)

        with patch("kubernetes_ops.services.admin_delete.ProviderJsonClient") as client_cls:
            client_cls.return_value.request.return_value = {
                "apiVersion": "v1",
                "kind": "Status",
                "status": "Success",
                "details": {"name": "payments-api", "kind": "deployments"},
            }
            response = self.client.post(
                reverse("api_kubernetes_admin_delete", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
                data=json.dumps(
                    {
                        "session_id": str(session.session_id),
                        "api_version": "apps/v1",
                        "kind": "Deployment",
                        "namespace": "payments",
                        "name": "payments-api",
                        "confirmation": "delete Deployment payments/payments-api",
                        "propagation_policy": "Foreground",
                        "reason": "delete failed deployment after approval",
                    }
                ),
                content_type="application/json",
            )
            method, path = client_cls.return_value.request.call_args.args[:2]
            body = client_cls.return_value.request.call_args.kwargs["body"]

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["operation"], "delete")
        self.assertEqual(method, "DELETE")
        self.assertEqual(path, "/k8s/clusters/c-prod/apis/apps/v1/namespaces/payments/deployments/payments-api")
        self.assertEqual(body["kind"], "DeleteOptions")
        self.assertEqual(body["propagationPolicy"], "Foreground")
        action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_DELETE)
        self.assertEqual(action.status, K8sAdminAction.STATUS_COMPLETED)
        self.assertEqual(action.request_payload_sanitized["reason"], "delete failed deployment after approval")
        self.assertEqual(action.request_payload_sanitized["confirmation"], "matched")
        self.assertEqual(action.response_summary["response_status"], "Success")
        audit = K8sAuditEvent.objects.get(action="k8s.admin_resource.delete")
        self.assertEqual(audit.payload["target"]["name"], "payments-api")
        self.assertEqual(audit.payload["reason"], "delete failed deployment after approval")
        self.assertEqual(audit.payload["result"]["status"], "Success")

    @override_settings(KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED=True)
    def test_delete_respects_session_namespace_and_kind_scope(self):
        user = self.create_user("k8s-delete-scope", grant_admin_write=True)
        session = self.create_write_session(user, allowed_namespaces=["platform"], allowed_kinds=["Deployment"])

        with self.assertRaises(AdminResourceError) as namespace_denied:
            delete_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="apps/v1",
                kind="Deployment",
                namespace="payments",
                name="payments-api",
                confirmation="delete Deployment payments/payments-api",
                reason="delete failed deployment",
                transport=lambda *args, **kwargs: {},
            )
        with self.assertRaises(AdminResourceError) as kind_denied:
            delete_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="v1",
                kind="Service",
                namespace="platform",
                name="payments-api",
                confirmation="delete Service platform/payments-api",
                reason="delete stale service",
                transport=lambda *args, **kwargs: {},
            )

        self.assertEqual(namespace_denied.exception.code, "admin_session_namespace_denied")
        self.assertEqual(kind_denied.exception.code, "admin_session_kind_denied")
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED=True)
    def test_delete_rejects_resource_that_does_not_match_declared_kind_before_provider_call(self):
        user = self.create_user("k8s-delete-kind-resource-mismatch", grant_admin_write=True)
        session = self.create_write_session(user, allowed_kinds=["Deployment"])
        provider_called = False

        def transport(*_args, **_kwargs):
            nonlocal provider_called
            provider_called = True
            return {}

        with self.assertRaises(AdminResourceError) as denied:
            delete_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="apps/v1",
                kind="Deployment",
                resource="secrets",
                namespace="payments",
                name="db-creds",
                confirmation="delete Deployment payments/db-creds",
                reason="attempt mismatched delete target",
                transport=transport,
            )

        self.assertEqual(denied.exception.code, "resource_kind_mismatch")
        self.assertFalse(provider_called)
        self.assertFalse(K8sAdminAction.objects.exists())
