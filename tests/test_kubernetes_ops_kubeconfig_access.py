from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sCluster, K8sClusterAccess, K8sNamespace, K8sProvider
from kubernetes_ops.services.kubeconfig import parse_kubeconfig_text, select_context


SAMPLE_KUBECONFIG = """
apiVersion: v1
kind: Config
current-context: lab
clusters:
  - name: lab-cluster
    cluster:
      server: https://k8s.lab.example
users:
  - name: lab-user
    user:
      token: demo-token-value
contexts:
  - name: lab
    context:
      cluster: lab-cluster
      user: lab-user
      namespace: default
  - name: other
    context:
      cluster: lab-cluster
      user: lab-user
"""


class KubeconfigParseTests(SimpleTestCase):
    def test_parse_contexts_and_current(self):
        parsed = parse_kubeconfig_text(SAMPLE_KUBECONFIG)
        self.assertEqual(parsed.current_context, "lab")
        self.assertEqual({item.name for item in parsed.contexts}, {"lab", "other"})
        selected = select_context(parsed, "other")
        self.assertEqual(selected.server, "https://k8s.lab.example")

    def test_rejects_empty(self):
        with self.assertRaises(ValueError):
            parse_kubeconfig_text(" ")


class KubeconfigConnectionApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="k8s-user", password="password-123")
        UserAppPermission.objects.create(user=self.user, feature="kubernetes", allowed=True)
        self.staff = User.objects.create_user(username="k8s-admin", password="password-123", is_staff=True)
        UserAppPermission.objects.create(user=self.staff, feature="kubernetes", allowed=True)
        self.client.force_login(self.user)

    def test_parse_endpoint_does_not_store_secret(self):
        response = self.client.post(
            reverse("api_kubernetes_connection_parse"),
            data='{"kubeconfig": %s}' % __import__("json").dumps(SAMPLE_KUBECONFIG),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["current_context"], "lab")
        self.assertNotIn("demo-token-value", __import__("json").dumps(payload))

    def test_create_rejects_invalid_yaml(self):
        response = self.client.post(
            reverse("api_kubernetes_connections_kubeconfig"),
            data='{"kubeconfig": "not: [yaml", "sync": false}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_access_grant_filters_cluster_list(self):
        cluster = K8sCluster.objects.create(name="platform-1", environment="prod")
        K8sNamespace.objects.create(cluster=cluster, name="payments")
        listed = self.client.get(reverse("api_kubernetes_clusters"))
        self.assertEqual(listed.json()["clusters"], [])

        self.client.force_login(self.staff)
        grant = self.client.post(
            reverse("api_kubernetes_cluster_access", kwargs={"cluster_id": f"cluster_{cluster.id}"}),
            data=__import__("json").dumps({"user": self.user.username, "namespaces": ["payments"]}),
            content_type="application/json",
        )
        self.assertEqual(grant.status_code, 201)

        self.client.force_login(self.user)
        listed = self.client.get(reverse("api_kubernetes_clusters"))
        names = [item["name"] for item in listed.json()["clusters"]]
        self.assertEqual(names, ["platform-1"])
        self.assertEqual(listed.json()["clusters"][0]["access_origin"], "granted")

        namespaces = self.client.get(
            reverse("api_kubernetes_cluster_namespaces", kwargs={"cluster_id": f"cluster_{cluster.id}"})
        ).json()["namespaces"]
        self.assertEqual([item["name"] for item in namespaces], ["payments"])
