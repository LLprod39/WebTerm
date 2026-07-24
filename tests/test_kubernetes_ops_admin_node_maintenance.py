import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_node_drain import build_node_drain_preflight
from kubernetes_ops.services.admin_node_maintenance import run_node_maintenance_action
from kubernetes_ops.services.admin_resources import AdminResourceError, KubernetesResourceRef, rancher_resource_path


class KubernetesOpsAdminNodeMaintenanceTests(TestCase):
    def create_user(self, username: str, *, grant_kubernetes: bool = True, grant_break_glass: bool = False) -> User:
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
            name="stage-kz-1",
            environment="stage",
            rancher_provider=self.provider,
            rancher_cluster_id="c-stage",
        )

    def create_break_glass_session(self, user: User, **kwargs) -> K8sAdminSession:
        defaults = {
            "user": user,
            "username_snapshot": user.username,
            "cluster": self.cluster,
            "mode": K8sAdminSession.MODE_BREAK_GLASS,
            "status": K8sAdminSession.STATUS_ACTIVE,
            "risk_tier": K8sAdminSession.RISK_CRITICAL,
            "allowed_verbs": ["get", "list", "watch", "logs", "yaml", "cordon", "uncordon", "drain"],
            "allowed_kinds": ["node"],
            "allowed_namespaces": ["*"],
            "reason": "node maintenance after incident approval",
            "approval_ref": "INC-2026-NODE-MAINT",
            "approved_by": user,
            "approved_at": timezone.now(),
            "expires_at": timezone.now() + timedelta(minutes=15),
        }
        defaults.update(kwargs)
        return K8sAdminSession.objects.create(**defaults)

    def node_response(self, *, unschedulable: bool) -> dict:
        return {
            "apiVersion": "v1",
            "kind": "Node",
            "metadata": {"name": "worker-1", "resourceVersion": "42", "labels": {"token": "raw-node-token"}},
            "spec": {"unschedulable": unschedulable},
        }

    def post_action(self, action: str, payload: dict):
        return self.client.post(
            reverse(f"api_kubernetes_admin_node_{action}", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_node_maintenance_disabled_by_default_before_provider_or_action(self):
        user = self.create_user("k8s-node-maint-disabled", grant_break_glass=True)
        session = self.create_break_glass_session(user)

        with self.assertRaises(AdminResourceError) as denied:
            run_node_maintenance_action(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                action="cordon",
                node_name="worker-1",
                reason="cordon node",
                transport=lambda *args, **kwargs: self.fail("provider must not be called"),
            )

        self.assertEqual(denied.exception.code, "native_node_maintenance_disabled")
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED=True)
    def test_regular_user_cannot_run_node_maintenance_without_break_glass(self):
        user = self.create_user("k8s-node-maint-regular")
        session = self.create_break_glass_session(user)
        self.client.force_login(user)

        response = self.post_action(
            "cordon", {"session_id": str(session.session_id), "node_name": "worker-1", "reason": "cordon node"}
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "break_glass_required")
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_node_maintenance.cordon_rejected").exists())

    @override_settings(KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED=True)
    def test_cordon_api_patches_node_unschedulable_and_audits_metadata(self):
        user = self.create_user("k8s-node-cordon", grant_break_glass=True)
        session = self.create_break_glass_session(user)
        self.client.force_login(user)

        with patch("kubernetes_ops.services.admin_node_maintenance.ProviderJsonClient") as client_cls:
            client_cls.return_value.request.return_value = self.node_response(unschedulable=True)
            response = self.post_action(
                "cordon", {"session_id": str(session.session_id), "node_name": "worker-1", "reason": "cordon node"}
            )
            method, path = client_cls.return_value.request.call_args.args[:2]
            body = client_cls.return_value.request.call_args.kwargs["body"]

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["operation"], "node_cordon")
        self.assertEqual(payload["status"], K8sAdminAction.STATUS_COMPLETED)
        self.assertTrue(payload["unschedulable"])
        self.assertEqual(payload["path"], "/k8s/clusters/c-stage/api/v1/nodes/worker-1")
        self.assertEqual(method, "PATCH")
        self.assertEqual(path, "/k8s/clusters/c-stage/api/v1/nodes/worker-1")
        self.assertEqual(body, {"spec": {"unschedulable": True}})
        self.assertEqual(payload["resource"]["metadata"]["labels"]["token"], "[redacted]")
        self.assertNotIn("raw-node-token", str(payload))
        action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_CORDON)
        self.assertEqual(action.resource_kind, "Node")
        self.assertEqual(action.resource_name, "worker-1")
        self.assertTrue(action.response_summary["unschedulable"])
        audit = K8sAuditEvent.objects.get(action="k8s.admin_node_maintenance.cordon")
        self.assertEqual(audit.payload["target"]["name"], "worker-1")
        self.assertTrue(audit.payload["unschedulable"])
        self.assertNotIn("cordon node", str(audit.payload))

    @override_settings(KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED=True)
    def test_uncordon_patches_node_schedulable(self):
        user = self.create_user("k8s-node-uncordon", grant_break_glass=True)
        session = self.create_break_glass_session(user)

        with patch("kubernetes_ops.services.admin_node_maintenance.ProviderJsonClient") as client_cls:
            client_cls.return_value.request.return_value = self.node_response(unschedulable=False)
            payload = run_node_maintenance_action(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                action="uncordon",
                node_name="worker-1",
                reason="return node to service",
            )
            body = client_cls.return_value.request.call_args.kwargs["body"]

        self.assertEqual(payload["operation"], "node_uncordon")
        self.assertFalse(payload["unschedulable"])
        self.assertEqual(body, {"spec": {"unschedulable": False}})
        self.assertEqual(K8sAdminAction.objects.get().verb, K8sAdminAction.VERB_UNCORDON)

    @override_settings(KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED=True)
    def test_drain_records_blocked_metadata_without_provider_call(self):
        user = self.create_user("k8s-node-drain", grant_break_glass=True)
        session = self.create_break_glass_session(user)
        self.client.force_login(user)

        response = self.post_action(
            "drain",
            {
                "session_id": str(session.session_id),
                "node_name": "worker-1",
                "reason": "drain before replacement",
                "confirmation": "drain Node worker-1",
                "options": {"ignore_daemonsets": True, "delete_emptydir_data": False, "force": False},
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["operation"], "node_drain")
        self.assertEqual(payload["status"], K8sAdminAction.STATUS_EXECUTION_BLOCKED)
        self.assertEqual(payload["blocked_reason"], "node_drain_execution_disabled")
        self.assertFalse(payload["drain_started"])
        self.assertFalse(payload["evictions_started"])
        action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_DRAIN)
        self.assertEqual(action.status, K8sAdminAction.STATUS_EXECUTION_BLOCKED)
        self.assertEqual(action.response_summary["blocked_reason"], "node_drain_execution_disabled")
        self.assertFalse(action.response_summary["payload_stored"])
        audit = K8sAuditEvent.objects.get(action="k8s.admin_node_maintenance.drain")
        self.assertEqual(audit.payload["blocked_reason"], "node_drain_execution_disabled")
        self.assertNotIn("drain before replacement", str(audit.payload))

    def test_drain_preflight_reads_pods_without_cordon_or_eviction(self):
        user = self.create_user("k8s-node-drain-preflight", grant_break_glass=True)
        session = self.create_break_glass_session(user)
        ref = KubernetesResourceRef(api_version="v1", kind="Node", resource="nodes", name="worker-1")
        path = rancher_resource_path(self.provider, self.cluster, ref)
        pods_payload = {
            "items": [
                {
                    "metadata": {
                        "name": "web-1",
                        "namespace": "payments",
                        "ownerReferences": [{"kind": "ReplicaSet", "name": "web-rs"}],
                    },
                    "spec": {"nodeName": "worker-1"},
                    "status": {"phase": "Running"},
                }
            ]
        }

        with patch("kubernetes_ops.services.admin_node_drain.ProviderJsonClient") as client_cls:
            client = client_cls.return_value
            client.request.return_value = pods_payload
            payload = build_node_drain_preflight(
                user=user,
                session=session,
                cluster=self.cluster,
                provider=self.provider,
                ref=ref,
                path=path,
                reason="preview only",
                confirmation="drain Node worker-1",
                options={"ignore_daemonsets": True, "delete_emptydir_data": False, "force": False, "max_pods": 50},
            )

        self.assertEqual(payload["operation"], "node_drain_preflight")
        self.assertEqual(payload["status"], K8sAdminAction.STATUS_PLANNED)
        self.assertFalse(payload["drain_started"])
        self.assertFalse(payload["evictions_started"])
        self.assertEqual(payload["pods_considered"], 1)
        self.assertEqual(payload["evictable_pod_count"], 1)
        self.assertEqual(client.request.call_count, 1)
        self.assertEqual(
            client.request.call_args.args[:2],
            ("GET", "/k8s/clusters/c-stage/api/v1/pods?fieldSelector=spec.nodeName%3Dworker-1&limit=51"),
        )
        action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_DRAIN)
        self.assertEqual(action.status, K8sAdminAction.STATUS_PLANNED)
        self.assertEqual(action.response_summary["source"], "provider_node_drain_preflight")
        self.assertFalse(action.response_summary["drain_started"])
        self.assertFalse(action.response_summary["evictions_started"])
        self.assertNotIn("preview only", str(action.response_summary))

    @override_settings(
        KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED=True, KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED=True
    )
    def test_drain_execution_cordons_node_and_uses_eviction_api(self):
        user = self.create_user("k8s-node-drain-execute", grant_break_glass=True)
        session = self.create_break_glass_session(user)
        self.client.force_login(user)
        pods_payload = {
            "items": [
                {
                    "metadata": {
                        "name": "web-1",
                        "namespace": "payments",
                        "ownerReferences": [{"kind": "ReplicaSet", "name": "web-rs"}],
                    },
                    "spec": {
                        "nodeName": "worker-1",
                        "volumes": [{"name": "config", "configMap": {"name": "web-config"}}],
                    },
                    "status": {"phase": "Running"},
                },
                {
                    "metadata": {
                        "name": "node-agent",
                        "namespace": "kube-system",
                        "ownerReferences": [{"kind": "DaemonSet", "name": "node-agent"}],
                    },
                    "spec": {"nodeName": "worker-1"},
                    "status": {"phase": "Running"},
                },
                {
                    "metadata": {
                        "name": "done-job",
                        "namespace": "batch",
                        "ownerReferences": [{"kind": "Job", "name": "done-job"}],
                    },
                    "spec": {"nodeName": "worker-1"},
                    "status": {"phase": "Succeeded"},
                },
            ]
        }

        with patch("kubernetes_ops.services.admin_node_drain.ProviderJsonClient") as client_cls:
            client = client_cls.return_value
            client.request.side_effect = [
                pods_payload,
                self.node_response(unschedulable=True),
                {"apiVersion": "policy/v1", "kind": "Eviction", "metadata": {"name": "web-1", "namespace": "payments"}},
            ]
            response = self.post_action(
                "drain",
                {
                    "session_id": str(session.session_id),
                    "node_name": "worker-1",
                    "reason": "approved node replacement",
                    "confirmation": "drain Node worker-1",
                    "options": {
                        "ignore_daemonsets": True,
                        "delete_emptydir_data": False,
                        "force": False,
                        "grace_period_seconds": 15,
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], K8sAdminAction.STATUS_COMPLETED)
        self.assertTrue(payload["drain_started"])
        self.assertTrue(payload["cordoned"])
        self.assertTrue(payload["evictions_started"])
        self.assertEqual(payload["evictions_requested"], 1)
        self.assertEqual(
            payload["evictions"], [{"namespace": "payments", "name": "web-1", "status": "eviction_requested"}]
        )
        self.assertEqual(payload["pods_skipped"]["daemonset"], 1)
        self.assertEqual(payload["pods_skipped"]["terminal"], 1)
        calls = client.request.call_args_list
        self.assertEqual(
            calls[0].args[:2],
            ("GET", "/k8s/clusters/c-stage/api/v1/pods?fieldSelector=spec.nodeName%3Dworker-1&limit=51"),
        )
        self.assertEqual(calls[1].args[:2], ("PATCH", "/k8s/clusters/c-stage/api/v1/nodes/worker-1"))
        self.assertEqual(calls[1].kwargs["body"], {"spec": {"unschedulable": True}})
        self.assertEqual(
            calls[2].args[:2], ("POST", "/k8s/clusters/c-stage/api/v1/namespaces/payments/pods/web-1/eviction")
        )
        self.assertEqual(calls[2].kwargs["body"]["kind"], "Eviction")
        self.assertEqual(calls[2].kwargs["body"]["apiVersion"], "policy/v1")
        action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_DRAIN)
        self.assertEqual(action.status, K8sAdminAction.STATUS_COMPLETED)
        self.assertEqual(action.response_summary["source"], "rancher_kubernetes_eviction_api")
        self.assertEqual(action.response_summary["evictions_requested"], 1)
        self.assertNotIn(
            "approved node replacement",
            str(K8sAuditEvent.objects.get(action="k8s.admin_node_maintenance.drain").payload),
        )

    @override_settings(
        KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED=True, KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED=True
    )
    def test_drain_blocks_emptydir_pods_before_cordon_or_eviction(self):
        user = self.create_user("k8s-node-drain-emptydir", grant_break_glass=True)
        session = self.create_break_glass_session(user)
        pods_payload = {
            "items": [
                {
                    "metadata": {
                        "name": "cache-1",
                        "namespace": "payments",
                        "ownerReferences": [{"kind": "ReplicaSet", "name": "cache-rs"}],
                    },
                    "spec": {"nodeName": "worker-1", "volumes": [{"name": "cache", "emptyDir": {}}]},
                    "status": {"phase": "Running"},
                }
            ]
        }

        with patch("kubernetes_ops.services.admin_node_drain.ProviderJsonClient") as client_cls:
            client = client_cls.return_value
            client.request.return_value = pods_payload
            payload = run_node_maintenance_action(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                action="drain",
                node_name="worker-1",
                reason="approved drain with local data",
                confirmation="drain Node worker-1",
            )

        self.assertEqual(payload["status"], K8sAdminAction.STATUS_EXECUTION_BLOCKED)
        self.assertEqual(payload["blocked_reason"], "emptydir_data_confirmation_required")
        self.assertFalse(payload["drain_started"])
        self.assertFalse(payload["evictions_started"])
        self.assertEqual(client.request.call_count, 1)
        self.assertEqual(
            client.request.call_args.args[:2],
            ("GET", "/k8s/clusters/c-stage/api/v1/pods?fieldSelector=spec.nodeName%3Dworker-1&limit=51"),
        )
        action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_DRAIN)
        self.assertEqual(action.status, K8sAdminAction.STATUS_EXECUTION_BLOCKED)
        self.assertEqual(action.response_summary["blocked_reason"], "emptydir_data_confirmation_required")
        self.assertEqual(action.response_summary["blockers"], {"emptydir": 1})

    @override_settings(
        KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED=True, KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED=True
    )
    def test_drain_blocks_truncated_pod_list_before_cordon_or_eviction(self):
        user = self.create_user("k8s-node-drain-truncated", grant_break_glass=True)
        session = self.create_break_glass_session(user)
        pods_payload = {
            "metadata": {"continue": "next-page-token"},
            "items": [
                {
                    "metadata": {
                        "name": "web-1",
                        "namespace": "payments",
                        "ownerReferences": [{"kind": "ReplicaSet", "name": "web-rs"}],
                    },
                    "spec": {"nodeName": "worker-1"},
                    "status": {"phase": "Running"},
                }
            ],
        }

        with patch("kubernetes_ops.services.admin_node_drain.ProviderJsonClient") as client_cls:
            client = client_cls.return_value
            client.request.return_value = pods_payload
            payload = run_node_maintenance_action(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                action="drain",
                node_name="worker-1",
                reason="approved drain with too many pods",
                confirmation="drain Node worker-1",
            )

        self.assertEqual(payload["status"], K8sAdminAction.STATUS_EXECUTION_BLOCKED)
        self.assertEqual(payload["blocked_reason"], "drain_pod_list_truncated")
        self.assertFalse(payload["drain_started"])
        self.assertEqual(client.request.call_count, 1)
        action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_DRAIN)
        self.assertEqual(action.response_summary["blockers"], {"pod_list_truncated": 1})

    @override_settings(KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED=True)
    def test_drain_requires_exact_confirmation_before_action(self):
        user = self.create_user("k8s-node-drain-confirmation", grant_break_glass=True)
        session = self.create_break_glass_session(user)

        with self.assertRaises(AdminResourceError) as denied:
            run_node_maintenance_action(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                action="drain",
                node_name="worker-1",
                reason="drain node",
                confirmation="wrong",
            )

        self.assertEqual(denied.exception.code, "confirmation_required")
        self.assertFalse(K8sAdminAction.objects.exists())
