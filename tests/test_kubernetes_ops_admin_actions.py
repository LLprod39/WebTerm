import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import (
    K8sAdminAction,
    K8sAdminRecording,
    K8sAdminRecordingEvent,
    K8sAdminSession,
    K8sAuditEvent,
    K8sCluster,
    K8sProvider,
)


class KubernetesOpsAdminActionEvidenceTests(TestCase):
    def create_user(
        self,
        username: str,
        *,
        grant_kubernetes: bool = True,
        grant_admin_write: bool = False,
        grant_break_glass: bool = False,
        is_staff: bool = False,
    ) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=is_staff)
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

    def create_session(self, user: User) -> K8sAdminSession:
        return K8sAdminSession.objects.create(
            user=user,
            username_snapshot=user.username,
            cluster=self.cluster,
            mode=K8sAdminSession.MODE_WRITE,
            status=K8sAdminSession.STATUS_ACTIVE,
            risk_tier=K8sAdminSession.RISK_HIGH,
            allowed_verbs=["get", "list", "watch", "logs", "yaml", "dry_run_apply", "apply"],
            allowed_kinds=["Deployment", "Secret"],
            allowed_namespaces=["payments"],
            reason="collect action evidence",
            expires_at=timezone.now() + timedelta(minutes=30),
        )

    def create_action(self, user: User, session: K8sAdminSession, **kwargs) -> K8sAdminAction:
        defaults = {
            "session": session,
            "user": user,
            "username_snapshot": user.username,
            "cluster": self.cluster,
            "namespace": "payments",
            "resource_api_version": "apps/v1",
            "resource_kind": "Deployment",
            "resource_name": "payments-api",
            "verb": K8sAdminAction.VERB_DRY_RUN_APPLY,
            "status": K8sAdminAction.STATUS_DRY_RUN,
            "request_payload_sanitized": {
                "kind": "Deployment",
                "token": "raw-token",
                "nested": {"password": "raw-password"},
            },
            "diff_summary": {"available": True, "credential": "raw-credential"},
            "response_summary": {"dry_run": True, "authorization": "Bearer raw-token", "safe": "ok"},
        }
        defaults.update(kwargs)
        return K8sAdminAction.objects.create(**defaults)

    def test_owner_lists_and_reads_sanitized_admin_actions(self):
        user = self.create_user("k8s-action-owner")
        session = self.create_session(user)
        action = self.create_action(user, session)
        self.client.force_login(user)

        list_response = self.client.get(
            reverse("api_kubernetes_admin_actions"),
            {"session_id": str(session.session_id), "limit": "10"},
        )
        detail_response = self.client.get(
            reverse("api_kubernetes_admin_action_detail", kwargs={"action_id": action.action_id})
        )

        self.assertEqual(list_response.status_code, 200)
        payload = list_response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["actions"][0]["id"], str(action.action_id))
        self.assertEqual(payload["actions"][0]["request_payload_sanitized"]["token"], "[redacted]")
        self.assertEqual(payload["actions"][0]["request_payload_sanitized"]["nested"]["password"], "[redacted]")
        self.assertEqual(payload["actions"][0]["diff_summary"]["credential"], "[redacted]")
        self.assertEqual(payload["actions"][0]["response_summary"]["authorization"], "[redacted]")
        self.assertNotIn("raw-token", json.dumps(payload))
        self.assertNotIn("raw-password", json.dumps(payload))
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["action"]["id"], str(action.action_id))

    def test_non_owner_cannot_read_other_users_admin_actions(self):
        owner = self.create_user("k8s-action-private-owner")
        session = self.create_session(owner)
        action = self.create_action(owner, session)

        other = self.create_user("k8s-action-private-other")
        self.client.force_login(other)

        list_response = self.client.get(
            reverse("api_kubernetes_admin_actions"), {"session_id": str(session.session_id)}
        )
        detail_response = self.client.get(
            reverse("api_kubernetes_admin_action_detail", kwargs={"action_id": action.action_id})
        )
        report_response = self.client.get(
            reverse("api_kubernetes_admin_action_report", kwargs={"action_id": action.action_id})
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["actions"], [])
        self.assertEqual(detail_response.status_code, 404)
        self.assertEqual(detail_response.json()["code"], "admin_action_not_found")
        self.assertEqual(report_response.status_code, 404)
        self.assertEqual(report_response.json()["code"], "admin_action_not_found")

    def test_owner_report_includes_sanitized_session_action_and_timeline(self):
        user = self.create_user("k8s-action-report-owner")
        session = self.create_session(user)
        session.metadata = {"token": "raw-session-token"}
        session.save(update_fields=["metadata", "updated_at"])
        action = self.create_action(user, session)
        recording = K8sAdminRecording.objects.create(
            session=session,
            action=action,
            user=user,
            username_snapshot=user.username,
            cluster=self.cluster,
            namespace="payments",
            resource_kind="Deployment",
            resource_name="payments-api",
            operation=K8sAdminRecording.OP_EXEC,
            status=K8sAdminRecording.STATUS_COMPLETED,
            mode="transcript_required",
            transcript_required=True,
            transcript_stored=False,
            payload_stored=False,
            policy_snapshot={"enabled": True, "authorization": "Bearer raw-token"},
            summary={"close_reason": "eof", "password": "raw-recording-password"},
            started_at=timezone.now(),
            finished_at=timezone.now(),
        )
        K8sAdminRecordingEvent.objects.create(
            recording=recording,
            sequence=1,
            stream=K8sAdminRecordingEvent.STREAM_STDOUT,
            data="TOKEN=raw-event-token",
            original_length=21,
            stored_length=21,
            redacted=False,
            metadata={"password": "raw-event-password"},
        )
        K8sAuditEvent.objects.create(
            user=user,
            username_snapshot=user.username,
            action="k8s.admin_session.create",
            provider="webterm",
            cluster=self.cluster,
            payload={"session_id": str(session.session_id), "token": "raw-session-token"},
        )
        K8sAuditEvent.objects.create(
            user=user,
            username_snapshot=user.username,
            action="k8s.admin_resource.dry_run_apply",
            provider="webterm",
            cluster=self.cluster,
            payload={
                "session_id": str(session.session_id),
                "action_id": str(action.action_id),
                "authorization": "Bearer raw-token",
            },
        )
        K8sAuditEvent.objects.create(
            user=user,
            username_snapshot=user.username,
            action="k8s.admin_resource.patch",
            provider="webterm",
            cluster=self.cluster,
            payload={"session_id": str(session.session_id), "action_id": "00000000-0000-0000-0000-000000000000"},
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("api_kubernetes_admin_action_report", kwargs={"action_id": action.action_id})
        )

        self.assertEqual(response.status_code, 200)
        report = response.json()["report"]
        self.assertEqual(report["action"]["id"], str(action.action_id))
        self.assertEqual(report["session"]["id"], str(session.session_id))
        self.assertEqual(report["session"]["metadata"]["token"], "[redacted]")
        self.assertEqual(report["summary"]["action_id"], str(action.action_id))
        self.assertEqual(report["summary"]["recording_count"], 1)
        self.assertEqual(report["recordings"][0]["id"], str(recording.recording_id))
        self.assertEqual(report["recordings"][0]["policy_snapshot"]["authorization"], "[redacted]")
        self.assertEqual(report["recordings"][0]["summary"]["password"], "[redacted]")
        self.assertEqual(report["recordings"][0]["event_count"], 1)
        self.assertEqual(report["recordings"][0]["events"][0]["data"], "TOKEN=[redacted]")
        self.assertEqual(report["recordings"][0]["events"][0]["metadata"]["password"], "[redacted]")
        self.assertTrue(report["summary"]["has_action_audit_event"])
        self.assertEqual(report["summary"]["timeline_event_count"], 2)
        self.assertEqual(
            [item["action"] for item in report["timeline"]],
            ["k8s.admin_session.create", "k8s.admin_resource.dry_run_apply"],
        )
        self.assertEqual(report["timeline"][0]["payload"]["token"], "[redacted]")
        self.assertEqual(report["timeline"][1]["payload"]["authorization"], "[redacted]")
        encoded = json.dumps(report)
        self.assertNotIn("raw-session-token", encoded)
        self.assertNotIn("raw-token", encoded)
        self.assertNotIn("raw-recording-password", encoded)
        self.assertNotIn("raw-event-token", encoded)
        self.assertNotIn("raw-event-password", encoded)
        self.assertNotIn("k8s.admin_resource.patch", encoded)

    def test_staff_can_list_all_admin_actions_with_filters(self):
        owner = self.create_user("k8s-action-staff-owner")
        session = self.create_session(owner)
        kept = self.create_action(
            owner, session, verb=K8sAdminAction.VERB_APPLY, status=K8sAdminAction.STATUS_COMPLETED
        )
        self.create_action(owner, session, verb=K8sAdminAction.VERB_DRY_RUN_APPLY, status=K8sAdminAction.STATUS_DRY_RUN)

        staff = self.create_user("k8s-action-staff", is_staff=True)
        self.client.force_login(staff)

        response = self.client.get(
            reverse("api_kubernetes_admin_actions"),
            {
                "all": "1",
                "cluster_id": f"cluster_{self.cluster.id}",
                "verb": K8sAdminAction.VERB_APPLY,
                "status": K8sAdminAction.STATUS_COMPLETED,
                "limit": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["limit"], 1)
        self.assertEqual(payload["actions"][0]["id"], str(kept.action_id))
        self.assertEqual(payload["actions"][0]["verb"], K8sAdminAction.VERB_APPLY)

    def test_staff_can_filter_admin_actions_by_post_review_status(self):
        owner = self.create_user("k8s-action-review-filter-owner")
        session = self.create_session(owner)
        pending = self.create_action(
            owner, session, verb=K8sAdminAction.VERB_APPLY, status=K8sAdminAction.STATUS_COMPLETED
        )
        reviewed = self.create_action(
            owner,
            session,
            verb=K8sAdminAction.VERB_DELETE,
            status=K8sAdminAction.STATUS_COMPLETED,
            response_summary={
                "post_review_status": "completed",
                "post_review": {"outcome": "verified", "summary": "checked", "reviewed_by": "staff"},
            },
        )
        not_ready = self.create_action(
            owner, session, verb=K8sAdminAction.VERB_PATCH, status=K8sAdminAction.STATUS_PLANNED
        )
        no_review = self.create_action(
            owner, session, verb=K8sAdminAction.VERB_GET, status=K8sAdminAction.STATUS_COMPLETED
        )
        staff = self.create_user("k8s-action-review-filter-staff", is_staff=True)
        self.client.force_login(staff)

        pending_response = self.client.get(
            reverse("api_kubernetes_admin_actions"), {"all": "1", "post_review_status": "pending", "limit": "10"}
        )
        completed_response = self.client.get(
            reverse("api_kubernetes_admin_actions"), {"all": "1", "post_review_status": "completed", "limit": "10"}
        )
        any_response = self.client.get(
            reverse("api_kubernetes_admin_actions"), {"all": "1", "post_review_status": "any", "limit": "10"}
        )
        none_response = self.client.get(
            reverse("api_kubernetes_admin_actions"), {"all": "1", "post_review_status": "none", "limit": "10"}
        )

        self.assertEqual(pending_response.status_code, 200)
        pending_payload = pending_response.json()
        self.assertEqual([item["id"] for item in pending_payload["actions"]], [str(pending.action_id)])
        self.assertEqual(pending_payload["review_summary"], {"pending": 1, "completed": 0, "not_ready": 0, "none": 0})
        self.assertEqual(pending_payload["post_review_status"], "pending")
        self.assertFalse(pending_payload["review_scan_truncated"])

        self.assertEqual(completed_response.status_code, 200)
        self.assertEqual([item["id"] for item in completed_response.json()["actions"]], [str(reviewed.action_id)])

        self.assertEqual(any_response.status_code, 200)
        self.assertEqual(
            {item["id"] for item in any_response.json()["actions"]},
            {str(pending.action_id), str(reviewed.action_id), str(not_ready.action_id)},
        )

        self.assertEqual(none_response.status_code, 200)
        self.assertEqual([item["id"] for item in none_response.json()["actions"]], [str(no_review.action_id)])

    def test_admin_action_post_review_status_filter_rejects_unknown_value(self):
        staff = self.create_user("k8s-action-review-filter-invalid", is_staff=True)
        self.client.force_login(staff)

        response = self.client.get(reverse("api_kubernetes_admin_actions"), {"post_review_status": "stale"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "post_review_status_invalid")

    def test_staff_with_matching_grant_can_post_review_admin_action_with_sanitized_evidence(self):
        owner = self.create_user("k8s-action-review-owner", grant_admin_write=True)
        session = self.create_session(owner)
        action = self.create_action(
            owner, session, verb=K8sAdminAction.VERB_APPLY, status=K8sAdminAction.STATUS_COMPLETED
        )
        reviewer = self.create_user("k8s-action-review-staff", is_staff=True, grant_admin_write=True)
        self.client.force_login(reviewer)

        response = self.client.post(
            reverse("api_kubernetes_admin_action_review", kwargs={"action_id": action.action_id}),
            data=json.dumps(
                {
                    "outcome": "verified",
                    "summary": "checked rollout output with Bearer raw-review-token",
                    "evidence_ref": "ticket password=raw-evidence-password",
                    "follow_up_ref": "INC-42",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["action"]["post_review_status"], "completed")
        self.assertFalse(payload["action"]["post_review_required"])
        self.assertEqual(payload["post_review"]["outcome"], "verified")
        self.assertEqual(payload["post_review"]["reviewed_by"], reviewer.username)
        encoded = json.dumps(payload)
        self.assertNotIn("raw-review-token", encoded)
        self.assertNotIn("raw-evidence-password", encoded)
        self.assertIn("[REDACTED:", encoded)

        action.refresh_from_db()
        self.assertEqual(action.response_summary["post_review_status"], "completed")
        self.assertEqual(action.response_summary["post_review"]["outcome"], "verified")
        self.assertNotIn("raw-review-token", json.dumps(action.response_summary))
        self.assertNotIn("raw-evidence-password", json.dumps(action.response_summary))

        audit = K8sAuditEvent.objects.get(action="k8s.admin_action.post_review")
        self.assertEqual(audit.payload["action_id"], str(action.action_id))
        self.assertEqual(audit.payload["post_review"]["outcome"], "verified")
        self.assertNotIn("raw-review-token", json.dumps(audit.payload))
        self.assertNotIn("raw-evidence-password", json.dumps(audit.payload))

        report_response = self.client.get(
            reverse("api_kubernetes_admin_action_report", kwargs={"action_id": action.action_id})
        )
        self.assertEqual(report_response.status_code, 200)
        report = report_response.json()["report"]
        self.assertEqual(report["summary"]["post_review_status"], "completed")
        self.assertTrue(report["summary"]["has_post_review"])

    def test_non_staff_owner_cannot_post_review_admin_action(self):
        owner = self.create_user("k8s-action-review-owner-denied", grant_admin_write=True)
        session = self.create_session(owner)
        action = self.create_action(
            owner, session, verb=K8sAdminAction.VERB_APPLY, status=K8sAdminAction.STATUS_COMPLETED
        )
        self.client.force_login(owner)

        response = self.client.post(
            reverse("api_kubernetes_admin_action_review", kwargs={"action_id": action.action_id}),
            data=json.dumps({"outcome": "verified", "summary": "owner tried to close own action"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "staff_required")
        action.refresh_from_db()
        self.assertNotIn("post_review", action.response_summary)
        self.assertTrue(
            K8sAuditEvent.objects.filter(
                action="k8s.admin_action.post_review_rejected", payload__code="staff_required"
            ).exists()
        )

    def test_break_glass_action_review_requires_break_glass_grant(self):
        owner = self.create_user("k8s-action-break-review-owner", grant_break_glass=True)
        session = self.create_session(owner)
        session.mode = K8sAdminSession.MODE_BREAK_GLASS
        session.risk_tier = K8sAdminSession.RISK_CRITICAL
        session.allowed_verbs = ["exec"]
        session.allowed_kinds = ["pod"]
        session.save(update_fields=["mode", "risk_tier", "allowed_verbs", "allowed_kinds", "updated_at"])
        action = self.create_action(
            owner,
            session,
            verb=K8sAdminAction.VERB_EXEC,
            status=K8sAdminAction.STATUS_EXECUTION_BLOCKED,
            resource_kind="Pod",
        )
        reviewer = self.create_user("k8s-action-break-review-staff", is_staff=True, grant_admin_write=True)
        self.client.force_login(reviewer)

        response = self.client.post(
            reverse("api_kubernetes_admin_action_review", kwargs={"action_id": action.action_id}),
            data=json.dumps({"outcome": "accepted", "summary": "reviewed blocked exec attempt"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "break_glass_required")
        action.refresh_from_db()
        self.assertNotIn("post_review", action.response_summary)

    def test_admin_actions_require_kubernetes_feature(self):
        user = self.create_user("k8s-action-no-feature", grant_kubernetes=False)
        self.client.force_login(user)

        response = self.client.get(reverse("api_kubernetes_admin_actions"))

        self.assertEqual(response.status_code, 403)
