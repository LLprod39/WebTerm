from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _fake_docker_path(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
    docker.chmod(0o755)
    return fake_bin


def _installer_env(fake_bin: Path) -> dict[str, str]:
    return {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "WEBTRERM_INSTALLER_NO_SUDO_REEXEC": "1",
    }


def _assert_private_env_file(path: Path) -> None:
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def _minimal_internal_project(tmp_path: Path) -> Path:
    project = tmp_path / "internal-project"
    (project / "docker").mkdir(parents=True)
    shutil.copy2(ROOT / "docker/install-production.sh", project / "docker/install-production.sh")
    (project / "docker-compose.production.yml").write_text("services: {}\n", encoding="utf-8")
    (project / ".env.production.example").write_text(
        "\n".join(
            (
                f"DJANGO_SECRET_KEY={'d' * 64}",
                f"MANAGED_SECRET_KEY={'m' * 64}",
                "SITE_URL=https://webterm.invalid",
                "FRONTEND_APP_URL=https://webterm.invalid",
                "ALLOWED_HOSTS=webterm.invalid",
                "CSRF_TRUSTED_ORIGINS=https://webterm.invalid",
                f"MASTER_PASSWORD={'a' * 48}",
                "POSTGRES_DB=webterm",
                "POSTGRES_USER=webterm",
                f"POSTGRES_PASSWORD={'p' * 32}",
                f"AGENT_COMMAND_RUNNER_IMAGE=sha256:{'a' * 64}",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return project


def _run_internal_installer(project: Path, fake_bin: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(project / "docker/install-production.sh"), "--validate-only"],
        cwd=project,
        env=_installer_env(fake_bin),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        umask=0o022,
    )


def test_internal_production_installer_creates_private_env_file(tmp_path: Path) -> None:
    fake_bin = _fake_docker_path(tmp_path)
    project = _minimal_internal_project(tmp_path)
    env_file = project / ".env.production"

    result = _run_internal_installer(project, fake_bin)

    assert result.returncode == 0, result.stderr
    _assert_private_env_file(env_file)


def test_internal_production_installer_repairs_existing_env_permissions(tmp_path: Path) -> None:
    fake_bin = _fake_docker_path(tmp_path)
    project = _minimal_internal_project(tmp_path)
    env_file = project / ".env.production"
    shutil.copy2(project / ".env.production.example", env_file)
    env_file.chmod(0o644)

    result = _run_internal_installer(project, fake_bin)

    assert result.returncode == 0, result.stderr
    _assert_private_env_file(env_file)


def test_internal_production_installer_rejects_symlink_env_file(tmp_path: Path) -> None:
    fake_bin = _fake_docker_path(tmp_path)
    project = _minimal_internal_project(tmp_path)
    external_file = tmp_path / "external.env"
    external_file.write_text("SENTINEL=unchanged\n", encoding="utf-8")
    (project / ".env.production").symlink_to(external_file)

    result = _run_internal_installer(project, fake_bin)

    assert result.returncode != 0
    assert "refusing symbolic-link env file" in result.stderr
    assert external_file.read_text(encoding="utf-8") == "SENTINEL=unchanged\n"


def test_one_command_installer_creates_private_env_file(tmp_path: Path) -> None:
    fake_bin = _fake_docker_path(tmp_path)
    project = tmp_path / "project"
    (project / "docker").mkdir(parents=True)
    shutil.copy2(ROOT / ".env.production.example", project / ".env.production.example")
    shutil.copy2(ROOT / "docker-compose.production.yml", project / "docker-compose.production.yml")
    shutil.copy2(ROOT / "docker/install-production.sh", project / "docker/install-production.sh")

    result = subprocess.run(
        [
            "bash",
            str(ROOT / "install-server.sh"),
            "--dir",
            str(project),
            "--host",
            "localhost",
            "--skip-docker-install",
            "--only-prepare",
        ],
        cwd=tmp_path,
        env=_installer_env(fake_bin),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        umask=0o022,
    )

    assert result.returncode == 0, result.stderr
    _assert_private_env_file(project / ".env.production")
