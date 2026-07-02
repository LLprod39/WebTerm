import json

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.models import (
    K8sActionRequest,
    K8sAppRef,
    K8sAuditEvent,
    K8sCluster,
    K8sFleetBundle,
    K8sPodRef,
    K8sProvider,
    K8sWorkloadRef,
)
from studio.models import PipelineDraftSession


class KubernetesOpsPermissionMatrixTests(TestCase):
    def create_user(
        self,
        username: str,
        *,
        grant_kubernetes: bool = True,
        grant_studio: bool = False,
        grant_admin_read: bool = False,
        grant_admin_write: bool = False,
        grant_break_glass: bool = False,
        grant_secret_read: bool = False,
        is_staff: bool = False,
    ) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=is_staff)
        grants = {
            "kubernetes": grant_kubernetes,
            "studio_pipelines": grant_studio,
            "kubernetes_admin_read": grant_admin_read,
            "kubernetes_admin_write": grant_admin_write,
            "kubernetes_break_glass": grant_break_glass,
            "kubernetes_secret_read": grant_secret_read,
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
            links={"rancher": "https://rancher.example.test/c/c-prod?token=cluster-token"},
        )
        self.app = K8sAppRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            environment="prod",
            owner=K8sAppRef.OWNER_DEVTRON,
            health=K8sCluster.HEALTH_WARNING,
            links={"devtron_app": "https://devtron.example.test/app/payments?token=app-token"},
        )
        self.workload = K8sWorkloadRef.objects.create(
            name="payments-api",
            cluster=self.cluster,
            namespace="payments",
            kind=K8sWorkloadRef.KIND_DEPLOYMENT,
            health=K8sCluster.HEALTH_WARNING,
            links={"rancher": "https://rancher.example.test/workload/payments?token=workload-token"},
        )
        self.pod = K8sPodRef.objects.create(
            cluster=self.cluster,
            namespace="payments",
            name="payments-api-abc123",
            links={"logs": "https://rancher.example.test/logs/payments?token=pod-token"},
        )
        K8sFleetBundle.objects.create(
            name="ingress-nginx",
            source="gitrepo/platform",
            target="prod-*",
            links={"rancher_fleet": "https://rancher.example.test/fleet/bundles/ingress-nginx?token=fleet-token"},
        )
        K8sAuditEvent.objects.create(action="k8s.cluster.view", provider="webterm", cluster=self.cluster)

    def read_only_routes(self):
        cluster_kwargs = {"cluster_id": f"cluster_{self.cluster.id}"}
        return [
            ("api_kubernetes_readiness", {}),
            ("api_kubernetes_overview", {}),
            ("api_kubernetes_clusters", {}),
            ("api_kubernetes_cluster_detail", cluster_kwargs),
            ("api_kubernetes_cluster_namespaces", cluster_kwargs),
            ("api_kubernetes_cluster_workloads", cluster_kwargs),
            ("api_kubernetes_cluster_pods", cluster_kwargs),
            ("api_kubernetes_cluster_network", cluster_kwargs),
            ("api_kubernetes_cluster_events", cluster_kwargs),
            ("api_kubernetes_fleet_bundles", {}),
            ("api_kubernetes_devtron_apps", {}),
            ("api_kubernetes_audit", {}),
            ("api_kubernetes_workload_describe", {"workload_id": f"workload_{self.workload.id}"}),
            ("api_kubernetes_pod_logs", {"pod_id": f"pod_{self.pod.id}"}),
        ]

    def admin_routes(self):
        provider_payload = {
            "name": "devtron-main",
            "kind": K8sProvider.KIND_DEVTRON,
            "base_url": "https://devtron.example.test",
            "auth_mode": K8sProvider.AUTH_NONE,
        }
        return [
            ("post", "api_kubernetes_providers", {}, provider_payload),
            ("patch", "api_kubernetes_provider_detail", {"provider_id": self.provider.id}, {"enabled": False}),
            ("delete", "api_kubernetes_provider_detail", {"provider_id": self.provider.id}, {}),
            ("post", "api_kubernetes_sync", {}, {"dry_run": True}),
            ("post", "api_kubernetes_provider_sync", {"provider_id": self.provider.id}, {"dry_run": True}),
            ("post", "api_kubernetes_provider_probe", {"provider_id": self.provider.id}, {}),
        ]

    def test_staff_without_explicit_kubernetes_feature_is_denied_before_admin_checks(self):
        user = self.create_user("staff-no-kubernetes", grant_kubernetes=False, is_staff=True)
        self.client.force_login(user)

        response = self.client.get(reverse("api_kubernetes_readiness"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "Forbidden")

    def test_kubernetes_reader_can_use_read_only_surface_and_get_policy_metadata(self):
        user = self.create_user("k8s-reader")
        self.client.force_login(user)

        for route_name, kwargs in self.read_only_routes():
            response = self.client.get(reverse(route_name, kwargs=kwargs))
            self.assertEqual(response.status_code, 200, route_name)

        payload = self.client.get(reverse("api_kubernetes_readiness")).json()
        checks = {item["id"]: item for item in payload["checks"]}
        self.assertEqual(checks["permission_matrix"]["status"], "ready")
        self.assertTrue(payload["access_policy"]["can_read"])
        self.assertTrue(payload["access_policy"]["can_read_log_snapshots"])
        self.assertFalse(payload["access_policy"]["can_audit_deeplinks"])
        self.assertFalse(payload["access_policy"]["can_admin_providers"])
        self.assertFalse(payload["access_policy"]["can_create_diagnosis_draft"])
        self.assertTrue(payload["access_policy"]["can_request_action_approval"])
        self.assertFalse(payload["access_policy"]["can_execute_approved_action"])
        self.assertFalse(payload["access_policy"]["can_admin_read"])
        self.assertFalse(payload["access_policy"]["can_live_resource_get"])
        self.assertFalse(payload["access_policy"]["can_admin_write"])
        self.assertFalse(payload["access_policy"]["can_dry_run_apply"])
        self.assertFalse(payload["access_policy"]["can_apply_yaml"])
        self.assertFalse(payload["access_policy"]["can_patch"])
        self.assertFalse(payload["access_policy"]["can_scale"])
        self.assertFalse(payload["access_policy"]["can_delete"])
        self.assertFalse(payload["access_policy"]["can_break_glass"])
        self.assertFalse(payload["access_policy"]["can_port_forward"])
        self.assertFalse(payload["access_policy"]["can_mutate_cluster_state"])
        self.assertFalse(payload["access_policy"]["can_exec"])
        self.assertIn("pod.exec", payload["access_policy"]["blocked_capabilities"])
        overview = self.client.get(reverse("api_kubernetes_overview")).json()
        self.assertEqual(overview["access_policy"], payload["access_policy"])
        self.assertEqual(overview["providers"][0]["base_url"], "")
        self.assertFalse(overview["providers"][0]["connection_details_visible"])
        self.assertEqual(overview["clusters"][0]["links"], {})
        self.assertEqual(overview["apps"][0]["links"], {})
        self.assertEqual(overview["workloads"][0]["links"], {})
        self.assertEqual(overview["fleet_rollouts"][0]["links"], {})
        self.assertFalse(overview["clusters"][0]["external_links_policy"]["visible"])
        self.assertNotIn("rancher.example.test", json.dumps(overview))
        self.assertNotIn("devtron.example.test", json.dumps(overview))

    def test_kubernetes_reader_cannot_read_provider_config(self):
        user = self.create_user("k8s-provider-config-reader")
        self.client.force_login(user)

        for route_name, kwargs in (
            ("api_kubernetes_providers", {}),
            ("api_kubernetes_provider_detail", {"provider_id": self.provider.id}),
        ):
            response = self.client.get(reverse(route_name, kwargs=kwargs))
            self.assertEqual(response.status_code, 403, route_name)
            self.assertEqual(response.json()["code"], "admin_required", route_name)

    def test_kubernetes_staff_can_read_sanitized_external_fallback_links(self):
        user = self.create_user("k8s-staff-fallback-links", is_staff=True)
        self.client.force_login(user)

        overview = self.client.get(reverse("api_kubernetes_overview")).json()
        provider_list = self.client.get(reverse("api_kubernetes_providers")).json()

        self.assertEqual(provider_list["providers"][0]["base_url"], "https://rancher.example.test")
        self.assertTrue(provider_list["providers"][0]["connection_details_visible"])
        self.assertEqual(overview["clusters"][0]["links"]["rancher"], "https://rancher.example.test/c/c-prod")
        self.assertEqual(overview["apps"][0]["links"]["devtron_app"], "https://devtron.example.test/app/payments")
        self.assertEqual(overview["workloads"][0]["links"]["rancher"], "https://rancher.example.test/workload/payments")
        self.assertEqual(overview["fleet_rollouts"][0]["links"]["rancher_fleet"], "https://rancher.example.test/fleet/bundles/ingress-nginx")
        self.assertTrue(overview["clusters"][0]["external_links_policy"]["visible"])
        self.assertNotIn("cluster-token", json.dumps(overview))
        self.assertNotIn("app-token", json.dumps(overview))
        self.assertNotIn("workload-token", json.dumps(overview))
        self.assertNotIn("fleet-token", json.dumps(overview))

    def test_kubernetes_reader_cannot_audit_external_deeplink(self):
        user = self.create_user("k8s-deeplink-reader")
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_deeplink_audit"),
            data=json.dumps(
                {
                    "target_type": "app",
                    "target_id": f"app_{self.app.id}",
                    "target_name": self.app.name,
                    "link_key": "logs",
                    "url": "https://devtron.example.test/logs?token=secret#tail",
                    "provider": K8sProvider.KIND_DEVTRON,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "admin_required")
        self.assertFalse(K8sAuditEvent.objects.filter(action="k8s.deeplink.open").exists())

    def test_kubernetes_staff_can_audit_external_deeplink_without_raw_url_tokens(self):
        user = self.create_user("k8s-deeplink-staff", is_staff=True)
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_deeplink_audit"),
            data=json.dumps(
                {
                    "target_type": "app",
                    "target_id": f"app_{self.app.id}",
                    "target_name": self.app.name,
                    "link_key": "logs",
                    "url": "https://devtron.example.test/logs?token=secret#tail",
                    "provider": K8sProvider.KIND_DEVTRON,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        event = K8sAuditEvent.objects.get(action="k8s.deeplink.open")
        self.assertEqual(event.payload["url"], "https://devtron.example.test/logs")
        self.assertNotIn("secret", str(event.payload))
        readiness = self.client.get(reverse("api_kubernetes_readiness")).json()
        self.assertTrue(readiness["access_policy"]["can_audit_deeplinks"])

    def test_kubernetes_reader_cannot_use_admin_provider_actions(self):
        user = self.create_user("k8s-reader-admin-denied")
        self.client.force_login(user)

        for method, route_name, kwargs, payload in self.admin_routes():
            response = getattr(self.client, method)(
                reverse(route_name, kwargs=kwargs),
                data=json.dumps(payload),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 403, route_name)
            self.assertEqual(response.json()["code"], "admin_required", route_name)

    def test_studio_diagnosis_requires_studio_feature_but_not_provider_admin(self):
        user = self.create_user("k8s-diagnosis-reader", grant_studio=True, is_staff=False)
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_diagnose_action"),
            data=json.dumps({"app_id": f"app_{self.app.id}"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(PipelineDraftSession.objects.count(), 1)
        readiness = self.client.get(reverse("api_kubernetes_readiness")).json()
        self.assertTrue(readiness["access_policy"]["can_create_diagnosis_draft"])
        self.assertFalse(readiness["access_policy"]["can_admin_providers"])

    def test_action_request_is_allowed_for_reader_but_execute_is_staff_only_and_disabled(self):
        user = self.create_user("k8s-action-policy-reader")
        self.client.force_login(user)

        request_response = self.client.post(
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
        execute_response = self.client.post(
            reverse("api_kubernetes_action_execute_approved"),
            data=json.dumps({"request_id": request_response.json()["request"]["id"]}),
            content_type="application/json",
        )

        self.assertEqual(request_response.status_code, 201)
        self.assertEqual(execute_response.status_code, 403)
        self.assertEqual(execute_response.json()["code"], "admin_required")

    def test_admin_mode_features_are_explicit_and_do_not_enable_native_mutations(self):
        user = self.create_user(
            "k8s-admin-mode-policy",
            grant_admin_read=True,
            grant_admin_write=True,
            grant_break_glass=True,
        )
        self.client.force_login(user)

        payload = self.client.get(reverse("api_kubernetes_readiness")).json()
        policy = payload["access_policy"]

        self.assertTrue(policy["can_admin_read"])
        self.assertTrue(policy["can_live_resource_get"])
        self.assertTrue(policy["can_view_full_yaml"])
        self.assertFalse(policy["can_view_secret_values"])
        self.assertTrue(policy["can_stream_logs"])
        self.assertTrue(policy["can_admin_write"])
        self.assertTrue(policy["can_dry_run_apply"])
        self.assertTrue(policy["can_break_glass"])
        self.assertTrue(policy["can_request_break_glass_session"])
        self.assertFalse(policy["can_apply_yaml"])
        self.assertFalse(policy["can_patch"])
        self.assertFalse(policy["can_scale"])
        self.assertFalse(policy["can_delete"])
        self.assertFalse(policy["can_exec"])
        self.assertFalse(policy["can_port_forward"])
        self.assertFalse(policy["can_mutate_cluster_state"])
        self.assertIn("apply_yaml", policy["blocked_capabilities"])
        self.assertIn("pod.exec", policy["blocked_capabilities"])

    @override_settings(
        KUBERNETES_ADMIN_MODE_ENABLED=False,
        KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True,
    )
    def test_admin_mode_global_kill_switch_disables_admin_capabilities_without_removing_read_access(self):
        user = self.create_user(
            "k8s-admin-mode-disabled-policy",
            grant_admin_read=True,
            grant_admin_write=True,
            grant_break_glass=True,
        )
        self.client.force_login(user)

        payload = self.client.get(reverse("api_kubernetes_readiness")).json()
        policy = payload["access_policy"]

        self.assertFalse(policy["admin_mode_enabled"])
        self.assertTrue(policy["can_read"])
        self.assertTrue(policy["has_kubernetes_admin_read_feature"])
        self.assertTrue(policy["has_kubernetes_admin_write_feature"])
        self.assertTrue(policy["has_kubernetes_break_glass_feature"])
        for key in ("can_admin_read", "can_live_resource_get", "can_admin_write", "can_dry_run_apply", "can_break_glass", "can_apply_yaml", "can_exec", "can_mutate_cluster_state"):
            self.assertFalse(policy[key], key)
        for key in ("admin_read_capabilities", "admin_write_request_capabilities", "break_glass_request_capabilities"):
            self.assertEqual(policy[key], [], key)
        self.assertIn("apply_yaml", policy["blocked_capabilities"])
        self.assertIn("pod.exec", policy["blocked_capabilities"])

    @override_settings(KUBERNETES_ADMIN_SECRET_READ_ENABLED=True)
    def test_secret_value_policy_requires_runtime_flag_admin_read_and_secret_read_feature(self):
        no_grant = self.create_user("k8s-secret-no-grant", grant_admin_read=True)
        self.client.force_login(no_grant)
        no_grant_policy = self.client.get(reverse("api_kubernetes_readiness")).json()["access_policy"]
        self.assertFalse(no_grant_policy["can_view_secret_values"])
        self.assertNotIn("secret.values.view", no_grant_policy["admin_read_capabilities"])

        with_grant = self.create_user("k8s-secret-with-grant", grant_admin_read=True, grant_secret_read=True)
        self.client.force_login(with_grant)
        with_grant_policy = self.client.get(reverse("api_kubernetes_readiness")).json()["access_policy"]
        self.assertTrue(with_grant_policy["has_kubernetes_secret_read_feature"])
        self.assertTrue(with_grant_policy["can_view_secret_values"])
        self.assertIn("secret.values.view", with_grant_policy["admin_read_capabilities"])

    def test_secret_value_policy_stays_disabled_without_runtime_flag(self):
        user = self.create_user("k8s-secret-flag-disabled", grant_admin_read=True, grant_secret_read=True)
        self.client.force_login(user)

        policy = self.client.get(reverse("api_kubernetes_readiness")).json()["access_policy"]

        self.assertTrue(policy["has_kubernetes_secret_read_feature"])
        self.assertFalse(policy["can_view_secret_values"])
        self.assertNotIn("secret.values.view", policy["admin_read_capabilities"])

    @override_settings(KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=True)
    def test_native_apply_policy_requires_runtime_flag_and_admin_write_feature(self):
        user = self.create_user("k8s-admin-apply-policy", grant_admin_write=True)
        self.client.force_login(user)

        payload = self.client.get(reverse("api_kubernetes_readiness")).json()
        policy = payload["access_policy"]

        self.assertTrue(policy["can_admin_write"])
        self.assertTrue(policy["can_apply_yaml"])
        self.assertTrue(policy["can_mutate_cluster_state"])
        self.assertNotIn("apply_yaml", policy["blocked_capabilities"])
        self.assertIn("scale", policy["blocked_capabilities"])

    @override_settings(KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=True, KUBERNETES_ADMIN_BREAK_GLASS_APPLY_BYPASS_ENABLED=True)
    def test_break_glass_apply_policy_requires_separate_runtime_flag(self):
        user = self.create_user("k8s-break-glass-apply-policy", grant_break_glass=True)
        self.client.force_login(user)

        payload = self.client.get(reverse("api_kubernetes_readiness")).json()
        policy = payload["access_policy"]

        self.assertTrue(policy["can_break_glass"])
        self.assertFalse(policy["can_apply_yaml"])
        self.assertTrue(policy["can_break_glass_apply"])
        self.assertTrue(policy["can_mutate_cluster_state"])
        self.assertNotIn("apply_yaml", policy["blocked_capabilities"])

    @override_settings(KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED=True)
    def test_native_patch_policy_requires_runtime_flag_and_admin_write_feature(self):
        user = self.create_user("k8s-admin-patch-policy", grant_admin_write=True)
        self.client.force_login(user)

        payload = self.client.get(reverse("api_kubernetes_readiness")).json()
        policy = payload["access_policy"]

        self.assertTrue(policy["can_admin_write"])
        self.assertTrue(policy["can_patch"])
        self.assertTrue(policy["can_mutate_cluster_state"])
        self.assertNotIn("patch", policy["blocked_capabilities"])
        self.assertIn("delete", policy["blocked_capabilities"])

    @override_settings(KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED=True)
    def test_native_delete_policy_requires_runtime_flag_and_admin_write_feature(self):
        user = self.create_user("k8s-admin-delete-policy", grant_admin_write=True)
        self.client.force_login(user)

        payload = self.client.get(reverse("api_kubernetes_readiness")).json()
        policy = payload["access_policy"]

        self.assertTrue(policy["can_admin_write"])
        self.assertTrue(policy["can_delete"])
        self.assertTrue(policy["can_mutate_cluster_state"])
        self.assertNotIn("delete", policy["blocked_capabilities"])
        self.assertIn("pod.exec", policy["blocked_capabilities"])

    @override_settings(KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True)
    def test_native_exec_policy_requires_runtime_flag_and_break_glass_feature(self):
        user = self.create_user("k8s-admin-exec-policy", grant_break_glass=True)
        self.client.force_login(user)

        payload = self.client.get(reverse("api_kubernetes_readiness")).json()
        policy = payload["access_policy"]

        self.assertTrue(policy["can_break_glass"])
        self.assertTrue(policy["can_exec"])
        self.assertNotIn("pod.exec", policy["blocked_capabilities"])
        self.assertIn("port_forward", policy["blocked_capabilities"])

    @override_settings(KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True)
    def test_native_port_forward_policy_requires_runtime_flag_and_break_glass_feature(self):
        user = self.create_user("k8s-admin-port-forward-policy", grant_break_glass=True)
        self.client.force_login(user)

        payload = self.client.get(reverse("api_kubernetes_readiness")).json()
        policy = payload["access_policy"]

        self.assertTrue(policy["can_break_glass"])
        self.assertTrue(policy["can_port_forward"])
        self.assertNotIn("port_forward", policy["blocked_capabilities"])
        self.assertIn("pod.exec", policy["blocked_capabilities"])

    @override_settings(KUBERNETES_ADMIN_NATIVE_SCALE_ENABLED=True, KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED=True)
    def test_native_scale_restart_policy_requires_runtime_flags_and_admin_write_feature(self):
        user = self.create_user("k8s-admin-workload-policy", grant_admin_write=True)
        self.client.force_login(user)

        payload = self.client.get(reverse("api_kubernetes_readiness")).json()
        policy = payload["access_policy"]

        self.assertTrue(policy["can_admin_write"])
        self.assertTrue(policy["can_scale"])
        self.assertTrue(policy["can_restart"])
        self.assertTrue(policy["can_mutate_cluster_state"])
        self.assertNotIn("scale", policy["blocked_capabilities"])
        self.assertNotIn("rollout_restart", policy["blocked_capabilities"])
        self.assertIn("delete", policy["blocked_capabilities"])
