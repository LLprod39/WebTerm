import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_node_maintenance import run_node_maintenance_action
from kubernetes_ops.services.admin_resources import AdminResourceError


class KubernetesOpsAdminNodeMaintenanceGuardTests(TestCase):
    def create_user(self, username: str, *, grant_kubernetes: bool = True, grant_break_glass: bool = False) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        if grant_kubernetes:
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
            name="stage-kz-1",
            environment="stage",
            rancher_provider=self.provider,
            rancher_cluster_id="c-stage",
        )

    def create_break_glass_session(self, user: User, **kwargs) -> K8sAdminSession:
        defaults = {
            "user": user,
            "username_snapshot": user.username,
            "cluster": self.cluster,
            "mode": K8sAdminSession.MODE_BREAK_GLASS,
            "status": K8sAdminSession.STATUS_ACTIVE,
            "risk_tier": K8sAdminSession.RISK_CRITICAL,
            "allowed_verbs": ["get", "list", "watch", "logs", "yaml", "cordon", "uncordon", "drain"],
            "allowed_kinds": ["node"],
            "allowed_namespaces": ["*"],
            "reason": "node maintenance after incident approval",
            "approval_ref": "INC-2026-NODE-MAINT",
            "approved_by": user,
            "approved_at": timezone.now(),
            "expires_at": timezone.now() + timedelta(minutes=15),
        }
        defaults.update(kwargs)
        return K8sAdminSession.objects.create(**defaults)

    def node_response(self, *, unschedulable: bool) -> dict:
        return {
            "apiVersion": "v1",
            "kind": "Node",
            "metadata": {"name": "worker-1", "resourceVersion": "42", "labels": {"token": "raw-node-token"}},
            "spec": {"unschedulable": unschedulable},
        }

    def post_action(self, action: str, payload: dict):
        return self.client.post(
            reverse(f"api_kubernetes_admin_node_{action}", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
            data=json.dumps(payload),
            content_type="application/json",
        )

    @override_settings(KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED=True)
    def test_node_maintenance_requires_approved_break_glass_before_provider_or_action(self):
        user = self.create_user("k8s-node-maint-unapproved", grant_break_glass=True)
        session = self.create_break_glass_session(user, approval_ref="", approved_by=None, approved_at=None)

        with self.assertRaises(AdminResourceError) as denied:
            run_node_maintenance_action(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                action="cordon",
                node_name="worker-1",
                reason="cordon node",
                transport=lambda *args, **kwargs: self.fail("provider must not be called"),
            )

        self.assertEqual(denied.exception.code, "admin_session_approval_required")
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED=True)
    def test_node_maintenance_respects_verb_and_node_scope(self):
        user = self.create_user("k8s-node-maint-scope", grant_break_glass=True)
        session_without_verb = self.create_break_glass_session(
            user, allowed_verbs=["get", "list"], allowed_kinds=["node"]
        )
        session_without_kind = self.create_break_glass_session(user, allowed_verbs=["cordon"], allowed_kinds=["pod"])

        with self.assertRaises(AdminResourceError) as verb_denied:
            run_node_maintenance_action(
                user=user,
                session_id=str(session_without_verb.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                action="cordon",
                node_name="worker-1",
                reason="cordon node",
            )
        with self.assertRaises(AdminResourceError) as kind_denied:
            run_node_maintenance_action(
                user=user,
                session_id=str(session_without_kind.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                action="cordon",
                node_name="worker-1",
                reason="cordon node",
            )

        self.assertEqual(verb_denied.exception.code, "admin_session_verb_denied")
        self.assertEqual(kind_denied.exception.code, "admin_session_kind_denied")
        self.assertFalse(K8sAdminAction.objects.exists())
