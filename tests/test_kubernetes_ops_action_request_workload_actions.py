import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sActionRequest, K8sCluster, K8sProvider, K8sWorkloadRef


class KubernetesOpsActionRequestWorkloadActionTests(TestCase):
    def create_user(self, username: str) -> User:
        user = User.objects.create_user(username=username, password="password-123")
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

    def test_reader_can_request_workload_scale_preview_with_replicas(self):
        user = self.create_user("k8s-action-scale-reader")
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_action_request_approval"),
            data=json.dumps(
                {
                    "action": K8sActionRequest.ACTION_K8S_WORKLOAD_SCALE,
                    "reason": "scale payments workers for traffic",
                    "target": {
                        "workload_id": f"workload_{self.workload.id}",
                        "replicas": 4,
                        "token": "super-secret-token",
                    },
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        request_payload = response.json()["request"]
        self.assertEqual(request_payload["action"], K8sActionRequest.ACTION_K8S_WORKLOAD_SCALE)
        self.assertEqual(request_payload["target"]["replicas"], 4)
        self.assertEqual(request_payload["preview"]["replicas"], 4)
        self.assertEqual(request_payload["preview"]["current_replicas"], 2)
        self.assertEqual(request_payload["preview"]["rollback_plan"]["strategy"], "scale_back")
        self.assertEqual(request_payload["preview"]["rollback_plan"]["previous_replicas"], 2)
        self.assertFalse(request_payload["execution_policy"]["native_execution_enabled"])
        self.assertNotIn("super-secret-token", str(response.json()))

    def test_workload_scale_request_requires_valid_replicas(self):
        user = self.create_user("k8s-action-scale-invalid")
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_action_request_approval"),
            data=json.dumps(
                {
                    "action": K8sActionRequest.ACTION_K8S_WORKLOAD_SCALE,
                    "reason": "bad scale",
                    "target": {"workload_id": f"workload_{self.workload.id}", "replicas": "not-a-number"},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "replicas_invalid")
        self.assertFalse(K8sActionRequest.objects.exists())

    def test_reader_can_request_resource_patch_preview_without_sensitive_body(self):
        user = self.create_user("k8s-action-patch-reader")
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_action_request_approval"),
            data=json.dumps(
                {
                    "action": K8sActionRequest.ACTION_K8S_RESOURCE_PATCH,
                    "reason": "add safe annotation",
                    "target": {
                        "cluster_id": f"cluster_{self.cluster.id}",
                        "api_version": "apps/v1",
                        "kind": "Deployment",
                        "namespace": "payments",
                        "name": "payments-api",
                        "patch_type": "merge",
                        "patch_body": {"metadata": {"annotations": {"webterm.io/request": "scale-window"}}},
                    },
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        request_payload = response.json()["request"]
        self.assertEqual(request_payload["action"], K8sActionRequest.ACTION_K8S_RESOURCE_PATCH)
        self.assertEqual(request_payload["target"]["patch_type"], "merge")
        self.assertEqual(request_payload["preview"]["patch_shape"]["top_level_fields"], ["metadata"])
        self.assertEqual(request_payload["preview"]["blast_radius"], "single_resource_patch")
        self.assertEqual(request_payload["preview"]["rollback_plan"]["strategy"], "reverse_patch")
        self.assertNotIn("patch_body", str(request_payload["preview"]["rollback_plan"]))

    def test_resource_patch_request_rejects_sensitive_body(self):
        user = self.create_user("k8s-action-patch-sensitive")
        self.client.force_login(user)

        response = self.client.post(
            reverse("api_kubernetes_action_request_approval"),
            data=json.dumps(
                {
                    "action": K8sActionRequest.ACTION_K8S_RESOURCE_PATCH,
                    "reason": "bad secret patch",
                    "target": {
                        "cluster_id": f"cluster_{self.cluster.id}",
                        "api_version": "apps/v1",
                        "kind": "Deployment",
                        "namespace": "payments",
                        "name": "payments-api",
                        "patch_body": {"metadata": {"annotations": {"token": "raw-secret-token"}}},
                    },
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "patch_body_sensitive")
        self.assertNotIn("raw-secret-token", str(response.json()))
        self.assertFalse(K8sActionRequest.objects.exists())
