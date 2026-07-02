from __future__ import annotations

import io
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from kubernetes_ops.models import K8sAuditEvent, K8sCluster
from kubernetes_ops.services.audit_retention import (
    MAX_AUDIT_RETENTION_DAYS,
    audit_retention_inventory,
    cleanup_kubernetes_audit_events,
    configured_audit_retention_days,
)


class KubernetesOpsAuditRetentionTests(TestCase):
    def test_configured_audit_retention_days_is_bounded(self):
        self.assertEqual(configured_audit_retention_days("bad"), 365)
        self.assertEqual(configured_audit_retention_days(0), 1)
        self.assertEqual(configured_audit_retention_days(99_999), MAX_AUDIT_RETENTION_DAYS)

    @override_settings(KUBERNETES_OPS_AUDIT_RETENTION_DAYS=30)
    def test_audit_retention_inventory_reports_expired_by_action(self):
        user = User.objects.create_user(username="k8s-retention-inventory", password="x")
        cluster = K8sCluster.objects.create(name="stage-webterm-ops")
        old = K8sAuditEvent.objects.create(user=user, username_snapshot=user.username, action="k8s.deeplink.open", cluster=cluster)
        recent = K8sAuditEvent.objects.create(user=user, username_snapshot=user.username, action="k8s.provider.probe", cluster=cluster)
        K8sAuditEvent.objects.filter(id=old.id).update(created_at=timezone.now() - timedelta(days=45))
        K8sAuditEvent.objects.filter(id=recent.id).update(created_at=timezone.now() - timedelta(days=5))

        result = audit_retention_inventory()

        self.assertEqual(result["retention_days"], 30)
        self.assertEqual(result["summary"]["expired_count"], 1)
        self.assertEqual(result["summary"]["retained_count"], 1)
        self.assertEqual(result["expired_by_action"], [{"action": "k8s.deeplink.open", "count": 1}])

    def test_audit_retention_cleanup_dry_run_preserves_rows(self):
        old = K8sAuditEvent.objects.create(action="k8s.provider.probe", payload={"secret": "not-returned"})
        K8sAuditEvent.objects.filter(id=old.id).update(created_at=timezone.now() - timedelta(days=400))

        result = cleanup_kubernetes_audit_events(retention_days=365, dry_run=True)

        self.assertEqual(result["expired_count"], 1)
        self.assertEqual(result["deleted_count"], 0)
        self.assertEqual(K8sAuditEvent.objects.count(), 1)
        self.assertNotIn("not-returned", str(result))

    def test_audit_retention_cleanup_apply_deletes_only_expired_rows(self):
        old = K8sAuditEvent.objects.create(action="k8s.provider.probe")
        recent = K8sAuditEvent.objects.create(action="k8s.pod.logs.snapshot")
        K8sAuditEvent.objects.filter(id=old.id).update(created_at=timezone.now() - timedelta(days=400))
        K8sAuditEvent.objects.filter(id=recent.id).update(created_at=timezone.now() - timedelta(days=1))

        result = cleanup_kubernetes_audit_events(retention_days=365, dry_run=False, batch_size=1)

        self.assertEqual(result["expired_count"], 1)
        self.assertEqual(result["deleted_count"], 1)
        self.assertFalse(K8sAuditEvent.objects.filter(id=old.id).exists())
        self.assertTrue(K8sAuditEvent.objects.filter(id=recent.id).exists())

    def test_cleanup_command_defaults_to_dry_run_and_apply_deletes(self):
        old = K8sAuditEvent.objects.create(action="k8s.provider.probe")
        K8sAuditEvent.objects.filter(id=old.id).update(created_at=timezone.now() - timedelta(days=400))
        dry_run_out = io.StringIO()

        call_command("cleanup_kubernetes_ops_audit", "--days", "365", stdout=dry_run_out)

        self.assertIn("dry_run=True", dry_run_out.getvalue())
        self.assertTrue(K8sAuditEvent.objects.filter(id=old.id).exists())

        apply_out = io.StringIO()
        call_command("cleanup_kubernetes_ops_audit", "--days", "365", "--apply", stdout=apply_out)

        self.assertIn("deleted=1", apply_out.getvalue())
        self.assertFalse(K8sAuditEvent.objects.filter(id=old.id).exists())
