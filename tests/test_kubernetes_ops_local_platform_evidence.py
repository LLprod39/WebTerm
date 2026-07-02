from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from kubernetes_ops.services.local_platform_evidence import (
    LocalPlatformProbeOptions,
    verify_kubernetes_local_platform,
    write_local_platform_evidence,
)


def _completed(payload: dict | None = None, *, stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["kubectl"],
        returncode=returncode,
        stdout=json.dumps(payload or {}) if payload is not None else stdout,
        stderr=stderr,
    )


def _namespace(name: str) -> dict:
    return {"metadata": {"name": name, "resourceVersion": "42"}}


def _service(name: str) -> dict:
    return {"metadata": {"name": name, "resourceVersion": "42"}, "spec": {"ports": [{"name": "http", "port": 80, "targetPort": 80}]}}


def _workload(name: str, *, replicas: int = 1, ready: int = 1) -> dict:
    return {"metadata": {"name": name}, "spec": {"replicas": replicas}, "status": {"readyReplicas": ready, "availableReplicas": ready}}


def test_local_platform_evidence_reports_ready_components():
    resources = {
        ("namespace", "", "cattle-system"): _namespace("cattle-system"),
        ("namespace", "", "cattle-fleet-system"): _namespace("cattle-fleet-system"),
        ("namespace", "", "devtroncd"): _namespace("devtroncd"),
    }
    for namespace, services, deployments, statefulsets in (
        ("cattle-system", ["rancher"], ["rancher", "rancher-webhook"], []),
        ("cattle-fleet-system", ["gitjob", "monitoring-fleet-controller"], ["fleet-controller", "gitjob", "helmops"], []),
        ("devtroncd", ["devtron-service", "dashboard-service"], ["devtron", "dashboard", "kubelink", "argocd-dex-server"], ["postgresql-postgresql"]),
    ):
        for service in services:
            resources[("service", namespace, service)] = _service(service)
        for deployment in deployments:
            resources[("deployment", namespace, deployment)] = _workload(deployment)
        for statefulset in statefulsets:
            resources[("statefulset", namespace, statefulset)] = _workload(statefulset)

    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        if args == ["config", "current-context"]:
            return _completed(stdout="kind-webterm-k8s\n")
        namespace = ""
        if "-n" in args:
            index = args.index("-n")
            namespace = args[index + 1]
        key = (args[-4], namespace, args[-3])
        return _completed(resources[key])

    report = verify_kubernetes_local_platform(LocalPlatformProbeOptions(), runner=runner)

    assert report["status"] == "ready"
    assert report["summary"] == {"ready": 3, "missing": 0, "total": 3}
    assert report["errors"] == []
    assert {item["id"] for item in report["components"]} == {"rancher", "fleet", "devtron"}
    devtron = next(item for item in report["components"] if item["id"] == "devtron")
    assert devtron["services"][0]["ports"][0]["port"] == 80


def test_local_platform_evidence_fails_on_missing_devtron_and_context_mismatch():
    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        if args == ["config", "current-context"]:
            return _completed(stdout="minikube\n")
        if "devtroncd" in args:
            return _completed(stderr="not found", returncode=1)
        if args[-4] in {"deployment", "statefulset"}:
            return _completed(_workload(args[-3]))
        return _completed(_namespace(args[-3]) if args[-4] == "namespace" else _service(args[-3]))

    report = verify_kubernetes_local_platform(LocalPlatformProbeOptions(), runner=runner)

    assert report["status"] == "missing"
    assert any(item.startswith("context_mismatch") for item in report["errors"])
    assert any("devtron:namespace_missing:devtroncd" in item for item in report["errors"])


def test_local_platform_evidence_writer(tmp_path: Path):
    output = tmp_path / "local-platform.json"

    write_local_platform_evidence({"status": "ready", "errors": []}, output)

    assert '"status": "ready"' in output.read_text(encoding="utf-8")


def test_local_platform_evidence_handles_missing_kubectl():
    with patch("kubernetes_ops.services.local_platform_evidence.subprocess.run", side_effect=FileNotFoundError("kubectl missing")):
        report = verify_kubernetes_local_platform(LocalPlatformProbeOptions(kubectl="missing-kubectl"))

    assert report["status"] == "missing"
    assert any("kubectl_context_unavailable" in item for item in report["errors"])
