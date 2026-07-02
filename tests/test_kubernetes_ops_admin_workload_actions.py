import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.admin_workload_actions import restart_kubernetes_workload, scale_kubernetes_workload


class KubernetesOpsAdminWorkloadActionTests(TestCase):
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
            "allowed_verbs": ["get", "list", "watch", "logs", "yaml", "dry_run_apply", "apply", "scale", "restart"],
            "allowed_kinds": ["Deployment", "StatefulSet", "DaemonSet"],
            "allowed_namespaces": ["payments"],
            "reason": "workload action after approval",
            "approval_ref": "CHG-2026-WORKLOAD",
            "approved_by": user,
            "approved_at": timezone.now(),
            "expires_at": timezone.now() + timedelta(minutes=30),
        }
        defaults.update(kwargs)
        return K8sAdminSession.objects.create(**defaults)

    def workload_response(self, *, kind: str = "Deployment") -> dict:
        return {
            "apiVersion": "apps/v1",
            "kind": kind,
            "metadata": {"name": "payments-api", "namespace": "payments"},
            "spec": {"replicas": 3, "template": {"metadata": {"annotations": {}}}},
            "status": {"readyReplicas": 2},
        }

    def test_scale_and_restart_are_disabled_by_default_before_provider_call(self):
        user = self.create_user("k8s-workload-disabled", grant_admin_write=True)
        session = self.create_write_session(user)

        with self.assertRaises(AdminResourceError) as scale_denied:
            scale_kubernetes_workload(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="apps/v1",
                kind="Deployment",
                namespace="payments",
                name="payments-api",
                replicas=3,
                reason="scale deployment",
                transport=lambda *args, **kwargs: self.fail("provider must not be called"),
            )
        with self.assertRaises(AdminResourceError) as restart_denied:
            restart_kubernetes_workload(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="apps/v1",
                kind="Deployment",
                namespace="payments",
                name="payments-api",
                reason="restart deployment",
                transport=lambda *args, **kwargs: self.fail("provider must not be called"),
            )

        self.assertEqual(scale_denied.exception.code, "native_scale_disabled")
        self.assertEqual(restart_denied.exception.code, "native_restart_disabled")
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(KUBERNETES_ADMIN_NATIVE_SCALE_ENABLED=True)
    def test_scale_uses_scale_subresource_and_records_action(self):
        user = self.create_user("k8s-scale-success", grant_admin_write=True)
        session = self.create_write_session(user)
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int, *, method: str = "GET", body=None):
            seen.update({"url": url, "headers": headers, "method": method, "body": body})
            return {"apiVersion": "autoscaling/v1", "kind": "Scale", "metadata": {"name": "payments-api", "namespace": "payments"}, "spec": {"replicas": 3}}

        payload = scale_kubernetes_workload(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="apps/v1",
            kind="Deployment",
            namespace="payments",
            name="payments-api",
            replicas=3,
            reason="scale deployment",
            transport=transport,
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["operation"], "scale")
        self.assertEqual(payload["replicas"], 3)
        self.assertEqual(payload["path"], "/k8s/clusters/c-prod/apis/apps/v1/namespaces/payments/deployments/payments-api/scale")
        self.assertEqual(seen["method"], "PATCH")
        self.assertIn("/scale", seen["url"])
        self.assertEqual(seen["headers"]["Content-Type"], "application/merge-patch+json")
        self.assertEqual(seen["body"], {"spec": {"replicas": 3}})
        action = K8sAdminAction.objects.get()
        self.assertEqual(action.verb, K8sAdminAction.VERB_SCALE)
        self.assertEqual(action.status, K8sAdminAction.STATUS_COMPLETED)
        self.assertEqual(action.request_payload_sanitized["replicas"], 3)
        self.assertEqual(action.response_summary["replicas"], 3)

    @override_settings(KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED=True)
    def test_restart_api_patches_rollout_annotation_and_audits_metadata(self):
        user = self.create_user("k8s-restart-api", grant_admin_write=True)
        session = self.create_write_session(user)
        self.client.force_login(user)

        with patch("kubernetes_ops.services.admin_workload_actions.ProviderJsonClient") as client_cls:
            client_cls.return_value.request.return_value = self.workload_response()
            response = self.client.post(
                reverse("api_kubernetes_admin_restart", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
                data=json.dumps(
                    {
                        "session_id": str(session.session_id),
                        "api_version": "apps/v1",
                        "kind": "Deployment",
                        "namespace": "payments",
                        "name": "payments-api",
                        "reason": "restart after config rollout",
                    }
                ),
                content_type="application/json",
            )
            method, path = client_cls.return_value.request.call_args.args[:2]
            body = client_cls.return_value.request.call_args.kwargs["body"]

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["operation"], "restart")
        self.assertEqual(method, "PATCH")
        self.assertEqual(path, "/k8s/clusters/c-prod/apis/apps/v1/namespaces/payments/deployments/payments-api")
        self.assertIn("kubectl.kubernetes.io/restartedAt", body["spec"]["template"]["metadata"]["annotations"])
        action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_RESTART)
        self.assertEqual(action.status, K8sAdminAction.STATUS_COMPLETED)
        self.assertIn("restarted_at", action.request_payload_sanitized)
        audit = K8sAuditEvent.objects.get(action="k8s.admin_resource.restart")
        self.assertEqual(audit.payload["target"]["name"], "payments-api")
        self.assertIn("restarted_at", audit.payload)

    @override_settings(KUBERNETES_ADMIN_NATIVE_SCALE_ENABLED=True, KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED=True)
    def test_workload_actions_respect_session_scope_and_kind_limits(self):
        user = self.create_user("k8s-workload-scope", grant_admin_write=True)
        session = self.create_write_session(user, allowed_namespaces=["platform"], allowed_kinds=["Deployment"])

        with self.assertRaises(AdminResourceError) as namespace_denied:
            scale_kubernetes_workload(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="apps/v1",
                kind="Deployment",
                namespace="payments",
                name="payments-api",
                replicas=2,
                reason="scale deployment",
                transport=lambda *args, **kwargs: {},
            )
        with self.assertRaises(AdminResourceError) as kind_denied:
            restart_kubernetes_workload(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="apps/v1",
                kind="Job",
                namespace="platform",
                name="nightly",
                reason="restart job",
                transport=lambda *args, **kwargs: {},
            )

        self.assertEqual(namespace_denied.exception.code, "admin_session_namespace_denied")
        self.assertEqual(kind_denied.exception.code, "kind_not_restartable")
        self.assertFalse(K8sAdminAction.objects.exists())
