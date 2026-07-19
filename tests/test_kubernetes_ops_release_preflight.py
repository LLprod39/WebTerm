from __future__ import annotations

import json
import subprocess
from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from kubernetes_ops.services.live_provider_smoke import LIVE_PROVIDER_SMOKE_SCHEMA_VERSION
from kubernetes_ops.services.release_contract import RELEASE_EVIDENCE_SCHEMA_VERSION
from kubernetes_ops.services.release_preflight import (
    PREFLIGHT_SCHEMA_VERSION,
    collect_kubernetes_release_preflight,
    load_kubernetes_release_preflight_artifact,
    write_kubernetes_release_preflight,
)


def _write_live_rbac_artifact(tmp_path, *, status: str = "ready", include_live_provider_smoke: bool = True) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    (artifact_dir / "kubernetes_ops_readonly_rbac_live_evidence.json").write_text(
        json.dumps(
            {
                "status": status,
                "checked_at": "2026-06-30T00:00:00+00:00",
                "context": "prod-kz",
                "allowed": [{"decision": "yes"}],
                "denied": [{"decision": "no"}],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    if include_live_provider_smoke:
        (artifact_dir / "kubernetes_ops_live_provider_smoke.json").write_text(
            json.dumps(
                {
                    "schema_version": LIVE_PROVIDER_SMOKE_SCHEMA_VERSION,
                    "status": status,
                    "success": status == "ready",
                    "checked_at": "2026-06-30T00:00:00+00:00",
                    "summary": {
                        "enabled_providers": 2,
                        "rancher_providers": 1,
                        "devtron_providers": 1,
                        "provider_probes_ok": 2,
                        "provider_probes_total": 2,
                        "sync_dry_run_ok": 2,
                        "sync_dry_run_total": 2,
                        "clusters": 1,
                        "namespaces": 2,
                        "workloads": 3,
                        "pods": 4,
                        "fleet_bundles": 1,
                        "apps": 8,
                        "backend_paths_status": "ready",
                        "backend_path_checks_ok": 3,
                        "backend_path_checks_total": 3,
                    },
                    "backend_paths": {"status": "ready", "success": True, "checks": []},
                    "provider_probes": [],
                    "sync_dry_run": [],
                    "errors": [],
                }
            ),
            encoding="utf-8",
        )
    (artifact_dir / "kubernetes_ops_local_platform_evidence.json").write_text(
        json.dumps(
            {
                "schema_version": "kubernetes_ops.local_platform_evidence.v1",
                "status": status,
                "checked_at": "2026-06-30T00:00:00+00:00",
                "context": "kind-webterm-k8s",
                "summary": {"ready": 3, "missing": 0, "total": 3},
                "components": [],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )


def _runner(returncodes: dict[str, int] | None = None, seen: list[str] | None = None):
    returncodes = returncodes or {}

    def run(command: str, cwd):
        if seen is not None:
            seen.append(command)
        return subprocess.CompletedProcess(command, returncodes.get(command, 0), stdout=f"ok {command}", stderr="")

    return run


def test_kubernetes_release_preflight_collects_required_command_results(tmp_path):
    _write_live_rbac_artifact(tmp_path)
    seen: list[str] = []

    with override_settings(BASE_DIR=tmp_path):
        report = collect_kubernetes_release_preflight(runner=_runner(seen=seen), cwd=tmp_path)

    assert report["schema_version"] == PREFLIGHT_SCHEMA_VERSION
    assert report["release_evidence_schema_version"] == RELEASE_EVIDENCE_SCHEMA_VERSION
    assert report["status"] == "ready"
    assert report["failed"] == []
    result_ids = {item["id"] for item in report["results"]}
    assert {
        "django_check",
        "architecture_guard",
        "migrations_dry_run",
        "kubernetes_backend_tests",
        "readonly_rbac_validate",
        "sync_prune_safety",
        "readonly_rbac_live",
        "local_platform_evidence",
        "live_provider_smoke",
        "interactive_transport_evidence",
        "interactive_live_smoke",
        "interactive_production_controls",
        "production_action_evidence",
        "external_evidence_bundle",
    } <= result_ids
    assert "release_evidence" not in result_ids
    assert "preflight_evidence" not in result_ids
    assert "release_handoff" not in result_ids
    backend_tests = next(item for item in report["results"] if item["id"] == "kubernetes_backend_tests")
    assert backend_tests["timeout_seconds"] == 1200
    assert backend_tests["env_keys"] == ["POSTGRES_STATEMENT_TIMEOUT_MS"]
    assert all("verify_kubernetes_ops_release" not in command for command in seen)
    assert all("verify_kubernetes_ops_preflight" not in command for command in seen)
    assert all("render_kubernetes_ops_release_handoff" not in command for command in seen)
    assert all("verify_kubernetes_ops_local_platform" not in command for command in seen)
    assert all("verify_kubernetes_ops_live_provider_smoke" not in command for command in seen)
    assert any("verify_kubernetes_ops_interactive_transport_evidence" in command for command in seen)
    assert any("verify_kubernetes_ops_interactive_live_smoke" in command for command in seen)
    assert any("verify_kubernetes_ops_interactive_production_controls" in command for command in seen)
    assert any("verify_kubernetes_ops_production_action_evidence" in command for command in seen)
    assert any("verify_kubernetes_ops_external_evidence_bundle" in command for command in seen)


def test_kubernetes_release_preflight_fails_when_command_fails(tmp_path):
    _write_live_rbac_artifact(tmp_path)

    with override_settings(BASE_DIR=tmp_path):
        report = collect_kubernetes_release_preflight(
            runner=_runner({"python manage.py check": 1}),
            cwd=tmp_path,
        )

    assert report["status"] == "failed"
    assert "django_check" in report["failed"]


def test_kubernetes_release_preflight_fails_when_live_provider_smoke_artifact_is_missing(tmp_path):
    _write_live_rbac_artifact(tmp_path, include_live_provider_smoke=False)

    with override_settings(BASE_DIR=tmp_path):
        report = collect_kubernetes_release_preflight(runner=_runner(), cwd=tmp_path)

    live_provider_smoke = next(item for item in report["results"] if item["id"] == "live_provider_smoke")
    assert report["status"] == "failed"
    assert "live_provider_smoke" in report["failed"]
    assert live_provider_smoke["mode"] == "existing_artifact"
    assert live_provider_smoke["error"] == "artifact missing"


def test_kubernetes_release_preflight_loads_ready_artifact(tmp_path):
    _write_live_rbac_artifact(tmp_path)

    with override_settings(BASE_DIR=tmp_path):
        report = collect_kubernetes_release_preflight(runner=_runner(), cwd=tmp_path)
        path = write_kubernetes_release_preflight(report)
        loaded = load_kubernetes_release_preflight_artifact(path)

    assert loaded["success"] is True
    assert loaded["status"] == "ready"
    assert loaded["schema_version"] == PREFLIGHT_SCHEMA_VERSION
    assert loaded["age_seconds"] is not None
    assert loaded["max_age_seconds"] == 86400
    assert loaded["errors"] == []


def test_kubernetes_release_preflight_blocks_stale_artifact(tmp_path):
    _write_live_rbac_artifact(tmp_path)

    with override_settings(BASE_DIR=tmp_path):
        report = collect_kubernetes_release_preflight(runner=_runner(), cwd=tmp_path)
        report["generated_at"] = (timezone.now() - timedelta(seconds=120)).isoformat()
        path = write_kubernetes_release_preflight(report)

    with override_settings(BASE_DIR=tmp_path, KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS=60):
        loaded = load_kubernetes_release_preflight_artifact(path)

    assert loaded["success"] is False
    assert loaded["status"] == "missing"
    assert loaded["age_seconds"] >= 120
    assert loaded["max_age_seconds"] == 60
    assert any("preflight artifact is stale" in item for item in loaded["errors"])


def test_kubernetes_release_preflight_blocks_missing_or_wrong_schema(tmp_path):
    with override_settings(BASE_DIR=tmp_path):
        missing = load_kubernetes_release_preflight_artifact()

    assert missing["success"] is False
    assert missing["status"] == "missing"

    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    path = artifact_dir / "kubernetes_ops_preflight_evidence.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "old",
                "release_evidence_schema_version": RELEASE_EVIDENCE_SCHEMA_VERSION,
                "status": "ready",
                "success": True,
                "results": [],
            }
        ),
        encoding="utf-8",
    )

    with override_settings(BASE_DIR=tmp_path):
        wrong_schema = load_kubernetes_release_preflight_artifact()

    assert wrong_schema["success"] is False
    assert any("schema_version" in item for item in wrong_schema["errors"])
    assert any("missing command results" in item for item in wrong_schema["errors"])
