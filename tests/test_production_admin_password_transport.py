import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_admin_password_never_crosses_process_arguments() -> None:
    internal = (ROOT / "docker/install-production.sh").read_text(encoding="utf-8")
    outer = (ROOT / "install-server.sh").read_text(encoding="utf-8")
    smoke = (ROOT / "docker/production-install-smoke.sh").read_text(encoding="utf-8")

    assert "--superuser-password PASS" not in internal
    assert '--superuser-password "$ADMIN_PASSWORD"' not in outer
    assert '--superuser-password "$ADMIN_PASSWORD"' not in smoke
    assert '-e DJANGO_SUPERUSER_PASSWORD="$SUPERUSER_PASSWORD"' not in internal
    assert 'python3 - "$LOGIN_PAYLOAD" "$ADMIN_USERNAME" "$ADMIN_PASSWORD"' not in smoke


def test_installers_never_print_admin_password() -> None:
    internal = (ROOT / "docker/install-production.sh").read_text(encoding="utf-8")
    outer = (ROOT / "install-server.sh").read_text(encoding="utf-8")

    assert "password: ${ADMIN_PASSWORD}" not in outer
    assert "password: (the one you passed to the installer)" not in internal


def test_installer_secret_file_must_be_private_and_not_a_symlink(tmp_path: Path) -> None:
    helper = ROOT / "docker/installer-secret-input.sh"
    secret = tmp_path / "admin-password"
    secret.write_text("private-password-sentinel\n", encoding="utf-8")
    secret.chmod(0o644)
    command = f'source "{helper}"; installer_read_secret VALUE "Admin password" file "$1"'

    exposed = subprocess.run(
        ["bash", "-c", command, "installer-secret-test", str(secret)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert exposed.returncode != 0
    assert "private-password-sentinel" not in exposed.stdout + exposed.stderr

    secret.chmod(0o600)
    symlink = tmp_path / "admin-password-link"
    symlink.symlink_to(secret)
    linked = subprocess.run(
        ["bash", "-c", command, "installer-secret-test", str(symlink)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert linked.returncode != 0
    assert "symbolic-link secret file" in linked.stderr
