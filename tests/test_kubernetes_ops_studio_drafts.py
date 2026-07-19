import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAppRef, K8sAuditEvent, K8sCluster
from studio.models import MCPServerPool, Pipeline, PipelineDraftSession, PipelineRun
from studio.skill_registry import get_skill


class KubernetesOpsStudioDraftTests(TestCase):
    def create_user(self, username: str, *, grant_kubernetes: bool = True, is_staff: bool = False) -> User:
        user = User.objects.create_user(username=username, password="password-123", is_staff=is_staff)
        if grant_kubernetes:
            UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        return user

    def grant_features(self, user: User, *features: str) -> None:
        for feature in features:
            UserAppPermission.objects.update_or_create(user=user, feature=feature, defaults={"allowed": True})

    def test_diagnose_action_creates_read_only_studio_draft(self):
        user = self.create_user("k8s-diagnosis-admin", is_staff=True)
        self.grant_features(user, "studio_pipelines", "studio_mcp")
        self.client.force_login(user)
        mcp = MCPServerPool.objects.create(
            name="Kubernetes MCP",
            description="kubectl read-only diagnostics",
            transport=MCPServerPool.TRANSPORT_STDIO,
            command="npx",
            args=["-y", "@modelcontextprotocol/server-kubernetes"],
            owner=user,
            last_test_ok=True,
        )
        cluster = K8sCluster.objects.create(name="prod-kz-1", environment="prod", labels={"kube_context": "prod-kz-context"})
        app = K8sAppRef.objects.create(
            name="payments-api",
            cluster=cluster,
            namespace="payments",
            environment="prod",
            owner=K8sAppRef.OWNER_DEVTRON,
            team="payments",
            health=K8sCluster.HEALTH_WARNING,
            version="2026.06.30-1",
            labels={"workload_kind": "statefulset"},
        )

        response = self.client.post(
            reverse("api_kubernetes_diagnose_action"),
            data=json.dumps({"app_id": f"app_{app.id}"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["success"])
        draft = payload["draft"]
        self.assertEqual(payload["target_url"], f"/studio/drafts?draft={draft['id']}")
        self.assertEqual(draft["status"], PipelineDraftSession.STATUS_READY)
        self.assertEqual(PipelineDraftSession.objects.count(), 1)
        self.assertFalse(Pipeline.objects.exists())
        self.assertFalse(PipelineRun.objects.exists())

        nodes = draft["latest_revision"]["preview_nodes"]
        inspect_node = next(node for node in nodes if node["id"] == "inspect")
        inspect_data = inspect_node["data"]
        self.assertEqual(inspect_data["tool_name"], "kubernetes_describe_workload")
        self.assertEqual(inspect_data["mcp_server_id"], mcp.id)
        self.assertEqual(inspect_data["permission_mode"], "READ_ONLY")
        self.assertEqual(inspect_data["operation_kind"], "kubernetes.workload.describe")
        self.assertFalse(inspect_data["mutates_state"])
        self.assertEqual(inspect_data["skill_slugs"], ["kubernetes-safety"])
        self.assertEqual(
            inspect_data["arguments"],
            {"cluster": "prod-kz-context", "namespace": "payments", "kind": "statefulset", "name": "payments-api"},
        )
        self.assertNotIn("kubernetes_rollout_restart", [node.get("data", {}).get("tool_name") for node in nodes])
        self.assertTrue(draft["latest_revision"]["response"]["validation"]["ok"])
        self.assertEqual(draft["latest_revision"]["response"]["resource_plan"]["skills"][0]["slug"], "kubernetes-safety")
        self.assertNotEqual(draft["latest_revision"]["response"]["risk"]["level"], "dangerous")
        self.assertTrue(K8sAuditEvent.objects.filter(action="k8s.diagnosis_draft.create", cluster=cluster).exists())

    def test_kubernetes_safety_skill_is_available_for_studio_policy(self):
        skill = get_skill("kubernetes-safety")

        self.assertEqual(skill.service, "kubernetes")
        self.assertEqual(skill.safety_level, "high")
        self.assertTrue(skill.runtime_policy)
        self.assertIn("kubernetes_describe_workload", skill.runtime_policy["required_preflight_tools"])

    def test_readiness_reports_studio_automation_when_mcp_is_bound(self):
        user = self.create_user("k8s-readiness-studio", is_staff=True)
        self.grant_features(user, "studio_pipelines", "studio_mcp")
        self.client.force_login(user)
        MCPServerPool.objects.create(
            name="Kubernetes MCP",
            description="kubectl read-only diagnostics",
            transport=MCPServerPool.TRANSPORT_STDIO,
            command="npx",
            args=["-y", "@modelcontextprotocol/server-kubernetes"],
            owner=user,
            last_test_ok=True,
        )

        response = self.client.get(reverse("api_kubernetes_readiness"))

        self.assertEqual(response.status_code, 200)
        checks = {item["id"]: item for item in response.json()["checks"]}
        self.assertEqual(checks["studio_automation"]["status"], "ready")
        self.assertFalse(checks["studio_automation"]["required"])
        self.assertIn("Kubernetes MCP", checks["studio_automation"]["detail"])

    def test_diagnose_action_requires_studio_pipelines_feature(self):
        user = self.create_user("k8s-diagnosis-no-studio")
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_diagnose_action"),
            data=json.dumps({"app_id": "app_1"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "studio_required")
        self.assertFalse(PipelineDraftSession.objects.exists())
