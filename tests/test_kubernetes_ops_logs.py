from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAuditEvent, K8sCluster, K8sPodRef, K8sProvider
from kubernetes_ops.services.logs import build_pod_log_snapshot


class KubernetesOpsLogsTests(TestCase):
    def create_user(self, username: str, *, is_staff: bool = False) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=is_staff)
        UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        return user

    def test_pod_logs_returns_404_for_missing_pod(self):
        user = self.create_user("k8s-logs-missing")
        self.client.force_login(user)

        response = self.client.get(reverse("api_kubernetes_pod_logs", kwargs={"pod_id": "pod_404"}))

        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()["success"])

    def test_pod_logs_hides_external_links_for_reader_and_records_audit_metadata(self):
        user = self.create_user("k8s-logs-reader")
        self.client.force_login(user)
        cluster = K8sCluster.objects.create(name="prod-kz-1", environment="prod")
        pod = K8sPodRef.objects.create(
            cluster=cluster,
            namespace="payments",
            name="payments-api-abc123",
            links={
                "logs": "https://devtron.example.test/apps/1/logs?token=raw-url-token#tail",
                "secret_link": "https://secret.example.test",
            },
            labels={"token": "raw-token"},
        )

        response = self.client.get(
            reverse("api_kubernetes_pod_logs", kwargs={"pod_id": f"pod_{pod.id}"}), {"tail": "2"}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertFalse(payload["available"])
        self.assertEqual(payload["source"], "not_configured")
        self.assertFalse(payload["policy"]["mutates_state"])
        self.assertFalse(payload["policy"]["streaming"])
        self.assertIn("exec", payload["policy"]["blocked_actions"])
        self.assertEqual(payload["policy"]["requested_tail_lines"], 2)
        self.assertEqual(payload["target"]["links"], {})
        self.assertFalse(payload["target"]["external_links_policy"]["visible"])
        self.assertEqual(payload["target"]["labels"]["token"], "[redacted]")
        self.assertNotIn("raw-url-token", str(payload))
        self.assertNotIn("raw-token", str(payload))

        event = K8sAuditEvent.objects.get(action="k8s.pod.logs.snapshot")
        self.assertEqual(event.cluster, cluster)
        self.assertEqual(event.payload["pod_id"], f"pod_{pod.id}")
        self.assertEqual(event.payload["line_count"], 0)
        self.assertNotIn("lines", event.payload)
        self.assertNotIn("raw-url-token", str(event.payload))

    def test_pod_logs_uses_default_rancher_proxy_template_when_provider_label_is_absent(self):
        user = self.create_user("k8s-logs-default-template")
        provider = K8sProvider.objects.create(
            name="rancher-default-log-template",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            auth_mode=K8sProvider.AUTH_NONE,
        )
        cluster = K8sCluster.objects.create(
            name="prod-kz-1",
            environment="prod",
            rancher_provider=provider,
            rancher_cluster_id="local",
        )
        pod = K8sPodRef.objects.create(cluster=cluster, namespace="payments", name="payments-api-abc123")
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen["url"] = url
            return "boot ok\nready\n"

        payload = build_pod_log_snapshot(f"pod_{pod.id}", tail_lines=2, transport=transport, user=user)

        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "provider_snapshot")
        self.assertEqual(payload["lines"], ["boot ok", "ready"])
        self.assertEqual(
            seen["url"],
            "https://rancher.example.test/k8s/clusters/local/api/v1/namespaces/payments/pods/payments-api-abc123/log?tailLines=2",
        )

    def test_pod_logs_staff_fallback_links_are_sanitized(self):
        user = self.create_user("k8s-logs-staff", is_staff=True)
        self.client.force_login(user)
        cluster = K8sCluster.objects.create(name="prod-kz-1", environment="prod")
        pod = K8sPodRef.objects.create(
            cluster=cluster,
            namespace="payments",
            name="payments-api-abc123",
            links={
                "logs": "https://devtron.example.test/apps/1/logs?token=raw-url-token#tail",
                "secret_link": "https://secret.example.test",
            },
        )

        response = self.client.get(
            reverse("api_kubernetes_pod_logs", kwargs={"pod_id": f"pod_{pod.id}"}), {"tail": "2"}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["target"]["external_links_policy"]["visible"])
        self.assertEqual(payload["target"]["links"]["logs"], "https://devtron.example.test/apps/1/logs")
        self.assertEqual(payload["target"]["links"]["secret_link"], "[redacted]")
        self.assertNotIn("raw-url-token", str(payload))

    def test_pod_logs_provider_snapshot_is_bounded_and_redacted(self):
        provider = K8sProvider.objects.create(
            name="rancher-main",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            auth_mode=K8sProvider.AUTH_NONE,
            secret_ref="",
            labels={
                "pod_logs_path_template": "/v3/pods/{namespace}:{pod_name}/logs?tail={tail}&cluster={cluster_id}",
            },
        )
        cluster = K8sCluster.objects.create(
            name="prod-kz-1",
            environment="prod",
            rancher_provider=provider,
            rancher_cluster_id="c-prod",
        )
        pod = K8sPodRef.objects.create(cluster=cluster, namespace="payments", name="payments-api-abc123")
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen["url"] = url
            seen["headers"] = headers
            seen["timeout"] = timeout
            return {"logs": "line one\npassword=super-secret\nAuthorization: Bearer abc.def\nlast line"}

        payload = build_pod_log_snapshot(f"pod_{pod.id}", tail_lines=3, transport=transport)

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "provider_snapshot")
        self.assertEqual(payload["line_count"], 3)
        self.assertTrue(payload["truncated"])
        self.assertEqual(
            seen["url"],
            "https://rancher.example.test/v3/pods/payments:payments-api-abc123/logs?tail=3&cluster=c-prod",
        )
        self.assertEqual(payload["lines"][0], "password=[redacted]")
        self.assertEqual(payload["lines"][1], "Authorization: Bearer [redacted]")
        self.assertEqual(payload["lines"][2], "last line")
        self.assertNotIn("super-secret", str(payload))
        self.assertNotIn("abc.def", str(payload))

    def test_pod_logs_provider_plain_text_snapshot_is_bounded_and_redacted(self):
        provider = K8sProvider.objects.create(
            name="rancher-text-logs",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            auth_mode=K8sProvider.AUTH_NONE,
            labels={
                "pod_logs_path_template": "/k8s/clusters/{cluster_id}/api/v1/namespaces/{namespace}/pods/{pod_name}/log?tailLines={tail}"
            },
        )
        cluster = K8sCluster.objects.create(
            name="prod-kz-logs",
            environment="prod",
            rancher_provider=provider,
            rancher_cluster_id="c-prod",
        )
        pod = K8sPodRef.objects.create(cluster=cluster, namespace="payments", name="payments-api-plain")

        def transport(url: str, headers: dict[str, str], timeout: int):
            return "first line\napi_key=raw-secret\nBearer abc.def\nlast line\n"

        payload = build_pod_log_snapshot(f"pod_{pod.id}", tail_lines=3, transport=transport)

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "provider_snapshot")
        self.assertEqual(payload["line_count"], 3)
        self.assertTrue(payload["truncated"])
        self.assertEqual(payload["lines"], ["api_key=[redacted]", "Bearer [redacted]", "last line"])
        self.assertNotIn("raw-secret", str(payload))
        self.assertNotIn("abc.def", str(payload))
