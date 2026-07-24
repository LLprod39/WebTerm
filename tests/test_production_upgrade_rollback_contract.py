from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_f13c_workflow_freezes_both_first_release_fixtures() -> None:
    workflow = (ROOT / ".github/workflows/production-upgrade-rollback-smoke.yml").read_text(encoding="utf-8")

    assert "b8924eeb1bcfd0647e80615eaa8c7684828e517a" in workflow
    assert "v0.1.0-rc.1" in workflow
    assert "__RC1_SHA__" not in workflow
    assert "fetch-depth: 0" in workflow
    assert "./docker/production-upgrade-rollback-smoke.sh" in workflow


def test_f13c_smoke_separates_application_rollback_from_database_restore() -> None:
    script = (ROOT / "docker/production-upgrade-rollback-smoke.sh").read_text(encoding="utf-8")

    for contract in (
        "verify_migration_history.py",
        "pre-upgrade-backup.sha256",
        "application-rollback-health.json",
        "application-rollback-integrity.json",
        "RESTORE_CONFIRM=RESTORE_WEBTERM",
        "restored-fixture-integrity.json",
        "database_reverse_migrations_attempted=false",
        "secret_artifacts_uploaded=false",
    ):
        assert contract in script


def test_f13c_lifecycle_probe_uses_only_cross_fixture_business_contracts() -> None:
    probe = (ROOT / "scripts/release_lifecycle_probe.py").read_text(encoding="utf-8")

    for contract in (
        '"auth_users"',
        '"servers"',
        '"pipelines"',
        '"managed_secrets"',
        "password_valid",
        "list_undecryptable_secrets",
    ):
        assert contract in probe
