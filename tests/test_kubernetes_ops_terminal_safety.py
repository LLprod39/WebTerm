from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.services.terminal_safety import TERMINAL_CAPABILITIES, build_kubernetes_terminal_safety_report
from kubernetes_ops.urls import urlpatterns


class KubernetesOpsTerminalSafetyTests(TestCase):
    def create_user(self, username: str) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        return user

    def test_readiness_exposes_terminal_threat_model_and_keeps_exec_disabled(self):
        user = self.create_user("k8s-terminal-policy")
        self.client.force_login(user)

        response = self.client.get(reverse("api_kubernetes_readiness"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        checks = {item["id"]: item for item in payload["checks"]}
        self.assertEqual(checks["terminal_exec_threat_model"]["status"], "ready")
        report = payload["terminal_safety"]
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["mode"], "disabled")
        self.assertFalse(report["native_exec_enabled"])
        self.assertFalse(report["native_streaming_enabled"])
        self.assertFalse(report["exec_recording_enabled"])
        self.assertFalse(report["native_port_forward_enabled"])
        self.assertFalse(report["native_port_forward_tunnel_enabled"])
        self.assertFalse(report["port_forward_recording_enabled"])
        self.assertFalse(report["cluster_terminal_enabled"])
        self.assertFalse(report["cluster_terminal_recording_enabled"])
        self.assertFalse(report["node_debug_enabled"])
        self.assertFalse(report["node_debug_recording_enabled"])
        self.assertEqual(report["interactive_metadata_retention_days"], 365)
        self.assertEqual(report["interactive_transcript_retention_days"], 30)
        self.assertEqual(report["transcript_event_max_chars"], 2000)
        self.assertEqual(report["transcript_event_max_count"], 2000)
        self.assertEqual(report["recording_cleanup_command"], "python manage.py cleanup_kubernetes_admin_recordings --apply")
        self.assertEqual(report["interactive_transport_prerequisites"]["status"], "ready")
        self.assertEqual(report["interactive_transport_prerequisites"]["enabled_transport_count"], 0)
        self.assertFalse(payload["access_policy"]["can_exec"])
        self.assertFalse(payload["access_policy"]["can_mutate_cluster_state"])
        for capability in TERMINAL_CAPABILITIES:
            self.assertIn(capability, report["blocked_capabilities"])
            self.assertIn(capability, payload["access_policy"]["blocked_capabilities"])
        self.assertIn("session recording", " ".join(report["production_prerequisites"]))
        self.assertIn("break-glass", " ".join(report["production_prerequisites"]))

    def test_terminal_safety_report_fails_closed_if_exec_flag_is_enabled(self):
        report = build_kubernetes_terminal_safety_report(
            policy={
                "can_exec": True,
                "can_port_forward": False,
                "can_mutate_cluster_state": False,
                "blocked_capabilities": list(TERMINAL_CAPABILITIES),
            }
        )

        self.assertEqual(report["status"], "missing")
        self.assertEqual(report["unsafe_enabled_flags"], ["can_exec"])

    @override_settings(KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True)
    def test_terminal_safety_report_exposes_native_exec_flag_and_stays_missing(self):
        user = self.create_user("k8s-terminal-native-exec")
        UserAppPermission.objects.create(user=user, feature="kubernetes_break_glass", allowed=True)

        report = build_kubernetes_terminal_safety_report(user)

        self.assertEqual(report["status"], "missing")
        self.assertTrue(report["native_exec_enabled"])
        self.assertFalse(report["exec_recording_enabled"])
        self.assertIn("pod.exec", report["missing_blocked_capabilities"])
        self.assertIn("can_exec", report["unsafe_enabled_flags"])

    @override_settings(KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True)
    def test_terminal_safety_report_exposes_native_port_forward_flag_and_stays_missing(self):
        user = self.create_user("k8s-terminal-native-port-forward")
        UserAppPermission.objects.create(user=user, feature="kubernetes_break_glass", allowed=True)

        report = build_kubernetes_terminal_safety_report(user)

        self.assertEqual(report["status"], "missing")
        self.assertTrue(report["native_port_forward_enabled"])
        self.assertFalse(report["native_port_forward_tunnel_enabled"])
        self.assertIn("port_forward", report["missing_blocked_capabilities"])
        self.assertIn("can_port_forward", report["unsafe_enabled_flags"])

    @override_settings(KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=True)
    def test_terminal_safety_report_exposes_port_forward_tunnel_flag_without_enabling_access(self):
        user = self.create_user("k8s-terminal-port-forward-tunnel")
        UserAppPermission.objects.create(user=user, feature="kubernetes_break_glass", allowed=True)

        report = build_kubernetes_terminal_safety_report(user)

        self.assertEqual(report["status"], "ready")
        self.assertFalse(report["native_port_forward_enabled"])
        self.assertTrue(report["native_port_forward_tunnel_enabled"])
        self.assertFalse(report["port_forward_recording_enabled"])
        self.assertNotIn("can_port_forward", report["unsafe_enabled_flags"])

    @override_settings(KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED=True)
    def test_terminal_safety_report_exposes_cluster_terminal_flag_without_enabling_access(self):
        user = self.create_user("k8s-terminal-cluster-terminal")
        UserAppPermission.objects.create(user=user, feature="kubernetes_break_glass", allowed=True)

        report = build_kubernetes_terminal_safety_report(user)

        self.assertEqual(report["status"], "ready")
        self.assertTrue(report["cluster_terminal_enabled"])
        self.assertFalse(report["cluster_terminal_recording_enabled"])
        self.assertIn("cluster_terminal", report["blocked_capabilities"])

    @override_settings(KUBERNETES_ADMIN_NODE_DEBUG_ENABLED=True)
    def test_terminal_safety_report_exposes_node_debug_flag_without_enabling_access(self):
        user = self.create_user("k8s-terminal-node-debug")
        UserAppPermission.objects.create(user=user, feature="kubernetes_break_glass", allowed=True)

        report = build_kubernetes_terminal_safety_report(user)

        self.assertEqual(report["status"], "ready")
        self.assertTrue(report["node_debug_enabled"])
        self.assertFalse(report["node_debug_recording_enabled"])
        self.assertIn("node_debug", report["blocked_capabilities"])

    def test_terminal_safety_report_fails_closed_if_required_block_is_missing(self):
        report = build_kubernetes_terminal_safety_report(
            policy={
                "can_exec": False,
                "can_port_forward": False,
                "can_mutate_cluster_state": False,
                "blocked_capabilities": ["pod.exec"],
            }
        )

        self.assertEqual(report["status"], "missing")
        self.assertIn("node_debug", report["missing_blocked_capabilities"])
        self.assertIn("port_forward", report["missing_blocked_capabilities"])

    def test_no_native_kubernetes_exec_or_port_forward_routes_are_registered(self):
        registered_routes = {str(pattern.pattern) for pattern in urlpatterns}

        self.assertNotIn("pods/<str:pod_id>/exec/", registered_routes)
        self.assertNotIn("pods/<str:pod_id>/attach/", registered_routes)
        self.assertNotIn("port-forward/", registered_routes)
        self.assertNotIn("terminal/", registered_routes)
        self.assertNotIn("pods/<str:pod_id>/node-debug/", registered_routes)
