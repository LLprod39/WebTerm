import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sActionRequest, K8sAdminSession, K8sAuditEvent, K8sCluster, K8sProvider


class KubernetesOpsApprovalSeparationTests(TestCase):
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

    def create_user(self, username: str, *, grant_admin_write: bool = False) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=True)
        UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        if grant_admin_write:
            UserAppPermission.objects.create(user=user, feature="kubernetes_admin_write", allowed=True)
        return user

    def test_staff_requester_cannot_approve_own_write_session(self):
        requester = self.create_user("k8s-write-self-approver", grant_admin_write=True)
        self.client.force_login(requester)
        create_response = self.client.post(
            reverse("api_kubernetes_admin_sessions"),
            data=json.dumps(
                {
                    "mode": K8sAdminSession.MODE_WRITE,
                    "cluster_id": f"cluster_{self.cluster.id}",
                    "namespace": "payments",
                    "reason": "request a write session that needs independent approval",
                }
            ),
            content_type="application/json",
        )
        session_id = create_response.json()["session"]["id"]

        approve_response = self.client.post(
            reverse("api_kubernetes_admin_session_approve", kwargs={"session_id": session_id}),
            data=json.dumps({"approval_ref": "CHG-SELF-APPROVAL"}),
            content_type="application/json",
        )

        self.assertEqual(approve_response.status_code, 403)
        self.assertEqual(approve_response.json()["code"], "self_approval_forbidden")
        session = K8sAdminSession.objects.get(session_id=session_id)
        self.assertEqual(session.status, K8sAdminSession.STATUS_PENDING_APPROVAL)
        self.assertEqual(session.approval_ref, "")
        self.assertIsNone(session.approved_at)
        self.assertIsNone(session.approved_by)
        rejection = K8sAuditEvent.objects.get(action="k8s.admin_session.approval_rejected")
        self.assertEqual(rejection.payload["code"], "self_approval_forbidden")

    def test_staff_requester_cannot_approve_own_external_action(self):
        requester = self.create_user("k8s-action-self-approver")
        self.client.force_login(requester)
        action_request = K8sActionRequest.objects.create(
            requested_by=requester,
            username_snapshot=requester.username,
            action=K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART,
            status=K8sActionRequest.STATUS_PENDING_APPROVAL,
            cluster=self.cluster,
            target={
                "cluster_id": f"cluster_{self.cluster.id}",
                "namespace": "payments",
                "kind": "deployment",
                "name": "payments-api",
            },
            preview={"blast_radius": "single_workload"},
            execution_policy={"native_execution_enabled": False},
            reason="restart after config rollout",
        )
        original_report = dict(action_request.report)
        original_policy = dict(action_request.execution_policy)

        response = self.client.post(
            reverse("api_kubernetes_action_approve_external", kwargs={"request_id": action_request.request_id}),
            data=json.dumps({"approval_ref": "CHG-K8S-SELF"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "self_approval_forbidden")
        action_request.refresh_from_db()
        self.assertEqual(action_request.status, K8sActionRequest.STATUS_PENDING_APPROVAL)
        self.assertEqual(action_request.approval_ref, "")
        self.assertEqual(action_request.report, original_report)
        self.assertEqual(action_request.execution_policy, original_policy)
        rejection = K8sAuditEvent.objects.get(action="k8s.action_request.approval_rejected")
        self.assertEqual(rejection.payload["code"], "self_approval_forbidden")
