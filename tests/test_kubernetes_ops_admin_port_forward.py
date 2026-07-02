from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminRecording, K8sAdminSession, K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_port_forward import prepare_kubernetes_port_forward_bridge
from kubernetes_ops.services.admin_port_forward_tunnel import prepare_kubernetes_port_forward_tunnel_context
from kubernetes_ops.services.admin_resources import AdminResourceError


class KubernetesOpsAdminPortForwardTests(TestCase):
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
            "approval_ref": "INC-2026-0002",
            "approved_by": user,
            "approved_at": timezone.now(),
            "allowed_verbs": ["get", "list", "watch", "logs", "yaml", "exec", "port_forward"],
            "allowed_kinds": ["service", "pod"],
            "allowed_namespaces": ["payments"],
            "expires_at": timezone.now() + timedelta(minutes=15),
        }
        defaults.update(kwargs)
        return K8sAdminSession.objects.create(**defaults)

    def test_port_forward_bridge_is_disabled_by_default_before_action_or_audit(self):
        user = self.create_user("k8s-pf-disabled")
        session = self.create_break_glass_session(user)

        with self.assertRaises(AdminResourceError) as raised:
            prepare_kubernetes_port_forward_bridge(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                namespace="payments",
                kind="Service",
                name="payments-api",
                remote_port=8080,
                reason="inspect service locally",
            )

        self.assertEqual(raised.exception.code, "native_port_forward_disabled")
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertFalse(K8sAuditEvent.objects.exists())

    @override_settings(
        KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS=["payments/service/payments-api:8080"],
    )
    def test_port_forward_bridge_records_metadata_only_blocked_action(self):
        user = self.create_user("k8s-pf-valid")
        session = self.create_break_glass_session(user)

        envelope = prepare_kubernetes_port_forward_bridge(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            namespace="payments",
            kind="Service",
            name="payments-api",
            remote_port=8080,
            local_port=18080,
            duration_seconds=120,
            reason="debug service from incident bridge",
            stream_id="pf-stream-1",
        )

        self.assertTrue(envelope["success"])
        self.assertEqual(envelope["status"], K8sAdminAction.STATUS_EXECUTION_BLOCKED)
        self.assertTrue(envelope["policy"]["requires_target_allowlist"])
        self.assertFalse(envelope["policy"]["provider_tunnel_enabled"])
        self.assertEqual(envelope["target"]["remote_port"], 8080)
        self.assertEqual(envelope["duration_seconds"], 120)
        action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_PORT_FORWARD)
        self.assertEqual(action.status, K8sAdminAction.STATUS_EXECUTION_BLOCKED)
        self.assertEqual(action.resource_kind, "Service")
        self.assertEqual(action.request_payload_sanitized["target"]["local_port"], 18080)
        recording = K8sAdminRecording.objects.get(action=action)
        self.assertEqual(recording.status, K8sAdminRecording.STATUS_BLOCKED)
        self.assertEqual(recording.operation, K8sAdminRecording.OP_PORT_FORWARD)
        self.assertFalse(recording.transcript_required)
        self.assertFalse(recording.payload_stored)
        self.assertEqual(envelope["recording"]["id"], str(recording.recording_id))
        audit = K8sAuditEvent.objects.get(action="k8s.admin_stream.port_forward_blocked")
        self.assertEqual(audit.payload["stream_id"], "pf-stream-1")
        self.assertEqual(audit.payload["target"]["remote_port"], 8080)
        self.assertEqual(audit.payload["recording_id"], str(recording.recording_id))

    @override_settings(KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True)
    def test_port_forward_requires_explicit_target_allowlist(self):
        user = self.create_user("k8s-pf-no-allowlist")
        session = self.create_break_glass_session(user)

        with self.assertRaises(AdminResourceError) as raised:
            prepare_kubernetes_port_forward_bridge(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                namespace="payments",
                kind="Service",
                name="payments-api",
                remote_port=8080,
                reason="debug service",
            )

        self.assertEqual(raised.exception.code, "port_forward_target_not_allowed")
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(
        KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS=["payments/service/payments-api:8080"],
    )
    def test_port_forward_requires_break_glass_session_mode(self):
        user = self.create_user("k8s-pf-write-session")
        session = self.create_break_glass_session(
            user,
            mode=K8sAdminSession.MODE_WRITE,
            risk_tier=K8sAdminSession.RISK_HIGH,
        )

        with self.assertRaises(AdminResourceError) as raised:
            prepare_kubernetes_port_forward_bridge(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                namespace="payments",
                kind="Service",
                name="payments-api",
                remote_port=8080,
                reason="debug service",
            )

        self.assertEqual(raised.exception.code, "break_glass_session_required")
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(
        KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS=["payments/service/payments-api:8080"],
    )
    def test_port_forward_requires_approved_break_glass_session_before_action(self):
        user = self.create_user("k8s-pf-unapproved")
        session = self.create_break_glass_session(user, approval_ref="", approved_by=None, approved_at=None)

        with self.assertRaises(AdminResourceError) as raised:
            prepare_kubernetes_port_forward_bridge(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                namespace="payments",
                kind="Service",
                name="payments-api",
                remote_port=8080,
                reason="debug service",
            )

        self.assertEqual(raised.exception.code, "admin_session_approval_required")
        self.assertEqual(raised.exception.payload["action"], K8sAdminAction.VERB_PORT_FORWARD)
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(
        KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS=["*"],
    )
    def test_port_forward_blocks_protected_namespace_before_action(self):
        user = self.create_user("k8s-pf-protected")
        session = self.create_break_glass_session(user, allowed_namespaces=["*"])

        with self.assertRaises(AdminResourceError) as raised:
            prepare_kubernetes_port_forward_bridge(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                namespace="kube-system",
                kind="Service",
                name="kube-dns",
                remote_port=53,
                reason="debug system service",
            )

        self.assertEqual(raised.exception.code, "port_forward_namespace_protected")
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(
        KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS=["payments/service/payments-api:8080"],
    )
    def test_port_forward_rejects_invalid_ports(self):
        user = self.create_user("k8s-pf-invalid-port")
        session = self.create_break_glass_session(user)

        with self.assertRaises(AdminResourceError) as raised:
            prepare_kubernetes_port_forward_bridge(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                namespace="payments",
                kind="Service",
                name="payments-api",
                remote_port=70000,
                reason="debug service",
            )

        self.assertEqual(raised.exception.code, "remote_port_out_of_range")
        self.assertFalse(K8sAdminAction.objects.exists())

    def test_port_forward_websocket_route_is_registered(self):
        from web_ui.routing import websocket_urlpatterns

        patterns = [str(pattern.pattern) for pattern in websocket_urlpatterns]
        self.assertIn("ws/kubernetes/admin/port-forward/<uuid:session_id>/", patterns)

    @override_settings(
        KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS=["payments/service/payments-api:8080"],
    )
    def test_port_forward_tunnel_requires_separate_tunnel_flag_before_action(self):
        user = self.create_user("k8s-pf-tunnel-disabled")
        session = self.create_break_glass_session(user)

        with self.assertRaises(AdminResourceError) as raised:
            prepare_kubernetes_port_forward_tunnel_context(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                namespace="payments",
                kind="Service",
                name="payments-api",
                remote_port=8080,
                reason="debug service tunnel",
            )

        self.assertEqual(raised.exception.code, "port_forward_tunnel_disabled")
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertFalse(K8sAuditEvent.objects.exists())

    @override_settings(
        KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS=["payments/service/payments-api:8080"],
    )
    def test_port_forward_tunnel_context_records_planned_metadata_only_action(self):
        self.provider.labels = {
            "port_forward_tunnel_path_template": "/k8s/clusters/{cluster_id}/api/v1/namespaces/{namespace}/services/{name}/portforward"
        }
        self.provider.save(update_fields=["labels"])
        user = self.create_user("k8s-pf-tunnel-valid")
        session = self.create_break_glass_session(user)

        envelope = prepare_kubernetes_port_forward_tunnel_context(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            namespace="payments",
            kind="Service",
            name="payments-api",
            remote_port=8080,
            local_port=18080,
            duration_seconds=120,
            reason="debug service tunnel",
            stream_id="pf-tunnel-1",
        )

        self.assertTrue(envelope["success"])
        self.assertEqual(envelope["status"], K8sAdminAction.STATUS_PLANNED)
        self.assertTrue(envelope["policy"]["provider_tunnel_enabled"])
        self.assertTrue(envelope["policy"]["recording_policy"]["enabled"])
        self.assertEqual(envelope["path"], "/k8s/clusters/c-prod/api/v1/namespaces/payments/services/payments-api/portforward")
        self.assertEqual(envelope["target"]["remote_port"], 8080)
        self.assertNotIn("token", str(envelope).lower())
        action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_PORT_FORWARD)
        self.assertEqual(action.status, K8sAdminAction.STATUS_PLANNED)
        self.assertEqual(action.response_summary["source"], "provider_port_forward_tunnel")
        self.assertEqual(action.response_summary["tunnel_started"], True)
        self.assertTrue(action.response_summary["recording_policy"]["enabled"])
        recording = K8sAdminRecording.objects.get(action=action)
        self.assertEqual(recording.status, K8sAdminRecording.STATUS_ACTIVE)
        self.assertEqual(recording.operation, K8sAdminRecording.OP_PORT_FORWARD)
        self.assertTrue(recording.policy_snapshot["enabled"])
        self.assertFalse(recording.payload_stored)
        self.assertEqual(envelope["recording"]["id"], str(recording.recording_id))
        audit = K8sAuditEvent.objects.get(action="k8s.admin_stream.port_forward_started")
        self.assertEqual(audit.payload["stream_id"], "pf-tunnel-1")
        self.assertTrue(audit.payload["recording_policy"]["enabled"])
        self.assertEqual(audit.payload["recording_id"], str(recording.recording_id))
