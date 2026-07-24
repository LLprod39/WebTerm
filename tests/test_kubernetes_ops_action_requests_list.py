from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.models import (
    K8sActionRequest,
    K8sCluster,
    K8sProvider,
    K8sWorkloadRef,
)


class KubernetesOpsActionRequestListAndStaffTests(TestCase):
    def create_user(self, username: str, *, grant_kubernetes: bool = True, is_staff: bool = False) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=is_staff)
        if grant_kubernetes:
            UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
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
        self.workload = K8sWorkloadRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            kind=K8sWorkloadRef.KIND_DEPLOYMENT,
            health=K8sCluster.HEALTH_WARNING,
            ready=1,
            desired=2,
        )

    def test_staff_can_filter_action_request_list_for_all_users(self):
        owner = self.create_user("k8s-action-list-filter-owner")
        staff = self.create_user("k8s-action-list-filter-staff", is_staff=True)
        matching_request = K8sActionRequest.objects.create(
            requested_by=owner,
            username_snapshot=owner.username,
            action=K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART,
            status=K8sActionRequest.STATUS_VERIFIED_EXTERNAL,
            risk_tier=K8sActionRequest.RISK_HIGH,
            cluster=self.cluster,
            target={"cluster_id": f"cluster_{self.cluster.id}"},
            preview={"blast_radius": "single_workload"},
            execution_policy={"native_execution_enabled": False},
            report={"status": K8sActionRequest.STATUS_VERIFIED_EXTERNAL, "verified": True},
            reason="restart verified",
        )
        K8sActionRequest.objects.create(
            requested_by=owner,
            username_snapshot=owner.username,
            action=K8sActionRequest.ACTION_FLEET_ROLLOUT_RESUME,
            status=K8sActionRequest.STATUS_PENDING_APPROVAL,
            risk_tier=K8sActionRequest.RISK_MEDIUM,
            target={"bundle_name": "platform-demo"},
            preview={"blast_radius": "fleet_bundle"},
            execution_policy={"native_execution_enabled": False},
            report={"status": "not_executed"},
            reason="resume later",
        )
        self.client.force_login(staff)

        response = self.client.get(
            reverse("api_kubernetes_action_requests"),
            {
                "all": "1",
                "status": K8sActionRequest.STATUS_VERIFIED_EXTERNAL,
                "action": K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART,
                "cluster_id": f"cluster_{self.cluster.id}",
                "risk_tier": K8sActionRequest.RISK_HIGH,
                "limit": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["limit"], 1)
        self.assertEqual(payload["requests"][0]["id"], str(matching_request.request_id))
        self.assertEqual(payload["requests"][0]["requested_by"], owner.username)

    def test_action_status_and_report_are_hidden_from_other_readers(self):
        owner = self.create_user("k8s-action-owner")
        other_reader = self.create_user("k8s-action-other-reader")
        action_request = K8sActionRequest.objects.create(
            requested_by=owner,
            username_snapshot=owner.username,
            action=K8sActionRequest.ACTION_FLEET_ROLLOUT_RESUME,
            status=K8sActionRequest.STATUS_PENDING_APPROVAL,
            risk_tier=K8sActionRequest.RISK_MEDIUM,
            target={"bundle_name": "platform-demo"},
            preview={"blast_radius": "fleet_bundle"},
            execution_policy={"native_execution_enabled": False},
            report={"status": "not_executed", "approval_ref": "CHG-SECRET"},
            reason="resume after manual check",
        )
        self.client.force_login(other_reader)

        status_response = self.client.get(
            reverse("api_kubernetes_action_status", kwargs={"request_id": action_request.request_id})
        )
        report_response = self.client.get(
            reverse("api_kubernetes_action_report", kwargs={"request_id": action_request.request_id})
        )

        self.assertEqual(status_response.status_code, 404)
        self.assertEqual(status_response.json()["code"], "request_not_found")
        self.assertEqual(report_response.status_code, 404)
        self.assertNotIn("CHG-SECRET", str(status_response.json()))
        self.assertNotIn("CHG-SECRET", str(report_response.json()))

    def test_staff_can_read_action_status_and_report_for_other_users(self):
        owner = self.create_user("k8s-action-owner-for-staff")
        staff = self.create_user("k8s-action-report-admin", is_staff=True)
        action_request = K8sActionRequest.objects.create(
            requested_by=owner,
            username_snapshot=owner.username,
            action=K8sActionRequest.ACTION_FLEET_ROLLOUT_RESUME,
            status=K8sActionRequest.STATUS_PENDING_APPROVAL,
            risk_tier=K8sActionRequest.RISK_MEDIUM,
            target={"bundle_name": "platform-demo"},
            preview={"blast_radius": "fleet_bundle"},
            execution_policy={"native_execution_enabled": False},
            report={"status": "not_executed"},
            reason="resume after manual check",
        )
        self.client.force_login(staff)

        status_response = self.client.get(
            reverse("api_kubernetes_action_status", kwargs={"request_id": action_request.request_id})
        )
        report_response = self.client.get(
            reverse("api_kubernetes_action_report", kwargs={"request_id": action_request.request_id})
        )

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["request"]["requested_by"], owner.username)
        self.assertEqual(report_response.status_code, 200)
        self.assertEqual(report_response.json()["report"]["status"], "not_executed")
