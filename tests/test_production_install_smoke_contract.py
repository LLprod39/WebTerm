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


def test_release_publishes_and_smokes_separate_ai_cli_images() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    smoke = (ROOT / "docker/production-install-smoke.sh").read_text(encoding="utf-8")

    for name, env_name in (
        ("ai-cli-docker-proxy", "WEBTERM_AI_CLI_DOCKER_PROXY_IMAGE"),
        ("ai-cli-egress-proxy", "WEBTERM_AI_CLI_EGRESS_PROXY_IMAGE"),
        ("ai-cli-runner-manager", "WEBTERM_AI_CLI_RUNNER_MANAGER_IMAGE"),
        ("ai-cli-codex-runner", "AI_CLI_CODEX_RUNNER_IMAGE"),
        ("ai-cli-grok-runner", "AI_CLI_GROK_RUNNER_IMAGE"),
    ):
        assert f"name: {name}" in workflow
        assert workflow.count(f'"{name}": "{env_name}"') == 2
    assert "target: codex" in workflow
    assert "target: grok" in workflow
    assert "GROK_BUILD_SHA256" in workflow
    assert 'F13A_WITH_AI_CLI: "1"' in workflow
    assert "UID 10001 credential volume passed" in smoke
    assert "ai-cli-egress-policy.txt" in smoke
    assert '"169.254.169.254:443"' in smoke
    assert '"postgres:5432"' in smoke
    assert '"api.openai.com:443"' in smoke
    assert '"api.x.ai:443"' in smoke


def test_ai_cli_images_install_only_hashed_locks_and_security_audits_them() -> None:
    backend_dockerfile = (ROOT / "docker/backend.Dockerfile").read_text(encoding="utf-8")
    manager_dockerfile = (ROOT / "docker/ai-cli-runner-manager.Dockerfile").read_text(encoding="utf-8")
    provider_dockerfile = (ROOT / "docker/ai-cli-provider-runner.Dockerfile").read_text(encoding="utf-8")
    security = (ROOT / ".github/workflows/security.yml").read_text(encoding="utf-8")
    sbom = (ROOT / "scripts/generate_sbom.py").read_text(encoding="utf-8")

    assert "--require-hashes -r /app/ai_cli_runner_manager/requirements.lock" in manager_dockerfile
    assert "--require-hashes --requirement /app/provider-requirements.lock" in provider_dockerfile
    assert "/opt/venv/bin/pip uninstall --yes pip setuptools wheel" in backend_dockerfile
    assert "/opt/venv/bin/pip uninstall --yes pip setuptools wheel" in manager_dockerfile
    assert "/opt/venv/bin/python -m pip uninstall --yes pip setuptools wheel" in provider_dockerfile
    for lock in ("ai_cli_runner_manager/requirements.lock", "ai_cli_runner_manager/provider-requirements.lock"):
        text = (ROOT / lock).read_text(encoding="utf-8")
        assert "--hash=sha256:" in text
        assert lock in security
        assert lock in sbom
    assert "pip-audit-ai-cli-$plane.json" in security
    assert "sbom-ai-cli-manager.cdx.json" in security
    assert "sbom-ai-cli-provider.cdx.json" in security


def test_optional_pilot_profiles_are_explicit_and_fail_closed() -> None:
    installer = (ROOT / "docker/install-production.sh").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")

    for flag in ("--with-ai-cli", "--with-observability", "--cleanup-ai-cli-credentials"):
        assert flag in installer
    assert "AI_CLI_RUNNER_IMAGE" not in compose
    assert "webterm-ai-cli-egress-proxy:latest" not in compose
    assert "webterm-ai-cli-runner-manager:latest" not in compose
    assert "api/ready/?scope=core" in compose
    assert 'profiles: ["observability"]' in compose
    assert "TELEGRAM_BOT_TOKEN is provisioned but --with-telegram-bot was not requested" in installer
    assert "--concurrency ${AI_CLI_AUTH_WORKER_CONCURRENCY:-4}" in compose
    assert "AI_CLI_AUTH_WORKER_CONCURRENCY must be an integer from 1 through 8" in installer
    assert "validate-pilot-capacity.py" in installer
    assert "--with-ai-cli requires PILOT_RESTRICTED_MODE=true" in installer
    assert "explicit disposable PILOT_SSH_ALLOWED_HOSTS/CIDRS/PORTS" in installer
    assert "compose restart nginx" in installer
    for key in (
        "PILOT_RESTRICTED_MODE",
        "PILOT_SSH_ALLOWED_HOSTS",
        "PILOT_SSH_ALLOWED_CIDRS",
        "PILOT_SSH_ALLOWED_PORTS",
    ):
        assert key in compose
    assert "pilot install requires the age command for encrypted backups" in installer
    assert "BACKUP_AGE_RECIPIENT_FILE must reference a provisioned public age recipient file" in installer
    assert "WEBTERM_ALERTMANAGER_IMAGE" in installer
    assert "alertmanager-config.txt" in (ROOT / "docker/production-install-smoke.sh").read_text(encoding="utf-8")


def test_ai_cli_egress_denies_private_and_metadata_destinations_before_provider_domains() -> None:
    squid = (ROOT / "docker/ai-cli-egress-squid.conf").read_text(encoding="utf-8")

    deny = squid.index("http_access deny forbidden_dst")
    allow = squid.index("http_access allow CONNECT provider_domains")
    assert deny < allow
    assert squid.index("http_access allow localhost manager") < squid.index("http_access deny manager")
    assert squid.index("http_access deny manager") < squid.index("http_access deny !CONNECT")
    for network in (
        "127.0.0.0/8",
        "169.254.0.0/16",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "::1/128",
        "fc00::/7",
    ):
        assert network in squid


def test_release_excludes_the_local_mcp_demo_fixture() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
    installer = (ROOT / "docker/install-production.sh").read_text(encoding="utf-8")
    production_env = (ROOT / ".env.production.example").read_text(encoding="utf-8")

    for content in (workflow, compose, installer, production_env):
        assert "WEBTERM_MCP_DEMO_IMAGE" not in content
        assert "STUDIO_MCP_DEMO_URL" not in content
        assert "mcp-demo" not in content


def test_release_tag_must_match_the_canonical_version() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip().replace(".", "_")

    assert "Verify release tag and contracts" in workflow
    assert 'expected="v$(tr -d' in workflow
    assert 'test "$GITHUB_REF_NAME" = "$expected"' in workflow
    assert f"docs/releases/V{version}_RELEASE_NOTES.md" in workflow


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


def test_production_installers_generate_the_required_mcp_runner_token() -> None:
    internal = (ROOT / "docker/install-production.sh").read_text(encoding="utf-8")
    outer = (ROOT / "install-server.sh").read_text(encoding="utf-8")

    assert 'generate_secret_if_needed "STUDIO_MCP_RUNNER_TOKEN" 64' in internal
    assert 'env_set STUDIO_MCP_RUNNER_TOKEN "$(random_string 64)"' in outer


def test_production_installer_starts_the_execution_planes() -> None:
    installer = (ROOT / "docker/install-production.sh").read_text(encoding="utf-8")
    smoke = (ROOT / "docker/production-install-smoke.sh").read_text(encoding="utf-8")

    service_block = installer.split("local services=(", 1)[1].split(")", 1)[0]
    assert "playbook-docker-proxy" in service_block
    assert "playbook-execution-worker" in service_block
    assert "pipeline-execution" in service_block
    assert "agent-execution" in service_block
    assert "wait_for_service pipeline-execution 180" in installer
    assert "wait_for_service agent-execution 180" in installer
    assert "mini-prod-pipeline-execution" in smoke
    assert '"studio_pipeline_execution"' in smoke
    assert "healthy_agent_execution_replicas" in smoke


def test_production_installer_reads_multi_replica_service_id_without_sigpipe() -> None:
    installer = (ROOT / "docker/install-production.sh").read_text(encoding="utf-8")
    helper = installer.split("service_container_id()", 1)[1].split("wait_for_service()", 1)[0]

    assert "compose ps -q" in helper
    assert "sed -n '1p'" in helper
    assert "head -n 1" not in helper


def test_production_installer_pulls_the_pinned_agent_command_runner() -> None:
    installer = (ROOT / "docker/install-production.sh").read_text(encoding="utf-8")

    runner_block = installer.split("ensure_agent_command_runner_image()", 1)[1].split(
        "configure_agent_command_network()", 1
    )[0]
    assert 'docker image inspect "$configured"' in runner_block
    assert 'docker pull "$configured"' in runner_block
    assert "Pulling the pinned ephemeral agent command runner" in runner_block


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
