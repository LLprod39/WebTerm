from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_f13b_workflow_runs_recovery_on_an_isolated_linux_runner() -> None:
    workflow = (ROOT / ".github/workflows/production-recovery-smoke.yml").read_text(encoding="utf-8")

    assert "runs-on: ubuntu-latest" in workflow
    assert "./docker/production-recovery-smoke.sh" in workflow
    assert "f13b-production-recovery-${{ github.sha }}" in workflow


def test_f13b_smoke_restores_all_critical_state_without_uploading_secrets() -> None:
    script = (ROOT / "docker/production-recovery-smoke.sh").read_text(encoding="utf-8")

    for required_probe in (
        "backup_postgres.sh",
        "restore_postgres.sh",
        "production.env",
        "config.tar.gz",
        "media.tar.gz",
        "redis.tar.gz",
        "recovery_integrity_manifest.py",
        'cmp "$ARTIFACT_DIR/source-integrity.json"',
        "restore_compose restart postgres",
        "restore_compose restart redis",
        "secret_artifacts_uploaded=false",
    ):
        assert required_probe in script

    workflow = (ROOT / ".github/workflows/production-recovery-smoke.yml").read_text(encoding="utf-8")
    assert "path: .ci-artifacts/production-recovery-smoke" in workflow
    assert "SENSITIVE_DIR" not in workflow


def test_postgres_scripts_target_the_real_production_service_and_require_confirmation() -> None:
    backup = (ROOT / "scripts/backup_postgres.sh").read_text(encoding="utf-8")
    restore = (ROOT / "scripts/restore_postgres.sh").read_text(encoding="utf-8")

    assert "POSTGRES_SERVICE:-postgres" in backup
    assert "pg_dump --format=custom" in backup
    assert "pg_restore --list" in backup
    assert "POSTGRES_SERVICE:-postgres" in restore
    assert "RESTORE_CONFIRM=RESTORE_WEBTERM" in restore
    assert "--clean --if-exists --exit-on-error" in restore


def test_recovery_manifest_checks_auth_secrets_domain_rows_and_persistent_volumes() -> None:
    script = (ROOT / "scripts/recovery_integrity_manifest.py").read_text(encoding="utf-8")

    for contract in (
        "password_valid",
        "list_undecryptable_secrets",
        '"servers"',
        '"pipelines"',
        '"pipeline_runs"',
        '"agent_runs"',
        '"audit_events"',
        '"plugin_packages"',
        '"managed_secrets"',
        'Path("/workspace/config_runtime")',
        'Path("/workspace/media")',
    ):
        assert contract in script
