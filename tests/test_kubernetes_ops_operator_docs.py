from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.services.operator_docs import (
    OPERATOR_RUNBOOK_RELATIVE_PATH,
    REQUIRED_RUNBOOK_MARKERS,
    build_kubernetes_operator_docs_report,
)


class KubernetesOpsOperatorDocsTests(TestCase):
    def create_user(self, username: str) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        return user

    def test_operator_runbook_contains_required_sections(self):
        report = build_kubernetes_operator_docs_report()

        self.assertEqual(report["status"], "ready", report["missing_markers"])
        self.assertTrue(report["exists"])
        self.assertEqual(report["runbook_path"], OPERATOR_RUNBOOK_RELATIVE_PATH)
        self.assertFalse(report["missing_markers"])
        for marker in REQUIRED_RUNBOOK_MARKERS:
            self.assertIn(marker, report["required_markers"])
        self.assertIn("provider_outage_dr", report["topics"])
        self.assertIn("admin_action_post_review", report["topics"])
        self.assertIn("admin_interactive_transport", report["topics"])
        self.assertIn("admin_recording_retention", report["topics"])
        self.assertIn("rollback_disablement", report["topics"])

    def test_operator_docs_report_fails_closed_for_missing_runbook(self):
        missing_root = Path("/tmp/webterm-missing-kubernetes-docs")

        report = build_kubernetes_operator_docs_report(base_dir=missing_root)

        self.assertEqual(report["status"], "missing")
        self.assertFalse(report["exists"])
        self.assertTrue(report["missing_markers"])

    def test_readiness_exposes_operator_docs_gate(self):
        user = self.create_user("k8s-operator-docs")
        self.client.force_login(user)

        response = self.client.get(reverse("api_kubernetes_readiness"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        checks = {item["id"]: item for item in payload["checks"]}
        self.assertEqual(checks["operator_docs"]["status"], "ready")
        self.assertFalse(checks["operator_docs"]["required"])
        self.assertEqual(payload["operator_docs"]["status"], "ready")
        self.assertEqual(payload["operator_docs"]["runbook_path"], OPERATOR_RUNBOOK_RELATIVE_PATH)
