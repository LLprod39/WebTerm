import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_schema_validation import validate_kubernetes_manifest_schema


class KubernetesOpsAdminSchemaValidationTests(TestCase):
    def create_user(self, username: str, *, grant_kubernetes: bool = True, grant_admin_write: bool = False) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        if grant_kubernetes:
            UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        if grant_admin_write:
            UserAppPermission.objects.create(user=user, feature="kubernetes_admin_write", allowed=True)
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

    def create_write_session(self, user: User, **kwargs) -> K8sAdminSession:
        defaults = {
            "user": user,
            "username_snapshot": user.username,
            "cluster": self.cluster,
            "mode": K8sAdminSession.MODE_WRITE,
            "status": K8sAdminSession.STATUS_ACTIVE,
            "risk_tier": K8sAdminSession.RISK_HIGH,
            "allowed_verbs": ["get", "list", "watch", "logs", "yaml", "dry_run_apply"],
            "allowed_kinds": ["Widget", "Deployment"],
            "allowed_namespaces": ["payments"],
            "reason": "validate custom resource manifest before dry-run",
            "approval_ref": "CHG-2026-SCHEMA",
            "approved_by": user,
            "approved_at": timezone.now(),
            "expires_at": timezone.now() + timedelta(minutes=30),
        }
        defaults.update(kwargs)
        return K8sAdminSession.objects.create(**defaults)

    def widget_manifest(self) -> dict:
        return {
            "apiVersion": "apps.example.com/v1",
            "kind": "Widget",
            "metadata": {"name": "payments-widget", "namespace": "payments"},
            "spec": {"size": "large", "token": "raw-widget-token"},
        }

    def crd_payload(self) -> dict:
        return {
            "items": [
                {
                    "metadata": {"name": "widgets.apps.example.com"},
                    "spec": {
                        "group": "apps.example.com",
                        "names": {"kind": "Widget", "plural": "widgets"},
                        "versions": [
                            {
                                "name": "v1",
                                "served": True,
                                "schema": {
                                    "openAPIV3Schema": {
                                        "type": "object",
                                        "required": ["apiVersion", "kind", "metadata", "spec"],
                                        "properties": {
                                            "spec": {
                                                "type": "object",
                                                "required": ["size", "mode"],
                                                "properties": {
                                                    "size": {"type": "integer", "minimum": 1},
                                                    "mode": {"type": "string", "enum": ["safe", "fast"]},
                                                },
                                            }
                                        },
                                    }
                                },
                            }
                        ],
                    },
                }
            ]
        }

    def test_schema_validation_uses_crd_openapi_schema_and_records_metadata_only(self):
        user = self.create_user("k8s-schema-writer", grant_admin_write=True)
        session = self.create_write_session(user)
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int):
            seen["url"] = url
            return self.crd_payload()

        payload = validate_kubernetes_manifest_schema(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            manifest=self.widget_manifest(),
            transport=transport,
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["operation"], "schema_validate")
        self.assertFalse(payload["mutates_state"])
        self.assertTrue(payload["schema_available"])
        self.assertFalse(payload["valid"])
        self.assertEqual(payload["validation"]["status"], "invalid")
        self.assertIn("$.spec.size", {error["path"] for error in payload["validation"]["errors"]})
        self.assertIn("$.spec.mode", {error["path"] for error in payload["validation"]["errors"]})
        self.assertEqual(payload["path"], "/k8s/clusters/c-prod/apis/apiextensions.k8s.io/v1/customresourcedefinitions")
        self.assertIn("/customresourcedefinitions", seen["url"])
        self.assertTrue(payload["redacted"])
        self.assertFalse(payload["submitted_summary"]["body_returned"])
        self.assertNotIn("raw-widget-token", str(payload))

        action = K8sAdminAction.objects.get()
        self.assertEqual(action.verb, K8sAdminAction.VERB_LIST)
        self.assertEqual(action.status, K8sAdminAction.STATUS_COMPLETED)
        self.assertTrue(action.request_payload_sanitized["schema_validation"])
        self.assertTrue(action.request_payload_sanitized["redacted"])
        self.assertEqual(action.response_summary["validation_status"], "invalid")
        self.assertEqual(action.response_summary["error_count"], 2)
        self.assertNotIn("raw-widget-token", str(action.request_payload_sanitized))
        self.assertNotIn("raw-widget-token", str(action.response_summary))

    def test_schema_validation_api_audits_counts_without_manifest_body(self):
        user = self.create_user("k8s-schema-api", grant_admin_write=True)
        session = self.create_write_session(user)
        self.client.force_login(user)

        with patch("kubernetes_ops.services.admin_schema_validation.ProviderJsonClient") as client_cls:
            client_cls.return_value.get.return_value = self.crd_payload()
            response = self.client.post(
                reverse("api_kubernetes_admin_schema_validate", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
                data=json.dumps({"session_id": str(session.session_id), "manifest": self.widget_manifest()}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["validation"]["status"], "invalid")
        self.assertNotIn("raw-widget-token", str(payload))
        audit = K8sAuditEvent.objects.get(action="k8s.admin_resource.schema_validate")
        self.assertEqual(audit.payload["validation_status"], "invalid")
        self.assertEqual(audit.payload["error_count"], 2)
        self.assertNotIn("raw-widget-token", str(audit.payload))

    def test_schema_validation_without_matching_crd_is_non_mutating_schema_unavailable(self):
        user = self.create_user("k8s-schema-missing", grant_admin_write=True)
        session = self.create_write_session(user)

        payload = validate_kubernetes_manifest_schema(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            manifest={
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "payments-api", "namespace": "payments"},
                "spec": {"replicas": 1},
            },
            transport=lambda *args, **kwargs: {"items": []},
        )

        self.assertTrue(payload["success"])
        self.assertFalse(payload["schema_available"])
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["validation"]["status"], "schema_unavailable")
        self.assertEqual(payload["schema_source"]["reason"], "crd_schema_not_found")

    def test_regular_kubernetes_user_cannot_validate_schema_without_admin_write(self):
        user = self.create_user("k8s-schema-regular")
        session = self.create_write_session(user)
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_admin_schema_validate", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
            data=json.dumps({"session_id": str(session.session_id), "manifest": self.widget_manifest()}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_write_required")
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_resource.schema_validate_rejected").exists())
