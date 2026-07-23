import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sActionRequest, K8sAuditEvent, K8sCluster, K8sProvider, K8sWorkloadRef


class KubernetesOpsActionLifecycleTests(TestCase):
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

    def _action_request(
        self, *, user: User, status: str = K8sActionRequest.STATUS_PENDING_APPROVAL, **overrides
    ) -> K8sActionRequest:
        defaults = {
            "requested_by": user,
            "username_snapshot": user.username,
            "action": K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART,
            "status": status,
            "cluster": self.cluster,
            "target": {
                "cluster_id": f"cluster_{self.cluster.id}",
                "namespace": "payments",
                "kind": "deployment",
                "name": "payments-api",
            },
            "preview": {"blast_radius": "single_workload"},
            "execution_policy": {"native_execution_enabled": False},
            "reason": "restart after config rollout",
        }
        defaults.update(overrides)
        return K8sActionRequest.objects.create(**defaults)

    def test_staff_can_record_external_approval_without_execution(self):
        staff = self.create_user("k8s-action-approver", is_staff=True)
        requester = self.create_user("k8s-action-approval-requester")
        self.client.force_login(staff)
        action_request = self._action_request(user=requester)

        response = self.client.post(
            reverse("api_kubernetes_action_approve_external", kwargs={"request_id": action_request.request_id}),
            data=json.dumps({"approval_ref": "CHG-K8S-123", "summary": "Approved after CAB review."}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["request"]
        self.assertEqual(payload["status"], K8sActionRequest.STATUS_APPROVED_EXTERNAL)
        self.assertEqual(payload["approval_ref"], "CHG-K8S-123")
        self.assertTrue(payload["report"]["approved"])
        self.assertFalse(payload["report"]["native_execution_performed_by_webterm"])
        self.assertFalse(payload["execution_policy"]["native_execution_enabled"])
        self.assertTrue(payload["execution_policy"]["external_approval_recorded"])
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.action_request.approve_external").exists())

    def test_external_approval_redacts_url_tokens_and_summary_before_response_and_audit(self):
        staff = self.create_user("k8s-action-approval-redaction", is_staff=True)
        requester = self.create_user("k8s-action-approval-redaction-requester")
        self.client.force_login(staff)
        action_request = self._action_request(user=requester)

        response = self.client.post(
            reverse("api_kubernetes_action_approve_external", kwargs={"request_id": action_request.request_id}),
            data=json.dumps(
                {
                    "approval_ref": "https://rancher.example.test/approve/change-1?token=raw-approval-token#tail",
                    "summary": "Approved after password=raw-approval-password",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["request"]["approval_ref"], "https://rancher.example.test/approve/change-1")
        self.assertEqual(payload["request"]["report"]["approval_ref"], "https://rancher.example.test/approve/change-1")
        self.assertEqual(payload["request"]["report"]["approval_summary"], "Approved after password=[redacted]")
        self.assertNotIn("raw-approval-token", str(payload))
        self.assertNotIn("raw-approval-password", str(payload))
        action_request.refresh_from_db()
        self.assertEqual(action_request.approval_ref, "https://rancher.example.test/approve/change-1")
        audit = K8sAuditEvent.objects.get(action="k8s.action_request.approve_external")
        self.assertNotIn("raw-approval-token", str(audit.payload))
        self.assertNotIn("raw-approval-password", str(audit.payload))

    def test_external_approval_requires_staff_and_approval_ref(self):
        reader = self.create_user("k8s-action-reader-approver")
        staff = self.create_user("k8s-action-missing-ref-approver", is_staff=True)
        action_request = self._action_request(user=reader)

        self.client.force_login(reader)
        denied = self.client.post(
            reverse("api_kubernetes_action_approve_external", kwargs={"request_id": action_request.request_id}),
            data=json.dumps({"approval_ref": "CHG-K8S-123"}),
            content_type="application/json",
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["code"], "admin_required")

        self.client.force_login(staff)
        missing_ref = self.client.post(
            reverse("api_kubernetes_action_approve_external", kwargs={"request_id": action_request.request_id}),
            data=json.dumps({"summary": "missing ref"}),
            content_type="application/json",
        )
        self.assertEqual(missing_ref.status_code, 400)
        self.assertEqual(missing_ref.json()["code"], "approval_ref_required")
        action_request.refresh_from_db()
        self.assertEqual(action_request.status, K8sActionRequest.STATUS_PENDING_APPROVAL)

    def test_execute_approved_action_is_blocked_and_audited(self):
        staff = self.create_user("k8s-action-admin", is_staff=True)
        self.client.force_login(staff)
        action_request = self._action_request(
            user=staff,
            status=K8sActionRequest.STATUS_APPROVED_EXTERNAL,
            execution_policy={"native_execution_enabled": False, "external_approval_recorded": True},
        )

        response = self.client.post(
            reverse("api_kubernetes_action_execute_approved"),
            data=json.dumps({"request_id": str(action_request.request_id)}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "execution_disabled_by_policy")
        action_request.refresh_from_db()
        self.assertEqual(action_request.status, K8sActionRequest.STATUS_EXECUTION_BLOCKED)
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.action_request.execute_blocked").exists())

    def test_execute_approved_does_not_overwrite_terminal_action_report(self):
        staff = self.create_user("k8s-action-admin-terminal", is_staff=True)
        self.client.force_login(staff)
        action_request = self._action_request(
            user=staff,
            status=K8sActionRequest.STATUS_VERIFIED_EXTERNAL,
            execution_policy={"native_execution_enabled": False, "external_verification_recorded": True},
            report={
                "status": K8sActionRequest.STATUS_VERIFIED_EXTERNAL,
                "verified": True,
                "summary": "already verified",
            },
        )

        response = self.client.post(
            reverse("api_kubernetes_action_execute_approved"),
            data=json.dumps({"request_id": str(action_request.request_id)}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "action_request_not_pending")
        action_request.refresh_from_db()
        self.assertEqual(action_request.status, K8sActionRequest.STATUS_VERIFIED_EXTERNAL)
        self.assertTrue(action_request.report["verified"])
        self.assertEqual(action_request.report["summary"], "already verified")
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.action_request.execute_rejected").exists())

    def test_staff_can_record_external_verification_without_secret_leakage(self):
        staff = self.create_user("k8s-action-verifier", is_staff=True)
        self.client.force_login(staff)
        action_request = self._action_request(
            user=staff,
            status=K8sActionRequest.STATUS_APPROVED_EXTERNAL,
            execution_policy={"native_execution_enabled": False, "external_approval_recorded": True},
            report={"status": K8sActionRequest.STATUS_APPROVED_EXTERNAL, "approved": True},
        )

        response = self.client.post(
            reverse("api_kubernetes_action_verify_external", kwargs={"request_id": action_request.request_id}),
            data=json.dumps(
                {
                    "outcome": "succeeded",
                    "summary": "Restart was completed in Rancher and pods are ready.",
                    "external_ref": "https://rancher.example.test/dashboard/c/local/apps/deployments/payments",
                    "checks": ["rollout status complete", "pods ready"],
                    "evidence": {
                        "ready": "2/2",
                        "token": "super-secret-token",
                        "authorization": "Bearer hidden",
                    },
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["request"]["status"], K8sActionRequest.STATUS_VERIFIED_EXTERNAL)
        self.assertTrue(payload["request"]["report"]["verified"])
        self.assertTrue(payload["request"]["report"]["external_execution"])
        self.assertFalse(payload["request"]["report"]["native_execution_performed_by_webterm"])
        self.assertEqual(payload["request"]["report"]["evidence"]["token"], "[redacted]")
        self.assertEqual(payload["request"]["report"]["evidence"]["authorization"], "[redacted]")
        self.assertNotIn("super-secret-token", str(payload))
        self.assertNotIn("Bearer hidden", str(payload))
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.action_request.verify_external").exists())

    def test_external_verification_redacts_ref_and_summary_before_response_and_audit(self):
        staff = self.create_user("k8s-action-verification-redaction", is_staff=True)
        self.client.force_login(staff)
        action_request = self._action_request(
            user=staff,
            status=K8sActionRequest.STATUS_APPROVED_EXTERNAL,
            execution_policy={"native_execution_enabled": False, "external_approval_recorded": True},
            report={"status": K8sActionRequest.STATUS_APPROVED_EXTERNAL, "approved": True},
        )

        response = self.client.post(
            reverse("api_kubernetes_action_verify_external", kwargs={"request_id": action_request.request_id}),
            data=json.dumps(
                {
                    "outcome": "succeeded",
                    "summary": "Verified with token=raw-verification-token",
                    "external_ref": "https://rancher.example.test/result/1?access_token=raw-access-token#tail",
                    "checks": ["pods ready"],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["request"]["report"]["summary"], "Verified with token=[redacted]")
        self.assertEqual(payload["request"]["report"]["external_ref"], "https://rancher.example.test/result/1")
        self.assertNotIn("raw-verification-token", str(payload))
        self.assertNotIn("raw-access-token", str(payload))
        action_request.refresh_from_db()
        self.assertEqual(action_request.report["external_ref"], "https://rancher.example.test/result/1")
        audit = K8sAuditEvent.objects.get(action="k8s.action_request.verify_external")
        self.assertNotIn("raw-verification-token", str(audit.payload))
        self.assertNotIn("raw-access-token", str(audit.payload))

    def test_external_verification_does_not_overwrite_terminal_action_report(self):
        staff = self.create_user("k8s-action-terminal-verifier", is_staff=True)
        self.client.force_login(staff)
        action_request = self._action_request(
            user=staff,
            status=K8sActionRequest.STATUS_EXECUTION_BLOCKED,
            report={"status": "blocked", "blocked_reason": "native execution disabled"},
        )

        response = self.client.post(
            reverse("api_kubernetes_action_verify_external", kwargs={"request_id": action_request.request_id}),
            data=json.dumps({"outcome": "succeeded", "summary": "should not overwrite"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "action_request_not_pending")
        action_request.refresh_from_db()
        self.assertEqual(action_request.status, K8sActionRequest.STATUS_EXECUTION_BLOCKED)
        self.assertEqual(action_request.report["blocked_reason"], "native execution disabled")
        self.assertNotIn("should not overwrite", str(action_request.report))
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.action_request.verification_rejected").exists())

    def test_external_verification_requires_staff(self):
        reader = self.create_user("k8s-action-nonstaff")
        self.client.force_login(reader)
        action_request = self._action_request(
            user=reader,
            status=K8sActionRequest.STATUS_APPROVED_EXTERNAL,
            execution_policy={"native_execution_enabled": False, "external_approval_recorded": True},
        )

        response = self.client.post(
            reverse("api_kubernetes_action_verify_external", kwargs={"request_id": action_request.request_id}),
            data=json.dumps({"outcome": "succeeded", "summary": "done"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_required")
        action_request.refresh_from_db()
        self.assertEqual(action_request.status, K8sActionRequest.STATUS_APPROVED_EXTERNAL)

    def test_external_verification_rejects_invalid_outcome_and_audits(self):
        staff = self.create_user("k8s-action-invalid-verifier", is_staff=True)
        self.client.force_login(staff)
        action_request = self._action_request(
            user=staff,
            status=K8sActionRequest.STATUS_APPROVED_EXTERNAL,
            execution_policy={"native_execution_enabled": False, "external_approval_recorded": True},
        )

        response = self.client.post(
            reverse("api_kubernetes_action_verify_external", kwargs={"request_id": action_request.request_id}),
            data=json.dumps({"outcome": "maybe", "summary": "not clear"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "verification_outcome_required")
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.action_request.verification_rejected").exists())

    def test_external_verification_requires_recorded_approval(self):
        staff = self.create_user("k8s-action-unapproved-verifier", is_staff=True)
        self.client.force_login(staff)
        action_request = self._action_request(user=staff)

        response = self.client.post(
            reverse("api_kubernetes_action_verify_external", kwargs={"request_id": action_request.request_id}),
            data=json.dumps({"outcome": "succeeded", "summary": "not approved yet"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "action_request_not_approved")
        action_request.refresh_from_db()
        self.assertEqual(action_request.status, K8sActionRequest.STATUS_PENDING_APPROVAL)

    def test_action_report_includes_bounded_audit_timeline_for_requester_and_staff(self):
        requester = self.create_user("k8s-action-timeline-requester")
        staff = self.create_user("k8s-action-timeline-staff", is_staff=True)
        self.client.force_login(requester)
        create_response = self.client.post(
            reverse("api_kubernetes_action_request_approval"),
            data=json.dumps(
                {
                    "action": K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART,
                    "reason": "restart after failed deployment",
                    "target": {"workload_id": f"workload_{self.workload.id}"},
                }
            ),
            content_type="application/json",
        )
        request_id = create_response.json()["request"]["id"]

        self.client.force_login(staff)
        approve_response = self.client.post(
            reverse("api_kubernetes_action_approve_external", kwargs={"request_id": request_id}),
            data=json.dumps({"approval_ref": "CHG-K8S-TIMELINE", "summary": "Approved externally."}),
            content_type="application/json",
        )
        verify_response = self.client.post(
            reverse("api_kubernetes_action_verify_external", kwargs={"request_id": request_id}),
            data=json.dumps(
                {"outcome": "succeeded", "summary": "External action completed.", "checks": ["pods ready"]}
            ),
            content_type="application/json",
        )
        staff_report = self.client.get(reverse("api_kubernetes_action_report", kwargs={"request_id": request_id}))

        self.client.force_login(requester)
        requester_report = self.client.get(reverse("api_kubernetes_action_report", kwargs={"request_id": request_id}))

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(verify_response.status_code, 200)
        self.assertEqual(staff_report.status_code, 200)
        self.assertEqual(requester_report.status_code, 200)
        timeline = staff_report.json()["timeline"]
        self.assertEqual(
            [item["action"] for item in timeline],
            [
                "k8s.action_request.create",
                "k8s.action_request.approve_external",
                "k8s.action_request.verify_external",
            ],
        )
        self.assertEqual(timeline[1]["payload"]["approval_ref"], "CHG-K8S-TIMELINE")
        self.assertEqual(requester_report.json()["timeline"], timeline)

    def test_action_report_sanitizes_request_report_and_timeline_payloads(self):
        requester = self.create_user("k8s-action-report-redaction-requester")
        self.client.force_login(requester)
        action_request = self._action_request(
            user=requester,
            status=K8sActionRequest.STATUS_VERIFIED_EXTERNAL,
            report={
                "status": K8sActionRequest.STATUS_VERIFIED_EXTERNAL,
                "verified": True,
                "evidence": {
                    "token": "raw-report-token",
                    "authorization": "Bearer raw-report-token",
                    "ready": "2/2",
                },
            },
            execution_policy={
                "native_execution_enabled": False,
                "credential": "raw-policy-token",
            },
        )
        K8sAuditEvent.objects.create(
            user=requester,
            username_snapshot=requester.username,
            action="k8s.action_request.verify_external",
            provider="webterm",
            cluster=self.cluster,
            payload={
                "request_id": str(action_request.request_id),
                "token": "raw-timeline-token",
                "authorization": "Bearer raw-timeline-token",
                "nested": {"password": "raw-password", "status": "ok"},
            },
        )

        response = self.client.get(
            reverse("api_kubernetes_action_report", kwargs={"request_id": action_request.request_id})
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["request"]["report"]["evidence"]["token"], "[redacted]")
        self.assertEqual(payload["report"]["evidence"]["authorization"], "[redacted]")
        self.assertEqual(payload["execution_policy"]["credential"], "[redacted]")
        self.assertEqual(payload["timeline"][0]["payload"]["token"], "[redacted]")
        self.assertEqual(payload["timeline"][0]["payload"]["nested"]["password"], "[redacted]")
        self.assertEqual(payload["summary"]["timeline_event_count"], 1)
        self.assertTrue(payload["summary"]["verified"])
        self.assertNotIn("raw-report-token", str(payload))
        self.assertNotIn("raw-policy-token", str(payload))
        self.assertNotIn("raw-timeline-token", str(payload))
        self.assertNotIn("raw-password", str(payload))
