import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sActionRequest, K8sAppRef, K8sAuditEvent, K8sCluster, K8sFleetBundle, K8sProvider, K8sWorkloadRef


class KubernetesOpsActionRequestTests(TestCase):
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

    def test_reader_can_request_rollout_restart_preview_without_secret_leakage(self):
        user = self.create_user("k8s-action-reader")
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_action_request_approval"),
            data=json.dumps(
                {
                    "action": K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART,
                    "reason": "restart after config rollout",
                    "target": {
                        "workload_id": f"workload_{self.workload.id}",
                        "token": "super-secret-token",
                    },
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        request_payload = payload["request"]
        self.assertEqual(request_payload["action"], K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART)
        self.assertEqual(request_payload["status"], K8sActionRequest.STATUS_PENDING_APPROVAL)
        self.assertEqual(request_payload["target"]["cluster_name"], "prod-kz-1")
        self.assertEqual(request_payload["preview"]["blast_radius"], "single_workload")
        self.assertEqual(request_payload["preview"]["rollback_plan"]["strategy"], "rollout_recovery")
        self.assertFalse(request_payload["preview"]["rollback_plan"]["payload_stored"])
        self.assertFalse(request_payload["execution_policy"]["native_execution_enabled"])
        self.assertTrue(request_payload["execution_policy"]["rollback_required"])
        self.assertNotIn("super-secret-token", str(payload))
        self.assertTrue(K8sActionRequest.objects.filter(request_id=request_payload["id"]).exists())
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.action_request.create").exists())

    def test_blocked_delete_namespace_request_is_rejected_and_audited(self):
        user = self.create_user("k8s-action-blocked")
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_action_request_approval"),
            data=json.dumps(
                {
                    "action": "delete_namespace",
                    "reason": "cleanup",
                    "target": {"cluster_id": f"cluster_{self.cluster.id}", "namespace": "payments"},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "action_blocked")
        self.assertFalse(K8sActionRequest.objects.exists())
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.action_request.rejected").exists())

    def test_high_risk_blocked_action_aliases_are_rejected_before_request_creation(self):
        user = self.create_user("k8s-action-blocked-aliases")
        self.client.force_login(user)

        for action in ("helm.delete", "rbac.edit", "cluster_admin_shell"):
            with self.subTest(action=action):
                response = self.client.post(
                    reverse("api_kubernetes_action_request_approval"),
                    data=json.dumps(
                        {
                            "action": action,
                            "reason": "try blocked action",
                            "target": {"cluster_id": f"cluster_{self.cluster.id}", "namespace": "payments"},
                        }
                    ),
                    content_type="application/json",
                )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["code"], "action_blocked")

        self.assertFalse(K8sActionRequest.objects.exists())

    def test_reader_can_request_gitops_merge_request_template_without_secret_leakage(self):
        user = self.create_user("k8s-action-gitops")
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_action_request_approval"),
            data=json.dumps(
                {
                    "action": K8sActionRequest.ACTION_GITOPS_CREATE_MERGE_REQUEST,
                    "reason": "bump payments chart image through GitOps",
                    "target": {
                        "cluster_id": f"cluster_{self.cluster.id}",
                        "repository": "https://gitlab.example.test/platform/charts.git?token=super-secret-token",
                        "source_branch": "webterm/payments-image-bump",
                        "target_branch": "main",
                        "path": "charts/payments/values-prod.yaml",
                        "title": "Bump payments image tag",
                        "changes": [
                            {
                                "path": "charts/payments/values-prod.yaml",
                                "operation": "update",
                                "summary": "Set image tag to 2026.06.30-1",
                            }
                        ],
                    },
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        request_payload = payload["request"]
        self.assertEqual(request_payload["action"], K8sActionRequest.ACTION_GITOPS_CREATE_MERGE_REQUEST)
        self.assertEqual(request_payload["risk_tier"], K8sActionRequest.RISK_LOW)
        self.assertEqual(request_payload["target"]["repository"], "https://gitlab.example.test/platform/charts.git")
        self.assertEqual(request_payload["target"]["cluster_name"], "prod-kz-1")
        self.assertEqual(request_payload["preview"]["blast_radius"], "gitops_merge_request")
        self.assertEqual(request_payload["preview"]["change_count"], 1)
        self.assertEqual(request_payload["preview"]["git_provider"], "gitlab")
        self.assertFalse(request_payload["preview"]["gitops_write_performed"])
        self.assertFalse(request_payload["preview"]["cluster_mutation_performed"])
        self.assertIn("merge_request_template", request_payload["preview"])
        template = request_payload["preview"]["merge_request_template"]
        self.assertEqual(template["provider"], "gitlab")
        self.assertEqual(template["source_branch"], "webterm/payments-image-bump")
        self.assertEqual(template["target_branch"], "main")
        self.assertTrue(template["draft"])
        self.assertTrue(template["remove_source_branch"])
        self.assertEqual(template["api_payload"]["source_branch"], "webterm/payments-image-bump")
        self.assertEqual(template["api_payload"]["target_branch"], "main")
        self.assertIn("fleet_bundle_reconciled", template["verification_plan"])
        self.assertEqual(template["file_changes"][0]["path"], "charts/payments/values-prod.yaml")
        self.assertEqual(request_payload["execution_policy"]["native_execution_mode"], "external_gitops")
        self.assertFalse(request_payload["execution_policy"]["native_execution_enabled"])
        self.assertNotIn("super-secret-token", str(payload))

    def test_gitops_merge_request_rejects_path_traversal_before_request_creation(self):
        user = self.create_user("k8s-action-gitops-bad-path")
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_action_request_approval"),
            data=json.dumps(
                {
                    "action": K8sActionRequest.ACTION_GITOPS_CREATE_MERGE_REQUEST,
                    "reason": "bad path",
                    "target": {
                        "repository": "https://gitlab.example.test/platform/charts.git",
                        "source_branch": "webterm/bad-path",
                        "target_branch": "main",
                        "path": "../secrets/prod.yaml",
                        "diff_summary": "Set token=raw-secret-token",
                    },
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "gitops_path_invalid")
        self.assertNotIn("raw-secret-token", str(response.json()))
        self.assertFalse(K8sActionRequest.objects.exists())
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.action_request.rejected").exists())

    def test_gitops_merge_request_rejects_missing_changes(self):
        user = self.create_user("k8s-action-gitops-missing-changes")
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_action_request_approval"),
            data=json.dumps(
                {
                    "action": K8sActionRequest.ACTION_GITOPS_CREATE_MERGE_REQUEST,
                    "reason": "missing diff",
                    "target": {
                        "repository": "https://git.example.test/platform/charts.git",
                        "source_branch": "webterm/no-diff",
                        "target_branch": "main",
                        "path": "charts/payments/values-prod.yaml",
                    },
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "gitops_changes_required")
        self.assertFalse(K8sActionRequest.objects.exists())
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.action_request.rejected").exists())

    def test_gitops_merge_request_rejects_repository_credentials_without_leakage(self):
        user = self.create_user("k8s-action-gitops-credentialed-repo")
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_action_request_approval"),
            data=json.dumps(
                {
                    "action": K8sActionRequest.ACTION_GITOPS_CREATE_MERGE_REQUEST,
                    "reason": "bad repository url",
                    "target": {
                        "repository": "https://bot:super-secret-token@git.example.test/platform/charts.git",
                        "source_branch": "webterm/bad-repo",
                        "target_branch": "main",
                        "path": "charts/payments/values-prod.yaml",
                        "diff_summary": "Set image tag to 2026.06.30-1",
                    },
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "gitops_repository_credentials")
        self.assertNotIn("super-secret-token", str(response.json()))
        self.assertFalse(K8sActionRequest.objects.exists())

    def test_reader_can_request_fleet_pause_preview_without_native_execution(self):
        bundle = K8sFleetBundle.objects.create(
            name="platform-demo",
            status=K8sFleetBundle.STATUS_ROLLING,
            ready=1,
            desired=2,
        )
        user = self.create_user("k8s-action-fleet-pause")
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_action_request_approval"),
            data=json.dumps(
                {
                    "action": K8sActionRequest.ACTION_FLEET_ROLLOUT_PAUSE,
                    "reason": "pause bad rollout",
                    "target": {"bundle_id": f"fleet_{bundle.id}", "token": "super-secret-token"},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        request_payload = response.json()["request"]
        self.assertEqual(request_payload["action"], K8sActionRequest.ACTION_FLEET_ROLLOUT_PAUSE)
        self.assertEqual(request_payload["preview"]["blast_radius"], "fleet_bundle")
        self.assertEqual(request_payload["preview"]["current_status"], K8sFleetBundle.STATUS_ROLLING)
        self.assertNotIn("token", request_payload["target"])
        self.assertEqual(request_payload["execution_policy"]["native_execution_mode"], "disabled")
        self.assertFalse(request_payload["execution_policy"]["native_execution_enabled"])
        self.assertNotIn("super-secret-token", str(response.json()))

    def test_reader_can_request_devtron_rollback_preview_with_public_only_links(self):
        app = K8sAppRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            owner=K8sAppRef.OWNER_DEVTRON,
            health=K8sCluster.HEALTH_WARNING,
            version="2026.07.01-1",
            links={"rollback": "https://devtron.example.test/app/rollback?token=super-secret-token"},
        )
        user = self.create_user("k8s-action-devtron-rollback")
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_action_request_approval"),
            data=json.dumps(
                {
                    "action": K8sActionRequest.ACTION_DEVTRON_OPEN_ROLLBACK,
                    "reason": "prepare rollback context",
                    "target": {"app_id": f"app_{app.id}"},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        request_payload = response.json()["request"]
        self.assertEqual(request_payload["action"], K8sActionRequest.ACTION_DEVTRON_OPEN_ROLLBACK)
        self.assertEqual(request_payload["preview"]["blast_radius"], "single_devtron_app")
        self.assertEqual(request_payload["preview"]["links"]["rollback"], "https://devtron.example.test/app/rollback")
        self.assertEqual(request_payload["execution_policy"]["native_execution_mode"], "external_devtron")
        self.assertFalse(request_payload["execution_policy"]["native_execution_enabled"])
        self.assertNotIn("super-secret-token", str(response.json()))

    def test_action_status_and_report_are_read_only(self):
        user = self.create_user("k8s-action-status")
        self.client.force_login(user)
        action_request = K8sActionRequest.objects.create(
            requested_by=user,
            username_snapshot=user.username,
            action=K8sActionRequest.ACTION_FLEET_ROLLOUT_RESUME,
            status=K8sActionRequest.STATUS_PENDING_APPROVAL,
            risk_tier=K8sActionRequest.RISK_MEDIUM,
            target={"bundle_name": "platform-demo", "token": "raw-status-token"},
            preview={"blast_radius": "fleet_bundle"},
            execution_policy={"native_execution_enabled": False, "credential": "raw-policy-token"},
            report={"status": "not_executed", "evidence": {"authorization": "Bearer raw-report-token"}},
            reason="resume after password=raw-reason-token",
            approval_ref="https://rancher.example.test/change?token=raw-approval-token#tail",
        )

        status_response = self.client.get(reverse("api_kubernetes_action_status", kwargs={"request_id": action_request.request_id}))
        report_response = self.client.get(reverse("api_kubernetes_action_report", kwargs={"request_id": action_request.request_id}))

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["request"]["id"], str(action_request.request_id))
        self.assertEqual(status_response.json()["request"]["target"]["token"], "[redacted]")
        self.assertEqual(status_response.json()["request"]["execution_policy"]["credential"], "[redacted]")
        self.assertEqual(report_response.status_code, 200)
        self.assertEqual(report_response.json()["report"]["status"], "not_executed")
        self.assertEqual(status_response.json()["request"]["reason"], "resume after password=[redacted]")
        self.assertEqual(status_response.json()["request"]["approval_ref"], "https://rancher.example.test/change")
        self.assertNotIn("raw-status-token", str(status_response.json()))
        self.assertNotIn("raw-policy-token", str(status_response.json()))
        self.assertNotIn("raw-reason-token", str(status_response.json()))
        self.assertNotIn("raw-approval-token", str(status_response.json()))
        self.assertNotIn("raw-report-token", str(report_response.json()))

    def test_action_request_list_is_owner_scoped_and_sanitized(self):
        owner = self.create_user("k8s-action-list-owner")
        other_reader = self.create_user("k8s-action-list-other")
        owner_request = K8sActionRequest.objects.create(
            requested_by=owner,
            username_snapshot=owner.username,
            action=K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART,
            status=K8sActionRequest.STATUS_PENDING_APPROVAL,
            risk_tier=K8sActionRequest.RISK_HIGH,
            cluster=self.cluster,
            target={"cluster_id": f"cluster_{self.cluster.id}", "token": "owner-secret-token"},
            preview={"blast_radius": "single_workload"},
            execution_policy={"native_execution_enabled": False, "credential": "owner-policy-token"},
            report={"status": "not_executed", "evidence": {"authorization": "Bearer owner-report-token"}},
            reason="restart after failed deployment",
        )
        other_request = K8sActionRequest.objects.create(
            requested_by=other_reader,
            username_snapshot=other_reader.username,
            action=K8sActionRequest.ACTION_FLEET_ROLLOUT_RESUME,
            status=K8sActionRequest.STATUS_APPROVED_EXTERNAL,
            risk_tier=K8sActionRequest.RISK_MEDIUM,
            target={"bundle_name": "platform-demo", "token": "other-secret-token"},
            preview={"blast_radius": "fleet_bundle"},
            execution_policy={"native_execution_enabled": False},
            report={"status": K8sActionRequest.STATUS_APPROVED_EXTERNAL},
            reason="resume after check",
        )
        self.client.force_login(owner)

        response = self.client.get(reverse("api_kubernetes_action_requests"), {"all": "1"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["requests"][0]["id"], str(owner_request.request_id))
        self.assertEqual(payload["requests"][0]["target"]["token"], "[redacted]")
        self.assertEqual(payload["requests"][0]["execution_policy"]["credential"], "[redacted]")
        self.assertEqual(payload["requests"][0]["report"]["evidence"]["authorization"], "[redacted]")
        self.assertNotIn(str(other_request.request_id), str(payload))
        self.assertNotIn("owner-secret-token", str(payload))
        self.assertNotIn("owner-policy-token", str(payload))
        self.assertNotIn("owner-report-token", str(payload))
        self.assertNotIn("other-secret-token", str(payload))

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

        status_response = self.client.get(reverse("api_kubernetes_action_status", kwargs={"request_id": action_request.request_id}))
        report_response = self.client.get(reverse("api_kubernetes_action_report", kwargs={"request_id": action_request.request_id}))

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

        status_response = self.client.get(reverse("api_kubernetes_action_status", kwargs={"request_id": action_request.request_id}))
        report_response = self.client.get(reverse("api_kubernetes_action_report", kwargs={"request_id": action_request.request_id}))

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["request"]["requested_by"], owner.username)
        self.assertEqual(report_response.status_code, 200)
        self.assertEqual(report_response.json()["report"]["status"], "not_executed")
