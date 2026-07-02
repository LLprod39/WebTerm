from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAuditEvent, K8sProvider
from kubernetes_ops.services.provider_probe import KubernetesProviderProbeResult, probe_kubernetes_provider


class KubernetesOpsProviderProbeTests(TestCase):
    def create_user(self, username: str, *, is_staff: bool = False) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=is_staff)
        UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        return user

    def test_provider_probe_uses_default_path_and_returns_safe_shape(self):
        provider = K8sProvider.objects.create(
            name="rancher-main",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            secret_ref="env:RANCHER_TOKEN",
        )

        def transport(url: str, headers: dict[str, str], timeout: int):
            self.assertEqual(url, "https://rancher.example.test/v3/clusters")
            self.assertEqual(headers["Authorization"], "Bearer probe-token")
            self.assertGreater(timeout, 0)
            return {"data": [{"id": "c-stage"}, {"id": "c-prod"}], "token": "provider-should-not-leak"}

        with patch.dict("os.environ", {"RANCHER_TOKEN": "probe-token"}):
            result = probe_kubernetes_provider(provider, transport=transport)

        self.assertTrue(result.success)
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.path, "/v3/clusters")
        self.assertEqual(result.item_count, 2)
        self.assertIn("data", result.payload_keys)
        self.assertIn("[redacted]", result.payload_keys)
        self.assertNotIn("provider-should-not-leak", str(result))
        self.assertNotIn("probe-token", str(result))

    def test_provider_probe_uses_explicit_path_and_redacts_transport_errors(self):
        provider = K8sProvider.objects.create(
            name="devtron-main",
            kind=K8sProvider.KIND_DEVTRON,
            base_url="https://devtron.example.test",
            secret_ref="env:DEVTRON_TOKEN",
            labels={"probe_path": "/orchestrator/app/list?token=query-token"},
        )

        def transport(url: str, headers: dict[str, str], timeout: int):
            self.assertEqual(url, "https://devtron.example.test/orchestrator/app/list?token=query-token")
            raise RuntimeError("upstream rejected secret-devtron-token")

        with patch.dict("os.environ", {"DEVTRON_TOKEN": "secret-devtron-token"}):
            result = probe_kubernetes_provider(provider, transport=transport)

        self.assertFalse(result.success)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.path, "/orchestrator/app/list")
        self.assertIn("***", result.error)
        self.assertNotIn("secret-devtron-token", result.error)
        self.assertNotIn("query-token", result.path)

    def test_devtron_provider_probe_uses_session_auth_when_configured(self):
        provider = K8sProvider.objects.create(
            name="devtron-local",
            kind=K8sProvider.KIND_DEVTRON,
            base_url="http://devtron.example.test",
            secret_ref="env:DEVTRON_ADMIN_PASSWORD",
            labels={
                "auth_strategy": "devtron_session",
                "auth_username": "admin",
                "login_path": "/orchestrator/api/v1/session",
                "probe_path": "/orchestrator/devtron/auth/verify/v2",
            },
        )
        calls = []

        def transport(url: str, headers: dict[str, str], timeout: int, *, method: str = "GET", body=None):
            calls.append((method, url, headers, body))
            if url.endswith("/orchestrator/api/v1/session"):
                self.assertEqual(method, "POST")
                self.assertEqual(body, {"username": "admin", "password": "devtron-admin-password"})
                self.assertNotIn("Authorization", headers)
                return {"result": {"token": "session-token"}}
            if url.endswith("/orchestrator/devtron/auth/verify/v2"):
                self.assertEqual(method, "GET")
                self.assertEqual(headers["Cookie"], "argocd.token=session-token")
                self.assertEqual(headers["token"], "session-token")
                self.assertNotIn("Authorization", headers)
                return {"emailId": "admin", "isSuperAdmin": True, "isVerified": True}
            raise AssertionError(url)

        with patch.dict("os.environ", {"DEVTRON_ADMIN_PASSWORD": "devtron-admin-password"}):
            result = probe_kubernetes_provider(provider, transport=transport)

        self.assertTrue(result.success)
        self.assertEqual(result.path, "/orchestrator/devtron/auth/verify/v2")
        self.assertEqual([call[0] for call in calls], ["POST", "GET"])

    def test_provider_probe_endpoint_requires_staff(self):
        user = self.create_user("k8s-reader")
        self.client.force_login(user)
        provider = K8sProvider.objects.create(
            name="rancher-main",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            auth_mode=K8sProvider.AUTH_NONE,
        )

        response = self.client.post(reverse("api_kubernetes_provider_probe", kwargs={"provider_id": provider.id}))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_required")

    def test_provider_probe_endpoint_audits_metadata_without_payload(self):
        user = self.create_user("k8s-admin-probe", is_staff=True)
        self.client.force_login(user)
        provider = K8sProvider.objects.create(
            name="rancher-main",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            auth_mode=K8sProvider.AUTH_NONE,
        )
        result = KubernetesProviderProbeResult(
            provider_id=provider.id,
            provider_name=provider.name,
            provider_kind=provider.kind,
            success=True,
            status="ready",
            path="/v3/clusters",
            item_count=2,
            payload_keys=("data",),
            duration_ms=12,
            checked_at="2026-06-30T08:00:00+00:00",
        )

        with patch("kubernetes_ops.probe_views.probe_kubernetes_provider", return_value=result):
            response = self.client.post(reverse("api_kubernetes_provider_probe", kwargs={"provider_id": provider.id}))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["probe"]["path"], "/v3/clusters")
        self.assertEqual(payload["probe"]["item_count"], 2)
        event = K8sAuditEvent.objects.get(action="k8s.provider.probe")
        self.assertEqual(event.provider, "rancher-main")
        self.assertEqual(event.payload["status"], "ready")
        self.assertEqual(event.payload["item_count"], 2)
        self.assertNotIn("payload_keys", event.payload)
