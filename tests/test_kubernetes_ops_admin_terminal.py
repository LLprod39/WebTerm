import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import (
    K8sAdminAction,
    K8sAdminRecording,
    K8sAdminSession,
    K8sAuditEvent,
    K8sCluster,
    K8sProvider,
)
from kubernetes_ops.services.admin_terminal import CLUSTER_TERMINAL_VERB


class KubernetesOpsAdminTerminalTests(TestCase):
    def create_user(self, username: str, *, grant_break_glass: bool = True) -> User:
        user = User.objects.create_user(username=username, password="password-123")
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
            "reason": "incident terminal inspection",
            "approval_ref": "INC-2026-TERM",
            "approved_by": user,
            "approved_at": timezone.now(),
            "allowed_verbs": ["get", "list", "watch", "logs", "yaml", "exec", "port_forward"],
            "allowed_kinds": ["pod"],
            "allowed_namespaces": ["payments"],
            "expires_at": timezone.now() + timedelta(minutes=15),
        }
        defaults.update(kwargs)
        return K8sAdminSession.objects.create(**defaults)

    def post_start(self, session_id, payload: dict):
        return self.client.post(
            reverse("api_kubernetes_admin_terminal_start", kwargs={"session_id": session_id}),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def post_stop(self, session_id, payload: dict):
        return self.client.post(
            reverse("api_kubernetes_admin_terminal_stop", kwargs={"session_id": session_id}),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_cluster_terminal_start_requires_approved_break_glass_before_action(self):
        user = self.create_user("k8s-terminal-unapproved")
        session = self.create_break_glass_session(user, approval_ref="", approved_by=None, approved_at=None)
        self.client.force_login(user)

        response = self.post_start(session.session_id, {"reason": "inspect namespace"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_session_approval_required")
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertFalse(K8sAuditEvent.objects.filter(action="k8s.admin_terminal.start_blocked").exists())

    def test_cluster_terminal_start_records_metadata_only_blocked_action(self):
        user = self.create_user("k8s-terminal-start")
        session = self.create_break_glass_session(user)
        self.client.force_login(user)

        response = self.post_start(
            session.session_id, {"reason": "inspect namespace", "include_restricted_context": True}
        )

        self.assertEqual(response.status_code, 200)
        terminal = response.json()["terminal"]
        payload_text = json.dumps(terminal)
        self.assertEqual(terminal["status"], K8sAdminAction.STATUS_EXECUTION_BLOCKED)
        self.assertEqual(terminal["blocked_reason"], "cluster_terminal_disabled")
        self.assertFalse(terminal["terminal_started"])
        self.assertFalse(terminal["transport_started"])
        self.assertFalse(terminal["policy"]["cluster_terminal_enabled"])
        self.assertTrue(terminal["recording_policy"]["required"])
        self.assertFalse(terminal["recording_policy"]["enabled"])
        self.assertEqual(terminal["restricted_context"]["namespace"], "payments")
        self.assertNotIn("kubeconfig", terminal["restricted_context"]["manifest_yaml"].lower())
        self.assertNotIn("token", terminal["restricted_context"]["manifest_yaml"].lower())
        self.assertNotIn("Secret", payload_text)
        action = K8sAdminAction.objects.get(verb=CLUSTER_TERMINAL_VERB)
        self.assertEqual(action.status, K8sAdminAction.STATUS_EXECUTION_BLOCKED)
        self.assertEqual(action.response_summary["blocked_reason"], "cluster_terminal_disabled")
        self.assertFalse(action.response_summary["payload_stored"])
        recording = K8sAdminRecording.objects.get(action=action)
        self.assertEqual(recording.status, K8sAdminRecording.STATUS_BLOCKED)
        self.assertEqual(recording.operation, K8sAdminRecording.OP_CLUSTER_TERMINAL)
        self.assertTrue(recording.transcript_required)
        self.assertFalse(recording.transcript_stored)
        self.assertFalse(recording.payload_stored)
        self.assertEqual(terminal["recording"]["id"], str(recording.recording_id))
        self.assertNotIn("Secret", json.dumps(recording.summary))
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_terminal.start_blocked").exists())

    @override_settings(KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED=True)
    def test_cluster_terminal_start_blocks_before_action_without_recording_flag(self):
        user = self.create_user("k8s-terminal-recording-required")
        session = self.create_break_glass_session(user)
        self.client.force_login(user)

        response = self.post_start(session.session_id, {"reason": "inspect namespace"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "cluster_terminal_recording_required")
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertFalse(K8sAuditEvent.objects.filter(action="k8s.admin_terminal.start_blocked").exists())

    @override_settings(
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED=True,
        KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED=True,
        KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF="",
    )
    def test_production_cluster_terminal_start_blocks_before_action_without_restricted_evidence(self):
        user = self.create_user("k8s-terminal-no-restricted-evidence")
        session = self.create_break_glass_session(user)
        self.client.force_login(user)

        response = self.post_start(session.session_id, {"reason": "inspect namespace"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "interactive_transport_prerequisites_required")
        self.assertIn("restricted_credential_evidence_required", response.json()["payload"]["blockers"])
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertFalse(K8sAuditEvent.objects.filter(action="k8s.admin_terminal.start_blocked").exists())

    @override_settings(
        KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED=True,
        KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED=True,
    )
    def test_cluster_terminal_start_blocks_before_action_without_provider_contract(self):
        user = self.create_user("k8s-terminal-no-provider-contract")
        session = self.create_break_glass_session(user)
        self.client.force_login(user)

        response = self.post_start(session.session_id, {"reason": "inspect namespace"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "interactive_transport_prerequisites_required")
        self.assertIn("provider_contract_required", response.json()["payload"]["blockers"])
        self.assertEqual(response.json()["payload"]["provider_contract"]["label"], "cluster_terminal_path_template")
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertFalse(K8sAuditEvent.objects.filter(action="k8s.admin_terminal.start_blocked").exists())

    @override_settings(
        KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED=True,
        KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED=True,
    )
    def test_cluster_terminal_start_stays_metadata_only_until_transport_exists(self):
        user = self.create_user("k8s-terminal-transport-not-implemented")
        session = self.create_break_glass_session(user)
        self.provider.labels = {
            "cluster_terminal_path_template": "/k8s/clusters/{cluster_id}/api/v1/namespaces/{namespace}/pods/webterm-terminal/exec"
        }
        self.provider.save(update_fields=["labels"])
        self.client.force_login(user)

        response = self.post_start(session.session_id, {"reason": "inspect namespace"})

        self.assertEqual(response.status_code, 200)
        terminal = response.json()["terminal"]
        self.assertEqual(terminal["blocked_reason"], "cluster_terminal_transport_not_implemented")
        self.assertTrue(terminal["policy"]["cluster_terminal_enabled"])
        self.assertTrue(terminal["policy"]["session_recording_enabled"])
        self.assertEqual(terminal["policy"]["provider_contract"]["status"], "ready")
        self.assertFalse(terminal["transport_started"])
        self.assertEqual(K8sAdminAction.objects.count(), 1)

    def test_cluster_terminal_stop_is_rejected_when_no_terminal_is_running_and_audited(self):
        user = self.create_user("k8s-terminal-stop")
        session = self.create_break_glass_session(user)
        self.client.force_login(user)

        response = self.post_stop(session.session_id, {"action_id": "not-started", "reason": "cleanup"})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "cluster_terminal_not_running")
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_terminal.stop_rejected").exists())
