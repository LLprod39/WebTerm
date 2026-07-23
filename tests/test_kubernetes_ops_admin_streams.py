from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminSession, K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.admin_streams import (
    active_admin_stream_session_status,
    bounded_stream_float,
    bounded_stream_int,
    build_log_stream_summary,
    close_admin_stream,
    fail_admin_stream,
    open_admin_log_stream_snapshot,
    open_admin_watch_stream_snapshot,
    start_admin_log_stream,
    start_admin_watch_stream,
    stop_admin_stream,
)


class KubernetesOpsAdminStreamTests(TestCase):
    def create_user(self, username: str, *, grant_kubernetes: bool = True, grant_admin_read: bool = False) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        if grant_kubernetes:
            UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        if grant_admin_read:
            UserAppPermission.objects.create(user=user, feature="kubernetes_admin_read", allowed=True)
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

    def create_read_session(self, user: User, **kwargs) -> K8sAdminSession:
        defaults = {
            "user": user,
            "username_snapshot": user.username,
            "cluster": self.cluster,
            "mode": K8sAdminSession.MODE_READ,
            "status": K8sAdminSession.STATUS_ACTIVE,
            "risk_tier": K8sAdminSession.RISK_LOW,
            "allowed_verbs": ["get", "list", "watch", "logs", "yaml"],
            "allowed_kinds": ["*"],
            "allowed_namespaces": ["*"],
            "expires_at": timezone.now() + timedelta(hours=1),
        }
        defaults.update(kwargs)
        return K8sAdminSession.objects.create(**defaults)

    def test_log_stream_snapshot_audits_start_stop_without_log_content(self):
        user = self.create_user("k8s-admin-log-stream", grant_admin_read=True)
        session = self.create_read_session(user)
        log_payload = {
            "success": True,
            "target": {"namespace": "payments", "name": "payments-api-abc123", "container": ""},
            "source": "provider_snapshot",
            "available": True,
            "lines": ["boot ok", "token=raw-secret"],
            "line_count": 2,
            "truncated": False,
        }

        with patch(
            "kubernetes_ops.services.admin_streams.get_admin_pod_log_snapshot", return_value=log_payload
        ) as snapshot:
            envelope = open_admin_log_stream_snapshot(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                namespace="payments",
                pod_name="payments-api-abc123",
                tail_lines=120,
                stream_id="stream-log-1",
            )

        self.assertEqual(envelope["stream_type"], "logs")
        self.assertEqual(envelope["summary"]["line_count"], 2)
        snapshot.assert_called_once()
        actions = list(K8sAuditEvent.objects.order_by("created_at").values_list("action", flat=True))
        self.assertEqual(actions, ["k8s.admin_stream.logs_started", "k8s.admin_stream.logs_stopped"])
        stopped = K8sAuditEvent.objects.get(action="k8s.admin_stream.logs_stopped")
        self.assertEqual(stopped.payload["line_count"], 2)
        self.assertIn("duration_ms", stopped.payload)
        self.assertNotIn("boot ok", str(stopped.payload))
        self.assertNotIn("raw-secret", str(stopped.payload))

    def test_watch_stream_snapshot_audits_metadata_without_resource_body(self):
        user = self.create_user("k8s-admin-watch-stream", grant_admin_read=True)
        session = self.create_read_session(user)
        watch_payload = {
            "success": True,
            "target": {"api_version": "apps/v1", "kind": "Deployment", "namespace": "payments", "name": ""},
            "source": "provider_watch_preview",
            "available": True,
            "events": [
                {
                    "type": "MODIFIED",
                    "resource_version": "42",
                    "object": {"metadata": {"name": "payments-api", "labels": {"token": "raw-token"}}},
                }
            ],
            "event_count": 1,
            "truncated": False,
            "latest_resource_version": "42",
        }

        with patch(
            "kubernetes_ops.services.admin_streams.get_admin_resource_watch_preview", return_value=watch_payload
        ):
            envelope = open_admin_watch_stream_snapshot(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="apps/v1",
                kind="Deployment",
                namespace="payments",
                limit=20,
                stream_id="stream-watch-1",
            )

        self.assertEqual(envelope["stream_type"], "watch")
        self.assertEqual(envelope["summary"]["event_count"], 1)
        stopped = K8sAuditEvent.objects.get(action="k8s.admin_stream.watch_stopped")
        self.assertEqual(stopped.payload["latest_resource_version"], "42")
        self.assertNotIn("payments-api", str(stopped.payload))
        self.assertNotIn("raw-token", str(stopped.payload))

    def test_admin_stream_requires_admin_read_before_provider_call(self):
        user = self.create_user("k8s-regular-stream")
        session = self.create_read_session(user)

        with (
            patch("kubernetes_ops.services.admin_streams.get_admin_pod_log_snapshot") as snapshot,
            self.assertRaises(AdminResourceError) as raised,
        ):
            open_admin_log_stream_snapshot(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                namespace="payments",
                pod_name="payments-api-abc123",
            )

        self.assertEqual(raised.exception.code, "admin_read_required")
        snapshot.assert_not_called()
        self.assertFalse(K8sAuditEvent.objects.exists())

    def test_admin_stream_rejects_expired_session_before_start_audit(self):
        user = self.create_user("k8s-expired-stream", grant_admin_read=True)
        session = self.create_read_session(user, expires_at=timezone.now() - timedelta(minutes=1))

        with self.assertRaises(AdminResourceError) as raised:
            open_admin_watch_stream_snapshot(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                api_version="v1",
                kind="Pod",
                namespace="payments",
            )

        self.assertEqual(raised.exception.code, "admin_session_not_active")
        session.refresh_from_db()
        self.assertEqual(session.status, K8sAdminSession.STATUS_EXPIRED)
        self.assertFalse(K8sAuditEvent.objects.exists())

    def test_admin_stream_rejects_closed_session_before_start_audit(self):
        user = self.create_user("k8s-closed-stream", grant_admin_read=True)
        session = self.create_read_session(user, status=K8sAdminSession.STATUS_CLOSED, closed_at=timezone.now())

        with self.assertRaises(AdminResourceError) as raised:
            open_admin_log_stream_snapshot(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{self.cluster.id}",
                namespace="payments",
                pod_name="payments-api-abc123",
            )

        self.assertEqual(raised.exception.code, "admin_session_not_active")
        self.assertFalse(K8sAuditEvent.objects.exists())

    def test_kubernetes_websocket_routes_are_registered(self):
        from web_ui.routing import websocket_urlpatterns

        patterns = [str(pattern.pattern) for pattern in websocket_urlpatterns]
        self.assertIn("ws/kubernetes/admin/logs/<uuid:session_id>/", patterns)
        self.assertIn("ws/kubernetes/admin/watch/<uuid:session_id>/", patterns)
        self.assertIn("ws/kubernetes/admin/exec/<uuid:session_id>/", patterns)
        self.assertIn("ws/kubernetes/admin/port-forward/<uuid:session_id>/", patterns)

    def test_follow_stream_lifecycle_records_single_start_stop_without_batch_body(self):
        user = self.create_user("k8s-admin-follow-stream", grant_admin_read=True)
        session = self.create_read_session(user)

        stream = start_admin_log_stream(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            namespace="payments",
            pod_name="payments-api-abc123",
            follow=True,
            stream_id="follow-log-1",
        )
        payload = {
            "target": {"namespace": "payments", "name": "payments-api-abc123"},
            "source": "provider_snapshot",
            "available": True,
            "lines": ["token=raw-secret"],
            "line_count": 1,
            "truncated": False,
        }
        summary = build_log_stream_summary(
            payload, started_at=stream["started_at"], duration_ms=25, batch_count=2, follow=True
        )
        summary["close_reason"] = "max_batches"
        stop_admin_stream(
            user=user,
            session_pk=stream["session_pk"],
            stream_id=stream["stream_id"],
            stream_type="logs",
            summary=summary,
        )

        actions = list(K8sAuditEvent.objects.order_by("created_at").values_list("action", flat=True))
        self.assertEqual(actions, ["k8s.admin_stream.logs_started", "k8s.admin_stream.logs_stopped"])
        stopped = K8sAuditEvent.objects.get(action="k8s.admin_stream.logs_stopped")
        self.assertEqual(stopped.payload["batch_count"], 2)
        self.assertTrue(stopped.payload["follow"])
        self.assertEqual(stopped.payload["close_reason"], "max_batches")
        self.assertNotIn("raw-secret", str(stopped.payload))

    def test_follow_stream_failure_records_error_code_without_batch_body(self):
        user = self.create_user("k8s-admin-follow-fail", grant_admin_read=True)
        session = self.create_read_session(user)

        stream = start_admin_log_stream(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            namespace="payments",
            pod_name="payments-api-abc123",
            follow=True,
            stream_id="follow-log-fail",
        )
        fail_admin_stream(
            user=user,
            session_pk=stream["session_pk"],
            stream_id=stream["stream_id"],
            stream_type="logs",
            error_code="admin_session_not_active",
            duration_ms=5,
        )

        failed = K8sAuditEvent.objects.get(action="k8s.admin_stream.logs_failed")
        self.assertEqual(failed.payload["error_code"], "admin_session_not_active")
        self.assertEqual(failed.payload["duration_ms"], 5)

    def test_log_follow_client_disconnect_records_stop_without_batch_body(self):
        user = self.create_user("k8s-admin-follow-disconnect", grant_admin_read=True)
        session = self.create_read_session(user)
        stream = start_admin_log_stream(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            namespace="payments",
            pod_name="payments-api-abc123",
            follow=True,
            stream_id="follow-log-disconnect",
        )
        payload = {
            "target": {"namespace": "payments", "name": "payments-api-abc123"},
            "source": "provider_snapshot",
            "available": True,
            "lines": ["boot ok", "token=raw-secret"],
            "line_count": 2,
            "truncated": False,
        }

        summary = close_admin_stream(
            user=user,
            stream=stream,
            last_payload=payload,
            batch_count=1,
            close_reason="client_disconnect",
        )

        self.assertEqual(summary["close_reason"], "client_disconnect")
        self.assertEqual(summary["batch_count"], 1)
        stopped = K8sAuditEvent.objects.get(action="k8s.admin_stream.logs_stopped")
        self.assertEqual(stopped.payload["close_reason"], "client_disconnect")
        self.assertEqual(stopped.payload["line_count"], 2)
        self.assertNotIn("boot ok", str(stopped.payload))
        self.assertNotIn("raw-secret", str(stopped.payload))

    def test_watch_follow_client_disconnect_records_stop_without_resource_body(self):
        user = self.create_user("k8s-admin-watch-disconnect", grant_admin_read=True)
        session = self.create_read_session(user)
        stream = start_admin_watch_stream(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="apps/v1",
            kind="Deployment",
            namespace="payments",
            follow=True,
            stream_id="follow-watch-disconnect",
        )
        payload = {
            "target": {"api_version": "apps/v1", "kind": "Deployment", "namespace": "payments", "name": ""},
            "source": "provider_watch_preview",
            "available": True,
            "events": [
                {
                    "type": "MODIFIED",
                    "resource_version": "42",
                    "object": {"metadata": {"name": "payments-api", "labels": {"token": "raw-token"}}},
                }
            ],
            "event_count": 1,
            "truncated": False,
            "latest_resource_version": "42",
        }

        summary = close_admin_stream(
            user=user,
            stream=stream,
            last_payload=payload,
            batch_count=1,
            close_reason="client_disconnect",
        )

        self.assertEqual(summary["close_reason"], "client_disconnect")
        self.assertEqual(summary["latest_resource_version"], "42")
        stopped = K8sAuditEvent.objects.get(action="k8s.admin_stream.watch_stopped")
        self.assertEqual(stopped.payload["close_reason"], "client_disconnect")
        self.assertEqual(stopped.payload["event_count"], 1)
        self.assertNotIn("payments-api", str(stopped.payload))
        self.assertNotIn("raw-token", str(stopped.payload))

    def test_log_follow_expiring_session_closes_stream_without_provider_body(self):
        user = self.create_user("k8s-admin-follow-expired", grant_admin_read=True)
        session = self.create_read_session(user)
        stream = start_admin_log_stream(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            namespace="payments",
            pod_name="payments-api-abc123",
            follow=True,
            stream_id="follow-log-expired",
        )
        session.expires_at = timezone.now() - timedelta(minutes=1)
        session.save(update_fields=["expires_at", "updated_at"])

        state = active_admin_stream_session_status(session_pk=stream["session_pk"])
        summary = close_admin_stream(
            user=user,
            stream=stream,
            last_payload={
                "target": {"namespace": "payments", "name": "payments-api-abc123"},
                "source": "not_started",
                "available": False,
                "line_count": 0,
                "session_status": state["status"],
            },
            batch_count=0,
            close_reason=state["code"],
        )

        self.assertFalse(state["active"])
        self.assertEqual(state["code"], "admin_session_expired")
        self.assertEqual(state["status"], K8sAdminSession.STATUS_EXPIRED)
        self.assertEqual(summary["close_reason"], "admin_session_expired")
        self.assertEqual(summary["session_status"], K8sAdminSession.STATUS_EXPIRED)
        stopped = K8sAuditEvent.objects.get(action="k8s.admin_stream.logs_stopped")
        self.assertEqual(stopped.payload["close_reason"], "admin_session_expired")
        self.assertEqual(stopped.payload["session_status"], K8sAdminSession.STATUS_EXPIRED)
        self.assertEqual(stopped.payload["line_count"], 0)

    def test_watch_follow_closed_session_closes_stream_without_resource_body(self):
        user = self.create_user("k8s-admin-watch-closed-midstream", grant_admin_read=True)
        session = self.create_read_session(user)
        stream = start_admin_watch_stream(
            user=user,
            session_id=str(session.session_id),
            cluster_id=f"cluster_{self.cluster.id}",
            api_version="apps/v1",
            kind="Deployment",
            namespace="payments",
            follow=True,
            stream_id="follow-watch-closed",
        )
        session.status = K8sAdminSession.STATUS_CLOSED
        session.closed_at = timezone.now()
        session.save(update_fields=["status", "closed_at", "updated_at"])

        state = active_admin_stream_session_status(session_pk=stream["session_pk"])
        summary = close_admin_stream(
            user=user,
            stream=stream,
            last_payload={
                "target": {"api_version": "apps/v1", "kind": "Deployment", "namespace": "payments", "name": ""},
                "source": "not_started",
                "available": False,
                "event_count": 0,
                "session_status": state["status"],
            },
            batch_count=0,
            close_reason=state["code"],
        )

        self.assertFalse(state["active"])
        self.assertEqual(state["code"], "admin_session_not_active")
        self.assertEqual(state["status"], K8sAdminSession.STATUS_CLOSED)
        self.assertEqual(summary["close_reason"], "admin_session_not_active")
        self.assertEqual(summary["session_status"], K8sAdminSession.STATUS_CLOSED)
        stopped = K8sAuditEvent.objects.get(action="k8s.admin_stream.watch_stopped")
        self.assertEqual(stopped.payload["close_reason"], "admin_session_not_active")
        self.assertEqual(stopped.payload["session_status"], K8sAdminSession.STATUS_CLOSED)
        self.assertEqual(stopped.payload["event_count"], 0)

    def test_stream_follow_bounds_are_fail_closed(self):
        self.assertEqual(bounded_stream_int("999", default=5, minimum=1, maximum=25), 25)
        self.assertEqual(bounded_stream_int("-1", default=5, minimum=1, maximum=25), 1)
        self.assertEqual(bounded_stream_int("bad", default=5, minimum=1, maximum=25), 5)
        self.assertEqual(bounded_stream_float("999", default=2.0, minimum=0.25, maximum=30.0), 30.0)
        self.assertEqual(bounded_stream_float("0", default=2.0, minimum=0.25, maximum=30.0), 0.25)
