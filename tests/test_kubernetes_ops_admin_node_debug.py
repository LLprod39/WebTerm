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
from kubernetes_ops.services.admin_node_debug import NODE_DEBUG_VERB


class KubernetesOpsAdminNodeDebugTests(TestCase):
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
            "namespace": "",
            "mode": K8sAdminSession.MODE_BREAK_GLASS,
            "status": K8sAdminSession.STATUS_ACTIVE,
            "risk_tier": K8sAdminSession.RISK_CRITICAL,
            "reason": "incident node debug",
            "approval_ref": "INC-2026-NODE",
            "approved_by": user,
            "approved_at": timezone.now(),
            "allowed_verbs": ["get", "list", "watch", "logs", "yaml", "exec", "port_forward"],
            "allowed_kinds": ["node"],
            "allowed_namespaces": ["*"],
            "expires_at": timezone.now() + timedelta(minutes=15),
        }
        defaults.update(kwargs)
        return K8sAdminSession.objects.create(**defaults)

    def post_start(self, session_id, payload: dict):
        return self.client.post(
            reverse("api_kubernetes_admin_node_debug_start", kwargs={"session_id": session_id}),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def post_stop(self, session_id, payload: dict):
        return self.client.post(
            reverse("api_kubernetes_admin_node_debug_stop", kwargs={"session_id": session_id}),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_node_debug_start_requires_approved_break_glass_before_action(self):
        user = self.create_user("k8s-node-debug-unapproved")
        session = self.create_break_glass_session(user, approval_ref="", approved_by=None, approved_at=None)
        self.client.force_login(user)

        response = self.post_start(session.session_id, {"node_name": "worker-1", "reason": "debug node"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_session_approval_required")
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertFalse(K8sAuditEvent.objects.filter(action="k8s.admin_node_debug.start_blocked").exists())

    def test_node_debug_start_records_metadata_only_blocked_action(self):
        user = self.create_user("k8s-node-debug-start")
        session = self.create_break_glass_session(user)
        self.client.force_login(user)

        response = self.post_start(session.session_id, {"node_name": "worker-1", "reason": "debug node"})

        self.assertEqual(response.status_code, 200)
        node_debug = response.json()["node_debug"]
        self.assertEqual(node_debug["status"], K8sAdminAction.STATUS_EXECUTION_BLOCKED)
        self.assertEqual(node_debug["blocked_reason"], "node_debug_disabled")
        self.assertFalse(node_debug["node_debug_started"])
        self.assertFalse(node_debug["transport_started"])
        self.assertEqual(node_debug["target"], {"kind": "Node", "name": "worker-1"})
        self.assertFalse(node_debug["policy"]["node_debug_enabled"])
        self.assertFalse(node_debug["policy"]["session_recording_enabled"])
        self.assertTrue(node_debug["recording_policy"]["required"])
        self.assertFalse(node_debug["recording_policy"]["enabled"])
        action = K8sAdminAction.objects.get(verb=NODE_DEBUG_VERB)
        self.assertEqual(action.status, K8sAdminAction.STATUS_EXECUTION_BLOCKED)
        self.assertEqual(action.resource_kind, "Node")
        self.assertEqual(action.resource_name, "worker-1")
        self.assertEqual(action.response_summary["blocked_reason"], "node_debug_disabled")
        self.assertFalse(action.response_summary["payload_stored"])
        recording = K8sAdminRecording.objects.get(action=action)
        self.assertEqual(recording.status, K8sAdminRecording.STATUS_BLOCKED)
        self.assertEqual(recording.operation, K8sAdminRecording.OP_NODE_DEBUG)
        self.assertTrue(recording.transcript_required)
        self.assertFalse(recording.transcript_stored)
        self.assertFalse(recording.payload_stored)
        self.assertEqual(node_debug["recording"]["id"], str(recording.recording_id))
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_node_debug.start_blocked").exists())

    @override_settings(KUBERNETES_ADMIN_NODE_DEBUG_ENABLED=True)
    def test_node_debug_start_blocks_before_action_without_recording_flag(self):
        user = self.create_user("k8s-node-debug-recording-required")
        session = self.create_break_glass_session(user)
        self.client.force_login(user)

        response = self.post_start(session.session_id, {"node_name": "worker-1", "reason": "debug node"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "node_debug_recording_required")
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertFalse(K8sAuditEvent.objects.filter(action="k8s.admin_node_debug.start_blocked").exists())

    @override_settings(
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_ADMIN_NODE_DEBUG_ENABLED=True,
        KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED=True,
        KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF="",
    )
    def test_production_node_debug_start_blocks_before_action_without_restricted_evidence(self):
        user = self.create_user("k8s-node-debug-no-restricted-evidence")
        session = self.create_break_glass_session(user)
        self.client.force_login(user)

        response = self.post_start(session.session_id, {"node_name": "worker-1", "reason": "debug node"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "interactive_transport_prerequisites_required")
        self.assertIn("restricted_credential_evidence_required", response.json()["payload"]["blockers"])
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertFalse(K8sAuditEvent.objects.filter(action="k8s.admin_node_debug.start_blocked").exists())

    @override_settings(
        KUBERNETES_ADMIN_NODE_DEBUG_ENABLED=True,
        KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED=True,
    )
    def test_node_debug_start_blocks_before_action_without_provider_contract(self):
        user = self.create_user("k8s-node-debug-no-provider-contract")
        session = self.create_break_glass_session(user)
        self.client.force_login(user)

        response = self.post_start(session.session_id, {"node_name": "worker-1", "reason": "debug node"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "interactive_transport_prerequisites_required")
        self.assertIn("provider_contract_required", response.json()["payload"]["blockers"])
        self.assertEqual(response.json()["payload"]["provider_contract"]["label"], "node_debug_path_template")
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertFalse(K8sAuditEvent.objects.filter(action="k8s.admin_node_debug.start_blocked").exists())

    @override_settings(
        KUBERNETES_ADMIN_NODE_DEBUG_ENABLED=True,
        KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED=True,
    )
    def test_node_debug_start_stays_metadata_only_until_transport_exists(self):
        user = self.create_user("k8s-node-debug-transport-not-implemented")
        session = self.create_break_glass_session(user)
        self.provider.labels = {
            "node_debug_path_template": "/k8s/clusters/{cluster_id}/api/v1/nodes/{node_name}/proxy/debug"
        }
        self.provider.save(update_fields=["labels"])
        self.client.force_login(user)

        response = self.post_start(session.session_id, {"node_name": "worker-1", "reason": "debug node"})

        self.assertEqual(response.status_code, 200)
        node_debug = response.json()["node_debug"]
        self.assertEqual(node_debug["blocked_reason"], "node_debug_transport_not_implemented")
        self.assertTrue(node_debug["policy"]["node_debug_enabled"])
        self.assertTrue(node_debug["policy"]["session_recording_enabled"])
        self.assertEqual(node_debug["policy"]["provider_contract"]["status"], "ready")
        self.assertFalse(node_debug["transport_started"])
        self.assertEqual(K8sAdminAction.objects.count(), 1)

    def test_node_debug_start_rejects_invalid_node_name_without_action(self):
        user = self.create_user("k8s-node-debug-invalid-node")
        session = self.create_break_glass_session(user)
        self.client.force_login(user)

        response = self.post_start(session.session_id, {"node_name": "bad/node", "reason": "debug node"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "node_name_invalid")
        self.assertFalse(K8sAdminAction.objects.exists())

    def test_node_debug_start_requires_node_scope(self):
        user = self.create_user("k8s-node-debug-denied-kind")
        session = self.create_break_glass_session(user, allowed_kinds=["pod"])
        self.client.force_login(user)

        response = self.post_start(session.session_id, {"node_name": "worker-1", "reason": "debug node"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_session_kind_denied")
        self.assertFalse(K8sAdminAction.objects.exists())

    def test_node_debug_stop_is_rejected_when_no_debug_is_running_and_audited(self):
        user = self.create_user("k8s-node-debug-stop")
        session = self.create_break_glass_session(user)
        self.client.force_login(user)

        response = self.post_stop(session.session_id, {"action_id": "not-started", "reason": "cleanup"})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "node_debug_not_running")
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_node_debug.stop_rejected").exists())
