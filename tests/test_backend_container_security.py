from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PYTHON_IMAGE = "python:3.11.15-slim-bookworm"


def test_backend_image_is_multistage_and_non_root():
    dockerfile = (ROOT / "docker" / "backend.Dockerfile").read_text(encoding="utf-8")
    builder, runtime = dockerfile.split(f"FROM {PYTHON_IMAGE} AS runtime", maxsplit=1)

    assert dockerfile.startswith(f"FROM {PYTHON_IMAGE} AS builder\n")
    assert "gcc" in builder
    assert "git" in builder
    assert "libldap2-dev" in builder
    assert "gcc" not in runtime
    assert "libldap2-dev" not in runtime
    assert "COPY --from=builder /opt/venv /opt/venv" in runtime
    assert "/etc/profile.d/webterm-venv.sh" in runtime
    assert "USER 10001:10001" in runtime
    assert "HEALTHCHECK" in runtime
    assert "/api/ready/" in runtime


def test_production_compose_prepares_volumes_for_non_root_backend():
    config = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text(encoding="utf-8"))
    services = config["services"]
    permissions = services["volume-permissions"]

    assert permissions["user"] == "0:0"
    assert permissions["network_mode"] == "none"
    assert permissions["read_only"] is True
    assert permissions["cap_drop"] == ["ALL"]
    assert services["backend"]["depends_on"]["volume-permissions"]["condition"] == "service_completed_successfully"
    assert services["playbook-execution-worker"]["group_add"] == ["${DOCKER_SOCKET_GID:-0}"]


def test_validator_socket_is_owned_by_backend_runtime_user():
    validator = (ROOT / "docker" / "ansible-runner" / "validator.py").read_text(encoding="utf-8")

    assert "os.chown(socket_path, RUNNER_UID, RUNNER_GID)" in validator


def test_installer_detects_host_docker_socket_group():
    installer = (ROOT / "docker" / "install-production.sh").read_text(encoding="utf-8")

    assert "configure_docker_socket_gid" in installer
    assert "stat -c '%g' /var/run/docker.sock" in installer
