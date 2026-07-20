"""Ansible setup helpers: binary/image detection, YAML + inventory generation.

Extracted from ansible_engine.py to keep modules under the size limit.
Re-exported from servers.services.ansible_engine for backward compatibility.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from servers.secret_utils import get_server_auth_secret, get_server_sudo_secret

logger = logging.getLogger(__name__)

# Prefer project image (built via docker/ansible-runner). Override with WEBTERM_ANSIBLE_IMAGE.
LOCAL_ANSIBLE_IMAGE = os.environ.get("WEBTERM_ANSIBLE_IMAGE_LOCAL", "webterm-ansible:latest")
FALLBACK_ANSIBLE_IMAGE = os.environ.get("WEBTERM_ANSIBLE_IMAGE_FALLBACK", "cytopia/ansible:latest-tools")


def _safe_host_name(name: str, server_id: int) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", (name or "").strip()) or f"server_{server_id}"
    if cleaned[0].isdigit():
        cleaned = f"h_{cleaned}"
    return cleaned[:64]


def _docker_image_exists(docker: str, image: str) -> bool:
    try:
        proc = subprocess.run(
            [docker, "image", "inspect", image],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        return proc.returncode == 0
    except Exception:
        return False


def resolve_docker_ansible_image(docker: str | None = None) -> tuple[str, bool]:
    """Return (image_name, ready). Prefers local project image, then env, then fallback."""
    docker = docker or shutil.which("docker") or "docker"
    candidates: list[str] = []
    # Explicit env always first if set to something other than default local
    env_img = (os.environ.get("WEBTERM_ANSIBLE_IMAGE") or "").strip()
    if env_img:
        candidates.append(env_img)
    candidates.extend([LOCAL_ANSIBLE_IMAGE, FALLBACK_ANSIBLE_IMAGE])
    # de-dupe preserve order
    seen: set[str] = set()
    ordered: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            ordered.append(c)
    for image in ordered:
        if _docker_image_exists(docker, image):
            return image, True
    # Not built yet — return preferred local name (user builds with docker compose / script)
    return ordered[0] if ordered else LOCAL_ANSIBLE_IMAGE, False


def detect_ansible() -> dict[str, Any]:
    """Discover how (if) ansible-playbook can be run on this host."""
    executable_name = "ansible-playbook.exe" if os.name == "nt" else "ansible-playbook"
    venv_candidate = Path(sys.executable).with_name(executable_name)
    native = str(venv_candidate) if venv_candidate.exists() else shutil.which("ansible-playbook")
    if native:
        version = _run_version([native, "--version"])
        return {
            "available": True,
            "method": "native",
            "binary": native,
            "version": version,
            "message": "ansible-playbook found on PATH",
        }

    # WSL
    wsl = shutil.which("wsl")
    if wsl:
        try:
            proc = subprocess.run(
                [wsl, "-e", "bash", "-lc", "ansible-playbook --version"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if proc.returncode == 0:
                version = (proc.stdout or "").splitlines()[0] if proc.stdout else "ansible (wsl)"
                return {
                    "available": True,
                    "method": "wsl",
                    "binary": "wsl",
                    "version": version,
                    "message": "ansible-playbook available via WSL",
                }
        except Exception as exc:
            logger.debug("WSL ansible probe failed: %s", exc)

    # Docker — ad-hoc runner container (no always-on service needed)
    docker = shutil.which("docker")
    if docker:
        image, image_ready = resolve_docker_ansible_image(docker)
        return {
            "available": True,
            "method": "docker",
            "binary": docker,
            "version": f"docker:{image}" + ("" if image_ready else " (build/pull required)"),
            "message": (
                "Ansible runs ad-hoc in Docker (no long-running agent). "
                + (
                    f"Image ready: {image}"
                    if image_ready
                    else f"Build image: docker build -t {LOCAL_ANSIBLE_IMAGE} -f docker/ansible-runner/Dockerfile ."
                )
            ),
            "image": image,
            "image_ready": image_ready,
            "build_hint": f"docker build -t {LOCAL_ANSIBLE_IMAGE} -f docker/ansible-runner/Dockerfile .",
        }

    return {
        "available": False,
        "method": "none",
        "binary": "",
        "version": "",
        "message": (
            "Ansible not found. Options: (1) pip install ansible-core  "
            f"(2) build Docker runner: docker build -t {LOCAL_ANSIBLE_IMAGE} -f docker/ansible-runner/Dockerfile .  "
            "(3) WSL with ansible-playbook. Shell fallback remains available."
        ),
    }


def _run_version(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
        line = (proc.stdout or proc.stderr or "").splitlines()
        return line[0] if line else "ansible-playbook"
    except Exception:
        return "ansible-playbook"


def tasks_to_ansible_yaml(
    *,
    name: str,
    tasks: list[dict[str, Any]],
    become: bool = True,
    gather_facts: bool = True,
) -> str:
    """Convert WebTerm task list into a minimal valid Ansible playbook (shell modules)."""
    lines = [
        f"- name: {json.dumps(name or 'WebTerm playbook')[1:-1]}",
        "  hosts: all",
        f"  become: {'true' if become else 'false'}",
        f"  gather_facts: {'true' if gather_facts else 'false'}",
        "  tasks:",
    ]
    for idx, task in enumerate(tasks):
        command = str(task.get("command") or "").strip()
        if not command or command.lstrip().startswith("#"):
            continue
        desc = str(task.get("description") or f"Task {idx + 1}").replace('"', "'")
        lines.append(f"    - name: {desc}")
        # Use free-form shell for multi-line / complex commands
        if "\n" in command:
            lines.append("      ansible.builtin.shell: |")
            for part in command.splitlines():
                lines.append(f"        {part}")
        else:
            # YAML-safe single line
            safe = command.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'      ansible.builtin.shell: "{safe}"')
        lines.append("      args:")
        lines.append("        executable: /bin/bash")
        if task.get("continue_on_error") or task.get("continueOnError"):
            lines.append("      ignore_errors: true")
        lines.append("      register: wt_task_result")
        lines.append("      changed_when: wt_task_result.rc == 0")
    if len(lines) <= 5:
        raise ValueError("No runnable tasks to convert into Ansible YAML")
    return "\n".join(lines) + "\n"


def ensure_playbook_yaml(snapshot: dict[str, Any], *, become: bool = True) -> str:
    """Prefer original source_yaml; otherwise build from tasks."""
    source = str(snapshot.get("source_yaml") or "").strip()
    if source:
        return source
    tasks = snapshot.get("tasks") or []
    if not isinstance(tasks, list):
        tasks = []
    return tasks_to_ansible_yaml(
        name=str(snapshot.get("name") or "WebTerm playbook"),
        tasks=tasks,
        become=become,
        gather_facts=True,
    )


def _write_inventory(
    workdir: Path,
    servers: list[Any],
    *,
    master_password: str = "",
    binding_groups: dict[str, list[int]] | None = None,
) -> tuple[Path, list[Path]]:
    """Write inventory.ini + optional key files. Returns (inventory_path, cleanup_paths)."""
    inv_path = workdir / "inventory.ini"
    cleanup: list[Path] = []
    lines = [
        "# Generated by WebTerm — real Ansible inventory",
        "",
        "[all]",
    ]
    groups: dict[str, list[str]] = {}
    binding_groups = binding_groups or {}

    for server in servers:
        host_alias = _safe_host_name(getattr(server, "name", ""), int(server.id))
        host = str(server.host)
        port = int(server.port or 22)
        user = str(server.username or "root")
        parts = [
            host_alias,
            f"ansible_host={host}",
            f"ansible_port={port}",
            f"ansible_user={user}",
            "ansible_connection=ssh",
            "ansible_python_interpreter=auto_silent",
            f"wt_server_id={server.id}",
            f"wt_server_name={json.dumps(server.name)[1:-1]}",
        ]

        auth_method = getattr(server, "auth_method", "password") or "password"
        key_path = (getattr(server, "key_path", "") or "").strip()

        if auth_method in ("key", "key_password") and key_path and Path(key_path).is_file():
            # Copy key into workdir for docker mounts
            key_dest = workdir / f"key_{server.id}"
            shutil.copy2(key_path, key_dest)
            with contextlib.suppress(OSError):
                os.chmod(key_dest, 0o600)
            cleanup.append(key_dest)
            # Inside docker/native workdir relative path
            parts.append(f"ansible_ssh_private_key_file={key_dest.name}")
            if auth_method == "key_password":
                try:
                    passphrase = get_server_auth_secret(server, master_password=master_password, fallback_plain="")
                    if passphrase:
                        # ssh-key with passphrase needs ssh-agent; store for advanced users in host vars comment
                        parts.append(f"ansible_ssh_passphrase={_ini_escape(passphrase)}")
                except Exception:
                    pass
        else:
            try:
                password = get_server_auth_secret(server, master_password=master_password, fallback_plain="")
            except Exception:
                password = ""
            if password:
                parts.append(f"ansible_ssh_pass={_ini_escape(password)}")
                parts.append(
                    "ansible_ssh_common_args='-o PreferredAuthentications=password -o PubkeyAuthentication=no'"
                )

        # sudo / become password
        try:
            sudo_pw = get_server_sudo_secret(server, master_password=master_password, fallback_plain="")
        except Exception:
            sudo_pw = ""
        if sudo_pw:
            parts.append(f"ansible_become_password={_ini_escape(sudo_pw)}")

        lines.append(" ".join(parts))

        group = getattr(server, "group", None)
        if group is not None and getattr(group, "name", None):
            gname = re.sub(r"[^a-zA-Z0-9_\-]", "_", group.name) or "group"
            groups.setdefault(gname, []).append(host_alias)
        for binding_name, server_ids in binding_groups.items():
            if int(server.id) in {int(item) for item in server_ids}:
                groups.setdefault(binding_name, []).append(host_alias)

    lines.append("")
    for gname, members in groups.items():
        lines.append(f"[{gname}]")
        lines.extend(members)
        lines.append("")

    lines.extend(
        [
            "[all:vars]",
            "ansible_ssh_common_args='-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'",
            "",
        ]
    )
    inv_path.write_text("\n".join(lines), encoding="utf-8")
    return inv_path, cleanup


def _ini_escape(value: str) -> str:
    # Keep inventory simple: strip quotes/newlines
    return value.replace("\n", "").replace("\r", "").replace(" ", "\\ ")


def _build_ansible_cfg(workdir: Path) -> Path:
    """Write ansible.cfg that never depends on the removed/optional `json` callback."""
    cfg = workdir / "ansible.cfg"
    cfg.write_text(
        "\n".join(
            [
                "[defaults]",
                "host_key_checking = False",
                "retry_files_enabled = False",
                # Built-in callbacks only — avoid 'Could not load json callback plugin'
                "stdout_callback = default",
                "bin_ansible_callbacks = False",
                "interpreter_python = auto_silent",
                "timeout = 30",
                "forks = 10",
                "display_skipped_hosts = True",
                "display_ok_hosts = True",
                "",
                "[ssh_connection]",
                "pipelining = True",
                "ssh_args = -o ControlMaster=auto -o ControlPersist=60s -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return cfg


def estimate_total_tasks(playbook_yaml: str) -> int:
    """Rough count of TASK headers ansible will print for one pass of the playbook.

    Counts indented `- name:` entries (tasks/handlers) plus one implicit
    "Gathering Facts" per play unless gather_facts is disabled for it.
    """
    if not playbook_yaml:
        return 0
    tasks = len(re.findall(r"^\s+-\s+name\s*:", playbook_yaml, re.MULTILINE))
    plays = len(re.findall(r"^-\s+name\s*:", playbook_yaml, re.MULTILINE)) or 1
    gather_disabled = len(re.findall(r"gather_facts\s*:\s*(?:false|no)\b", playbook_yaml, re.IGNORECASE))
    return tasks + max(0, plays - gather_disabled)
