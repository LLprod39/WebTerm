import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_dry_run import dry_run_apply_kubernetes_resource
from kubernetes_ops.services.admin_resources import AdminResourceError


class KubernetesOpsAdminDryRunTests(TestCase):
    def create_user(
        self,
        username: str,
        *,
        grant_kubernetes: bool = True,
        grant_admin_read: bool = False,
        grant_admin_write: bool = False,
    ) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        grants = {
            "kubernetes": grant_kubernetes,
            "kubernetes_admin_read": grant_admin_read,
            "kubernetes_admin_write": grant_admin_write,
        }
        for feature, allowed in grants.items():
            if allowed:
                UserAppPermission.objects.create(user=user, feature=feature, allowed=True)
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
            "allowed_kinds": ["Deployment", "Service", "Ingress"],
            "allowed_namespaces": ["payments"],
            "reason": "validate manifest through server-side dry-run",
            "approval_ref": "CHG-2026-DRY-RUN",
            "approved_by": user,
            "approved_at": timezone.now(),
            "expires_at": timezone.now() + timedelta(minutes=30),
        }
        defaults.update(kwargs)
        return K8sAdminSession.objects.create(**defaults)

    def deployment_manifest(self) -> str:
        return """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payments-api
  namespace: payments
  labels:
    app: payments
spec:
  replicas: 1
"""

    def test_admin_write_session_dry_runs_apply_through_rancher_without_mutating_state(self):
        user = self.create_user("k8s-admin-dry-run", grant_admin_write=True)
        session = self.create_write_session(user)
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int, *, method: str = "GET", body=None):
            seen.update({"url": url, "headers": headers, "method": method, "body": body, "timeout": timeout})
            return {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "payments-api", "namespace": "payments", "managedFields": [{"manager": "webterm"}]},
                "spec": {"replicas": 2},
                "status": {"observedGeneration": 10},
            }

        payload = dry_run_apply_kubernetes_resource(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            manifest_yaml=self.deployment_manifest(),
            transport=transport,
        )

        self.assertTrue(payload["success"])
        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["mutates_state"])
        self.assertEqual(payload["operation"], "dry_run_apply")
        self.assertEqual(payload["target"]["kind"], "Deployment")
        self.assertEqual(payload["path"], "/k8s/clusters/c-prod/apis/apps/v1/namespaces/payments/deployments/payments-api")
        self.assertEqual(seen["method"], "PATCH")
        self.assertIn("dryRun=All", seen["url"])
        self.assertIn("fieldManager=webterm-admin-mode", seen["url"])
        self.assertEqual(seen["headers"]["Content-Type"], "application/apply-patch+yaml")
        self.assertEqual(seen["body"]["spec"]["replicas"], 1)
        self.assertIn("status", payload["diff_summary"]["server_added_top_level_fields"])
        changes_by_path = {item["path"]: item for item in payload["diff"]["changes"]}
        self.assertEqual(changes_by_path["/spec/replicas"]["operation"], "changed")
        self.assertEqual(changes_by_path["/spec/replicas"]["before"]["value"], 1)
        self.assertEqual(changes_by_path["/spec/replicas"]["after"]["value"], 2)
        self.assertEqual(changes_by_path["/status"]["operation"], "added")
        self.assertFalse(payload["diff"]["truncated"])
        self.assertIn("apply_yaml", payload["policy"]["blocked_actions"])

        action = K8sAdminAction.objects.get()
        self.assertEqual(action.verb, K8sAdminAction.VERB_DRY_RUN_APPLY)
        self.assertEqual(action.status, K8sAdminAction.STATUS_DRY_RUN)
        self.assertEqual(action.resource_kind, "Deployment")
        self.assertEqual(action.response_summary["dry_run"], True)
        self.assertEqual(action.response_summary["diff_change_count"], payload["diff"]["change_count"])
        self.assertEqual(action.diff_summary["available"], True)
        self.assertNotIn("changes", action.diff_summary)

    def test_dry_run_requires_admin_write_policy_and_active_write_session(self):
        reader = self.create_user("k8s-reader-only", grant_admin_read=True)
        read_session = K8sAdminSession.objects.create(
            user=reader,
            username_snapshot=reader.username,
            cluster=self.cluster,
            mode=K8sAdminSession.MODE_READ,
            status=K8sAdminSession.STATUS_ACTIVE,
            risk_tier=K8sAdminSession.RISK_LOW,
            allowed_verbs=["get", "list", "watch", "logs", "yaml"],
            allowed_kinds=["*"],
            allowed_namespaces=["*"],
            expires_at=timezone.now() + timedelta(hours=1),
        )

        with self.assertRaises(AdminResourceError) as denied:
            dry_run_apply_kubernetes_resource(
                user=reader,
                session_id=str(read_session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                manifest_yaml=self.deployment_manifest(),
                transport=lambda *args, **kwargs: {},
            )
        self.assertEqual(denied.exception.code, "admin_write_required")

        writer = self.create_user("k8s-writer-pending", grant_admin_write=True)
        pending_session = self.create_write_session(writer, status=K8sAdminSession.STATUS_PENDING_APPROVAL)
        with self.assertRaises(AdminResourceError) as inactive:
            dry_run_apply_kubernetes_resource(
                user=writer,
                session_id=str(pending_session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                manifest_yaml=self.deployment_manifest(),
                transport=lambda *args, **kwargs: {},
            )
        self.assertEqual(inactive.exception.code, "admin_write_session_not_active")
        self.assertFalse(K8sAdminAction.objects.exists())

    def test_dry_run_requires_approved_write_session_before_provider_call(self):
        user = self.create_user("k8s-admin-dry-run-unapproved", grant_admin_write=True)
        session = self.create_write_session(user, approval_ref="", approved_by=None, approved_at=None)

        with self.assertRaises(AdminResourceError) as denied:
            dry_run_apply_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                manifest_yaml=self.deployment_manifest(),
                transport=lambda *args, **kwargs: self.fail("provider must not be called"),
            )

        self.assertEqual(denied.exception.code, "admin_session_approval_required")
        self.assertEqual(denied.exception.payload["action"], K8sAdminAction.VERB_DRY_RUN_APPLY)
        self.assertFalse(K8sAdminAction.objects.exists())

    def test_dry_run_respects_session_namespace_and_kind_scope(self):
        user = self.create_user("k8s-admin-scope", grant_admin_write=True)
        session = self.create_write_session(user, allowed_kinds=["Service"], allowed_namespaces=["platform"])

        with self.assertRaises(AdminResourceError) as denied:
            dry_run_apply_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                manifest_yaml=self.deployment_manifest(),
                transport=lambda *args, **kwargs: {},
            )

        self.assertEqual(denied.exception.code, "admin_session_namespace_denied")
        self.assertFalse(K8sAdminAction.objects.exists())

    def test_secret_dry_run_redacts_payload_response_action_and_audit(self):
        user = self.create_user("k8s-admin-secret-dry-run", grant_admin_write=True)
        session = self.create_write_session(user, allowed_kinds=["Secret"])
        self.client.force_login(user)

        with patch("kubernetes_ops.services.admin_dry_run.ProviderJsonClient") as client_cls:
            client_cls.return_value.request.return_value = {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": "db-creds", "namespace": "payments"},
                "data": {"password": "cGFzc3dvcmQ="},
                "stringData": {"dsn": "postgres://raw-secret"},
            }
            response = self.client.post(
                reverse("api_kubernetes_admin_dry_run_apply", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
                data=json.dumps(
                    {
                        "session_id": str(session.session_id),
                        "manifest_yaml": """
apiVersion: v1
kind: Secret
metadata:
  name: db-creds
  namespace: payments
stringData:
  dsn: postgres://raw-secret
""",
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["redacted"])
        self.assertTrue(payload["diff"]["redacted"])
        self.assertEqual(payload["submitted"]["stringData"]["dsn"], "[redacted]")
        self.assertEqual(payload["resource"]["data"]["password"], "[redacted]")
        self.assertNotIn("postgres://raw-secret", str(payload))
        self.assertNotIn("cGFzc3dvcmQ=", str(payload))

        action = K8sAdminAction.objects.get()
        self.assertTrue(action.request_payload_sanitized["redacted"])
        self.assertTrue(action.response_summary["redacted"])
        self.assertIn("diff_change_count", action.response_summary)
        self.assertNotIn("changes", action.diff_summary)
        self.assertNotIn("postgres://raw-secret", str(action.request_payload_sanitized))
        self.assertNotIn("postgres://raw-secret", str(action.response_summary))
        audit = K8sAuditEvent.objects.get(action="k8s.admin_resource.dry_run_apply")
        self.assertEqual(audit.payload["target"]["kind"], "Secret")
        self.assertTrue(audit.payload["redacted"])
        self.assertIn("diff_change_count", audit.payload)
        self.assertNotIn("changes", str(audit.payload))
        self.assertNotIn("postgres://raw-secret", str(audit.payload))

    def test_api_rejects_invalid_manifest_yaml_with_audit_metadata_only(self):
        user = self.create_user("k8s-admin-invalid-yaml", grant_admin_write=True)
        session = self.create_write_session(user)
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_admin_dry_run_apply", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
            data=json.dumps({"session_id": str(session.session_id), "manifest_yaml": "kind: ["}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "manifest_yaml_invalid")
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_resource.dry_run_apply_rejected").exists())
        self.assertFalse(K8sAdminAction.objects.exists())
