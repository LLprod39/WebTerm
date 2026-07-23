from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sActionRequest, K8sCluster, K8sProvider


class KubernetesOpsActionSummaryTests(TestCase):
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

    def test_action_summary_is_owner_scoped_metadata_only_and_sanitized(self):
        owner = self.create_user("k8s-action-summary-owner")
        other_reader = self.create_user("k8s-action-summary-other")
        owner_request = K8sActionRequest.objects.create(
            requested_by=owner,
            username_snapshot=owner.username,
            action=K8sActionRequest.ACTION_K8S_RESOURCE_APPLY,
            status=K8sActionRequest.STATUS_EXECUTED_NATIVE,
            risk_tier=K8sActionRequest.RISK_HIGH,
            cluster=self.cluster,
            target={
                "cluster_id": f"cluster_{self.cluster.id}",
                "namespace": "payments",
                "kind": "Deployment",
                "name": "payments-api",
                "token": "owner-summary-secret-token",
            },
            preview={
                "blast_radius": "single_resource",
                "rollback_plan": {
                    "status": "required",
                    "strategy": "apply_revert",
                    "payload_stored": False,
                    "sensitive_values_stored": False,
                    "evidence": {"password": "owner-summary-rollback-password"},
                },
            },
            execution_policy={"native_execution_enabled": True, "credential": "owner-summary-policy-token"},
            report={
                "status": K8sActionRequest.STATUS_EXECUTED_NATIVE,
                "admin_action_id": "admin-action-1",
                "verification_plan": {
                    "status": "pending",
                    "mode": "native_post_action",
                    "required": True,
                    "check_ids": ["apply_action_completed", "recent_warning_events_checked"],
                    "payload_stored": False,
                    "sensitive_values_stored": False,
                    "evidence": {"authorization": "Bearer owner-summary-report-token"},
                },
            },
            reason="apply after token=owner-summary-reason-token",
            approval_ref="https://change.example.test/CHG-1?token=owner-summary-approval-token#tail",
        )
        other_request = K8sActionRequest.objects.create(
            requested_by=other_reader,
            username_snapshot=other_reader.username,
            action=K8sActionRequest.ACTION_FLEET_ROLLOUT_PAUSE,
            status=K8sActionRequest.STATUS_PENDING_APPROVAL,
            risk_tier=K8sActionRequest.RISK_MEDIUM,
            cluster=self.cluster,
            target={"bundle_name": "platform-demo", "token": "other-summary-secret-token"},
            preview={"blast_radius": "fleet_bundle"},
            execution_policy={"native_execution_enabled": False},
            report={"status": "not_executed"},
            reason="pause later",
        )
        self.client.force_login(owner)

        response = self.client.get(reverse("api_kubernetes_action_summary"), {"all": "1"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["operation"], "action_request_summary")
        self.assertEqual(payload["visibility"], "requester")
        self.assertFalse(payload["policy"]["mutates_state"])
        self.assertFalse(payload["policy"]["native_execution"])
        self.assertEqual(payload["counts"]["total"], 1)
        self.assertEqual(payload["counts"]["needs_verification"], 1)
        self.assertEqual(payload["counts"]["pending_approval"], 0)
        self.assertEqual(payload["counts"]["high_risk_attention"], 1)
        item = payload["queues"]["needs_verification"][0]
        self.assertEqual(item["id"], str(owner_request.request_id))
        self.assertEqual(item["target"]["namespace"], "payments")
        self.assertEqual(item["target"]["kind"], "Deployment")
        self.assertEqual(item["target"]["name"], "payments-api")
        self.assertEqual(item["rollback"]["strategy"], "apply_revert")
        self.assertEqual(item["verification"]["status"], "pending")
        self.assertTrue(item["verification"]["required"])
        self.assertIn("apply_action_completed", item["verification"]["check_ids"])
        self.assertNotIn(str(other_request.request_id), str(payload))
        self.assertNotIn("owner-summary-secret-token", str(payload))
        self.assertNotIn("owner-summary-policy-token", str(payload))
        self.assertNotIn("owner-summary-report-token", str(payload))
        self.assertNotIn("owner-summary-reason-token", str(payload))
        self.assertNotIn("owner-summary-approval-token", str(payload))
        self.assertNotIn("owner-summary-rollback-password", str(payload))
        self.assertNotIn("other-summary-secret-token", str(payload))

    def test_staff_action_summary_supports_filters_and_all_users(self):
        owner = self.create_user("k8s-action-summary-filter-owner")
        staff = self.create_user("k8s-action-summary-filter-staff", is_staff=True)
        matching_request = K8sActionRequest.objects.create(
            requested_by=owner,
            username_snapshot=owner.username,
            action=K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART,
            status=K8sActionRequest.STATUS_PENDING_APPROVAL,
            risk_tier=K8sActionRequest.RISK_HIGH,
            cluster=self.cluster,
            target={
                "cluster_id": f"cluster_{self.cluster.id}",
                "namespace": "payments",
                "kind": "Deployment",
                "name": "payments-api",
            },
            preview={"blast_radius": "single_workload"},
            execution_policy={"native_execution_enabled": False},
            report={"status": "not_executed"},
            reason="restart pending",
        )
        K8sActionRequest.objects.create(
            requested_by=owner,
            username_snapshot=owner.username,
            action=K8sActionRequest.ACTION_FLEET_ROLLOUT_RESUME,
            status=K8sActionRequest.STATUS_VERIFIED_EXTERNAL,
            risk_tier=K8sActionRequest.RISK_MEDIUM,
            target={"bundle_name": "platform-demo"},
            preview={"blast_radius": "fleet_bundle"},
            execution_policy={"native_execution_enabled": False},
            report={"status": K8sActionRequest.STATUS_VERIFIED_EXTERNAL, "verified": True},
            reason="verified",
        )
        self.client.force_login(staff)

        response = self.client.get(
            reverse("api_kubernetes_action_summary"),
            {
                "all": "1",
                "status": K8sActionRequest.STATUS_PENDING_APPROVAL,
                "action": K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART,
                "risk_tier": K8sActionRequest.RISK_HIGH,
                "cluster_id": f"cluster_{self.cluster.id}",
                "queue_limit": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["visibility"], "staff_all")
        self.assertEqual(payload["counts"]["total"], 1)
        self.assertEqual(payload["counts"]["pending_approval"], 1)
        self.assertEqual(payload["counts"]["production_like_attention"], 1)
        self.assertEqual(payload["counts"]["by_status"][K8sActionRequest.STATUS_PENDING_APPROVAL], 1)
        self.assertEqual(payload["counts"]["by_action"][K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART], 1)
        self.assertEqual(payload["counts"]["by_risk"][K8sActionRequest.RISK_HIGH], 1)
        self.assertEqual(len(payload["queues"]["pending_approval"]), 1)
        self.assertEqual(payload["queues"]["pending_approval"][0]["id"], str(matching_request.request_id))
        self.assertEqual(payload["queues"]["pending_approval"][0]["requested_by"], owner.username)
