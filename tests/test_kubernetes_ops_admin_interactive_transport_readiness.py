from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_exec_stream import prepare_kubernetes_exec_stream_context
from kubernetes_ops.services.admin_interactive_transport_readiness import build_admin_interactive_transport_report
from kubernetes_ops.services.admin_port_forward_tunnel import prepare_kubernetes_port_forward_tunnel_context
from kubernetes_ops.services.admin_resources import AdminResourceError


class KubernetesOpsAdminInteractiveTransportReadinessTests(TestCase):
    def create_user(self, username: str) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        UserAppPermission.objects.create(user=user, feature="kubernetes_break_glass", allowed=True)
        return user

    def setUp(self):
        self.provider = K8sProvider.objects.create(
            name="rancher-interactive-transport",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            auth_mode=K8sProvider.AUTH_NONE,
            labels={
                "pod_exec_stream_path_template": "/k8s/clusters/{cluster_id}/api/v1/namespaces/{namespace}/pods/{pod_name}/exec",
                "port_forward_tunnel_path_template": "/k8s/clusters/{cluster_id}/api/v1/namespaces/{namespace}/services/{name}/portforward",
                "cluster_terminal_path_template": "/k8s/clusters/{cluster_id}/api/v1/namespaces/{namespace}/pods/webterm-terminal/exec",
                "node_debug_path_template": "/k8s/clusters/{cluster_id}/api/v1/nodes/{node_name}/proxy/debug",
            },
        )
        self.cluster = K8sCluster.objects.create(
            name="interactive-transport-cluster",
            environment="prod",
            rancher_provider=self.provider,
            rancher_cluster_id="c-prod",
        )
        self.user = self.create_user("k8s-interactive-transport")
        self.session = K8sAdminSession.objects.create(
            user=self.user,
            username_snapshot=self.user.username,
            cluster=self.cluster,
            namespace="payments",
            mode=K8sAdminSession.MODE_BREAK_GLASS,
            status=K8sAdminSession.STATUS_ACTIVE,
            risk_tier=K8sAdminSession.RISK_CRITICAL,
            reason="incident transport",
            approval_ref="INC-TRANSPORT",
            approved_by=self.user,
            approved_at=timezone.now(),
            allowed_verbs=["get", "list", "watch", "logs", "yaml", "exec", "port_forward"],
            allowed_kinds=["pod"],
            allowed_namespaces=["payments"],
            expires_at=timezone.now() + timedelta(minutes=15),
        )

    def test_interactive_transport_report_is_ready_when_transports_are_disabled(self):
        report = build_admin_interactive_transport_report()

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["enabled_transport_count"], 0)
        self.assertFalse(report["restricted_credential_evidence_present"])

    @override_settings(
        KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED=True,
        KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED=True,
    )
    def test_cluster_terminal_readiness_requires_provider_contract_when_enabled(self):
        self.provider.labels = {
            "pod_exec_stream_path_template": "/k8s/clusters/{cluster_id}/api/v1/namespaces/{namespace}/pods/{pod_name}/exec",
            "port_forward_tunnel_path_template": "/k8s/clusters/{cluster_id}/api/v1/namespaces/{namespace}/services/{name}/portforward",
        }
        self.provider.save(update_fields=["labels"])

        report = build_admin_interactive_transport_report()

        self.assertEqual(report["status"], "missing")
        self.assertIn("cluster_terminal:provider_contract_required", report["blockers"])
        transport = next(item for item in report["transports"] if item["id"] == "cluster_terminal")
        self.assertEqual(transport["provider_contract"]["label"], "cluster_terminal_path_template")
        self.assertEqual(transport["provider_contract"]["missing_provider_count"], 1)

    @override_settings(
        KUBERNETES_ADMIN_NODE_DEBUG_ENABLED=True,
        KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED=True,
    )
    def test_node_debug_readiness_rejects_invalid_provider_contract(self):
        self.provider.labels = {"node_debug_path_template": "/k8s/clusters/{cluster_id}/api/v1/nodes/debug"}
        self.provider.save(update_fields=["labels"])

        report = build_admin_interactive_transport_report()

        self.assertEqual(report["status"], "missing")
        self.assertIn("node_debug:provider_contract_invalid", report["blockers"])
        transport = next(item for item in report["transports"] if item["id"] == "node_debug")
        self.assertEqual(transport["provider_contract"]["invalid_provider_count"], 1)

    @override_settings(
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True,
        KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=True,
        KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED=True,
        KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF="",
    )
    def test_interactive_transport_report_blocks_production_exec_without_restricted_evidence(self):
        report = build_admin_interactive_transport_report()

        self.assertEqual(report["status"], "missing")
        self.assertTrue(report["production_environment"])
        self.assertIn("exec_stream:restricted_credential_evidence_required", report["blockers"])
        exec_report = next(item for item in report["transports"] if item["id"] == "exec_stream")
        self.assertTrue(exec_report["enabled"])
        self.assertTrue(exec_report["recording_enabled"])
        self.assertFalse(exec_report["restricted_credential_evidence_ready"])

    @override_settings(
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True,
        KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=True,
        KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED=True,
        KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF="artifact:restricted-sa-proof-123",
    )
    def test_interactive_transport_report_accepts_production_exec_with_restricted_evidence(self):
        report = build_admin_interactive_transport_report()

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["enabled_transport_count"], 1)
        self.assertTrue(report["restricted_credential_evidence_present"])
        self.assertEqual(report["blockers"], [])

    @override_settings(
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True,
        KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=True,
        KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED=True,
        KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF="",
    )
    def test_exec_stream_is_blocked_before_action_without_restricted_evidence_in_production(self):
        with self.assertRaises(AdminResourceError) as raised:
            prepare_kubernetes_exec_stream_context(
                user=self.user,
                session_id=str(self.session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                namespace="payments",
                pod_name="payments-api-abc123",
                command=["env"],
                reason="inspect env",
            )

        self.assertEqual(raised.exception.code, "interactive_transport_prerequisites_required")
        self.assertEqual(raised.exception.payload["operation"], "exec_stream")
        self.assertIn("restricted_credential_evidence_required", raised.exception.payload["blockers"])
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertFalse(K8sAuditEvent.objects.exists())

    @override_settings(
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS=["payments/service/payments-api:8080"],
        KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF="",
    )
    def test_port_forward_tunnel_is_blocked_before_action_without_restricted_evidence_in_production(self):
        with self.assertRaises(AdminResourceError) as raised:
            prepare_kubernetes_port_forward_tunnel_context(
                user=self.user,
                session_id=str(self.session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                namespace="payments",
                kind="Service",
                name="payments-api",
                remote_port=8080,
                reason="debug service",
            )

        self.assertEqual(raised.exception.code, "interactive_transport_prerequisites_required")
        self.assertEqual(raised.exception.payload["operation"], "port_forward_tunnel")
        self.assertIn("restricted_credential_evidence_required", raised.exception.payload["blockers"])
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertFalse(K8sAuditEvent.objects.exists())

    @override_settings(
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS=["payments/service/payments-api:8080"],
        KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF="artifact:restricted-sa-proof-123",
        KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF="artifact:network-policy-proof-456",
    )
    def test_production_port_forward_tunnel_readiness_requires_exact_network_policy_evidence(self):
        report = build_admin_interactive_transport_report()

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["blockers"], [])
        transport = next(item for item in report["transports"] if item["id"] == "port_forward_tunnel")
        self.assertTrue(transport["enabled"])
        self.assertTrue(transport["network_policy"]["network_policy_evidence_present"])
        self.assertEqual(transport["network_policy"]["allowed_target_count"], 1)
        self.assertFalse(transport["network_policy"]["wildcard_targets_present"])
        self.assertTrue(transport["network_policy"]["default_protected_namespaces_covered"])
        self.assertLessEqual(transport["network_policy"]["max_duration_seconds"], 900)

    @override_settings(
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS=["payments/service/payments-api:8080"],
        KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF="artifact:restricted-sa-proof-123",
        KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF="",
    )
    def test_port_forward_tunnel_is_blocked_before_action_without_network_policy_evidence_in_production(self):
        with self.assertRaises(AdminResourceError) as raised:
            prepare_kubernetes_port_forward_tunnel_context(
                user=self.user,
                session_id=str(self.session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                namespace="payments",
                kind="Service",
                name="payments-api",
                remote_port=8080,
                reason="debug service",
            )

        self.assertEqual(raised.exception.code, "interactive_transport_prerequisites_required")
        self.assertEqual(raised.exception.payload["operation"], "port_forward_tunnel")
        self.assertIn("network_policy_evidence_required", raised.exception.payload["blockers"])
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertFalse(K8sAuditEvent.objects.exists())

    @override_settings(
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS=["payments/service/*:8080"],
        KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF="artifact:restricted-sa-proof-123",
        KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF="artifact:network-policy-proof-456",
    )
    def test_production_port_forward_tunnel_rejects_wildcard_allowlist_readiness(self):
        report = build_admin_interactive_transport_report()

        self.assertEqual(report["status"], "missing")
        self.assertIn("port_forward_tunnel:target_wildcard_not_allowed", report["blockers"])
        transport = next(item for item in report["transports"] if item["id"] == "port_forward_tunnel")
        self.assertTrue(transport["network_policy"]["wildcard_targets_present"])

    @override_settings(
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED=True,
        KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED=True,
        KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF="",
    )
    def test_production_cluster_terminal_readiness_requires_restricted_evidence(self):
        report = build_admin_interactive_transport_report()

        self.assertEqual(report["status"], "missing")
        self.assertIn("cluster_terminal:restricted_credential_evidence_required", report["blockers"])
        transport = next(item for item in report["transports"] if item["id"] == "cluster_terminal")
        self.assertTrue(transport["enabled"])
        self.assertTrue(transport["recording_enabled"])
        self.assertFalse(transport["restricted_credential_evidence_ready"])

    @override_settings(
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_ADMIN_NODE_DEBUG_ENABLED=True,
        KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED=True,
        KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF="",
    )
    def test_production_node_debug_readiness_requires_restricted_evidence(self):
        report = build_admin_interactive_transport_report()

        self.assertEqual(report["status"], "missing")
        self.assertIn("node_debug:restricted_credential_evidence_required", report["blockers"])
        transport = next(item for item in report["transports"] if item["id"] == "node_debug")
        self.assertTrue(transport["enabled"])
        self.assertTrue(transport["recording_enabled"])
        self.assertFalse(transport["restricted_credential_evidence_ready"])

    @override_settings(
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True,
        KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=True,
        KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED=True,
        KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF="",
    )
    def test_readiness_exposes_interactive_transport_prerequisites(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("api_kubernetes_readiness"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        checks = {item["id"]: item for item in payload["checks"]}
        self.assertEqual(checks["admin_interactive_transport"]["status"], "missing")
        self.assertFalse(checks["admin_interactive_transport"]["required"])
        self.assertEqual(payload["admin_interactive_transport"]["status"], "missing")
        self.assertIn(
            "exec_stream:restricted_credential_evidence_required", payload["admin_interactive_transport"]["blockers"]
        )
