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
        'bash "$ROOT_DIR/docker/install-production.sh"',
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


def test_https_runtime_smoke_matches_browser_csrf_and_websocket_origin() -> None:
    harness = (ROOT / "docker/multi_user_load_smoke.py").read_text(encoding="utf-8")

    assert "self.csrf_token = self.csrf_cookie" in harness
    assert 'origin=self.base_url.rstrip("/")' in harness
    assert 'headers={"Cookie": self._cookie_header()}' in harness
    assert "ws_token" not in harness
    assert "api/auth/ws-token" not in harness
    assert "await _poll_agent_run(" in harness
