from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_f13a_workflow_runs_the_production_installer_on_linux() -> None:
    workflow = (ROOT / ".github/workflows/production-install-smoke.yml").read_text(encoding="utf-8")

    assert "runs-on: ubuntu-latest" in workflow
    assert "./docker/production-install-smoke.sh" in workflow
    assert "f13a-production-install-${{ github.sha }}" in workflow


def test_release_publishes_and_smokes_the_socket_proxy_image() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "name: playbook-docker-proxy" in workflow
    assert "dockerfile: docker/playbook-socket-proxy.Dockerfile" in workflow
    assert workflow.count('"playbook-docker-proxy": "WEBTERM_PLAYBOOK_DOCKER_PROXY_IMAGE"') == 2
    assert "name: agent-command-runner" in workflow
    assert "dockerfile: docker/agent-command-runner/Dockerfile" in workflow
    assert workflow.count('"agent-command-runner": "AGENT_COMMAND_RUNNER_IMAGE"') == 2
    assert "name: agent-command-docker-proxy" in workflow
    assert workflow.count('"agent-command-docker-proxy": "WEBTERM_AGENT_COMMAND_DOCKER_PROXY_IMAGE"') == 2


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
        "PLAYBOOK_DOCKER_PROXY_PRIVILEGED_BLOCK_OK",
        "AGENT_COMMAND_DOCKER_PROXY_PRIVILEGED_BLOCK_OK",
        "docker run --pull=never --rm --name webterm-pb-r999-d999-a1 --privileged",
        "--terminal-sessions-per-user 1",
        "--pipeline-runs-per-user 1",
        "--agent-runs-per-user 1",
    ):
        assert required_probe in script


def test_production_installer_does_not_ignore_deploy_check_failure() -> None:
    installer = (ROOT / "docker/install-production.sh").read_text(encoding="utf-8")

    assert "compose exec -T backend python manage.py check --deploy" in installer
    assert "check --deploy || true" not in installer


def test_production_installer_starts_the_playbook_execution_plane() -> None:
    installer = (ROOT / "docker/install-production.sh").read_text(encoding="utf-8")

    service_block = installer.split("local services=(", 1)[1].split(")", 1)[0]
    assert "playbook-docker-proxy" in service_block
    assert "playbook-execution-worker" in service_block


def test_https_runtime_smoke_matches_browser_csrf_and_websocket_origin() -> None:
    harness = (ROOT / "docker/multi_user_load_smoke.py").read_text(encoding="utf-8")

    assert "self.csrf_token = self.csrf_cookie" in harness
    assert 'origin=self.base_url.rstrip("/")' in harness
    assert "self.session.cookie_jar.filter_cookies(URL(self.base_url))" in harness
    assert 'headers={"Cookie": self._cookie_header()}' not in harness
    assert "aiohttp.ClientTimeout(" in harness
    assert "aiohttp.ClientWSTimeout(" in harness
    assert "asyncio.wait_for(" in harness
    assert "ws_token" not in harness
    assert "api/auth/ws-token" not in harness
    assert "await _poll_agent_run(" in harness


def test_https_runtime_smoke_has_an_outer_process_deadline() -> None:
    script = (ROOT / "docker/production-install-smoke.sh").read_text(encoding="utf-8")

    assert "require_command timeout" in script
    assert "timeout --signal=TERM --kill-after=15s 300s" in script


def test_f13a_smoke_pins_and_confirms_one_ssh_host_key() -> None:
    script = (ROOT / "docker/production-install-smoke.sh").read_text(encoding="utf-8")
    sshd_config = (ROOT / "docker/sshd_smoke_config").read_text(encoding="utf-8")

    host_key_lines = [line for line in sshd_config.splitlines() if line.startswith("HostKey ")]
    assert host_key_lines == ["HostKey /etc/ssh/ssh_host_ed25519_key"]
    assert "ssh-keygen -lf //etc/ssh/ssh_host_ed25519_key.pub -E sha256" in script
    assert "--ssh-host-key-fingerprint '$SMOKE_SSH_FINGERPRINT'" in script
