"""Build a fail-closed Docker command for untrusted Ansible execution."""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

_VOLUME_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_NETWORK_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_HOST_ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")
_IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_WORKDIR_RE = re.compile(r"^pb-r(?P<run>\d+)-d(?P<dispatch>\d+)-a(?P<attempt>\d+)$")
RUNNER_UID = 10001
RUNNER_GID = 10001
RUNTIME_LABEL_PREFIX = "com.webterm.playbook"

logger = logging.getLogger(__name__)


def probe_image_runtime_metadata(docker: str, image_id: str) -> dict | None:
    """Read the trusted runner manifest with the socket-proxy probe profile."""
    probe_name = f"webterm-pb-probe-{secrets.token_hex(8)}"
    try:
        result = subprocess.run(
            [
                docker,
                "run",
                "--rm",
                "--pull=never",
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--cgroupns=private",
                "--pids-limit=32",
                "--memory=128m",
                "--cpus=0.25",
                "--user=10001:10001",
                "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=64m",
                f"--name={probe_name}",
                "--label=com.webterm.playbook.probe=runtime-metadata",
                "--entrypoint=python",
                image_id,
                "-B",
                "/opt/webterm/runtime_metadata.py",
                "--print",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        document = json.loads(result.stdout) if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None
    digest = document.get("runtime_digest") if isinstance(document, dict) else None
    return document if isinstance(digest, str) and _IMAGE_ID_RE.fullmatch(digest) else None


class AnsibleIsolationError(RuntimeError):
    """The configured isolated execution environment is unsafe or unavailable."""


@dataclass(frozen=True)
class AnsibleRuntimeIdentity:
    run_id: int
    dispatch_id: int
    attempt_count: int

    def __post_init__(self) -> None:
        if min(self.run_id, self.dispatch_id, self.attempt_count) <= 0:
            raise ValueError("Ansible runtime identity values must be positive")

    @property
    def slug(self) -> str:
        return f"pb-r{self.run_id}-d{self.dispatch_id}-a{self.attempt_count}"

    @property
    def container_name(self) -> str:
        return f"webterm-{self.slug}"

    @property
    def labels(self) -> dict[str, str]:
        return {
            f"{RUNTIME_LABEL_PREFIX}.run_id": str(self.run_id),
            f"{RUNTIME_LABEL_PREFIX}.dispatch_id": str(self.dispatch_id),
            f"{RUNTIME_LABEL_PREFIX}.attempt": str(self.attempt_count),
        }

    @classmethod
    def from_workdir_name(cls, value: str) -> AnsibleRuntimeIdentity | None:
        match = _WORKDIR_RE.fullmatch(value)
        if match is None:
            return None
        return cls(
            run_id=int(match.group("run")),
            dispatch_id=int(match.group("dispatch")),
            attempt_count=int(match.group("attempt")),
        )


@dataclass(frozen=True)
class RuntimeCleanupResult:
    status: str
    message: str = ""

    @property
    def safe_to_retry(self) -> bool:
        return self.status in {"absent", "removed", "not_required"}


def bind_isolated_runtime_identity(
    *,
    run_id: int,
    dispatch_id: int | None,
    attempt_count: int | None,
    expected_digest: str,
    actual_digest: str,
    isolation_required: bool,
) -> tuple[AnsibleRuntimeIdentity | None, str]:
    if not isolation_required:
        return None, ""
    if not dispatch_id or not attempt_count:
        return None, "Isolated Ansible execution requires a durable dispatch claim."
    if not expected_digest or expected_digest != actual_digest:
        return None, (
            "The isolated Ansible runtime changed after validation; validate this revision again before running."
        )
    return AnsibleRuntimeIdentity(run_id, dispatch_id, attempt_count), ""


def isolated_execution_required() -> bool:
    if (os.environ.get("DJANGO_SETTINGS_MODULE") or "").strip() == "web_ui.settings.production":
        return True
    return (os.environ.get("WEBTERM_ANSIBLE_REQUIRE_ISOLATED", "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def docker_host_alias() -> str:
    configured = os.environ.get("WEBTERM_ANSIBLE_DOCKER_HOST_ALIAS")
    alias = "host.docker.internal" if configured is None else configured.strip()
    if alias and not _HOST_ALIAS_RE.fullmatch(alias):
        raise AnsibleIsolationError("Ansible Docker host alias is invalid")
    return alias


def route_loopback_to_docker_host(host: str, docker_host: str) -> str:
    """Route loopback inventory targets through the Docker host gateway."""

    normalized_host = host.strip("[]").lower()
    try:
        is_loopback = ipaddress.ip_address(normalized_host).is_loopback
    except ValueError:
        is_loopback = normalized_host == "localhost"
    return docker_host if docker_host and is_loopback else host


def create_ansible_workdir(runtime_identity: AnsibleRuntimeIdentity | None = None) -> Path:
    configured = (os.environ.get("WEBTERM_ANSIBLE_RUNTIME_ROOT") or "").strip()
    if not configured:
        if runtime_identity is not None and isolated_execution_required():
            raise AnsibleIsolationError(
                "Isolated Ansible execution requires WEBTERM_ANSIBLE_RUNTIME_ROOT for crash cleanup"
            )
        prefix = f"{runtime_identity.slug}-" if runtime_identity else "webterm_ansible_"
        return Path(tempfile.mkdtemp(prefix=prefix))
    root = Path(configured).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    with suppress(OSError):
        os.chmod(root, 0o700)
    if runtime_identity is not None:
        workdir = root / runtime_identity.slug
        try:
            workdir.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise AnsibleIsolationError("Ansible runtime directory already exists for this claim attempt") from exc
        return workdir
    return Path(tempfile.mkdtemp(prefix="run_", dir=root))


def _inspect_runtime_container(
    runtime_identity: AnsibleRuntimeIdentity,
    *,
    docker: str | None = None,
) -> tuple[str, str]:
    executable = docker or shutil.which("docker")
    if not executable:
        return "unavailable", "Docker is unavailable"
    try:
        result = subprocess.run(
            [
                executable,
                "container",
                "inspect",
                "--format",
                "{{json .Config.Labels}}",
                runtime_identity.container_name,
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return "unavailable", str(exc)[:500]
    if result.returncode != 0:
        error = (result.stderr or result.stdout or "").strip()
        if "no such container" in error.lower() or "no such object" in error.lower():
            return "absent", ""
        return "unavailable", error[:500]
    try:
        labels = json.loads((result.stdout or "{}").strip())
    except json.JSONDecodeError:
        return "unavailable", "Docker returned invalid container metadata"
    if not isinstance(labels, dict) or any(labels.get(key) != value for key, value in runtime_identity.labels.items()):
        return "mismatch", "Container identity labels do not match the dispatch fence"
    return "matched", executable


def cleanup_ansible_runtime_job(
    runtime_identity: AnsibleRuntimeIdentity,
    *,
    docker: str | None = None,
) -> RuntimeCleanupResult:
    status, detail = _inspect_runtime_container(runtime_identity, docker=docker)
    if status != "matched":
        return RuntimeCleanupResult(status, detail)
    executable = docker or detail
    try:
        result = subprocess.run(
            [executable, "container", "rm", "--force", runtime_identity.container_name],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return RuntimeCleanupResult("unavailable", str(exc)[:500])
    if result.returncode == 0:
        return RuntimeCleanupResult("removed")
    error = (result.stderr or result.stdout or "").strip()
    if "no such container" in error.lower() or "no such object" in error.lower():
        return RuntimeCleanupResult("absent")
    return RuntimeCleanupResult("unavailable", error[:500])


def cleanup_claim_runtime_job(
    run_id: int,
    dispatch_id: int,
    attempt_count: int,
) -> RuntimeCleanupResult:
    if not isolated_execution_required() or attempt_count <= 0:
        return RuntimeCleanupResult("not_required")
    return cleanup_ansible_runtime_job(AnsibleRuntimeIdentity(run_id, dispatch_id, attempt_count))


def cleanup_claim_runtime_after_commit(run_id: int, dispatch_id: int, attempt_count: int) -> None:
    cleanup = cleanup_claim_runtime_job(run_id, dispatch_id, attempt_count)
    if not cleanup.safe_to_retry:
        logger.error(
            "Could not confirm cleanup of isolated Ansible runtime pb-r%s-d%s-a%s: %s (%s)",
            run_id,
            dispatch_id,
            attempt_count,
            cleanup.status,
            cleanup.message,
        )


def scavenge_ansible_workdirs(*, now: float | None = None) -> dict[str, int]:
    configured = (os.environ.get("WEBTERM_ANSIBLE_RUNTIME_ROOT") or "").strip()
    summary = {"removed": 0, "active": 0, "skipped": 0}
    if not configured:
        return summary
    root = Path(configured).expanduser().resolve()
    if not root.is_dir():
        return summary
    try:
        ttl = int(os.environ.get("WEBTERM_ANSIBLE_RUNTIME_TTL_SECONDS", "7200"))
    except ValueError:
        ttl = 7200
    ttl = max(600, ttl)
    current = time.time() if now is None else float(now)
    try:
        candidates = list(root.iterdir())
    except OSError:
        summary["skipped"] += 1
        return summary
    for candidate in candidates:
        identity = AnsibleRuntimeIdentity.from_workdir_name(candidate.name)
        if identity is None or candidate.is_symlink() or not candidate.is_dir():
            continue
        try:
            if current - candidate.stat().st_mtime < ttl:
                continue
        except OSError:
            summary["skipped"] += 1
            continue
        cleanup = cleanup_ansible_runtime_job(identity)
        if not cleanup.safe_to_retry:
            summary["active" if cleanup.status in {"matched", "mismatch"} else "skipped"] += 1
            continue
        try:
            resolved = candidate.resolve(strict=True)
            if resolved.parent != root:
                summary["skipped"] += 1
                continue
            shutil.rmtree(resolved)
            summary["removed"] += 1
        except OSError:
            summary["skipped"] += 1
    return summary


def prepare_workdir_for_runner(workdir: Path, *, named_volume: bool) -> str:
    """Make runtime files readable only by the identity used inside the job."""

    if named_volume:
        uid, gid = RUNNER_UID, RUNNER_GID
    elif os.name == "posix":
        uid, gid = os.getuid(), os.getgid()
    else:
        uid, gid = RUNNER_UID, RUNNER_GID
    for path in [workdir, *workdir.rglob("*")]:
        if hasattr(os, "chown"):
            with suppress(OSError):
                os.chown(path, uid, gid)
        with suppress(OSError):
            os.chmod(path, 0o700 if path.is_dir() else 0o600)
    return f"{uid}:{gid}"


def build_isolated_docker_command(
    *,
    docker: str,
    image: str,
    workdir: Path,
    ansible_args: list[str],
    runtime_identity: AnsibleRuntimeIdentity | None = None,
) -> list[str]:
    volume = (os.environ.get("WEBTERM_ANSIBLE_DOCKER_RUNTIME_VOLUME") or "").strip()
    if volume and not _VOLUME_NAME_RE.fullmatch(volume):
        raise AnsibleIsolationError("Ansible runtime volume name is invalid")
    network = (os.environ.get("WEBTERM_ANSIBLE_DOCKER_NETWORK") or "bridge").strip()
    if not _NETWORK_NAME_RE.fullmatch(network) or network == "host":
        raise AnsibleIsolationError("Ansible runner must use a non-host Docker network")
    if runtime_identity is not None and isolated_execution_required() and not _IMAGE_ID_RE.fullmatch(image):
        raise AnsibleIsolationError("Isolated Ansible execution requires an immutable Docker image ID")

    user = prepare_workdir_for_runner(workdir, named_volume=bool(volume))
    command = [
        docker,
        "run",
        "--rm",
        "--pull=never",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--cgroupns=private",
        "--pids-limit=256",
        "--memory",
        (os.environ.get("WEBTERM_ANSIBLE_DOCKER_MEMORY") or "512m").strip(),
        "--cpus",
        (os.environ.get("WEBTERM_ANSIBLE_DOCKER_CPUS") or "1.0").strip(),
        "--network",
        network,
    ]
    host_alias = docker_host_alias()
    if host_alias:
        command.extend(["--add-host", f"{host_alias}:host-gateway"])
    command.extend(
        [
            "--user",
            user,
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=64m",
        ]
    )
    if runtime_identity is not None:
        command.extend(["--name", runtime_identity.container_name])
        for key, value in runtime_identity.labels.items():
            command.extend(["--label", f"{key}={value}"])
    if volume:
        runtime_root = Path(os.environ.get("WEBTERM_ANSIBLE_RUNTIME_ROOT") or "").resolve()
        try:
            relative = workdir.resolve().relative_to(runtime_root)
        except (OSError, ValueError) as exc:
            raise AnsibleIsolationError("Ansible workdir is outside its runtime volume") from exc
        if len(relative.parts) != 1:
            raise AnsibleIsolationError("Ansible runtime volume requires a per-run subdirectory")
        command.extend(
            [
                "--mount",
                f"type=volume,src={volume},dst=/ansible,volume-subpath={relative.as_posix()}",
            ]
        )
    else:
        command.extend(["--mount", f"type=bind,src={workdir.resolve()},dst=/ansible"])
    command.extend(
        [
            "-w",
            "/ansible",
            "-e",
            "HOME=/tmp",
            "-e",
            "ANSIBLE_LOCAL_TEMP=/tmp/ansible-local",
            "-e",
            "ANSIBLE_FORCE_COLOR=0",
            "-e",
            "ANSIBLE_NOCOLOR=1",
            "-e",
            "ANSIBLE_CONFIG=/ansible/ansible.cfg",
            "--entrypoint",
            "ansible-playbook",
            image,
            *ansible_args[1:],
        ]
    )
    return command
