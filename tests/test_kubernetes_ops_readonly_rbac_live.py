from __future__ import annotations

import subprocess
from pathlib import Path

from kubernetes_ops.services.readonly_rbac_live import KubectlProbeOptions, verify_kubernetes_readonly_rbac_live, write_live_rbac_evidence


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["kubectl"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_readonly_rbac_live_probe_passes_expected_can_i_matrix(tmp_path: Path):
    manifest = tmp_path / "rbac.yaml"
    manifest.write_text("kind: List\n", encoding="utf-8")

    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        command = " ".join(args)
        if args == ["config", "current-context"]:
            return _completed("kind-webterm-k8s\n")
        if "apply -f" in command:
            return _completed("configured\n")
        if "delete pods" in command or "patch deployments.apps" in command or "create pods" in command:
            return _completed("no\n", returncode=1)
        if "escalate clusterroles" in command:
            return _completed("no\n", "Warning: resource is not namespace scoped\n", 1)
        return _completed("yes\n")

    report = verify_kubernetes_readonly_rbac_live(KubectlProbeOptions(manifest_path=manifest, apply_manifest=True), runner=runner)

    assert report["status"] == "ready"
    assert report["context"] == "kind-webterm-k8s"
    assert report["applied"] is True
    assert report["errors"] == []
    assert all(item["allowed"] for item in report["allowed"])
    assert not any(item["allowed"] for item in report["denied"])


def test_readonly_rbac_live_probe_fails_when_delete_is_allowed(tmp_path: Path):
    manifest = tmp_path / "rbac.yaml"
    manifest.write_text("kind: List\n", encoding="utf-8")

    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        command = " ".join(args)
        if args == ["config", "current-context"]:
            return _completed("kind-webterm-k8s\n")
        if "delete pods" in command:
            return _completed("yes\n")
        if "create pods" in command or "patch deployments.apps" in command or "escalate clusterroles" in command:
            return _completed("no\n", returncode=1)
        return _completed("yes\n")

    report = verify_kubernetes_readonly_rbac_live(KubectlProbeOptions(manifest_path=manifest), runner=runner)

    assert report["status"] == "missing"
    assert "unexpected_allowed:delete:pods" in report["errors"]


def test_readonly_rbac_live_evidence_writer(tmp_path: Path):
    output = tmp_path / "evidence.json"

    write_live_rbac_evidence({"status": "ready", "errors": []}, output)

    assert '"status": "ready"' in output.read_text(encoding="utf-8")
