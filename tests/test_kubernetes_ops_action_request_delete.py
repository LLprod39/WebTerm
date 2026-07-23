import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sActionRequest, K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider


class KubernetesOpsActionRequestDeleteTests(TestCase):
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

    def write_session(self, user: User) -> K8sAdminSession:
        return K8sAdminSession.objects.create(
            user=user,
            username_snapshot=user.username,
            cluster=self.cluster,
            mode=K8sAdminSession.MODE_WRITE,
            status=K8sAdminSession.STATUS_ACTIVE,
            risk_tier=K8sAdminSession.RISK_HIGH,
            allowed_verbs=["get", "list", "watch", "logs", "yaml", "delete"],
            allowed_kinds=["Deployment"],
            allowed_namespaces=["payments"],
            reason="delete action request after approval",
            approval_ref="CHG-ACTION-DELETE",
            approved_by=user,
            approved_at=timezone.now(),
            expires_at=timezone.now() + timedelta(minutes=30),
        )

    def test_reader_can_request_resource_delete_preview_with_exact_confirmation(self):
        user = self.create_user("k8s-action-delete-reader")
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_action_request_approval"),
            data=json.dumps(
                {
                    "action": K8sActionRequest.ACTION_K8S_RESOURCE_DELETE,
                    "reason": "delete failed deployment after replacement is ready",
                    "target": {
                        "cluster_id": f"cluster_{self.cluster.id}",
                        "api_version": "apps/v1",
                        "kind": "Deployment",
                        "namespace": "payments",
                        "name": "payments-api",
                        "confirmation": "delete Deployment payments/payments-api",
                        "propagation_policy": "Foreground",
                    },
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        request_payload = response.json()["request"]
        self.assertEqual(request_payload["action"], K8sActionRequest.ACTION_K8S_RESOURCE_DELETE)
        self.assertEqual(request_payload["preview"]["blast_radius"], "single_resource_delete")
        self.assertEqual(request_payload["preview"]["expected_confirmation"], "delete Deployment payments/payments-api")
        self.assertEqual(request_payload["preview"]["propagation_policy"], "Foreground")
        self.assertEqual(request_payload["preview"]["rollback_plan"]["strategy"], "restore_deleted_resource")
        self.assertIn("restore_source_ref", request_payload["preview"]["rollback_plan"]["evidence_required"])
        self.assertNotIn("confirmation", str(request_payload["preview"]["affected"]))
        self.assertNotIn("confirmation", str(request_payload["preview"]["rollback_plan"]))
        self.assertFalse(request_payload["execution_policy"]["native_execution_enabled"])

    def test_resource_delete_request_requires_exact_confirmation_before_approval(self):
        user = self.create_user("k8s-action-delete-bad-confirmation")
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_action_request_approval"),
            data=json.dumps(
                {
                    "action": K8sActionRequest.ACTION_K8S_RESOURCE_DELETE,
                    "reason": "delete failed deployment",
                    "target": {
                        "cluster_id": f"cluster_{self.cluster.id}",
                        "api_version": "apps/v1",
                        "kind": "Deployment",
                        "namespace": "payments",
                        "name": "payments-api",
                        "confirmation": "delete payments-api",
                    },
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "delete_confirmation_mismatch")
        self.assertEqual(response.json()["payload"]["expected_confirmation"], "delete Deployment payments/payments-api")
        self.assertFalse(K8sActionRequest.objects.exists())

    def test_resource_delete_request_blocks_protected_namespace(self):
        user = self.create_user("k8s-action-delete-protected")
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_action_request_approval"),
            data=json.dumps(
                {
                    "action": K8sActionRequest.ACTION_K8S_RESOURCE_DELETE,
                    "reason": "bad delete",
                    "target": {
                        "cluster_id": f"cluster_{self.cluster.id}",
                        "api_version": "apps/v1",
                        "kind": "Deployment",
                        "namespace": "kube-system",
                        "name": "coredns",
                        "confirmation": "delete Deployment kube-system/coredns",
                    },
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "delete_namespace_protected")
        self.assertFalse(K8sActionRequest.objects.exists())

    @override_settings(
        KUBERNETES_ACTION_REQUEST_NATIVE_EXECUTION_ENABLED=True, KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED=True
    )
    def test_execute_approved_delete_uses_admin_write_session(self):
        staff = self.create_user("k8s-action-admin-delete", is_staff=True)
        session = self.write_session(staff)
        action_request = K8sActionRequest.objects.create(
            requested_by=staff,
            username_snapshot=staff.username,
            action=K8sActionRequest.ACTION_K8S_RESOURCE_DELETE,
            status=K8sActionRequest.STATUS_APPROVED_EXTERNAL,
            cluster=self.cluster,
            target={
                "cluster_id": f"cluster_{self.cluster.id}",
                "api_version": "apps/v1",
                "kind": "Deployment",
                "namespace": "payments",
                "name": "payments-api",
                "confirmation": "delete Deployment payments/payments-api",
                "propagation_policy": "Foreground",
            },
            preview={"blast_radius": "single_resource_delete"},
            approval_ref="CHG-ACTION-DELETE",
            execution_policy={"native_execution_enabled": False, "external_approval_recorded": True},
            report={"status": K8sActionRequest.STATUS_APPROVED_EXTERNAL, "approved": True},
            reason="delete failed deployment after replacement is ready",
        )
        self.client.force_login(staff)

        with patch("kubernetes_ops.services.admin_delete.ProviderJsonClient") as client_cls:
            client_cls.return_value.request.return_value = {"apiVersion": "v1", "kind": "Status", "status": "Success"}
            response = self.client.post(
                reverse("api_kubernetes_action_execute_approved"),
                data=json.dumps({"request_id": str(action_request.request_id), "session_id": str(session.session_id)}),
                content_type="application/json",
            )
            method, path = client_cls.return_value.request.call_args.args[:2]
            body = client_cls.return_value.request.call_args.kwargs["body"]

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["request"]["status"], K8sActionRequest.STATUS_EXECUTED_NATIVE)
        self.assertEqual(payload["request"]["report"]["operation"], "delete")
        self.assertTrue(payload["request"]["report"]["native_execution_performed_by_webterm"])
        self.assertEqual(method, "DELETE")
        self.assertEqual(path, "/k8s/clusters/c-prod/apis/apps/v1/namespaces/payments/deployments/payments-api")
        self.assertEqual(body["propagationPolicy"], "Foreground")
        admin_action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_DELETE)
        self.assertEqual(payload["request"]["report"]["admin_action_id"], str(admin_action.action_id))
        self.assertEqual(admin_action.status, K8sAdminAction.STATUS_COMPLETED)
