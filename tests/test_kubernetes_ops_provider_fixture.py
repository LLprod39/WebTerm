from __future__ import annotations

import importlib.util
from pathlib import Path


def test_kubernetes_provider_fixture_exposes_admin_resource_discovery():
    fixture = _load_fixture_module()

    core = fixture.k8s_payload_for_path("/k8s/clusters/c-webterm-demo/api/v1")
    groups = fixture.k8s_payload_for_path("/k8s/clusters/c-webterm-demo/apis")
    apps = fixture.k8s_payload_for_path("/k8s/clusters/c-webterm-demo/apis/apps/v1")
    deployments = fixture.k8s_payload_for_path(
        "/k8s/clusters/c-webterm-demo/apis/apps/v1/namespaces/payments/deployments"
    )
    pod_logs = fixture.k8s_payload_for_path(
        "/k8s/clusters/c-webterm-demo/api/v1/namespaces/payments/pods/broken-worker-5dbb6df98c-jx2kf/log"
    )

    assert core["kind"] == "APIResourceList"
    assert {item["name"] for item in core["resources"]} >= {"pods", "services", "secrets"}
    assert {item["name"] for item in groups["groups"]} >= {"apps", "networking.k8s.io", "apiextensions.k8s.io"}
    assert {item["name"] for item in apps["resources"]} >= {"deployments", "replicasets"}
    assert [item["metadata"]["name"] for item in deployments["items"]] == ["payments-api", "broken-worker"]
    assert pod_logs["lines"] == [
        "broken-worker-5dbb6df98c-jx2kf: demo log line 1",
        "broken-worker-5dbb6df98c-jx2kf: demo log line 2",
    ]


def _load_fixture_module():
    path = Path(__file__).resolve().parents[1] / ".tools" / "k8s-provider-fixture.py"
    spec = importlib.util.spec_from_file_location("k8s_provider_fixture", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module
