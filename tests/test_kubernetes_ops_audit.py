import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAppRef, K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.serializers import serialize_cluster_event


class KubernetesOpsAuditTests(TestCase):
    def create_user(self, username: str, *, is_staff: bool = False) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=is_staff)
        UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        return user

    def test_audit_endpoint_is_read_only_and_serializes_events(self):
        user = self.create_user("k8s-audit-reader")
        self.client.force_login(user)
        cluster = K8sCluster.objects.create(name="audit-cluster")
        K8sAuditEvent.objects.create(
            user=user,
            username_snapshot=user.username,
            action="k8s.view.overview",
            provider="webterm",
            cluster=cluster,
            payload={"source": "test"},
        )

        response = self.client.get(reverse("api_kubernetes_audit"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["events"][0]["action"], "k8s.view.overview")
        self.assertEqual(payload["events"][0]["cluster"], "audit-cluster")

    def test_audit_serializers_redact_raw_payload_secrets_as_fail_safe(self):
        user = self.create_user("k8s-audit-redaction")
        self.client.force_login(user)
        cluster = K8sCluster.objects.create(name="audit-redaction-cluster")
        event = K8sAuditEvent.objects.create(
            user=user,
            username_snapshot=user.username,
            action="k8s.audit.redaction",
            provider="webterm",
            cluster=cluster,
            payload={
                "token": "raw-audit-token",
                "message": "password=raw-audit-password\nAuthorization: Bearer abc.def",
                "url": "https://bot:raw-url-password@rancher.example.test/path?token=raw-url-token#frag",
                "nested": {"dsn": "postgres://user:raw-db-password@db:5432/app"},
            },
        )

        response = self.client.get(reverse("api_kubernetes_audit"))
        cluster_event = serialize_cluster_event(event)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        serialized = str(payload) + str(cluster_event)
        for raw in ("raw-audit-token", "raw-audit-password", "raw-url-password", "raw-url-token", "raw-db-password", "abc.def"):
            self.assertNotIn(raw, serialized)
        self.assertEqual(payload["events"][0]["payload"]["token"], "[redacted]")
        self.assertEqual(payload["events"][0]["payload"]["url"], "https://rancher.example.test/path")

    def test_deeplink_audit_records_sanitized_url_and_cluster_context_for_staff(self):
        user = self.create_user("k8s-deeplink-staff", is_staff=True)
        self.client.force_login(user)
        cluster = K8sCluster.objects.create(name="prod-kz-1")
        app = K8sAppRef.objects.create(
            name="payments-api",
            cluster=cluster,
            namespace="payments",
            owner=K8sAppRef.OWNER_DEVTRON,
            health=K8sCluster.HEALTH_HEALTHY,
            links={"logs": "https://devtron.example.test/logs?token=secret"},
        )

        response = self.client.post(
            reverse("api_kubernetes_deeplink_audit"),
            data=json.dumps(
                {
                    "target_type": "app",
                    "target_id": f"app_{app.id}",
                    "target_name": app.name,
                    "link_key": "logs",
                    "url": "https://devtron.example.test/logs?token=secret#tail",
                    "provider": K8sProvider.KIND_DEVTRON,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        event = K8sAuditEvent.objects.get(action="k8s.deeplink.open")
        self.assertEqual(event.cluster, cluster)
        self.assertEqual(event.provider, K8sProvider.KIND_DEVTRON)
        self.assertEqual(event.payload["target_name"], "payments-api")
        self.assertEqual(event.payload["url"], "https://devtron.example.test/logs")
        self.assertEqual(event.payload["host"], "devtron.example.test")
        self.assertNotIn("secret", str(event.payload))

    def test_deeplink_audit_rejects_reader_before_recording_external_url(self):
        user = self.create_user("k8s-deeplink-reader")
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_deeplink_audit"),
            data=json.dumps(
                {
                    "target_type": "app",
                    "target_id": "app_1",
                    "target_name": "payments-api",
                    "link_key": "logs",
                    "url": "https://devtron.example.test/logs?token=secret#tail",
                    "provider": K8sProvider.KIND_DEVTRON,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_required")
        self.assertFalse(K8sAuditEvent.objects.filter(action="k8s.deeplink.open").exists())

    def test_deeplink_audit_rejects_non_http_urls(self):
        user = self.create_user("k8s-deeplink-invalid", is_staff=True)
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_deeplink_audit"),
            data=json.dumps({"target_type": "cluster", "link_key": "rancher", "url": "javascript:alert(1)"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("http(s)", response.json()["error"])
        self.assertFalse(K8sAuditEvent.objects.exists())
