from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminRecording, K8sAdminRecordingEvent, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_recording_readiness import build_admin_recording_retention_report


class KubernetesOpsAdminRecordingReadinessTests(TestCase):
    def create_user(self, username: str) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        return user

    def test_recording_retention_report_exposes_cleanup_commands_and_counts(self):
        user = self.create_user("k8s-recording-readiness")
        provider = K8sProvider.objects.create(name="rancher-recording-readiness", kind=K8sProvider.KIND_RANCHER, base_url="https://rancher.example.test", auth_mode=K8sProvider.AUTH_NONE)
        cluster = K8sCluster.objects.create(name="recording-readiness", environment="prod", rancher_provider=provider)
        session = K8sAdminSession.objects.create(
            user=user,
            username_snapshot=user.username,
            cluster=cluster,
            mode=K8sAdminSession.MODE_BREAK_GLASS,
            status=K8sAdminSession.STATUS_ACTIVE,
            risk_tier=K8sAdminSession.RISK_CRITICAL,
            allowed_verbs=["exec"],
            allowed_kinds=["pod"],
            allowed_namespaces=["payments"],
            reason="readiness",
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        action = K8sAdminAction.objects.create(
            session=session,
            user=user,
            username_snapshot=user.username,
            cluster=cluster,
            namespace="payments",
            resource_kind="Pod",
            resource_name="payments-api",
            verb=K8sAdminAction.VERB_EXEC,
            status=K8sAdminAction.STATUS_COMPLETED,
        )
        recording = K8sAdminRecording.objects.create(
            session=session,
            action=action,
            user=user,
            username_snapshot=user.username,
            cluster=cluster,
            namespace="payments",
            resource_kind="Pod",
            resource_name="payments-api",
            operation=K8sAdminRecording.OP_EXEC,
            status=K8sAdminRecording.STATUS_COMPLETED,
            mode="transcript_required",
            transcript_required=True,
            transcript_stored=True,
            metadata_delete_after=timezone.now() + timedelta(days=1),
            transcript_delete_after=timezone.now() - timedelta(days=1),
        )
        K8sAdminRecordingEvent.objects.create(recording=recording, sequence=1, stream=K8sAdminRecordingEvent.STREAM_STDOUT, data="TOKEN=raw-event-token")

        report = build_admin_recording_retention_report()

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["command"], "python manage.py cleanup_kubernetes_admin_recordings --apply")
        self.assertEqual(report["dry_run_command"], "python manage.py cleanup_kubernetes_admin_recordings")
        self.assertEqual(report["inventory_command"], "python manage.py cleanup_kubernetes_admin_recordings --inventory")
        self.assertEqual(report["summary"]["transcript_expired_count"], 1)
        self.assertEqual(report["summary"]["transcript_event_expired_count"], 1)
        self.assertNotIn("raw-event-token", str(report))

    def test_readiness_exposes_admin_recording_retention_gate(self):
        user = self.create_user("k8s-recording-readiness-api")
        self.client.force_login(user)

        response = self.client.get(reverse("api_kubernetes_readiness"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        checks = {item["id"]: item for item in payload["checks"]}
        self.assertEqual(checks["admin_recording_retention"]["status"], "ready")
        self.assertFalse(checks["admin_recording_retention"]["required"])
        self.assertEqual(payload["admin_recording_retention"]["status"], "ready")
        self.assertEqual(payload["admin_recording_retention"]["command"], "python manage.py cleanup_kubernetes_admin_recordings --apply")
