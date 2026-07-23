from __future__ import annotations

import io
import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import (
    K8sAdminAction,
    K8sAdminRecording,
    K8sAdminRecordingEvent,
    K8sAdminSession,
    K8sCluster,
    K8sProvider,
)
from kubernetes_ops.services.admin_recording import cleanup_interactive_recordings, recording_retention_inventory


class KubernetesOpsAdminRecordingEvidenceTests(TestCase):
    def create_user(self, username: str, *, grant_kubernetes: bool = True, is_staff: bool = False) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=is_staff)
        if grant_kubernetes:
            UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        return user

    def setUp(self):
        self.provider = K8sProvider.objects.create(
            name="rancher-recordings",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            auth_mode=K8sProvider.AUTH_NONE,
        )
        self.cluster = K8sCluster.objects.create(
            name="recordings-prod",
            environment="prod",
            rancher_provider=self.provider,
            rancher_cluster_id="c-recordings",
        )

    def create_session(self, user: User) -> K8sAdminSession:
        return K8sAdminSession.objects.create(
            user=user,
            username_snapshot=user.username,
            cluster=self.cluster,
            mode=K8sAdminSession.MODE_BREAK_GLASS,
            status=K8sAdminSession.STATUS_ACTIVE,
            risk_tier=K8sAdminSession.RISK_CRITICAL,
            allowed_verbs=["exec"],
            allowed_kinds=["pod"],
            allowed_namespaces=["payments"],
            reason="inspect recording evidence",
            expires_at=timezone.now() + timedelta(minutes=30),
        )

    def create_action(self, user: User, session: K8sAdminSession) -> K8sAdminAction:
        return K8sAdminAction.objects.create(
            session=session,
            user=user,
            username_snapshot=user.username,
            cluster=self.cluster,
            namespace="payments",
            resource_api_version="v1",
            resource_kind="Pod",
            resource_name="payments-api",
            verb=K8sAdminAction.VERB_EXEC,
            status=K8sAdminAction.STATUS_COMPLETED,
            request_payload_sanitized={"command": "env", "token": "raw-action-token"},
            response_summary={"exit_code": 0, "password": "raw-action-password"},
        )

    def create_recording(
        self, user: User, session: K8sAdminSession, action: K8sAdminAction, **kwargs
    ) -> K8sAdminRecording:
        now = timezone.now()
        defaults = {
            "session": session,
            "action": action,
            "user": user,
            "username_snapshot": user.username,
            "cluster": self.cluster,
            "namespace": "payments",
            "resource_kind": "Pod",
            "resource_name": "payments-api",
            "operation": K8sAdminRecording.OP_EXEC,
            "status": K8sAdminRecording.STATUS_COMPLETED,
            "mode": "transcript_required",
            "transcript_required": True,
            "transcript_stored": True,
            "payload_stored": False,
            "metadata_delete_after": now + timedelta(days=365),
            "transcript_delete_after": now + timedelta(days=30),
            "policy_snapshot": {"enabled": True, "authorization": "Bearer raw-policy-token"},
            "summary": {"close_reason": "provider_eof", "secret": "raw-summary-secret"},
            "started_at": now,
            "finished_at": now,
        }
        defaults.update(kwargs)
        return K8sAdminRecording.objects.create(**defaults)

    def test_owner_lists_and_reads_sanitized_recording_events(self):
        user = self.create_user("k8s-recording-owner")
        session = self.create_session(user)
        action = self.create_action(user, session)
        recording = self.create_recording(user, session, action)
        K8sAdminRecordingEvent.objects.create(
            recording=recording,
            sequence=1,
            stream=K8sAdminRecordingEvent.STREAM_STDOUT,
            data="TOKEN=raw-event-token",
            original_length=21,
            stored_length=21,
            redacted=False,
            metadata={"password": "raw-event-password"},
        )
        self.client.force_login(user)

        list_response = self.client.get(
            reverse("api_kubernetes_admin_recordings"), {"session_id": str(session.session_id), "limit": "10"}
        )
        detail_response = self.client.get(
            reverse("api_kubernetes_admin_recording_detail", kwargs={"recording_id": recording.recording_id})
        )

        self.assertEqual(list_response.status_code, 200)
        list_payload = list_response.json()
        self.assertEqual(list_payload["count"], 1)
        self.assertEqual(list_payload["recordings"][0]["id"], str(recording.recording_id))
        self.assertEqual(list_payload["recordings"][0]["policy_snapshot"]["authorization"], "[redacted]")
        self.assertNotIn("events", list_payload["recordings"][0])
        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()["recording"]
        self.assertEqual(detail["events"][0]["data"], "TOKEN=[redacted]")
        self.assertEqual(detail["events"][0]["metadata"]["password"], "[redacted]")
        encoded = json.dumps({"list": list_payload, "detail": detail})
        self.assertNotIn("raw-event-token", encoded)
        self.assertNotIn("raw-event-password", encoded)
        self.assertNotIn("raw-policy-token", encoded)
        self.assertNotIn("raw-summary-secret", encoded)

    def test_non_owner_cannot_read_other_users_recordings(self):
        owner = self.create_user("k8s-recording-private-owner")
        session = self.create_session(owner)
        action = self.create_action(owner, session)
        recording = self.create_recording(owner, session, action)
        other = self.create_user("k8s-recording-private-other")
        self.client.force_login(other)

        list_response = self.client.get(
            reverse("api_kubernetes_admin_recordings"), {"session_id": str(session.session_id)}
        )
        detail_response = self.client.get(
            reverse("api_kubernetes_admin_recording_detail", kwargs={"recording_id": recording.recording_id})
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["recordings"], [])
        self.assertEqual(detail_response.status_code, 404)
        self.assertEqual(detail_response.json()["code"], "admin_recording_not_found")

    def test_staff_can_list_all_recordings_with_filters(self):
        owner = self.create_user("k8s-recording-staff-owner")
        session = self.create_session(owner)
        action = self.create_action(owner, session)
        kept = self.create_recording(owner, session, action, operation=K8sAdminRecording.OP_EXEC)
        self.create_recording(
            owner,
            session,
            action,
            operation=K8sAdminRecording.OP_PORT_FORWARD,
            transcript_required=False,
            transcript_stored=False,
        )
        staff = self.create_user("k8s-recording-staff", is_staff=True)
        self.client.force_login(staff)

        response = self.client.get(
            reverse("api_kubernetes_admin_recordings"),
            {
                "all": "1",
                "cluster_id": f"cluster_{self.cluster.id}",
                "operation": K8sAdminRecording.OP_EXEC,
                "limit": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["recordings"][0]["id"], str(kept.recording_id))

    def test_recordings_require_kubernetes_feature(self):
        user = self.create_user("k8s-recording-no-feature", grant_kubernetes=False)
        self.client.force_login(user)

        response = self.client.get(reverse("api_kubernetes_admin_recordings"))

        self.assertEqual(response.status_code, 403)

    def test_recording_retention_inventory_and_cleanup(self):
        user = self.create_user("k8s-recording-retention")
        session = self.create_session(user)
        action = self.create_action(user, session)
        now = timezone.now()
        metadata_expired = self.create_recording(
            user,
            session,
            action,
            metadata_delete_after=now - timedelta(days=1),
            transcript_delete_after=now - timedelta(days=1),
        )
        transcript_expired = self.create_recording(
            user,
            session,
            action,
            metadata_delete_after=now + timedelta(days=10),
            transcript_delete_after=now - timedelta(days=1),
        )
        recent = self.create_recording(
            user,
            session,
            action,
            metadata_delete_after=now + timedelta(days=10),
            transcript_delete_after=now + timedelta(days=10),
        )
        for recording in (metadata_expired, transcript_expired, recent):
            K8sAdminRecordingEvent.objects.create(
                recording=recording, sequence=1, stream=K8sAdminRecordingEvent.STREAM_STDOUT, data="ok"
            )

        inventory = recording_retention_inventory(now=now)
        self.assertEqual(inventory["summary"]["metadata_expired_count"], 1)
        self.assertEqual(inventory["summary"]["transcript_expired_count"], 1)
        self.assertEqual(inventory["summary"]["transcript_event_expired_count"], 1)

        dry_run = cleanup_interactive_recordings(now=now, dry_run=True, batch_size=1)
        self.assertEqual(dry_run["metadata_deleted_count"], 0)
        self.assertEqual(dry_run["transcript_event_deleted_count"], 0)
        self.assertEqual(K8sAdminRecording.objects.count(), 3)
        self.assertEqual(K8sAdminRecordingEvent.objects.count(), 3)

        applied = cleanup_interactive_recordings(now=now, dry_run=False, batch_size=1)
        self.assertEqual(applied["metadata_deleted_count"], 1)
        self.assertEqual(applied["transcript_event_deleted_count"], 1)
        self.assertFalse(K8sAdminRecording.objects.filter(id=metadata_expired.id).exists())
        transcript_expired.refresh_from_db()
        self.assertFalse(transcript_expired.transcript_stored)
        self.assertFalse(K8sAdminRecordingEvent.objects.filter(recording=transcript_expired).exists())
        self.assertTrue(K8sAdminRecordingEvent.objects.filter(recording=recent).exists())

    def test_recording_cleanup_command_defaults_to_dry_run_and_apply_deletes(self):
        user = self.create_user("k8s-recording-command")
        session = self.create_session(user)
        action = self.create_action(user, session)
        recording = self.create_recording(
            user, session, action, metadata_delete_after=timezone.now() - timedelta(days=1)
        )
        dry_run_out = io.StringIO()

        call_command("cleanup_kubernetes_admin_recordings", stdout=dry_run_out)

        self.assertIn("dry_run=True", dry_run_out.getvalue())
        self.assertTrue(K8sAdminRecording.objects.filter(id=recording.id).exists())

        apply_out = io.StringIO()
        call_command("cleanup_kubernetes_admin_recordings", "--apply", stdout=apply_out)

        self.assertIn("metadata_deleted=1", apply_out.getvalue())
        self.assertFalse(K8sAdminRecording.objects.filter(id=recording.id).exists())
