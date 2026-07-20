"""Non-executing Ansible syntax validation for compatibility revisions."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from servers.services.ansible_output import _to_wsl_path, shlex_quote
from servers.services.ansible_setup import _build_ansible_cfg, detect_ansible, resolve_docker_ansible_image

_AUTO_INSTALL_COLLECTIONS = {"ansible.posix", "community.general"}


def _required_managed_collections(playbook_yaml: str) -> list[str]:
    referenced = set(re.findall(r"\b([a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)\.[a-zA-Z0-9_]+\b", playbook_yaml))
    return sorted(referenced & _AUTO_INSTALL_COLLECTIONS)


def _native_galaxy_binary(ansible_playbook: str) -> str:
    binary = Path(ansible_playbook)
    suffix = binary.suffix if binary.suffix.lower() in {".exe", ".cmd", ".bat"} else ""
    sibling = binary.with_name(f"ansible-galaxy{suffix}")
    return str(sibling) if sibling.exists() else str(shutil.which("ansible-galaxy") or sibling)


def _ensure_managed_collections(detection: dict[str, Any], required: list[str]) -> dict[str, Any]:
    if not required or str(detection.get("method") or "") == "docker":
        return {"status": "not_needed", "installed": []}

    method = str(detection.get("method") or "")
    if method == "native":
        galaxy = _native_galaxy_binary(str(detection.get("binary") or "ansible-playbook"))
        list_command = [galaxy, "collection", "list", "--format", "json"]
        install_command = [galaxy, "collection", "install", *required]
    elif method == "wsl":
        list_command = ["wsl", "-e", "bash", "-lc", "ansible-galaxy collection list --format json"]
        names = " ".join(required)
        install_command = ["wsl", "-e", "bash", "-lc", f"ansible-galaxy collection install {names}"]
    else:
        return {"status": "failed", "installed": [], "message": "Unsupported Ansible runtime"}

    try:
        listed = subprocess.run(list_command, capture_output=True, text=True, timeout=30, check=False)
        listing = (listed.stdout or "") + (listed.stderr or "")
        missing = [name for name in required if name not in listing]
        if not missing:
            return {"status": "ready", "installed": []}
        if method == "native":
            install_command = install_command[:3] + missing
        else:
            install_command[-1] = f"ansible-galaxy collection install {' '.join(missing)}"
        installed = subprocess.run(install_command, capture_output=True, text=True, timeout=180, check=False)
    except Exception as exc:
        return {"status": "failed", "installed": [], "message": str(exc)[:1000]}
    if installed.returncode != 0:
        output = ((installed.stdout or "") + "\n" + (installed.stderr or "")).strip()
        return {
            "status": "failed",
            "installed": [],
            "message": f"Could not install required Ansible collections: {', '.join(missing)}. {output[-1500:]}",
        }
    return {"status": "installed", "installed": missing}


def validate_playbook_syntax(playbook_yaml: str) -> dict[str, Any]:
    detection = detect_ansible()
    if not detection.get("available"):
        return {"status": "skipped", "passed": None, "message": detection.get("message") or "Ansible unavailable"}
    collection_setup = _ensure_managed_collections(detection, _required_managed_collections(playbook_yaml))
    if collection_setup.get("status") == "failed":
        return {
            "status": "failed",
            "passed": False,
            "message": collection_setup.get("message") or "Required Ansible collection setup failed",
            "method": detection.get("method"),
            "collection_setup": collection_setup,
        }
    with tempfile.TemporaryDirectory(prefix="webterm_ansible_syntax_") as temp_dir:
        workdir = Path(temp_dir)
        (workdir / "playbook.yml").write_text(playbook_yaml, encoding="utf-8")
        (workdir / "inventory.ini").write_text("localhost ansible_connection=local\n", encoding="utf-8")
        _build_ansible_cfg(workdir)
        method = str(detection.get("method") or "")
        env = os.environ.copy()
        env["ANSIBLE_CONFIG"] = str(workdir / "ansible.cfg")
        env["ANSIBLE_FORCE_COLOR"] = "0"
        env["ANSIBLE_NOCOLOR"] = "1"
        if method == "native":
            command = [detection["binary"], "--syntax-check", "-i", "inventory.ini", "playbook.yml"]
            cwd = str(workdir)
        elif method == "wsl":
            wsl_dir = _to_wsl_path(workdir)
            command = [
                "wsl",
                "-e",
                "bash",
                "-lc",
                f"cd {shlex_quote(wsl_dir)} && ANSIBLE_CONFIG=./ansible.cfg ansible-playbook "
                "--syntax-check -i inventory.ini playbook.yml",
            ]
            cwd = None
        elif method == "docker":
            image, ready = resolve_docker_ansible_image(str(detection.get("binary") or "docker"))
            if not ready:
                return {"status": "skipped", "passed": None, "message": f"Ansible image is not ready: {image}"}
            command = [
                str(detection.get("binary") or "docker"),
                "run",
                "--rm",
                "-v",
                f"{workdir.resolve()}:/ansible:ro",
                "-w",
                "/ansible",
                image,
                "--syntax-check",
                "-i",
                "inventory.ini",
                "playbook.yml",
            ]
            cwd = None
        else:
            return {"status": "skipped", "passed": None, "message": "Unsupported Ansible runtime"}
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=env if method == "native" else None,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except Exception as exc:
            return {"status": "failed", "passed": False, "message": str(exc)[:1000]}
        output = ((result.stdout or "") + ("\n" + result.stderr if result.stderr else "")).strip()
        return {
            "status": "passed" if result.returncode == 0 else "failed",
            "passed": result.returncode == 0,
            "message": output[-4000:] or f"ansible-playbook exited with {result.returncode}",
            "method": method,
            "collection_setup": collection_setup,
        }
