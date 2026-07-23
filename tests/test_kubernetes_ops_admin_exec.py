from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
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
from kubernetes_ops.services.admin_exec import prepare_kubernetes_exec_bridge
from kubernetes_ops.services.admin_exec_stream import prepare_kubernetes_exec_stream_context
from kubernetes_ops.services.admin_resources import AdminResourceError


class KubernetesOpsAdminExecTests(TestCase):
    def create_user(
        self,
        username: str,
        *,
        grant_kubernetes: bool = True,
        grant_break_glass: bool = True,
    ) -> User:
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
            "reason": "incident inspection",
            "approval_ref": "INC-2026-0001",
            "approved_by": user,
            "approved_at": timezone.now(),
            "allowed_verbs": ["get", "list", "watch", "logs", "yaml", "exec", "port_forward"],
            "allowed_kinds": ["pod"],
            "allowed_namespaces": ["payments"],
            "expires_at": timezone.now() + timedelta(minutes=15),
        }
        defaults.update(kwargs)
        return K8sAdminSession.objects.create(**defaults)

    def test_exec_bridge_is_disabled_by_default_before_action_or_audit(self):
        user = self.create_user("k8s-exec-disabled")
        session = self.create_break_glass_session(user)

        with self.assertRaises(AdminResourceError) as raised:
            prepare_kubernetes_exec_bridge(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                namespace="payments",
                pod_name="payments-api-abc123",
                command="/bin/sh",
                reason="inspect pod state",
            )

        self.assertEqual(raised.exception.code, "native_exec_disabled")
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertFalse(K8sAuditEvent.objects.exists())

    @override_settings(KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True)
    def test_exec_bridge_validates_break_glass_and_records_metadata_only_blocked_action(self):
        user = self.create_user("k8s-exec-valid")
        session = self.create_break_glass_session(user)

        envelope = prepare_kubernetes_exec_bridge(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            namespace="payments",
            pod_name="payments-api-abc123",
            container="api",
            command=["env", "TOKEN=raw-secret"],
            reason="inspect pod env shape",
            tty=True,
            stdin=True,
            stream_id="exec-stream-1",
        )

        self.assertTrue(envelope["success"])
        self.assertEqual(envelope["status"], K8sAdminAction.STATUS_EXECUTION_BLOCKED)
        self.assertFalse(envelope["policy"]["provider_streaming_enabled"])
        self.assertFalse(envelope["policy"]["records_transcript"])
        self.assertEqual(envelope["command"]["executable"], "env")
        action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_EXEC)
        self.assertEqual(action.status, K8sAdminAction.STATUS_EXECUTION_BLOCKED)
        self.assertEqual(action.resource_kind, "Pod")
        recording = K8sAdminRecording.objects.get(action=action)
        self.assertEqual(recording.status, K8sAdminRecording.STATUS_BLOCKED)
        self.assertEqual(recording.operation, K8sAdminRecording.OP_EXEC)
        self.assertTrue(recording.transcript_required)
        self.assertFalse(recording.transcript_stored)
        self.assertFalse(recording.payload_stored)
        self.assertIn("recording", envelope)
        self.assertEqual(envelope["recording"]["id"], str(recording.recording_id))
        self.assertNotIn("raw-secret", str(action.request_payload_sanitized))
        audit = K8sAuditEvent.objects.get(action="k8s.admin_stream.exec_blocked")
        self.assertEqual(audit.payload["stream_id"], "exec-stream-1")
        self.assertEqual(audit.payload["recording_id"], str(recording.recording_id))
        self.assertNotIn("raw-secret", str(audit.payload))

    @override_settings(KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True)
    def test_exec_stream_requires_separate_streaming_flag_before_action(self):
        user = self.create_user("k8s-exec-stream-disabled")
        session = self.create_break_glass_session(user)

        with self.assertRaises(AdminResourceError) as raised:
            prepare_kubernetes_exec_stream_context(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                namespace="payments",
                pod_name="payments-api-abc123",
                command=["env"],
                reason="inspect pod env shape",
            )

        self.assertEqual(raised.exception.code, "exec_streaming_disabled")
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertFalse(K8sAuditEvent.objects.exists())

    @override_settings(
        KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True,
        KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=True,
        KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED=True,
    )
    def test_exec_stream_context_records_started_metadata_only_action(self):
        self.provider.labels = {
            "pod_exec_stream_path_template": "/k8s/clusters/{cluster_id}/api/v1/namespaces/{namespace}/pods/{pod_name}/exec"
        }
        self.provider.save(update_fields=["labels"])
        user = self.create_user("k8s-exec-stream-context")
        session = self.create_break_glass_session(user)

        envelope = prepare_kubernetes_exec_stream_context(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            namespace="payments",
            pod_name="payments-api-abc123",
            container="api",
            command=["env", "TOKEN=raw-secret"],
            reason="inspect pod env shape",
            stream_id="exec-stream-context",
            timeout_seconds=4,
        )

        self.assertEqual(envelope["status"], K8sAdminAction.STATUS_PLANNED)
        self.assertTrue(envelope["policy"]["provider_streaming_enabled"])
        self.assertFalse(envelope["policy"]["records_transcript"])
        self.assertTrue(envelope["policy"]["recording_policy"]["enabled"])
        self.assertEqual(
            envelope["path"], "/k8s/clusters/c-prod/api/v1/namespaces/payments/pods/payments-api-abc123/exec"
        )
        self.assertEqual(envelope["_timeout_seconds"], 4)
        action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_EXEC)
        self.assertEqual(action.status, K8sAdminAction.STATUS_PLANNED)
        self.assertTrue(action.response_summary["recording_policy"]["enabled"])
        recording = K8sAdminRecording.objects.get(action=action)
        self.assertEqual(recording.status, K8sAdminRecording.STATUS_ACTIVE)
        self.assertEqual(recording.operation, K8sAdminRecording.OP_EXEC)
        self.assertTrue(recording.policy_snapshot["enabled"])
        self.assertFalse(recording.transcript_stored)
        self.assertEqual(envelope["recording"]["id"], str(recording.recording_id))
        self.assertNotIn("raw-secret", str(action.request_payload_sanitized))
        audit = K8sAuditEvent.objects.get(action="k8s.admin_stream.exec_started")
        self.assertTrue(audit.payload["recording_policy"]["enabled"])
        self.assertEqual(audit.payload["recording_id"], str(recording.recording_id))
        self.assertNotIn("raw-secret", str(audit.payload))

    @override_settings(KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True)
    def test_exec_bridge_requires_break_glass_session_mode(self):
        user = self.create_user("k8s-exec-write-session")
        session = self.create_break_glass_session(
            user,
            mode=K8sAdminSession.MODE_WRITE,
            risk_tier=K8sAdminSession.RISK_HIGH,
        )

        with self.assertRaises(AdminResourceError) as raised:
            prepare_kubernetes_exec_bridge(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                namespace="payments",
                pod_name="payments-api-abc123",
                command="/bin/sh",
                reason="inspect pod state",
            )

        self.assertEqual(raised.exception.code, "break_glass_session_required")
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True)
    def test_exec_bridge_requires_approved_break_glass_session_before_action(self):
        user = self.create_user("k8s-exec-unapproved")
        session = self.create_break_glass_session(user, approval_ref="", approved_by=None, approved_at=None)

        with self.assertRaises(AdminResourceError) as raised:
            prepare_kubernetes_exec_bridge(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                namespace="payments",
                pod_name="payments-api-abc123",
                command="/bin/sh",
                reason="inspect pod state",
            )

        self.assertEqual(raised.exception.code, "admin_session_approval_required")
        self.assertEqual(raised.exception.payload["action"], K8sAdminAction.VERB_EXEC)
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True)
    def test_exec_bridge_blocks_protected_namespace_before_session_action(self):
        user = self.create_user("k8s-exec-protected")
        session = self.create_break_glass_session(user, allowed_namespaces=["*"])

        with self.assertRaises(AdminResourceError) as raised:
            prepare_kubernetes_exec_bridge(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                namespace="kube-system",
                pod_name="coredns-abc123",
                command="/bin/sh",
                reason="inspect system pod",
            )

        self.assertEqual(raised.exception.code, "exec_namespace_protected")
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True)
    def test_exec_bridge_blocks_inline_shell_and_denied_commands(self):
        user = self.create_user("k8s-exec-command-policy")
        session = self.create_break_glass_session(user)

        for command, code in [
            ("sh -c 'cat /var/run/secrets/kubernetes.io/serviceaccount/token'", "exec_shell_inline_denied"),
            ("kubectl get secrets", "exec_command_denied"),
        ]:
            with self.subTest(command=command):
                with self.assertRaises(AdminResourceError) as raised:
                    prepare_kubernetes_exec_bridge(
                        user=user,
                        session_id=str(session.session_id),
                        cluster_id=f"cluster_{self.cluster.id}",
                        namespace="payments",
                        pod_name="payments-api-abc123",
                        command=command,
                        reason="inspect pod state",
                    )
                self.assertEqual(raised.exception.code, code)

        self.assertFalse(K8sAdminAction.objects.exists())

    def test_exec_websocket_route_is_registered(self):
        from web_ui.routing import websocket_urlpatterns

        patterns = [str(pattern.pattern) for pattern in websocket_urlpatterns]
        self.assertIn("ws/kubernetes/admin/exec/<uuid:session_id>/", patterns)
