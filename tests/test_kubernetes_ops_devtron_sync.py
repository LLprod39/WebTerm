from __future__ import annotations

import pytest

from kubernetes_ops.models import K8sAppRef, K8sCluster, K8sProvider
from kubernetes_ops.services.sync import sync_devtron_provider


@pytest.mark.django_db
def test_devtron_provider_sync_merges_apps_into_existing_cluster(monkeypatch):
    monkeypatch.setenv("DEVTRON_TOKEN", "devtron-token")
    K8sCluster.objects.create(name="stage-webterm-ops", rancher_cluster_id="c-stage", health=K8sCluster.HEALTH_WARNING)
    provider = K8sProvider.objects.create(
        name="devtron-main",
        kind=K8sProvider.KIND_DEVTRON,
        base_url="https://devtron.example.test",
        secret_ref="env:DEVTRON_TOKEN",
    )

    def transport(url, headers, timeout):
        assert url.endswith("/orchestrator/app/list")
        assert headers["Authorization"] == "Bearer devtron-token"
        return {
            "apps": [
                {
                    "appName": "demo-api",
                    "clusterName": "stage-webterm-ops",
                    "clusterId": "devtron-stage",
                    "namespace": "demo",
                    "environmentName": "stage",
                    "teamName": "platform",
                    "appStatus": "Deployed",
                    "releaseVersion": "2026.06.29-2",
                    "links": {"logs": "https://devtron.example.test/app/demo-api/logs"},
                }
            ]
        }

    result = sync_devtron_provider(provider, transport=transport)

    assert result.success is True
    assert result.apps == 1
    assert K8sCluster.objects.count() == 1
    cluster = K8sCluster.objects.get(name="stage-webterm-ops")
    assert cluster.devtron_cluster_id == "devtron-stage"
    assert cluster.health == K8sCluster.HEALTH_WARNING
    app = K8sAppRef.objects.get(name="demo-api", cluster=cluster)
    assert app.owner == K8sAppRef.OWNER_DEVTRON
    assert app.health == K8sCluster.HEALTH_HEALTHY
    assert app.version == "2026.06.29-2"
    assert app.links["logs"] == "https://devtron.example.test/app/demo-api/logs"


@pytest.mark.django_db
def test_devtron_provider_sync_supports_session_auth_and_helm_apps_payload(monkeypatch):
    monkeypatch.setenv("DEVTRON_ADMIN_PASSWORD", "devtron-admin-password")
    cluster = K8sCluster.objects.create(name="local", rancher_cluster_id="local", health=K8sCluster.HEALTH_HEALTHY)
    K8sAppRef.objects.create(
        name="removed-app",
        cluster=cluster,
        namespace="old",
        owner=K8sAppRef.OWNER_DEVTRON,
        health=K8sCluster.HEALTH_HEALTHY,
    )
    provider = K8sProvider.objects.create(
        name="devtron-local",
        kind=K8sProvider.KIND_DEVTRON,
        base_url="http://devtron.example.test",
        secret_ref="env:DEVTRON_ADMIN_PASSWORD",
        labels={
            "auth_strategy": "devtron_session",
            "auth_username": "admin",
            "login_path": "/orchestrator/api/v1/session",
            "apps_path": "/orchestrator/application?clusterIds=1",
            "cluster_name_map": {"default_cluster": "local"},
        },
    )
    calls = []

    def transport(url, headers, timeout, *, method="GET", body=None):
        calls.append((method, url, headers, body))
        if url.endswith("/orchestrator/api/v1/session"):
            assert method == "POST"
            assert "Authorization" not in headers
            assert body == {"username": "admin", "password": "devtron-admin-password"}
            return {"code": 200, "result": {"token": "session-token"}}
        if url.endswith("/orchestrator/application?clusterIds=1"):
            assert method == "GET"
            assert headers["Cookie"] == "argocd.token=session-token"
            assert headers["token"] == "session-token"
            assert "Authorization" not in headers
            return {
                "result": {
                    "applicationType": "HELM-APP",
                    "helmApps": [
                        {
                            "appId": "1|devtroncd|devtron",
                            "appName": "devtron",
                            "chartName": "devtron-operator",
                            "environmentDetail": {
                                "clusterId": 1,
                                "clusterName": "default_cluster",
                                "namespace": "devtroncd",
                            },
                            "projectId": 0,
                        }
                    ],
                }
            }
        raise AssertionError(url)

    result = sync_devtron_provider(provider, transport=transport)

    assert result.success is True
    assert result.apps == 1
    assert [call[0] for call in calls] == ["POST", "GET"]
    cluster = K8sCluster.objects.get(name="local")
    assert cluster.devtron_cluster_id == "1"
    app = K8sAppRef.objects.get(name="devtron", cluster=cluster)
    assert app.namespace == "devtroncd"
    assert app.version == "devtron-operator"
    assert not K8sAppRef.objects.filter(name="removed-app", cluster=cluster).exists()


@pytest.mark.django_db
def test_provider_sync_redacts_token_from_persisted_error(monkeypatch):
    monkeypatch.setenv("DEVTRON_TOKEN", "super-secret-token")
    provider = K8sProvider.objects.create(
        name="devtron-main",
        kind=K8sProvider.KIND_DEVTRON,
        base_url="https://devtron.example.test",
        secret_ref="env:DEVTRON_TOKEN",
    )

    def transport(url, headers, timeout):
        raise RuntimeError("request failed with super-secret-token")

    result = sync_devtron_provider(provider, transport=transport)

    assert result.success is False
    assert "super-secret-token" not in result.error
    provider.refresh_from_db()
    assert "super-secret-token" not in provider.last_error
    assert "***" in provider.last_error
