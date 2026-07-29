import json
from datetime import timedelta
from unittest.mock import patch as mock_patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_patch import patch_kubernetes_resource
from kubernetes_ops.services.admin_resources import AdminResourceError


class KubernetesOpsAdminPatchTests(TestCase):
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
            "allowed_verbs": ["get", "list", "watch", "logs", "yaml", "dry_run_apply", "apply", "patch"],
            "allowed_kinds": ["Deployment", "Service", "Secret"],
            "allowed_namespaces": ["payments"],
            "reason": "patch after approval",
            "approval_ref": "CHG-2026-PATCH",
            "approved_by": user,
            "approved_at": timezone.now(),
            "expires_at": timezone.now() + timedelta(minutes=30),
        }
        defaults.update(kwargs)
        return K8sAdminSession.objects.create(**defaults)

    def deployment_response(self) -> dict:
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "payments-api", "namespace": "payments"},
            "spec": {"replicas": 2},
            "status": {"readyReplicas": 2},
        }

    def test_patch_is_disabled_by_default_before_provider_call(self):
        user = self.create_user("k8s-patch-disabled", grant_admin_write=True)
        session = self.create_write_session(user)

        with self.assertRaises(AdminResourceError) as denied:
            patch_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="apps/v1",
                kind="Deployment",
                namespace="payments",
                name="payments-api",
                patch_body={"metadata": {"labels": {"patched": "true"}}},
                reason="patch deployment label",
                transport=lambda *args, **kwargs: self.fail("provider must not be called"),
            )

        self.assertEqual(denied.exception.code, "native_patch_disabled")
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED=True)
    def test_patch_uses_merge_patch_and_records_metadata_only(self):
        user = self.create_user("k8s-patch-success", grant_admin_write=True)
        session = self.create_write_session(user)
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int, *, method: str = "GET", body=None):
            seen.update({"url": url, "headers": headers, "method": method, "body": body})
            return self.deployment_response()

        payload = patch_kubernetes_resource(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="apps/v1",
            kind="Deployment",
            namespace="payments",
            name="payments-api",
            patch_body={"metadata": {"labels": {"patched": "true"}}},
            reason="patch deployment label",
            transport=transport,
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["operation"], "patch")
        self.assertEqual(payload["patch_type"], "merge")
        self.assertEqual(
            payload["path"], "/k8s/clusters/c-prod/apis/apps/v1/namespaces/payments/deployments/payments-api"
        )
        self.assertEqual(seen["method"], "PATCH")
        self.assertEqual(seen["headers"]["Content-Type"], "application/merge-patch+json")
        self.assertEqual(seen["body"], {"metadata": {"labels": {"patched": "true"}}})
        action = K8sAdminAction.objects.get()
        self.assertEqual(action.verb, K8sAdminAction.VERB_PATCH)
        self.assertEqual(action.status, K8sAdminAction.STATUS_COMPLETED)
        self.assertEqual(action.request_payload_sanitized["patch_type"], "merge")
        self.assertEqual(action.request_payload_sanitized["top_level_fields"], ["metadata"])
        self.assertNotIn("patched", str(action.request_payload_sanitized))

    @override_settings(KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED=True)
    def test_patch_api_redacts_secret_response_action_and_audit(self):
        user = self.create_user("k8s-secret-patch", grant_admin_write=True)
        session = self.create_write_session(user)
        self.client.force_login(user)

        with mock_patch("kubernetes_ops.services.admin_patch.ProviderJsonClient") as client_cls:
            client_cls.return_value.request.return_value = {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": "db-creds", "namespace": "payments"},
                "data": {"password": "cGFzc3dvcmQ="},
                "stringData": {"dsn": "postgres://raw-secret"},
            }
            response = self.client.post(
                reverse("api_kubernetes_admin_patch", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
                data=json.dumps(
                    {
                        "session_id": str(session.session_id),
                        "api_version": "v1",
                        "kind": "Secret",
                        "namespace": "payments",
                        "name": "db-creds",
                        "reason": "rotate secret metadata after approval",
                        "patch": {"stringData": {"dsn": "postgres://raw-secret"}},
                    }
                ),
                content_type="application/json",
            )
            method, path = client_cls.return_value.request.call_args.args[:2]

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(method, "PATCH")
        self.assertEqual(path, "/k8s/clusters/c-prod/api/v1/namespaces/payments/secrets/db-creds")
        self.assertTrue(payload["redacted"])
        self.assertEqual(payload["resource"]["data"]["password"], "[redacted]")
        self.assertNotIn("postgres://raw-secret", str(payload))
        self.assertNotIn("cGFzc3dvcmQ=", str(payload))
        action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_PATCH)
        self.assertTrue(action.request_payload_sanitized["redacted"])
        self.assertNotIn("postgres://raw-secret", str(action.request_payload_sanitized))
        self.assertNotIn("postgres://raw-secret", str(action.response_summary))
        audit = K8sAuditEvent.objects.get(action="k8s.admin_resource.patch")
        self.assertEqual(audit.payload["target"]["kind"], "Secret")
        self.assertTrue(audit.payload["redacted"])
        self.assertNotIn("postgres://raw-secret", str(audit.payload))

    @override_settings(KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED=True)
    def test_patch_respects_session_namespace_and_kind_scope(self):
        user = self.create_user("k8s-patch-scope", grant_admin_write=True)
        session = self.create_write_session(user, allowed_namespaces=["platform"], allowed_kinds=["Deployment"])

        with self.assertRaises(AdminResourceError) as namespace_denied:
            patch_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="apps/v1",
                kind="Deployment",
                namespace="payments",
                name="payments-api",
                patch_body={"metadata": {"labels": {"patched": "true"}}},
                reason="patch deployment label",
                transport=lambda *args, **kwargs: {},
            )
        with self.assertRaises(AdminResourceError) as kind_denied:
            patch_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="v1",
                kind="Service",
                namespace="platform",
                name="payments-api",
                patch_body={"metadata": {"labels": {"patched": "true"}}},
                reason="patch service label",
                transport=lambda *args, **kwargs: {},
            )

        self.assertEqual(namespace_denied.exception.code, "admin_session_namespace_denied")
        self.assertEqual(kind_denied.exception.code, "admin_session_kind_denied")
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED=True)
    def test_patch_rejects_resource_that_does_not_match_declared_kind_before_provider_call(self):
        user = self.create_user("k8s-patch-kind-resource-mismatch", grant_admin_write=True)
        session = self.create_write_session(user, allowed_kinds=["Deployment"])
        provider_called = False

        def transport(*_args, **_kwargs):
            nonlocal provider_called
            provider_called = True
            return {}

        with self.assertRaises(AdminResourceError) as denied:
            patch_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="apps/v1",
                kind="Deployment",
                resource="secrets",
                namespace="payments",
                name="db-creds",
                patch_body={"metadata": {"labels": {"patched": "true"}}},
                reason="attempt mismatched patch target",
                transport=transport,
            )

        self.assertEqual(denied.exception.code, "resource_kind_mismatch")
        self.assertFalse(provider_called)
        self.assertFalse(K8sAdminAction.objects.exists())
