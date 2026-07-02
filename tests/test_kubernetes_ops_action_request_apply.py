import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sActionRequest, K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_dry_run import manifest_fingerprint


class KubernetesOpsActionRequestApplyTests(TestCase):
    def create_user(self, username: str, *, is_staff: bool = False) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=is_staff)
        UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
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

    def deployment_manifest(self, *, replicas: int = 2) -> dict:
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "payments-api", "namespace": "payments"},
            "spec": {"replicas": replicas, "template": {"metadata": {"labels": {"app": "payments-api"}}, "spec": {"containers": [{"name": "api", "image": "registry.example.test/payments:1"}]}}},
        }

    def write_session(self, user: User) -> K8sAdminSession:
        return K8sAdminSession.objects.create(
            user=user,
            username_snapshot=user.username,
            cluster=self.cluster,
            mode=K8sAdminSession.MODE_WRITE,
            status=K8sAdminSession.STATUS_ACTIVE,
            risk_tier=K8sAdminSession.RISK_HIGH,
            allowed_verbs=["get", "list", "watch", "logs", "yaml", "dry_run_apply", "apply"],
            allowed_kinds=["Deployment"],
            allowed_namespaces=["payments"],
            reason="apply action request after approval",
            approval_ref="CHG-ACTION-APPLY",
            approved_by=user,
            approved_at=timezone.now(),
            expires_at=timezone.now() + timedelta(minutes=30),
        )

    def dry_run_proof(self, user: User, session: K8sAdminSession, manifest: dict | None = None) -> K8sAdminAction:
        manifest = manifest or self.deployment_manifest()
        return K8sAdminAction.objects.create(
            session=session,
            user=user,
            username_snapshot=user.username,
            cluster=self.cluster,
            namespace="payments",
            resource_api_version="apps/v1",
            resource_kind="Deployment",
            resource_name="payments-api",
            verb=K8sAdminAction.VERB_DRY_RUN_APPLY,
            status=K8sAdminAction.STATUS_DRY_RUN,
            request_payload_sanitized={
                "target": {"api_version": "apps/v1", "kind": "Deployment", "resource": "deployments", "namespace": "payments", "name": "payments-api"},
                "manifest_fingerprint": manifest_fingerprint(manifest),
                "submitted_top_level_fields": sorted(manifest.keys()),
                "redacted": False,
            },
            diff_summary={"available": True, "changed": True},
            response_summary={"dry_run": True},
        )

    def test_staff_can_request_apply_preview_from_dry_run_proof_without_storing_manifest(self):
        staff = self.create_user("k8s-action-apply-preview", is_staff=True)
        session = self.write_session(staff)
        proof = self.dry_run_proof(staff, session)
        self.client.force_login(staff)

        response = self.client.post(
            reverse("api_kubernetes_action_request_approval"),
            data=json.dumps(
                {
                    "action": K8sActionRequest.ACTION_K8S_RESOURCE_APPLY,
                    "reason": "apply deployment after successful dry-run",
                    "target": {
                        "cluster_id": f"cluster_{self.cluster.id}",
                        "dry_run_action_id": str(proof.action_id),
                        "manifest": {"token": "raw-manifest-token"},
                    },
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        request_payload = response.json()["request"]
        self.assertEqual(request_payload["action"], K8sActionRequest.ACTION_K8S_RESOURCE_APPLY)
        self.assertEqual(request_payload["preview"]["blast_radius"], "single_resource_apply")
        self.assertEqual(request_payload["preview"]["rollback_plan"]["strategy"], "apply_revert")
        self.assertIn("rollback_dry_run_action_id", request_payload["preview"]["rollback_plan"]["evidence_required"])
        self.assertEqual(request_payload["target"]["dry_run_action_id"], str(proof.action_id))
        self.assertNotIn("manifest", request_payload["target"])
        self.assertNotIn("manifest", request_payload["preview"])
        self.assertNotIn("manifest_fingerprint", str(request_payload["preview"]["rollback_plan"]["target"]))
        self.assertNotIn("raw-manifest-token", str(response.json()))

    def test_apply_request_rejects_dry_run_proof_from_another_user(self):
        owner = self.create_user("k8s-action-apply-proof-owner", is_staff=True)
        requester = self.create_user("k8s-action-apply-other", is_staff=True)
        proof = self.dry_run_proof(owner, self.write_session(owner))
        self.client.force_login(requester)

        response = self.client.post(
            reverse("api_kubernetes_action_request_approval"),
            data=json.dumps(
                {
                    "action": K8sActionRequest.ACTION_K8S_RESOURCE_APPLY,
                    "reason": "try another proof",
                    "target": {"cluster_id": f"cluster_{self.cluster.id}", "dry_run_action_id": str(proof.action_id)},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "dry_run_proof_owner_mismatch")
        self.assertFalse(K8sActionRequest.objects.exists())

    @override_settings(KUBERNETES_ACTION_REQUEST_NATIVE_EXECUTION_ENABLED=True, KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=True)
    def test_execute_approved_apply_requires_manifest_at_execution_time(self):
        staff = self.create_user("k8s-action-admin-apply-no-manifest", is_staff=True)
        session = self.write_session(staff)
        proof = self.dry_run_proof(staff, session)
        action_request = K8sActionRequest.objects.create(
            requested_by=staff,
            username_snapshot=staff.username,
            action=K8sActionRequest.ACTION_K8S_RESOURCE_APPLY,
            status=K8sActionRequest.STATUS_APPROVED_EXTERNAL,
            cluster=self.cluster,
            target={"cluster_id": f"cluster_{self.cluster.id}", "namespace": "payments", "kind": "Deployment", "name": "payments-api", "dry_run_action_id": str(proof.action_id)},
            preview={"blast_radius": "single_resource_apply"},
            approval_ref="CHG-ACTION-APPLY",
            execution_policy={"native_execution_enabled": False, "external_approval_recorded": True},
            report={"status": K8sActionRequest.STATUS_APPROVED_EXTERNAL, "approved": True},
            reason="apply deployment after successful dry-run",
        )
        self.client.force_login(staff)

        response = self.client.post(
            reverse("api_kubernetes_action_execute_approved"),
            data=json.dumps({"request_id": str(action_request.request_id), "session_id": str(session.session_id)}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "manifest_required")
        self.assertFalse(K8sAdminAction.objects.filter(verb=K8sAdminAction.VERB_APPLY).exists())

    @override_settings(KUBERNETES_ACTION_REQUEST_NATIVE_EXECUTION_ENABLED=True, KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=True)
    def test_execute_approved_apply_uses_admin_write_session_and_matching_dry_run_proof(self):
        staff = self.create_user("k8s-action-admin-apply", is_staff=True)
        session = self.write_session(staff)
        manifest = self.deployment_manifest(replicas=3)
        proof = self.dry_run_proof(staff, session, manifest)
        action_request = K8sActionRequest.objects.create(
            requested_by=staff,
            username_snapshot=staff.username,
            action=K8sActionRequest.ACTION_K8S_RESOURCE_APPLY,
            status=K8sActionRequest.STATUS_APPROVED_EXTERNAL,
            cluster=self.cluster,
            target={
                "cluster_id": f"cluster_{self.cluster.id}",
                "api_version": "apps/v1",
                "kind": "Deployment",
                "resource": "deployments",
                "namespace": "payments",
                "name": "payments-api",
                "dry_run_action_id": str(proof.action_id),
            },
            preview={"blast_radius": "single_resource_apply", "dry_run_proof": {"id": str(proof.action_id)}},
            approval_ref="CHG-ACTION-APPLY",
            execution_policy={"native_execution_enabled": False, "external_approval_recorded": True},
            report={"status": K8sActionRequest.STATUS_APPROVED_EXTERNAL, "approved": True},
            reason="apply deployment after successful dry-run",
        )
        self.client.force_login(staff)

        with patch("kubernetes_ops.services.admin_apply.ProviderJsonClient") as client_cls:
            client_cls.return_value.request.return_value = manifest
            response = self.client.post(
                reverse("api_kubernetes_action_execute_approved"),
                data=json.dumps({"request_id": str(action_request.request_id), "session_id": str(session.session_id), "manifest": manifest}),
                content_type="application/json",
            )
            method, path = client_cls.return_value.request.call_args.args[:2]
            body = client_cls.return_value.request.call_args.kwargs["body"]

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["request"]["status"], K8sActionRequest.STATUS_EXECUTED_NATIVE)
        self.assertEqual(payload["request"]["report"]["operation"], "apply")
        self.assertEqual(payload["request"]["report"]["dry_run_action_id"], str(proof.action_id))
        self.assertFalse(payload["request"]["report"]["dry_run_bypassed"])
        verification_plan = payload["request"]["report"]["verification_plan"]
        self.assertEqual(verification_plan["status"], "pending")
        self.assertEqual(
            verification_plan["check_ids"],
            ["apply_action_completed", "resource_generation_observed", "recent_warning_events_checked"],
        )
        self.assertFalse(verification_plan["payload_stored"])
        self.assertNotIn("registry.example.test/payments:1", str(verification_plan))
        self.assertEqual(method, "PATCH")
        self.assertEqual(path, "/k8s/clusters/c-prod/apis/apps/v1/namespaces/payments/deployments/payments-api?fieldManager=webterm-admin-mode")
        self.assertEqual(body, manifest)
        admin_action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_APPLY)
        self.assertEqual(payload["request"]["report"]["admin_action_id"], str(admin_action.action_id))
        self.assertEqual(admin_action.status, K8sAdminAction.STATUS_COMPLETED)
