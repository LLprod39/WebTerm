import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sActionRequest, K8sCluster, K8sProvider, K8sWorkloadRef
from kubernetes_ops.services.action_production_templates import production_rollout_restart_template_is_safe


class KubernetesOpsActionProductionTemplateTests(TestCase):
    def setUp(self):
        provider = K8sProvider.objects.create(
            name="rancher-main",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rancher.example.test",
            auth_mode=K8sProvider.AUTH_NONE,
        )
        self.cluster = K8sCluster.objects.create(
            name="prod-kz-1",
            environment="prod",
            rancher_provider=provider,
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

    def test_rollout_restart_request_contains_production_template(self):
        user = User.objects.create_user(username="k8s-prod-restart-template", password="password-123")
        UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_action_request_approval"),
            data=json.dumps(
                {
                    "action": K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART,
                    "reason": "restart after production deploy",
                    "target": {"workload_id": f"workload_{self.workload.id}", "token": "raw-secret-token"},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        template = payload["request"]["preview"]["production_rollout_restart_template"]
        self.assertEqual(template["status"], "ready")
        self.assertEqual(template["mode"], "approval_verification_report")
        self.assertFalse(template["direct_execution"])
        self.assertTrue(template["approval"]["required"])
        self.assertTrue(template["verification"]["required"])
        self.assertTrue(template["report"]["required"])
        self.assertEqual(template["rollback"]["strategy"], "rollout_recovery")
        self.assertEqual(
            [item["id"] for item in template["lifecycle"]], ["request", "approve", "execute", "verify", "report"]
        )
        self.assertEqual(
            template["verification"]["check_ids"],
            ["rollout_status_observed", "pod_readiness_observed", "recent_warning_events_checked"],
        )
        self.assertTrue(production_rollout_restart_template_is_safe(template))
        self.assertNotIn("raw-secret-token", str(payload))

    def test_production_restart_template_safety_rejects_payload_storage(self):
        self.assertFalse(
            production_rollout_restart_template_is_safe(
                {"status": "ready", "direct_execution": False, "payload_stored": True}
            )
        )
