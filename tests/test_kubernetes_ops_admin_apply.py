import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_apply import apply_kubernetes_resource
from kubernetes_ops.services.admin_dry_run import dry_run_apply_kubernetes_resource
from kubernetes_ops.services.admin_resources import AdminResourceError


class KubernetesOpsAdminApplyTests(TestCase):
    def create_user(
        self,
        username: str,
        *,
        grant_kubernetes: bool = True,
        grant_admin_write: bool = False,
        grant_break_glass: bool = False,
    ) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        if grant_kubernetes:
            UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        if grant_admin_write:
            UserAppPermission.objects.create(user=user, feature="kubernetes_admin_write", allowed=True)
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
            "allowed_verbs": ["get", "list", "watch", "logs", "yaml", "dry_run_apply", "apply"],
            "allowed_kinds": ["Deployment", "Service", "Ingress", "Secret"],
            "allowed_namespaces": ["payments"],
            "reason": "apply after server-side dry-run",
            "approval_ref": "CHG-2026-APPLY",
            "approved_by": user,
            "approved_at": timezone.now(),
            "expires_at": timezone.now() + timedelta(minutes=30),
        }
        defaults.update(kwargs)
        return K8sAdminSession.objects.create(**defaults)

    def create_break_glass_session(self, user: User, **kwargs) -> K8sAdminSession:
        defaults = {
            "user": user,
            "username_snapshot": user.username,
            "cluster": self.cluster,
            "mode": K8sAdminSession.MODE_BREAK_GLASS,
            "status": K8sAdminSession.STATUS_ACTIVE,
            "risk_tier": K8sAdminSession.RISK_CRITICAL,
            "allowed_verbs": ["get", "list", "watch", "logs", "yaml", "apply"],
            "allowed_kinds": ["Deployment"],
            "allowed_namespaces": ["payments"],
            "reason": "break-glass apply during incident",
            "approval_ref": "INC-2026-APPLY",
            "approved_by": user,
            "approved_at": timezone.now(),
            "expires_at": timezone.now() + timedelta(minutes=15),
        }
        defaults.update(kwargs)
        return K8sAdminSession.objects.create(**defaults)

    def deployment_manifest(self, *, replicas: int = 1) -> dict:
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "payments-api", "namespace": "payments", "labels": {"app": "payments"}},
            "spec": {"replicas": replicas},
        }

    def create_dry_run_proof(self, user: User, session: K8sAdminSession, manifest: dict | None = None) -> K8sAdminAction:
        dry_run_apply_kubernetes_resource(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            manifest=manifest or self.deployment_manifest(),
            transport=lambda *args, **kwargs: manifest or self.deployment_manifest(),
        )
        return K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_DRY_RUN_APPLY)

    def test_apply_is_disabled_by_default_before_provider_call(self):
        user = self.create_user("k8s-apply-disabled", grant_admin_write=True)
        session = self.create_write_session(user)

        with self.assertRaises(AdminResourceError) as denied:
            apply_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                dry_run_action_id="missing",
                reason="apply deployment",
                manifest=self.deployment_manifest(),
                transport=lambda *args, **kwargs: self.fail("provider must not be called"),
            )

        self.assertEqual(denied.exception.code, "native_apply_disabled")
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=True)
    def test_apply_requires_matching_successful_dry_run_proof(self):
        user = self.create_user("k8s-apply-proof", grant_admin_write=True)
        session = self.create_write_session(user)

        with self.assertRaises(AdminResourceError) as missing:
            apply_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                dry_run_action_id="",
                reason="apply deployment",
                manifest=self.deployment_manifest(),
                transport=lambda *args, **kwargs: {},
            )
        self.assertEqual(missing.exception.code, "dry_run_proof_required")

        proof = self.create_dry_run_proof(user, session, self.deployment_manifest(replicas=1))
        with self.assertRaises(AdminResourceError) as mismatch:
            apply_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                dry_run_action_id=str(proof.action_id),
                reason="apply deployment",
                manifest=self.deployment_manifest(replicas=2),
                transport=lambda *args, **kwargs: {},
            )

        self.assertEqual(mismatch.exception.code, "dry_run_manifest_mismatch")
        self.assertEqual(K8sAdminAction.objects.count(), 1)

    @override_settings(KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=True)
    def test_break_glass_apply_bypass_is_disabled_without_explicit_flag(self):
        user = self.create_user("k8s-apply-break-glass-disabled", grant_break_glass=True)
        session = self.create_break_glass_session(user)

        with self.assertRaises(AdminResourceError) as denied:
            apply_kubernetes_resource(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                dry_run_action_id="",
                reason="incident apply",
                manifest=self.deployment_manifest(),
                transport=lambda *args, **kwargs: self.fail("provider must not be called"),
            )

        self.assertEqual(denied.exception.code, "break_glass_apply_disabled")
        self.assertFalse(K8sAdminAction.objects.exists())

    @override_settings(KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=True)
    def test_apply_uses_dry_run_proof_and_patches_without_dryrun(self):
        user = self.create_user("k8s-apply-success", grant_admin_write=True)
        session = self.create_write_session(user)
        proof = self.create_dry_run_proof(user, session)
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int, *, method: str = "GET", body=None):
            seen.update({"url": url, "headers": headers, "method": method, "body": body})
            return {**self.deployment_manifest(), "status": {"observedGeneration": 11}}

        payload = apply_kubernetes_resource(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            dry_run_action_id=str(proof.action_id),
            reason="apply deployment",
            manifest=self.deployment_manifest(),
            transport=transport,
        )

        self.assertTrue(payload["success"])
        self.assertFalse(payload["dry_run"])
        self.assertTrue(payload["mutates_state"])
        self.assertEqual(payload["operation"], "apply")
        self.assertEqual(seen["method"], "PATCH")
        self.assertIn("fieldManager=webterm-admin-mode", seen["url"])
        self.assertNotIn("dryRun=All", seen["url"])
        self.assertEqual(seen["headers"]["Content-Type"], "application/apply-patch+yaml")
        action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_APPLY)
        self.assertEqual(action.status, K8sAdminAction.STATUS_COMPLETED)
        self.assertEqual(action.response_summary["dry_run_action_id"], str(proof.action_id))
        self.assertEqual(action.diff_summary["available"], True)

    @override_settings(KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=True, KUBERNETES_ADMIN_BREAK_GLASS_APPLY_BYPASS_ENABLED=True)
    def test_break_glass_apply_bypasses_dry_run_with_explicit_audit_marker(self):
        user = self.create_user("k8s-break-glass-apply", grant_break_glass=True)
        session = self.create_break_glass_session(user)
        seen = {}

        def transport(url: str, headers: dict[str, str], timeout: int, *, method: str = "GET", body=None):
            seen.update({"url": url, "headers": headers, "method": method, "body": body})
            return {**self.deployment_manifest(), "status": {"observedGeneration": 12}}

        payload = apply_kubernetes_resource(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            dry_run_action_id="",
            reason="incident approved break-glass apply",
            manifest=self.deployment_manifest(),
            transport=transport,
        )

        self.assertTrue(payload["success"])
        self.assertTrue(payload["break_glass"])
        self.assertIsNone(payload["dry_run_proof"])
        self.assertFalse(payload["policy"]["requires_dry_run_proof"])
        self.assertTrue(payload["policy"]["requires_break_glass_session"])
        self.assertTrue(payload["policy"]["dry_run_bypassed"])
        self.assertEqual(seen["method"], "PATCH")
        self.assertNotIn("dryRun=All", seen["url"])
        action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_APPLY)
        self.assertEqual(action.status, K8sAdminAction.STATUS_COMPLETED)
        self.assertTrue(action.request_payload_sanitized["dry_run_bypassed"])
        self.assertTrue(action.request_payload_sanitized["break_glass"])
        self.assertEqual(action.request_payload_sanitized["approval_ref"], "INC-2026-APPLY")
        self.assertTrue(action.response_summary["dry_run_bypassed"])
        self.assertEqual(action.response_summary["break_glass_session_id"], str(session.session_id))
        self.assertEqual(action.diff_summary["reason"], "break_glass_dry_run_bypass")

    @override_settings(KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=True)
    def test_apply_api_redacts_secret_payload_response_action_and_audit(self):
        user = self.create_user("k8s-secret-apply", grant_admin_write=True)
        session = self.create_write_session(user)
        self.client.force_login(user)
        manifest = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "db-creds", "namespace": "payments"},
            "stringData": {"dsn": "postgres://raw-secret"},
        }
        proof = self.create_dry_run_proof(user, session, manifest)

        with patch("kubernetes_ops.services.admin_apply.ProviderJsonClient") as client_cls:
            client_cls.return_value.request.return_value = {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": "db-creds", "namespace": "payments"},
                "data": {"password": "cGFzc3dvcmQ="},
                "stringData": {"dsn": "postgres://raw-secret"},
            }
            response = self.client.post(
                reverse("api_kubernetes_admin_apply", kwargs={"cluster_id": f"cluster_{self.cluster.id}"}),
                data=json.dumps(
                    {
                        "session_id": str(session.session_id),
                        "dry_run_action_id": str(proof.action_id),
                        "reason": "apply secret after dry-run proof",
                        "manifest": manifest,
                    }
                ),
                content_type="application/json",
            )
            called_path = client_cls.return_value.request.call_args.args[1]

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["redacted"])
        self.assertEqual(payload["resource"]["data"]["password"], "[redacted]")
        self.assertNotIn("postgres://raw-secret", str(payload))
        self.assertNotIn("cGFzc3dvcmQ=", str(payload))
        self.assertIn("fieldManager=webterm-admin-mode", called_path)
        self.assertNotIn("dryRun=All", called_path)

        action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_APPLY)
        self.assertTrue(action.request_payload_sanitized["redacted"])
        self.assertTrue(action.response_summary["redacted"])
        self.assertNotIn("postgres://raw-secret", str(action.request_payload_sanitized))
        self.assertNotIn("postgres://raw-secret", str(action.response_summary))
        audit = K8sAuditEvent.objects.get(action="k8s.admin_resource.apply")
        self.assertEqual(audit.payload["target"]["kind"], "Secret")
        self.assertTrue(audit.payload["redacted"])
        self.assertNotIn("postgres://raw-secret", str(audit.payload))
