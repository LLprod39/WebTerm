import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminSession, K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_restricted_context import (
    build_restricted_kube_context_for_session,
    validate_restricted_kube_context_bundle,
)


class KubernetesOpsAdminRestrictedContextTests(TestCase):
    def create_user(self, username: str, *, grant_break_glass: bool = True, is_staff: bool = False) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=is_staff)
        UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        if grant_break_glass:
            UserAppPermission.objects.create(user=user, feature="kubernetes_break_glass", allowed=True)
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

    def create_break_glass_session(self, user: User, **kwargs) -> K8sAdminSession:
        defaults = {
            "user": user,
            "username_snapshot": user.username,
            "cluster": self.cluster,
            "namespace": "payments",
            "mode": K8sAdminSession.MODE_BREAK_GLASS,
            "status": K8sAdminSession.STATUS_ACTIVE,
            "risk_tier": K8sAdminSession.RISK_CRITICAL,
            "reason": "incident terminal prep",
            "approval_ref": "INC-2026-CTX",
            "approved_by": user,
            "approved_at": timezone.now(),
            "allowed_verbs": ["get", "list", "watch", "logs", "yaml", "exec", "port_forward"],
            "allowed_kinds": ["pod"],
            "allowed_namespaces": ["payments"],
            "expires_at": timezone.now() + timedelta(minutes=15),
        }
        defaults.update(kwargs)
        return K8sAdminSession.objects.create(**defaults)

    def post_context(self, session_id, payload: dict):
        return self.client.post(
            reverse("api_kubernetes_admin_session_restricted_context", kwargs={"session_id": session_id}),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_restricted_context_requires_active_approved_break_glass_session(self):
        user = self.create_user("k8s-context-unapproved")
        session = self.create_break_glass_session(user, approval_ref="", approved_by=None, approved_at=None)
        self.client.force_login(user)

        response = self.post_context(session.session_id, {"include_manifest": True})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_session_approval_required")
        self.assertFalse(K8sAuditEvent.objects.filter(action="k8s.admin_session.restricted_context").exists())
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_session.restricted_context_rejected").exists())

    def test_restricted_context_returns_namespace_scoped_manifest_without_credentials(self):
        user = self.create_user("k8s-context-valid")
        session = self.create_break_glass_session(user)
        self.client.force_login(user)

        response = self.post_context(session.session_id, {"include_manifest": True})

        self.assertEqual(response.status_code, 200)
        context = response.json()["restricted_context"]
        payload_text = json.dumps(context)
        self.assertEqual(context["status"], "ready")
        self.assertEqual(context["namespace"], "payments")
        self.assertFalse(context["terminal_bridge_enabled"])
        self.assertFalse(context["node_debug_enabled"])
        self.assertFalse(context["applies_manifest"])
        self.assertFalse(context["contains_kubeconfig"])
        self.assertFalse(context["contains_token"])
        self.assertIn("pods/exec", payload_text)
        self.assertIn("pods/portforward", payload_text)
        self.assertNotIn("ClusterRole", payload_text)
        self.assertNotIn("Secret", payload_text)
        self.assertNotIn("nodes", payload_text)
        self.assertNotIn("kubeconfig", context["manifest_yaml"].lower())
        self.assertNotIn("token", context["manifest_yaml"].lower())
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_session.restricted_context").exists())

    @override_settings(KUBERNETES_ADMIN_MODE_ENABLED=False)
    def test_global_admin_mode_kill_switch_blocks_restricted_context_without_deleting_session(self):
        user = self.create_user("k8s-context-admin-disabled")
        session = self.create_break_glass_session(user)
        self.client.force_login(user)

        response = self.post_context(session.session_id, {"include_manifest": True})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_mode_disabled")
        session.refresh_from_db()
        self.assertEqual(session.status, K8sAdminSession.STATUS_ACTIVE)
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_session.restricted_context_rejected").exists())

    def test_restricted_context_rejects_wildcard_namespace(self):
        user = self.create_user("k8s-context-wildcard")
        session = self.create_break_glass_session(user, namespace="", allowed_namespaces=["*"])
        self.client.force_login(user)

        response = self.post_context(session.session_id, {})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "restricted_context_namespace_required")
        self.assertFalse(K8sAuditEvent.objects.filter(action="k8s.admin_session.restricted_context").exists())

    def test_restricted_context_validation_fails_closed_for_secret_or_cluster_scoped_rules(self):
        user = self.create_user("k8s-context-validation")
        session = self.create_break_glass_session(user)
        context = build_restricted_kube_context_for_session(session=session)
        bundle = {
            "namespace": context["namespace"],
            "service_account_name": context["service_account_name"],
            "role_name": context["role_name"],
            "manifests": [
                {"kind": "ClusterRole", "metadata": {"name": "bad", "namespace": context["namespace"]}, "rules": []},
                {
                    "kind": "ServiceAccount",
                    "metadata": {"name": context["service_account_name"], "namespace": context["namespace"]},
                },
                {
                    "kind": "Role",
                    "metadata": {"name": context["role_name"], "namespace": context["namespace"]},
                    "rules": [{"apiGroups": [""], "resources": ["secrets"], "verbs": ["get", "delete"]}],
                },
                {
                    "kind": "RoleBinding",
                    "metadata": {"name": context["binding_name"], "namespace": context["namespace"]},
                    "subjects": [
                        {
                            "kind": "ServiceAccount",
                            "name": context["service_account_name"],
                            "namespace": context["namespace"],
                        }
                    ],
                    "roleRef": {"kind": "Role", "name": context["role_name"]},
                },
            ],
        }

        validation = validate_restricted_kube_context_bundle(bundle)

        self.assertEqual(validation["status"], "missing")
        self.assertIn("cluster_scoped_rbac_forbidden", validation["errors"])
        self.assertTrue(any("denied_resources:secrets" in item for item in validation["errors"]))
        self.assertTrue(any("base_write_verbs:delete" in item for item in validation["errors"]))
