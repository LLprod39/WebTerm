import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import (
    K8sActionRequest,
    K8sAdminAction,
    K8sAdminSession,
    K8sAuditEvent,
    K8sCluster,
    K8sEvent,
    K8sPodRef,
    K8sProvider,
    K8sWorkloadRef,
)
from kubernetes_ops.services.action_verification import record_native_action_verification_evaluation


class KubernetesOpsActionNativeExecutionTests(TestCase):
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
        self.workload = K8sWorkloadRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            kind=K8sWorkloadRef.KIND_DEPLOYMENT,
            health=K8sCluster.HEALTH_WARNING,
            ready=1,
            desired=2,
        )

    def write_session(self, user: User) -> K8sAdminSession:
        return K8sAdminSession.objects.create(
            user=user,
            username_snapshot=user.username,
            cluster=self.cluster,
            mode=K8sAdminSession.MODE_WRITE,
            status=K8sAdminSession.STATUS_ACTIVE,
            risk_tier=K8sAdminSession.RISK_HIGH,
            allowed_verbs=["get", "list", "watch", "logs", "yaml", "patch", "scale", "restart"],
            allowed_kinds=["Deployment", "StatefulSet", "DaemonSet"],
            allowed_namespaces=["payments"],
            reason="restart action request after approval",
            approval_ref="CHG-ACTION-NATIVE",
            approved_by=user,
            approved_at=timezone.now(),
            expires_at=timezone.now() + timedelta(minutes=30),
        )

    def action_request(
        self,
        user: User,
        *,
        action: str = K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART,
        replicas: int | None = None,
        patch_body: dict | None = None,
    ) -> K8sActionRequest:
        target = {
            "cluster_id": f"cluster_{self.cluster.id}",
            "namespace": "payments",
            "kind": "deployment",
            "name": "payments-api",
        }
        if replicas is not None:
            target["replicas"] = replicas
        if patch_body is not None:
            target["patch_type"] = "merge"
            target["patch_body"] = patch_body
        return K8sActionRequest.objects.create(
            requested_by=user,
            username_snapshot=user.username,
            action=action,
            status=K8sActionRequest.STATUS_APPROVED_EXTERNAL,
            cluster=self.cluster,
            target=target,
            preview={"blast_radius": "single_workload"},
            approval_ref="CHG-ACTION-NATIVE",
            execution_policy={"native_execution_enabled": False, "external_approval_recorded": True},
            report={"status": K8sActionRequest.STATUS_APPROVED_EXTERNAL, "approved": True},
            reason="restart after config rollout",
        )

    @override_settings(
        KUBERNETES_ACTION_REQUEST_NATIVE_EXECUTION_ENABLED=True, KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED=True
    )
    def test_execute_approved_restart_uses_admin_write_session_and_native_verification(self):
        staff = self.create_user("k8s-action-admin-native", is_staff=True)
        session = self.write_session(staff)
        action_request = self.action_request(staff)
        self.client.force_login(staff)

        with patch("kubernetes_ops.services.admin_workload_actions.ProviderJsonClient") as client_cls:
            client_cls.return_value.request.return_value = {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "payments-api", "namespace": "payments"},
                "spec": {"template": {"metadata": {"annotations": {}}}},
                "status": {"readyReplicas": 2},
            }
            response = self.client.post(
                reverse("api_kubernetes_action_execute_approved"),
                data=json.dumps({"request_id": str(action_request.request_id), "session_id": str(session.session_id)}),
                content_type="application/json",
            )
            method, path = client_cls.return_value.request.call_args.args[:2]

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["request"]["status"], K8sActionRequest.STATUS_EXECUTED_NATIVE)
        self.assertTrue(payload["request"]["report"]["native_execution_performed_by_webterm"])
        self.assertFalse(payload["request"]["report"]["external_execution"])
        self.assertEqual(payload["request"]["report"]["operation"], "restart")
        self.assertEqual(payload["request"]["report"]["rollback_plan"]["strategy"], "rollout_recovery")
        self.assertFalse(payload["request"]["report"]["rollback_plan"]["payload_stored"])
        verification_plan = payload["request"]["report"]["verification_plan"]
        self.assertEqual(verification_plan["status"], "pending")
        self.assertEqual(verification_plan["mode"], "native_post_action")
        self.assertEqual(
            verification_plan["check_ids"],
            ["rollout_status_observed", "pod_readiness_observed", "recent_warning_events_checked"],
        )
        self.assertFalse(verification_plan["payload_stored"])
        self.assertEqual(method, "PATCH")
        self.assertEqual(path, "/k8s/clusters/c-prod/apis/apps/v1/namespaces/payments/deployments/payments-api")
        admin_action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_RESTART)
        self.assertEqual(payload["request"]["report"]["admin_action_id"], str(admin_action.action_id))
        self.assertEqual(admin_action.status, K8sAdminAction.STATUS_COMPLETED)
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.action_request.execute_native").exists())

        verify_response = self.client.post(
            reverse("api_kubernetes_action_verify_external", kwargs={"request_id": action_request.request_id}),
            data=json.dumps(
                {
                    "outcome": "succeeded",
                    "summary": "Native restart verified with token=raw-native-verification-token",
                    "external_ref": "https://rancher.example.test/result/native?token=raw-native-ref-token#tail",
                    "checks": ["rollout status complete", "pods ready"],
                    "evidence": {"ready": "2/2", "authorization": "Bearer raw-native-evidence-token"},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(verify_response.status_code, 200)
        verified_payload = verify_response.json()
        self.assertEqual(verified_payload["request"]["status"], K8sActionRequest.STATUS_VERIFIED_NATIVE)
        self.assertEqual(verified_payload["request"]["report"]["verification_mode"], "native_post_action")
        self.assertTrue(verified_payload["request"]["report"]["native_execution_performed_by_webterm"])
        self.assertFalse(verified_payload["request"]["report"]["external_execution"])
        self.assertEqual(verified_payload["request"]["report"]["admin_action_id"], str(admin_action.action_id))
        self.assertEqual(
            verified_payload["request"]["report"]["summary"], "Native restart verified with token=[redacted]"
        )
        self.assertEqual(
            verified_payload["request"]["report"]["external_ref"], "https://rancher.example.test/result/native"
        )
        self.assertEqual(verified_payload["request"]["report"]["evidence"]["authorization"], "[redacted]")
        self.assertEqual(verified_payload["request"]["report"]["verification_plan"]["status"], "verified")
        self.assertEqual(verified_payload["request"]["report"]["verification_plan"]["recorded_check_count"], 2)
        self.assertTrue(
            all(
                item["status"] == "recorded"
                for item in verified_payload["request"]["report"]["verification_plan"]["checks"]
            )
        )
        self.assertNotIn("raw-native-verification-token", str(verified_payload))
        self.assertNotIn("raw-native-ref-token", str(verified_payload))
        self.assertNotIn("raw-native-evidence-token", str(verified_payload))
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.action_request.verify_native").exists())

    @override_settings(
        KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
        KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF="",
        KUBERNETES_ACTION_REQUEST_NATIVE_EXECUTION_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED=True,
    )
    def test_execute_approved_restart_requires_restricted_credential_evidence_in_production_mode(self):
        staff = self.create_user("k8s-action-admin-native-restricted", is_staff=True)
        session = self.write_session(staff)
        action_request = self.action_request(staff)
        self.client.force_login(staff)

        with patch("kubernetes_ops.services.admin_workload_actions.ProviderJsonClient") as client_cls:
            response = self.client.post(
                reverse("api_kubernetes_action_execute_approved"),
                data=json.dumps({"request_id": str(action_request.request_id), "session_id": str(session.session_id)}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["code"], "restricted_credential_evidence_required")
        self.assertEqual(payload["payload"]["target_environment"], "production")
        self.assertEqual(
            payload["payload"]["requires"],
            ["KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF"],
        )
        self.assertFalse(client_cls.called)
        action_request.refresh_from_db()
        self.assertEqual(action_request.status, K8sActionRequest.STATUS_APPROVED_EXTERNAL)
        self.assertFalse(K8sAdminAction.objects.exists())
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.action_request.execute_rejected").exists())

    @override_settings(
        KUBERNETES_ACTION_REQUEST_NATIVE_EXECUTION_ENABLED=True, KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED=True
    )
    def test_auto_native_verification_closes_restart_after_fresh_readonly_inventory(self):
        staff = self.create_user("k8s-action-admin-auto-verify", is_staff=True)
        session = self.write_session(staff)
        action_request = self.action_request(staff)
        self.client.force_login(staff)

        with patch("kubernetes_ops.services.admin_workload_actions.ProviderJsonClient") as client_cls:
            client_cls.return_value.request.return_value = {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "payments-api", "namespace": "payments"},
                "status": {"readyReplicas": 2},
            }
            response = self.client.post(
                reverse("api_kubernetes_action_execute_approved"),
                data=json.dumps({"request_id": str(action_request.request_id), "session_id": str(session.session_id)}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        action_request.refresh_from_db()
        fresh_sync = timezone.now() + timedelta(seconds=1)
        self.cluster.last_sync_at = fresh_sync
        self.cluster.save(update_fields=["last_sync_at", "updated_at"])
        self.workload.ready = 2
        self.workload.desired = 2
        self.workload.health = K8sCluster.HEALTH_HEALTHY
        self.workload.last_sync_at = fresh_sync
        self.workload.save(update_fields=["ready", "desired", "health", "last_sync_at", "updated_at"])
        K8sPodRef.objects.create(
            cluster=self.cluster,
            namespace="payments",
            name="payments-api-7f8c9",
            health=K8sCluster.HEALTH_HEALTHY,
            phase="Running",
            owner_kind="ReplicaSet",
            owner_name="payments-api",
            ready_containers=1,
            total_containers=1,
            last_sync_at=fresh_sync,
        )

        updated = record_native_action_verification_evaluation(action_request=action_request, evaluated_by="unit-test")

        self.assertEqual(updated.status, K8sActionRequest.STATUS_VERIFIED_NATIVE)
        self.assertTrue(updated.report["verified"])
        self.assertEqual(updated.report["verification_mode"], "native_post_action_auto")
        self.assertEqual(updated.report["verification_plan"]["status"], "verified")
        self.assertTrue(updated.execution_policy["native_verification_auto_recorded"])
        self.assertTrue(all(item["status"] == "passed" for item in updated.report["verification_plan"]["checks"]))
        self.assertFalse(updated.report["verification_plan"]["payload_stored"])

    @override_settings(
        KUBERNETES_ACTION_REQUEST_NATIVE_EXECUTION_ENABLED=True, KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED=True
    )
    def test_auto_native_verification_keeps_restart_open_when_warning_events_exist(self):
        staff = self.create_user("k8s-action-admin-auto-review", is_staff=True)
        session = self.write_session(staff)
        action_request = self.action_request(staff)
        self.client.force_login(staff)

        with patch("kubernetes_ops.services.admin_workload_actions.ProviderJsonClient") as client_cls:
            client_cls.return_value.request.return_value = {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "payments-api", "namespace": "payments"},
                "status": {"readyReplicas": 2},
            }
            response = self.client.post(
                reverse("api_kubernetes_action_execute_approved"),
                data=json.dumps({"request_id": str(action_request.request_id), "session_id": str(session.session_id)}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        action_request.refresh_from_db()
        fresh_sync = timezone.now() + timedelta(seconds=1)
        self.cluster.last_sync_at = fresh_sync
        self.cluster.save(update_fields=["last_sync_at", "updated_at"])
        self.workload.ready = 2
        self.workload.desired = 2
        self.workload.health = K8sCluster.HEALTH_HEALTHY
        self.workload.last_sync_at = fresh_sync
        self.workload.save(update_fields=["ready", "desired", "health", "last_sync_at", "updated_at"])
        K8sPodRef.objects.create(
            cluster=self.cluster,
            namespace="payments",
            name="payments-api-7f8c9",
            health=K8sCluster.HEALTH_HEALTHY,
            phase="Running",
            owner_name="payments-api",
            ready_containers=1,
            total_containers=1,
            last_sync_at=fresh_sync,
        )
        K8sEvent.objects.create(
            cluster=self.cluster,
            event_uid="warn-after-restart",
            severity=K8sEvent.SEVERITY_WARNING,
            namespace="payments",
            involved_kind="Deployment",
            involved_name="payments-api",
            reason="BackOff",
            message="warning after restart",
            last_seen_at=fresh_sync,
            last_sync_at=fresh_sync,
        )

        updated = record_native_action_verification_evaluation(action_request=action_request, evaluated_by="unit-test")

        self.assertEqual(updated.status, K8sActionRequest.STATUS_EXECUTED_NATIVE)
        self.assertFalse(updated.report["verified"])
        self.assertEqual(updated.report["verification_plan"]["status"], "needs_review")
        self.assertFalse(updated.execution_policy["native_verification_auto_recorded"])
        warning_check = [
            item
            for item in updated.report["verification_plan"]["checks"]
            if item["id"] == "recent_warning_events_checked"
        ][0]
        self.assertEqual(warning_check["status"], "needs_review")
        self.assertEqual(warning_check["evidence"]["warning_event_count"], 1)

    @override_settings(
        KUBERNETES_ACTION_REQUEST_NATIVE_EXECUTION_ENABLED=True, KUBERNETES_ADMIN_NATIVE_SCALE_ENABLED=True
    )
    def test_execute_approved_scale_uses_admin_write_session(self):
        staff = self.create_user("k8s-action-admin-scale", is_staff=True)
        session = self.write_session(staff)
        action_request = self.action_request(staff, action=K8sActionRequest.ACTION_K8S_WORKLOAD_SCALE, replicas=4)
        self.client.force_login(staff)

        with patch("kubernetes_ops.services.admin_workload_actions.ProviderJsonClient") as client_cls:
            client_cls.return_value.request.return_value = {
                "apiVersion": "autoscaling/v1",
                "kind": "Scale",
                "metadata": {"name": "payments-api", "namespace": "payments"},
                "spec": {"replicas": 4},
            }
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
        self.assertEqual(payload["request"]["report"]["operation"], "scale")
        self.assertEqual(payload["request"]["report"]["replicas"], 4)
        self.assertEqual(
            payload["request"]["report"]["verification_plan"]["check_ids"],
            ["desired_replicas_observed", "workload_readiness_observed", "recent_warning_events_checked"],
        )
        self.assertEqual(payload["request"]["report"]["verification_plan"]["checks"][0]["expected"], 4)
        self.assertEqual(method, "PATCH")
        self.assertEqual(path, "/k8s/clusters/c-prod/apis/apps/v1/namespaces/payments/deployments/payments-api/scale")
        self.assertEqual(body, {"spec": {"replicas": 4}})
        admin_action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_SCALE)
        self.assertEqual(payload["request"]["report"]["admin_action_id"], str(admin_action.action_id))
        self.assertEqual(admin_action.status, K8sAdminAction.STATUS_COMPLETED)

    @override_settings(
        KUBERNETES_ACTION_REQUEST_NATIVE_EXECUTION_ENABLED=True, KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED=True
    )
    def test_execute_approved_patch_uses_admin_write_session(self):
        staff = self.create_user("k8s-action-admin-patch", is_staff=True)
        session = self.write_session(staff)
        action_request = self.action_request(
            staff,
            action=K8sActionRequest.ACTION_K8S_RESOURCE_PATCH,
            patch_body={"metadata": {"annotations": {"webterm.io/request": "safe-patch"}}},
        )
        self.client.force_login(staff)

        with patch("kubernetes_ops.services.admin_patch.ProviderJsonClient") as client_cls:
            client_cls.return_value.request.return_value = {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "payments-api", "namespace": "payments"},
                "spec": {"replicas": 2},
            }
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
        self.assertEqual(payload["request"]["report"]["operation"], "patch")
        self.assertEqual(payload["request"]["report"]["patch_type"], "merge")
        self.assertEqual(
            payload["request"]["report"]["verification_plan"]["check_ids"],
            ["patch_action_completed", "resource_generation_observed", "recent_warning_events_checked"],
        )
        self.assertEqual(method, "PATCH")
        self.assertEqual(path, "/k8s/clusters/c-prod/apis/apps/v1/namespaces/payments/deployments/payments-api")
        self.assertEqual(body, {"metadata": {"annotations": {"webterm.io/request": "safe-patch"}}})
        admin_action = K8sAdminAction.objects.get(verb=K8sAdminAction.VERB_PATCH)
        self.assertEqual(payload["request"]["report"]["admin_action_id"], str(admin_action.action_id))
        self.assertEqual(admin_action.status, K8sAdminAction.STATUS_COMPLETED)
