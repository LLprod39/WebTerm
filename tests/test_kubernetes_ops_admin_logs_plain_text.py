from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_logs import get_admin_pod_log_snapshot, get_admin_pod_log_stream_batch


class KubernetesOpsAdminPlainTextLogsTests(TestCase):
    def test_admin_pod_logs_accepts_plain_text_provider_payload(self):
        provider = K8sProvider.objects.create(
            name="rancher-admin-text-logs",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            auth_mode=K8sProvider.AUTH_NONE,
        )
        cluster = K8sCluster.objects.create(
            name="admin-text-logs-cluster",
            environment="test",
            rancher_provider=provider,
            rancher_cluster_id="local",
        )
        user = User.objects.create_user(username="k8s-admin-text-logs", password="password-123")
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

        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen["url"] = url
            return "boot ok\npassword=raw-secret\nAuthorization: Bearer abc.def\nready\n"

        payload = get_admin_pod_log_snapshot(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{cluster.id}",
            namespace="payments",
            pod_name="payments-api-plain",
            tail_lines=3,
            transport=transport,
        )

        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "provider_snapshot")
        self.assertEqual(payload["line_count"], 3)
        self.assertEqual(payload["lines"], ["password=[redacted]", "Authorization: Bearer [redacted]", "ready"])
        self.assertEqual(seen["url"], "https://rancher.example.test/k8s/clusters/local/api/v1/namespaces/payments/pods/payments-api-plain/log?tailLines=3")
        self.assertNotIn("raw-secret", str(payload))
        self.assertNotIn("abc.def", str(payload))
        action = K8sAdminAction.objects.get()
        self.assertEqual(action.verb, K8sAdminAction.VERB_LOGS)
        self.assertEqual(action.response_summary["line_count"], 3)
        self.assertNotIn("raw-secret", str(action.response_summary))

    def test_admin_pod_log_stream_batch_uses_provider_stream_template(self):
        provider = K8sProvider.objects.create(
            name="rancher-admin-stream-logs",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            auth_mode=K8sProvider.AUTH_NONE,
            labels={"pod_logs_stream_path_template": "/k8s/clusters/{cluster_id}/api/v1/namespaces/{namespace}/pods/{pod_name}/log?follow=1&tailLines={tail}"},
        )
        cluster = K8sCluster.objects.create(
            name="admin-stream-logs-cluster",
            environment="test",
            rancher_provider=provider,
            rancher_cluster_id="local",
        )
        user = User.objects.create_user(username="k8s-admin-stream-logs", password="password-123")
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
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen["url"] = url
            seen["headers"] = headers
            seen["timeout"] = timeout
            return "boot ok\napi_key=raw-secret\nready\n"

        payload = get_admin_pod_log_stream_batch(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{cluster.id}",
            namespace="payments",
            pod_name="payments-api-stream",
            tail_lines=2,
            timeout_seconds=3,
            transport=transport,
        )

        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "provider_stream_batch")
        self.assertTrue(payload["policy"]["streaming"])
        self.assertEqual(payload["policy"]["timeout_seconds"], 3)
        self.assertEqual(payload["lines"], ["boot ok", "api_key=[redacted]"])
        self.assertEqual(payload["line_count"], 2)
        self.assertTrue(payload["truncated"])
        self.assertEqual(seen["timeout"], 3)
        self.assertEqual(seen["url"], "https://rancher.example.test/k8s/clusters/local/api/v1/namespaces/payments/pods/payments-api-stream/log?follow=1&tailLines=2")
        self.assertIn("text/plain", seen["headers"]["Accept"])
        self.assertNotIn("raw-secret", str(payload))
        action = K8sAdminAction.objects.get()
        self.assertEqual(action.response_summary["source"], "provider_stream_batch")
        self.assertEqual(action.response_summary["line_count"], 2)

    def test_admin_pod_logs_default_template_appends_selected_container_query(self):
        provider = K8sProvider.objects.create(
            name="rancher-admin-container-logs",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            auth_mode=K8sProvider.AUTH_NONE,
        )
        cluster = K8sCluster.objects.create(
            name="admin-container-logs-cluster",
            environment="test",
            rancher_provider=provider,
            rancher_cluster_id="local",
        )
        user = User.objects.create_user(username="k8s-admin-container-logs", password="password-123")
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
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen["url"] = url
            return "api boot ok\n"

        payload = get_admin_pod_log_snapshot(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{cluster.id}",
            namespace="payments",
            pod_name="payments-api-multi",
            container="api",
            tail_lines=4,
            transport=transport,
        )

        self.assertTrue(payload["available"])
        self.assertEqual(payload["target"]["container"], "api")
        self.assertEqual(
            seen["url"],
            "https://rancher.example.test/k8s/clusters/local/api/v1/namespaces/payments/pods/payments-api-multi/log?tailLines=4&container=api",
        )
        action = K8sAdminAction.objects.get()
        self.assertTrue(action.response_summary["container_present"])
        self.assertNotIn("api boot ok", str(action.response_summary))

    def test_admin_pod_log_stream_batch_appends_selected_container_query(self):
        provider = K8sProvider.objects.create(
            name="rancher-admin-container-stream-logs",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            auth_mode=K8sProvider.AUTH_NONE,
            labels={"pod_logs_stream_path_template": "/k8s/clusters/{cluster_id}/api/v1/namespaces/{namespace}/pods/{pod_name}/log?follow=1&tailLines={tail}"},
        )
        cluster = K8sCluster.objects.create(
            name="admin-container-stream-logs-cluster",
            environment="test",
            rancher_provider=provider,
            rancher_cluster_id="local",
        )
        user = User.objects.create_user(username="k8s-admin-container-stream-logs", password="password-123")
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
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen["url"] = url
            return "sidecar ready\n"

        payload = get_admin_pod_log_stream_batch(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{cluster.id}",
            namespace="payments",
            pod_name="payments-api-multi",
            container="sidecar",
            tail_lines=2,
            timeout_seconds=3,
            transport=transport,
        )

        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "provider_stream_batch")
        self.assertEqual(
            seen["url"],
            "https://rancher.example.test/k8s/clusters/local/api/v1/namespaces/payments/pods/payments-api-multi/log?follow=1&tailLines=2&container=sidecar",
        )
        action = K8sAdminAction.objects.get()
        self.assertTrue(action.response_summary["container_present"])

    def test_admin_pod_log_stream_batch_does_not_duplicate_container_placeholder(self):
        provider = K8sProvider.objects.create(
            name="rancher-admin-container-placeholder-logs",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            auth_mode=K8sProvider.AUTH_NONE,
            labels={"pod_logs_stream_path_template": "/k8s/clusters/{cluster_id}/api/v1/namespaces/{namespace}/pods/{pod_name}/log?follow=1&tailLines={tail}&container={container}"},
        )
        cluster = K8sCluster.objects.create(
            name="admin-container-placeholder-logs-cluster",
            environment="test",
            rancher_provider=provider,
            rancher_cluster_id="local",
        )
        user = User.objects.create_user(username="k8s-admin-container-placeholder-logs", password="password-123")
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
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen["url"] = url
            return "worker ready\n"

        payload = get_admin_pod_log_stream_batch(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{cluster.id}",
            namespace="payments",
            pod_name="payments-api-multi",
            container="worker",
            tail_lines=2,
            timeout_seconds=3,
            transport=transport,
        )

        self.assertTrue(payload["available"])
        self.assertEqual(seen["url"].count("container=worker"), 1)
        self.assertEqual(
            seen["url"],
            "https://rancher.example.test/k8s/clusters/local/api/v1/namespaces/payments/pods/payments-api-multi/log?follow=1&tailLines=2&container=worker",
        )
