from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_f13a_workflow_runs_the_production_installer_on_linux() -> None:
    workflow = (ROOT / ".github/workflows/production-install-smoke.yml").read_text(encoding="utf-8")

    assert "runs-on: ubuntu-latest" in workflow
    assert "./docker/production-install-smoke.sh" in workflow
    assert "f13a-production-install-${{ github.sha }}" in workflow


def test_f13a_smoke_enforces_release_profile_runtime_gates() -> None:
    script = (ROOT / "docker/production-install-smoke.sh").read_text(encoding="utf-8")

    for required_probe in (
        "makemigrations --check --dry-run",
        "check --deploy",
        "/api/settings/readiness/",
        "plugin_route_status",
        "worker-heartbeats.json",
        "celery -A web_ui inspect ping",
        "--terminal-sessions-per-user 1",
        "--pipeline-runs-per-user 1",
        "--agent-runs-per-user 1",
    ):
        assert required_probe in script


def test_production_installer_does_not_ignore_deploy_check_failure() -> None:
    installer = (ROOT / "docker/install-production.sh").read_text(encoding="utf-8")

    assert "compose exec -T backend python manage.py check --deploy" in installer
    assert "check --deploy || true" not in installer
