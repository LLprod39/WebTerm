from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_nodes import list_cluster_nodes


class KubernetesOpsAdminNodeTests(TestCase):
    def create_user(self, username: str, *, grant_kubernetes: bool = True, grant_admin_read: bool = False) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        if grant_kubernetes:
            UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        if grant_admin_read:
            UserAppPermission.objects.create(user=user, feature="kubernetes_admin_read", allowed=True)
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

    def create_read_session(self, user: User, **kwargs) -> K8sAdminSession:
        defaults = {
            "user": user,
            "username_snapshot": user.username,
            "cluster": self.cluster,
            "mode": K8sAdminSession.MODE_READ,
            "status": K8sAdminSession.STATUS_ACTIVE,
            "risk_tier": K8sAdminSession.RISK_LOW,
            "allowed_verbs": ["get", "list", "watch", "logs", "yaml"],
            "allowed_kinds": ["*"],
            "allowed_namespaces": ["*"],
            "expires_at": timezone.now() + timedelta(hours=1),
        }
        defaults.update(kwargs)
        return K8sAdminSession.objects.create(**defaults)

    def nodes_payload(self) -> dict:
        return {
            "items": [
                {
                    "apiVersion": "v1",
                    "kind": "Node",
                    "metadata": {
                        "name": "worker-1",
                        "uid": "uid-worker-1",
                        "resourceVersion": "101",
                        "creationTimestamp": "2026-07-01T01:00:00Z",
                        "labels": {"node-role.kubernetes.io/worker": "", "token": "raw-label-token"},
                        "annotations": {"checksum/config": "abc", "password": "raw-annotation-secret"},
                    },
                    "spec": {"taints": [{"key": "dedicated", "value": "payments", "effect": "NoSchedule"}]},
                    "status": {
                        "capacity": {"cpu": "4", "memory": "16Gi", "pods": "110"},
                        "allocatable": {"cpu": "3900m", "memory": "14Gi", "pods": "100"},
                        "addresses": [{"type": "InternalIP", "address": "10.42.0.10"}],
                        "conditions": [
                            {
                                "type": "Ready",
                                "status": "True",
                                "reason": "KubeletReady",
                                "message": "kubelet is posting ready status",
                                "lastTransitionTime": "2026-07-01T01:10:00Z",
                            }
                        ],
                        "nodeInfo": {
                            "architecture": "amd64",
                            "operatingSystem": "linux",
                            "kubeletVersion": "v1.30.0",
                            "containerRuntimeVersion": "containerd://1.7.0",
                        },
                        "images": [{"names": ["example/app:1"]}, {"names": ["example/app:2"]}],
                    },
                },
                {
                    "apiVersion": "v1",
                    "kind": "Node",
                    "metadata": {"name": "worker-2", "uid": "uid-worker-2", "resourceVersion": "102"},
                    "spec": {"unschedulable": True},
                    "status": {
                        "conditions": [
                            {
                                "type": "Ready",
                                "status": "False",
                                "reason": "KubeletNotReady",
                                "message": "password=raw-node-secret",
                            }
                        ]
                    },
                },
            ]
        }

    def test_admin_node_view_summarizes_nodes_through_rancher_proxy_and_audits_counts_only(self):
        user = self.create_user("k8s-admin-nodes", grant_admin_read=True)
        session = self.create_read_session(user)
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen["url"] = url
            return self.nodes_payload()

        payload = list_cluster_nodes(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            transport=transport,
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["operation"], "node_list")
        self.assertEqual(payload["path"], "/k8s/clusters/c-prod/api/v1/nodes")
        self.assertEqual(seen["url"], "https://rancher.example.test/k8s/clusters/c-prod/api/v1/nodes")
        self.assertEqual(payload["summary"]["node_count"], 2)
        self.assertEqual(payload["summary"]["ready_count"], 1)
        self.assertEqual(payload["summary"]["not_ready_count"], 1)
        self.assertEqual(payload["summary"]["unschedulable_count"], 1)
        self.assertEqual(payload["summary"]["tainted_count"], 1)
        self.assertEqual(payload["nodes"][0]["roles"], ["worker"])
        self.assertEqual(payload["nodes"][0]["capacity"]["cpu"], "4")
        self.assertEqual(payload["nodes"][0]["node_info"]["kubeletVersion"], "v1.30.0")
        self.assertIn("token", payload["nodes"][0]["label_keys"])
        self.assertIn("password", payload["nodes"][0]["annotation_keys"])
        self.assertEqual(payload["nodes"][1]["ready_message"], "password=[redacted]")
        self.assertFalse(payload["policy"]["mutates_state"])
        self.assertIn("drain", payload["policy"]["blocked_actions"])
        self.assertNotIn("raw-label-token", str(payload))
        self.assertNotIn("raw-annotation-secret", str(payload))
        self.assertNotIn("raw-node-secret", str(payload))

        action = K8sAdminAction.objects.get()
        self.assertEqual(action.verb, K8sAdminAction.VERB_LIST)
        self.assertEqual(action.resource_kind, "Node")
        self.assertEqual(action.response_summary["node_count"], 2)
        self.assertEqual(action.response_summary["ready_count"], 1)
        self.assertEqual(action.response_summary["not_ready_count"], 1)
        self.assertNotIn("worker-1", str(action.response_summary))
        self.assertNotIn("raw-node-secret", str(action.response_summary))

    def test_admin_nodes_api_is_session_gated_and_audits_metadata(self):
        user = self.create_user("k8s-admin-nodes-api", grant_admin_read=True)
        session = self.create_read_session(user)
        self.client.force_login(user)

        with patch("kubernetes_ops.services.admin_nodes.ProviderJsonClient") as client_cls:
            client_cls.return_value.get.return_value = self.nodes_payload()
            response = self.client.get(
                reverse("api_kubernetes_admin_nodes", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
                {"session_id": str(session.session_id), "limit": "10"},
            )
            client_cls.return_value.get.assert_called_with("/k8s/clusters/c-prod/api/v1/nodes")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["operation"], "node_list")
        self.assertEqual(payload["summary"]["node_count"], 2)
        self.assertNotIn("raw-node-secret", str(payload))
        audit = K8sAuditEvent.objects.get(action="k8s.admin_resource.nodes")
        self.assertEqual(audit.payload["node_count"], 2)
        self.assertEqual(audit.payload["ready_count"], 1)
        self.assertNotIn("worker-1", str(audit.payload))
        self.assertNotIn("raw-node-secret", str(audit.payload))

    def test_regular_kubernetes_user_cannot_read_admin_nodes_without_admin_read(self):
        user = self.create_user("k8s-regular-nodes")
        session = self.create_read_session(user)
        self.client.force_login(user)

        response = self.client.get(
            reverse("api_kubernetes_admin_nodes", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
            {"session_id": str(session.session_id)},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_read_required")
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_resource.nodes_rejected").exists())
