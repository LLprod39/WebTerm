from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_action_review_readiness import build_admin_action_post_review_report


class KubernetesOpsAdminActionReviewReadinessTests(TestCase):
    def create_user(self, username: str) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        return user

    def setUp(self):
        self.user = self.create_user("k8s-action-review-readiness")
        self.provider = K8sProvider.objects.create(
            name="rancher-action-review-readiness",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            auth_mode=K8sProvider.AUTH_NONE,
        )
        self.cluster = K8sCluster.objects.create(
            name="action-review-readiness",
            environment="prod",
            rancher_provider=self.provider,
        )
        self.session = K8sAdminSession.objects.create(
            user=self.user,
            username_snapshot=self.user.username,
            cluster=self.cluster,
            mode=K8sAdminSession.MODE_WRITE,
            status=K8sAdminSession.STATUS_ACTIVE,
            risk_tier=K8sAdminSession.RISK_HIGH,
            allowed_verbs=["get", "apply", "patch", "delete"],
            allowed_kinds=["Deployment"],
            allowed_namespaces=["payments"],
            reason="review readiness",
            expires_at=timezone.now() + timedelta(minutes=30),
        )

    def create_action(self, **kwargs) -> K8sAdminAction:
        defaults = {
            "session": self.session,
            "user": self.user,
            "username_snapshot": self.user.username,
            "cluster": self.cluster,
            "namespace": "payments",
            "resource_api_version": "apps/v1",
            "resource_kind": "Deployment",
            "resource_name": "payments-api",
            "verb": K8sAdminAction.VERB_APPLY,
            "status": K8sAdminAction.STATUS_COMPLETED,
            "response_summary": {},
        }
        defaults.update(kwargs)
        return K8sAdminAction.objects.create(**defaults)

    def test_admin_action_post_review_report_counts_pending_review_queue(self):
        pending = self.create_action(verb=K8sAdminAction.VERB_APPLY, status=K8sAdminAction.STATUS_COMPLETED)
        self.create_action(
            verb=K8sAdminAction.VERB_DELETE,
            status=K8sAdminAction.STATUS_COMPLETED,
            response_summary={"post_review": {"outcome": "verified", "summary": "checked"}},
        )
        self.create_action(verb=K8sAdminAction.VERB_PATCH, status=K8sAdminAction.STATUS_PLANNED)
        self.create_action(verb=K8sAdminAction.VERB_GET, status=K8sAdminAction.STATUS_COMPLETED)

        report = build_admin_action_post_review_report()

        self.assertEqual(report["status"], "manual")
        self.assertEqual(report["summary"]["pending"], 1)
        self.assertEqual(report["summary"]["completed"], 1)
        self.assertEqual(report["summary"]["not_ready"], 1)
        self.assertEqual(report["summary"]["none"], 1)
        self.assertEqual(report["pending_url"], "/api/kubernetes/admin/actions/?all=1&post_review_status=pending")
        self.assertEqual(report["pending_actions"][0]["action_id"], str(pending.action_id))
        self.assertEqual(report["pending_actions"][0]["verb"], K8sAdminAction.VERB_APPLY)

    def test_readiness_exposes_admin_action_post_review_gate(self):
        self.create_action(verb=K8sAdminAction.VERB_APPLY, status=K8sAdminAction.STATUS_COMPLETED)
        self.client.force_login(self.user)

        response = self.client.get(reverse("api_kubernetes_readiness"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        checks = {item["id"]: item for item in payload["checks"]}
        self.assertEqual(checks["admin_action_post_review"]["status"], "manual")
        self.assertFalse(checks["admin_action_post_review"]["required"])
        self.assertEqual(payload["admin_action_post_review"]["status"], "manual")
        self.assertEqual(payload["admin_action_post_review"]["summary"]["pending"], 1)
