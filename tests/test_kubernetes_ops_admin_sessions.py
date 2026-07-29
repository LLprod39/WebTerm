import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminSession, K8sAuditEvent, K8sCluster, K8sProvider


class KubernetesOpsAdminSessionTests(TestCase):
    def create_user(
        self,
        username: str,
        *,
        grant_kubernetes: bool = True,
        grant_admin_read: bool = False,
        grant_admin_write: bool = False,
        grant_break_glass: bool = False,
        is_staff: bool = False,
    ) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=is_staff)
        grants = {
            "kubernetes": grant_kubernetes,
            "kubernetes_admin_read": grant_admin_read,
            "kubernetes_admin_write": grant_admin_write,
            "kubernetes_break_glass": grant_break_glass,
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

    def post_session(self, payload: dict):
        return self.client.post(
            reverse("api_kubernetes_admin_sessions"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_regular_kubernetes_reader_cannot_create_admin_read_session(self):
        user = self.create_user("k8s-reader")
        self.client.force_login(user)

        response = self.post_session({"mode": K8sAdminSession.MODE_READ, "cluster_id": f"cluster_{self.cluster.id}"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_read_required")
        self.assertFalse(K8sAdminSession.objects.exists())
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_session.rejected").exists())

    def test_admin_read_user_gets_active_read_session_only(self):
        user = self.create_user("k8s-admin-read", grant_admin_read=True)
        self.client.force_login(user)

        response = self.post_session(
            {
                "mode": K8sAdminSession.MODE_READ,
                "cluster_id": f"cluster_{self.cluster.id}",
                "namespace": "payments",
                "ttl_minutes": 999,
            }
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["session"]
        self.assertEqual(payload["mode"], K8sAdminSession.MODE_READ)
        self.assertEqual(payload["status"], K8sAdminSession.STATUS_ACTIVE)
        self.assertEqual(payload["cluster_name"], "prod-kz-1")
        self.assertEqual(payload["namespace"], "payments")
        self.assertIn("yaml", payload["allowed_verbs"])
        self.assertNotIn("apply", payload["allowed_verbs"])
        self.assertEqual(K8sAdminSession.objects.get().risk_tier, K8sAdminSession.RISK_LOW)

    @override_settings(KUBERNETES_ADMIN_MODE_ENABLED=False)
    def test_global_admin_mode_kill_switch_blocks_new_sessions_without_deleting_existing_data(self):
        user = self.create_user("k8s-admin-disabled-session", grant_admin_read=True)
        existing = K8sAdminSession.objects.create(
            user=user,
            username_snapshot=user.username,
            cluster=self.cluster,
            mode=K8sAdminSession.MODE_READ,
            status=K8sAdminSession.STATUS_ACTIVE,
            risk_tier=K8sAdminSession.RISK_LOW,
            allowed_verbs=["get", "list", "watch", "logs", "yaml"],
            allowed_kinds=["*"],
            allowed_namespaces=["*"],
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(user)

        response = self.post_session({"mode": K8sAdminSession.MODE_READ, "cluster_id": f"cluster_{self.cluster.id}"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_mode_disabled")
        self.assertTrue(K8sAdminSession.objects.filter(id=existing.id, status=K8sAdminSession.STATUS_ACTIVE).exists())
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_session.rejected").exists())

    def test_write_session_requires_write_feature_and_reason(self):
        reader = self.create_user("k8s-admin-read-no-write", grant_admin_read=True)
        self.client.force_login(reader)

        no_feature = self.post_session({"mode": K8sAdminSession.MODE_WRITE, "reason": "need safe dry-run"})
        self.assertEqual(no_feature.status_code, 403)
        self.assertEqual(no_feature.json()["code"], "admin_write_required")

        writer = self.create_user("k8s-admin-write", grant_admin_write=True)
        self.client.force_login(writer)
        missing_reason = self.post_session({"mode": K8sAdminSession.MODE_WRITE})

        self.assertEqual(missing_reason.status_code, 400)
        self.assertEqual(missing_reason.json()["code"], "reason_required")
        self.assertFalse(K8sAdminSession.objects.exists())

    def test_write_session_is_pending_until_staff_approval(self):
        requester = self.create_user("k8s-write-requester", grant_admin_write=True)
        self.client.force_login(requester)
        create_response = self.post_session(
            {
                "mode": K8sAdminSession.MODE_WRITE,
                "cluster_id": f"cluster_{self.cluster.id}",
                "namespace": "payments",
                "reason": "dry-run a manifest before opening a GitOps change",
            }
        )
        session_id = create_response.json()["session"]["id"]

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["session"]["status"], K8sAdminSession.STATUS_PENDING_APPROVAL)

        approver = self.create_user("k8s-write-approver", grant_admin_write=True, is_staff=True)
        self.client.force_login(approver)
        approve_response = self.client.post(
            reverse("api_kubernetes_admin_session_approve", kwargs={"session_id": session_id}),
            data=json.dumps({"approval_ref": "CHG-2026-0001"}),
            content_type="application/json",
        )

        self.assertEqual(approve_response.status_code, 200)
        payload = approve_response.json()["session"]
        self.assertEqual(payload["status"], K8sAdminSession.STATUS_ACTIVE)
        self.assertEqual(payload["approval_ref"], "CHG-2026-0001")
        self.assertEqual(payload["approved_by"], approver.username)

    def test_write_session_cannot_expand_mode_allowed_kinds(self):
        requester = self.create_user("k8s-write-kind-escalation", grant_admin_write=True)
        self.client.force_login(requester)

        response = self.post_session(
            {
                "mode": K8sAdminSession.MODE_WRITE,
                "cluster_id": f"cluster_{self.cluster.id}",
                "namespace": "payments",
                "reason": "request a write session",
                "allowed_kinds": ["Deployment", "Secret"],
            }
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "allowed_kinds_out_of_scope")
        self.assertFalse(K8sAdminSession.objects.exists())

    def test_nonstaff_user_cannot_approve_write_session(self):
        requester = self.create_user("k8s-write-requester-nonstaff", grant_admin_write=True)
        self.client.force_login(requester)
        create_response = self.post_session(
            {"mode": K8sAdminSession.MODE_WRITE, "reason": "need dry-run before GitOps change"}
        )
        session_id = create_response.json()["session"]["id"]

        approve_response = self.client.post(
            reverse("api_kubernetes_admin_session_approve", kwargs={"session_id": session_id}),
            data=json.dumps({"approval_ref": "CHG-2026-0002"}),
            content_type="application/json",
        )

        self.assertEqual(approve_response.status_code, 403)
        self.assertEqual(approve_response.json()["code"], "staff_required")

    def test_expired_pending_session_cannot_be_silently_extended_by_approval(self):
        requester = self.create_user("k8s-write-requester-expired-approval", grant_admin_write=True)
        self.client.force_login(requester)
        create_response = self.post_session(
            {
                "mode": K8sAdminSession.MODE_WRITE,
                "cluster_id": f"cluster_{self.cluster.id}",
                "namespace": "payments",
                "reason": "approval window should expire",
            }
        )
        session_id = create_response.json()["session"]["id"]
        session = K8sAdminSession.objects.get(session_id=session_id)
        original_expires_at = timezone.now() - timedelta(minutes=1)
        session.expires_at = original_expires_at
        session.save(update_fields=["expires_at", "updated_at"])

        approver = self.create_user("k8s-write-approver-expired-approval", grant_admin_write=True, is_staff=True)
        self.client.force_login(approver)
        approve_response = self.client.post(
            reverse("api_kubernetes_admin_session_approve", kwargs={"session_id": session_id}),
            data=json.dumps({"approval_ref": "CHG-EXPIRED-SHOULD-NOT-ACTIVATE"}),
            content_type="application/json",
        )

        self.assertEqual(approve_response.status_code, 409)
        self.assertEqual(approve_response.json()["code"], "admin_session_not_pending")
        session.refresh_from_db()
        self.assertEqual(session.status, K8sAdminSession.STATUS_EXPIRED)
        self.assertEqual(session.expires_at, original_expires_at)
        self.assertEqual(session.approval_ref, "")
        self.assertIsNone(session.approved_at)
        self.assertIsNone(session.approved_by)
        self.assertIn("expired_at", session.metadata)
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_session.approval_rejected").exists())

    def test_break_glass_requires_explicit_feature_and_stays_pending(self):
        writer = self.create_user("k8s-write-no-break-glass", grant_admin_write=True)
        self.client.force_login(writer)
        denied = self.post_session(
            {"mode": K8sAdminSession.MODE_BREAK_GLASS, "reason": "production incident investigation"}
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["code"], "break_glass_required")

        break_glass_user = self.create_user("k8s-break-glass", grant_break_glass=True)
        self.client.force_login(break_glass_user)
        response = self.post_session(
            {
                "mode": K8sAdminSession.MODE_BREAK_GLASS,
                "cluster_id": f"cluster_{self.cluster.id}",
                "namespace": "payments",
                "reason": "incident bridge needs pod-level inspection",
            }
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["session"]
        self.assertEqual(payload["status"], K8sAdminSession.STATUS_PENDING_APPROVAL)
        self.assertEqual(payload["risk_tier"], K8sAdminSession.RISK_CRITICAL)
        self.assertIn("exec", payload["allowed_verbs"])
        self.assertNotIn("apply", payload["allowed_verbs"])
        self.assertTrue(payload["post_review_required"])
        self.assertEqual(payload["post_review_status"], "pending")

    @override_settings(KUBERNETES_ADMIN_BREAK_GLASS_APPLY_BYPASS_ENABLED=True)
    def test_break_glass_session_includes_apply_only_when_bypass_flag_is_enabled(self):
        break_glass_user = self.create_user("k8s-break-glass-apply-session", grant_break_glass=True)
        self.client.force_login(break_glass_user)

        response = self.post_session(
            {
                "mode": K8sAdminSession.MODE_BREAK_GLASS,
                "cluster_id": f"cluster_{self.cluster.id}",
                "namespace": "payments",
                "reason": "incident bridge needs emergency apply",
            }
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["session"]
        self.assertEqual(payload["status"], K8sAdminSession.STATUS_PENDING_APPROVAL)
        self.assertIn("exec", payload["allowed_verbs"])
        self.assertIn("apply", payload["allowed_verbs"])

    def test_owner_can_revoke_active_read_session(self):
        user = self.create_user("k8s-admin-read-revoke", grant_admin_read=True)
        self.client.force_login(user)
        create_response = self.post_session({"mode": K8sAdminSession.MODE_READ})
        session_id = create_response.json()["session"]["id"]

        revoke_response = self.client.post(
            reverse("api_kubernetes_admin_session_revoke", kwargs={"session_id": session_id}),
            data=json.dumps({"reason": "finished inspection"}),
            content_type="application/json",
        )

        self.assertEqual(revoke_response.status_code, 200)
        self.assertEqual(revoke_response.json()["session"]["status"], K8sAdminSession.STATUS_REVOKED)
        self.assertEqual(K8sAdminSession.objects.get().metadata["revoked_reason"], "finished inspection")

    def test_owner_can_close_active_read_session(self):
        user = self.create_user("k8s-admin-read-close", grant_admin_read=True)
        self.client.force_login(user)
        create_response = self.post_session({"mode": K8sAdminSession.MODE_READ})
        session_id = create_response.json()["session"]["id"]

        close_response = self.client.post(
            reverse("api_kubernetes_admin_session_close", kwargs={"session_id": session_id}),
            data=json.dumps({"reason": "finished safe inspection"}),
            content_type="application/json",
        )

        self.assertEqual(close_response.status_code, 200)
        payload = close_response.json()["session"]
        session = K8sAdminSession.objects.get()
        self.assertEqual(payload["status"], K8sAdminSession.STATUS_CLOSED)
        self.assertTrue(payload["closed_at"])
        self.assertEqual(session.status, K8sAdminSession.STATUS_CLOSED)
        self.assertIsNotNone(session.closed_at)
        self.assertEqual(session.metadata["closed_by"], user.username)
        self.assertEqual(session.metadata["closed_reason"], "finished safe inspection")
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_session.close").exists())

    def test_staff_can_close_another_users_active_session(self):
        owner = self.create_user("k8s-admin-read-close-owner", grant_admin_read=True)
        self.client.force_login(owner)
        create_response = self.post_session({"mode": K8sAdminSession.MODE_READ})
        session_id = create_response.json()["session"]["id"]

        staff = self.create_user("k8s-admin-read-close-staff", is_staff=True)
        self.client.force_login(staff)
        close_response = self.client.post(
            reverse("api_kubernetes_admin_session_close", kwargs={"session_id": session_id}),
            data=json.dumps({"reason": "operator handoff finished"}),
            content_type="application/json",
        )

        self.assertEqual(close_response.status_code, 200)
        session = K8sAdminSession.objects.get()
        self.assertEqual(session.status, K8sAdminSession.STATUS_CLOSED)
        self.assertEqual(session.metadata["closed_by"], staff.username)

    def test_non_owner_cannot_close_admin_session(self):
        owner = self.create_user("k8s-admin-read-close-private", grant_admin_read=True)
        self.client.force_login(owner)
        create_response = self.post_session({"mode": K8sAdminSession.MODE_READ})
        session_id = create_response.json()["session"]["id"]

        other = self.create_user("k8s-admin-read-close-other", grant_admin_read=True)
        self.client.force_login(other)
        close_response = self.client.post(
            reverse("api_kubernetes_admin_session_close", kwargs={"session_id": session_id}),
            data=json.dumps({"reason": "not my session"}),
            content_type="application/json",
        )

        self.assertEqual(close_response.status_code, 404)
        self.assertEqual(close_response.json()["code"], "admin_session_not_found")
        self.assertEqual(K8sAdminSession.objects.get().status, K8sAdminSession.STATUS_ACTIVE)

    def test_pending_or_expired_session_cannot_be_closed(self):
        requester = self.create_user("k8s-admin-write-close-pending", grant_admin_write=True)
        self.client.force_login(requester)
        create_response = self.post_session({"mode": K8sAdminSession.MODE_WRITE, "reason": "planned manifest review"})
        session_id = create_response.json()["session"]["id"]

        pending_close = self.client.post(
            reverse("api_kubernetes_admin_session_close", kwargs={"session_id": session_id}),
            data=json.dumps({"reason": "request not approved"}),
            content_type="application/json",
        )

        self.assertEqual(pending_close.status_code, 409)
        self.assertEqual(pending_close.json()["code"], "admin_session_not_active")

        reader = self.create_user("k8s-admin-read-close-expired", grant_admin_read=True)
        self.client.force_login(reader)
        expired_response = self.post_session({"mode": K8sAdminSession.MODE_READ})
        expired_session = K8sAdminSession.objects.get(session_id=expired_response.json()["session"]["id"])
        expired_session.expires_at = timezone.now()
        expired_session.save(update_fields=["expires_at", "updated_at"])

        expired_close = self.client.post(
            reverse("api_kubernetes_admin_session_close", kwargs={"session_id": expired_session.session_id}),
            data=json.dumps({"reason": "too late"}),
            content_type="application/json",
        )

        self.assertEqual(expired_close.status_code, 409)
        self.assertEqual(expired_close.json()["code"], "admin_session_not_active")
        expired_session.refresh_from_db()
        self.assertEqual(expired_session.status, K8sAdminSession.STATUS_EXPIRED)

    def test_break_glass_post_review_requires_closed_session_and_staff_break_glass_reviewer(self):
        requester = self.create_user("k8s-break-glass-review-requester", grant_break_glass=True)
        self.client.force_login(requester)
        create_response = self.post_session(
            {
                "mode": K8sAdminSession.MODE_BREAK_GLASS,
                "cluster_id": f"cluster_{self.cluster.id}",
                "namespace": "payments",
                "reason": "incident bridge needs emergency inspection",
            }
        )
        session_id = create_response.json()["session"]["id"]

        staff = self.create_user("k8s-break-glass-reviewer", grant_break_glass=True, is_staff=True)
        self.client.force_login(staff)
        approve_response = self.client.post(
            reverse("api_kubernetes_admin_session_approve", kwargs={"session_id": session_id}),
            data=json.dumps({"approval_ref": "INC-2026-REVIEW"}),
            content_type="application/json",
        )
        self.assertEqual(approve_response.status_code, 200)

        active_review = self.client.post(
            reverse("api_kubernetes_admin_session_review", kwargs={"session_id": session_id}),
            data=json.dumps({"outcome": "accepted", "summary": "review before close"}),
            content_type="application/json",
        )
        self.assertEqual(active_review.status_code, 409)
        self.assertEqual(active_review.json()["code"], "post_review_not_ready")

        self.client.force_login(requester)
        close_response = self.client.post(
            reverse("api_kubernetes_admin_session_close", kwargs={"session_id": session_id}),
            data=json.dumps({"reason": "incident inspection finished"}),
            content_type="application/json",
        )
        self.assertEqual(close_response.status_code, 200)

        nonstaff_review = self.client.post(
            reverse("api_kubernetes_admin_session_review", kwargs={"session_id": session_id}),
            data=json.dumps({"outcome": "accepted", "summary": "requester cannot self-review"}),
            content_type="application/json",
        )
        self.assertEqual(nonstaff_review.status_code, 403)
        self.assertEqual(nonstaff_review.json()["code"], "staff_required")

        self.client.force_login(staff)
        review_response = self.client.post(
            reverse("api_kubernetes_admin_session_review", kwargs={"session_id": session_id}),
            data=json.dumps(
                {
                    "outcome": "needs_followup",
                    "summary": "commands matched the incident bridge scope",
                    "evidence_ref": "INC-2026-REVIEW#postmortem",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(review_response.status_code, 200)
        payload = review_response.json()["session"]
        self.assertFalse(payload["post_review_required"])
        self.assertEqual(payload["post_review_status"], "completed")
        self.assertEqual(payload["post_review"]["outcome"], "needs_followup")
        self.assertEqual(payload["post_review"]["reviewed_by"], staff.username)
        session = K8sAdminSession.objects.get(session_id=session_id)
        self.assertFalse(session.metadata["post_review_required"])
        self.assertEqual(session.metadata["post_review"]["evidence_ref"], "INC-2026-REVIEW#postmortem")
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.admin_session.post_review").exists())

    def test_non_break_glass_session_does_not_accept_post_review(self):
        user = self.create_user("k8s-admin-read-review", grant_admin_read=True)
        self.client.force_login(user)
        create_response = self.post_session({"mode": K8sAdminSession.MODE_READ})
        session_id = create_response.json()["session"]["id"]
        close_response = self.client.post(
            reverse("api_kubernetes_admin_session_close", kwargs={"session_id": session_id}),
            data=json.dumps({"reason": "finished read session"}),
            content_type="application/json",
        )
        self.assertEqual(close_response.status_code, 200)

        staff = self.create_user("k8s-admin-read-review-staff", grant_break_glass=True, is_staff=True)
        self.client.force_login(staff)
        review_response = self.client.post(
            reverse("api_kubernetes_admin_session_review", kwargs={"session_id": session_id}),
            data=json.dumps({"outcome": "accepted", "summary": "not needed"}),
            content_type="application/json",
        )

        self.assertEqual(review_response.status_code, 409)
        self.assertEqual(review_response.json()["code"], "post_review_not_required")
