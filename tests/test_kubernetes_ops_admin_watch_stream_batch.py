from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_watch import get_admin_resource_watch_stream_batch


class KubernetesOpsAdminWatchStreamBatchTests(TestCase):
    def test_admin_resource_watch_stream_batch_marks_provider_stream_contract(self):
        provider = K8sProvider.objects.create(
            name="rancher-watch-stream",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            auth_mode=K8sProvider.AUTH_NONE,
        )
        cluster = K8sCluster.objects.create(
            name="watch-stream-cluster",
            environment="test",
            rancher_provider=provider,
            rancher_cluster_id="local",
        )
        user = User.objects.create_user(username="k8s-watch-stream", password="password-123")
        UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        UserAppPermission.objects.create(user=user, feature="kubernetes_admin_read", allowed=True)
        session = K8sAdminSession.objects.create(
            user=user,
            username_snapshot=user.username,
            cluster=cluster,
            mode=K8sAdminSession.MODE_READ,
            status=K8sAdminSession.STATUS_ACTIVE,
            risk_tier=K8sAdminSession.RISK_LOW,
            allowed_verbs=["get", "list", "watch", "logs", "yaml"],
            allowed_kinds=["*"],
            allowed_namespaces=["*"],
            expires_at=timezone.now() + timedelta(hours=1),
        )

        def transport(url: str, headers: dict[str, str], timeout: int):
            return {
                "items": [
                    {
                        "type": "ADDED",
                        "object": {
                            "apiVersion": "apps/v1",
                            "kind": "Deployment",
                            "metadata": {"name": "payments-api", "namespace": "payments", "resourceVersion": "42"},
                        },
                    }
                ]
            }

        payload = get_admin_resource_watch_stream_batch(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{cluster.id}",
            api_version="apps/v1",
            kind="Deployment",
            namespace="payments",
            resource_version="41",
            limit=5,
            timeout_seconds=6,
            transport=transport,
        )

        self.assertEqual(payload["operation"], "resource_watch_stream_batch")
        self.assertEqual(payload["source"], "provider_watch_stream_batch")
        self.assertTrue(payload["policy"]["streaming"])
        self.assertEqual(payload["policy"]["timeout_seconds"], 6)
        self.assertEqual(payload["latest_resource_version"], "42")
        self.assertEqual(payload["event_count"], 1)
        action = K8sAdminAction.objects.get()
        self.assertEqual(action.verb, K8sAdminAction.VERB_WATCH)
        self.assertEqual(action.response_summary["source"], "provider_watch_stream_batch")
        self.assertEqual(action.response_summary["latest_resource_version"], "42")
