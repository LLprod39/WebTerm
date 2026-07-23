from __future__ import annotations

import json

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core_ui.models import UserAppPermission


class KubernetesOpsCapabilitiesTests(TestCase):
    def create_user(
        self,
        username: str,
        *,
        grant_kubernetes: bool = True,
        grant_admin_read: bool = False,
        grant_admin_write: bool = False,
        grant_break_glass: bool = False,
        grant_secret_read: bool = False,
    ) -> User:
        user = User.objects.create_user(username=username, password="password-123")
        grants = {
            "kubernetes": grant_kubernetes,
            "kubernetes_admin_read": grant_admin_read,
            "kubernetes_admin_write": grant_admin_write,
            "kubernetes_break_glass": grant_break_glass,
            "kubernetes_secret_read": grant_secret_read,
        }
        for feature, allowed in grants.items():
            if allowed:
                UserAppPermission.objects.create(user=user, feature=feature, allowed=True)
        return user

    def test_capabilities_require_explicit_kubernetes_feature(self):
        user = self.create_user("k8s-capabilities-no-feature", grant_kubernetes=False)
        self.client.force_login(user)

        response = self.client.get(reverse("api_kubernetes_capabilities"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "Forbidden")

    def test_reader_capabilities_are_safe_and_do_not_expose_external_data(self):
        user = self.create_user("k8s-capabilities-reader")
        self.client.force_login(user)

        response = self.client.get(reverse("api_kubernetes_capabilities"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        workflows = {item["id"]: item for item in payload["workflows"]}
        modes = {item["id"]: item for item in payload["modes"]}
        self.assertEqual(payload["operation"], "kubernetes_capabilities")
        self.assertFalse(payload["policy"]["mutates_state"])
        self.assertFalse(payload["policy"]["runs_live_checks"])
        self.assertTrue(modes["kubernetes"]["active"])
        self.assertFalse(modes["kubernetes_admin_read"]["active"])
        self.assertTrue(workflows["safe_cockpit"]["available"])
        self.assertTrue(workflows["action_request"]["available"])
        self.assertFalse(workflows["live_resource_explorer"]["available"])
        self.assertEqual(
            workflows["live_resource_explorer"]["blocked_reason"], "kubernetes_admin_read_feature_required"
        )
        self.assertFalse(workflows["apply_yaml"]["available"])
        self.assertFalse(workflows["pod_exec"]["available"])
        self.assertEqual(payload["summary"]["mutating_available"], 0)
        self.assertIn("pod.exec", payload["blocked_capabilities"])
        serialized = json.dumps(payload)
        self.assertNotIn("rancher.example", serialized)
        self.assertNotIn("token=", serialized)
        self.assertNotIn("secret_ref", serialized)

    @override_settings(
        KUBERNETES_ADMIN_SECRET_READ_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_SCALE_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True,
        KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=True,
        KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED=True,
        KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED=True,
        KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED=True,
        KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED=True,
        KUBERNETES_ADMIN_NODE_DEBUG_ENABLED=True,
        KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED=True,
    )
    def test_admin_capabilities_reflect_features_and_runtime_flags(self):
        user = self.create_user(
            "k8s-capabilities-admin",
            grant_admin_read=True,
            grant_admin_write=True,
            grant_break_glass=True,
            grant_secret_read=True,
        )
        self.client.force_login(user)

        payload = self.client.get(reverse("api_kubernetes_capabilities")).json()

        workflows = {item["id"]: item for item in payload["workflows"]}
        modes = {item["id"]: item for item in payload["modes"]}
        self.assertTrue(modes["kubernetes_admin_read"]["active"])
        self.assertTrue(modes["kubernetes_admin_write"]["active"])
        self.assertTrue(modes["kubernetes_break_glass"]["active"])
        self.assertTrue(modes["kubernetes_secret_read"]["active"])
        for workflow_id in (
            "live_resource_explorer",
            "logs_stream",
            "secret_values",
            "dry_run_apply",
            "apply_yaml",
            "patch",
            "scale",
            "rollout_restart",
            "delete",
            "pod_exec",
            "port_forward",
            "node_maintenance",
            "node_drain",
            "cluster_terminal",
            "node_debug",
        ):
            self.assertTrue(workflows[workflow_id]["available"], workflow_id)
        self.assertTrue(workflows["pod_exec"]["transport_enabled"])
        self.assertTrue(workflows["port_forward"]["transport_enabled"])
        self.assertGreater(payload["summary"]["mutating_available"], 0)
        self.assertTrue(payload["runtime_flags"]["KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED"])

    @override_settings(
        KUBERNETES_ADMIN_MODE_ENABLED=False,
        KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True,
    )
    def test_capabilities_respect_global_admin_mode_kill_switch(self):
        user = self.create_user(
            "k8s-capabilities-kill-switch",
            grant_admin_read=True,
            grant_admin_write=True,
            grant_break_glass=True,
        )
        self.client.force_login(user)

        payload = self.client.get(reverse("api_kubernetes_capabilities")).json()

        workflows = {item["id"]: item for item in payload["workflows"]}
        modes = {item["id"]: item for item in payload["modes"]}
        self.assertTrue(modes["kubernetes"]["active"])
        self.assertFalse(modes["kubernetes_admin_read"]["active"])
        self.assertFalse(modes["kubernetes_admin_write"]["active"])
        self.assertFalse(modes["kubernetes_break_glass"]["active"])
        self.assertTrue(workflows["safe_cockpit"]["available"])
        self.assertFalse(workflows["live_resource_explorer"]["available"])
        self.assertFalse(workflows["apply_yaml"]["available"])
        self.assertFalse(workflows["pod_exec"]["available"])
        self.assertEqual(
            workflows["live_resource_explorer"]["blocked_reason"], "kubernetes_admin_mode_enabled_disabled"
        )
