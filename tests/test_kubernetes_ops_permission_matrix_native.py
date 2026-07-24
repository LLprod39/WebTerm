from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.models import (
    K8sAppRef,
    K8sAuditEvent,
    K8sCluster,
    K8sFleetBundle,
    K8sPodRef,
    K8sProvider,
    K8sWorkloadRef,
)


class KubernetesOpsNativeMutationPolicyTests(TestCase):
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

    @override_settings(
        KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=True, KUBERNETES_ADMIN_BREAK_GLASS_APPLY_BYPASS_ENABLED=True
    )
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
