from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_resource_describe import get_cluster_resource_live_describe


class KubernetesOpsAdminResourceLiveDescribeTests(TestCase):
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

    def create_user(self, username: str, *, grant_kubernetes: bool = True, grant_admin_read: bool = False) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        if grant_kubernetes:
            UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        if grant_admin_read:
            UserAppPermission.objects.create(user=user, feature="kubernetes_admin_read", allowed=True)
        return user

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

    def test_live_describe_combines_resource_events_and_related_context_without_raw_body_in_action(self):
        user = self.create_user("k8s-live-describe", grant_admin_read=True)
        session = self.create_read_session(user)
        seen_urls: list[str] = []

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen_urls.append(url)
            if "/events?" in url:
                return {
                    "items": [
                        {
                            "metadata": {"name": "payments-api.17a", "namespace": "payments"},
                            "type": "Warning",
                            "reason": "Unhealthy",
                            "message": "probe failed password=event-secret",
                            "source": {"component": "kubelet", "token": "source-token"},
                            "involvedObject": {
                                "apiVersion": "apps/v1",
                                "kind": "Deployment",
                                "namespace": "payments",
                                "name": "payments-api",
                            },
                        }
                    ]
                }
            if "/pods?" in url:
                return {
                    "items": [
                        {
                            "apiVersion": "v1",
                            "kind": "Pod",
                            "metadata": {"name": "payments-api-abc", "namespace": "payments", "resourceVersion": "52"},
                            "spec": {"nodeName": "node-a"},
                            "status": {
                                "phase": "Running",
                                "podIP": "10.42.0.12",
                                "conditions": [{"type": "Ready", "status": "True"}],
                                "containerStatuses": [{"name": "api", "restartCount": 2}],
                            },
                        }
                    ]
                }
            if "/replicasets?" in url:
                return {
                    "items": [
                        {
                            "apiVersion": "apps/v1",
                            "kind": "ReplicaSet",
                            "metadata": {
                                "name": "payments-api-7f77",
                                "namespace": "payments",
                                "resourceVersion": "51",
                                "ownerReferences": [
                                    {
                                        "apiVersion": "apps/v1",
                                        "kind": "Deployment",
                                        "name": "payments-api",
                                        "controller": True,
                                    }
                                ],
                            },
                            "status": {"replicas": 2, "readyReplicas": 1},
                        }
                    ]
                }
            return {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {
                    "name": "payments-api",
                    "namespace": "payments",
                    "uid": "uid-1",
                    "resourceVersion": "50",
                    "labels": {"app": "payments", "safe": "yes"},
                    "annotations": {"checksum/config": "abc"},
                    "managedFields": [{"manager": "kubectl"}],
                },
                "spec": {
                    "replicas": 2,
                    "selector": {"matchLabels": {"app": "payments"}},
                    "template": {"spec": {"containers": [{"name": "api"}, {"name": "sidecar"}]}},
                },
                "status": {
                    "replicas": 2,
                    "readyReplicas": 1,
                    "availableReplicas": 1,
                    "conditions": [{"type": "Available", "status": "False", "message": "password=status-secret"}],
                },
            }

        payload = get_cluster_resource_live_describe(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="apps/v1",
            kind="Deployment",
            namespace="payments",
            name="payments-api",
            event_limit=5,
            transport=transport,
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["operation"], "resource_live_describe")
        self.assertEqual(
            payload["paths"]["resource"],
            "/k8s/clusters/c-prod/apis/apps/v1/namespaces/payments/deployments/payments-api",
        )
        self.assertEqual(payload["summary"]["spec"]["container_count"], 2)
        self.assertEqual(payload["summary"]["status"]["conditions"][0]["message"], "password=[redacted]")
        self.assertEqual(payload["events"]["event_count"], 1)
        self.assertEqual(payload["events"]["events"][0]["message"], "probe failed password=[redacted]")
        self.assertEqual(payload["events"]["events"][0]["source"]["token"], "[redacted]")
        self.assertEqual(payload["related"]["pods"]["item_count"], 1)
        self.assertEqual(payload["related"]["pods"]["items"][0]["restart_count"], 2)
        self.assertTrue(payload["related"]["pods"]["items"][0]["ready"])
        self.assertEqual(payload["related"]["controllers"]["item_count"], 1)
        self.assertEqual(payload["related"]["controllers"]["items"][0]["ready_replicas"], 1)
        self.assertIn("labelSelector=app%3Dpayments", seen_urls[2])
        self.assertNotIn("event-secret", str(payload))
        self.assertNotIn("source-token", str(payload))
        self.assertNotIn("status-secret", str(payload))

        action = K8sAdminAction.objects.get()
        self.assertEqual(action.verb, K8sAdminAction.VERB_GET)
        self.assertTrue(action.response_summary["live_describe"])
        self.assertEqual(action.response_summary["event_count"], 1)
        self.assertEqual(action.response_summary["related_pod_count"], 1)
        self.assertEqual(action.response_summary["related_controller_count"], 1)
        self.assertNotIn("payments-api-abc", str(action.response_summary))
        self.assertNotIn("event-secret", str(action.response_summary))

    def test_live_describe_api_is_session_gated_and_audits_only_metadata(self):
        user = self.create_user("k8s-live-describe-api", grant_admin_read=True)
        session = self.create_read_session(user)
        self.client.force_login(user)

        with (
            patch("kubernetes_ops.services.admin_resource_describe.ProviderJsonClient") as describe_client,
            patch("kubernetes_ops.services.admin_resource_describe_related.ProviderJsonClient") as related_client,
            patch("kubernetes_ops.services.admin_resource_events.ProviderJsonClient") as events_client,
        ):
            describe_client.return_value.get.return_value = {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {"name": "payments-api", "namespace": "payments"},
                "spec": {"selector": {"app": "payments"}, "ports": [{"port": 80}]},
            }
            related_client.return_value.get.return_value = {
                "items": [
                    {"metadata": {"name": "payments-api-abc", "namespace": "payments"}, "status": {"phase": "Running"}}
                ]
            }
            events_client.return_value.get.return_value = {
                "items": [{"metadata": {"name": "event-1"}, "message": "secret event body"}]
            }
            response = self.client.get(
                reverse("api_kubernetes_admin_resource_describe", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
                {
                    "session_id": str(session.session_id),
                    "api_version": "v1",
                    "kind": "Service",
                    "namespace": "payments",
                    "name": "payments-api",
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["operation"], "resource_live_describe")
        self.assertEqual(body["related"]["pods"]["item_count"], 1)
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_resource.describe").exists())
        audit = K8sAuditEvent.objects.get(action="k8s.admin_resource.describe")
        self.assertEqual(audit.payload["event_count"], 1)
        self.assertEqual(audit.payload["related_pod_count"], 1)
        self.assertNotIn("secret event body", str(audit.payload))
        self.assertNotIn("payments-api-abc", str(audit.payload))

    def test_regular_kubernetes_user_cannot_live_describe_admin_resource(self):
        user = self.create_user("k8s-live-describe-regular")
        session = self.create_read_session(user)
        self.client.force_login(user)

        response = self.client.get(
            reverse("api_kubernetes_admin_resource_describe", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
            {
                "session_id": str(session.session_id),
                "api_version": "apps/v1",
                "kind": "Deployment",
                "namespace": "payments",
                "name": "payments-api",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_read_required")
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_resource.describe_rejected").exists())
