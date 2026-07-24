"""Non-executing Ansible syntax validation for compatibility revisions."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from servers.services.ansible_docker_runtime import (
    AnsibleIsolationError,
    build_isolated_docker_command,
    create_ansible_workdir,
)
from servers.services.ansible_output import _to_wsl_path, shlex_quote
from servers.services.ansible_project import materialize_ansible_project
from servers.services.ansible_setup import _build_ansible_cfg, detect_ansible, resolve_docker_ansible_image
from servers.services.ansible_validator_client import (
    AnsibleValidatorError,
    validate_with_isolated_service,
    validator_socket_path,
)

_AUTO_INSTALL_COLLECTIONS = {"ansible.posix", "community.general"}


def build_execution_readiness(
    report: dict[str, Any] | None,
    *,
    syntax_check: dict[str, Any] | None,
    targets_count: int,
    requires_runtime: bool = True,
    requires_bindings: bool = True,
) -> dict[str, dict[str, Any]]:
    """Classify execution gates without conflating static and runtime checks."""

    report = report if isinstance(report, dict) else {}
    issues = report.get("issues") if isinstance(report.get("issues"), list) else []
    static_ready = not any(item.get("severity") == "error" for item in issues if isinstance(item, dict))
    missing_bindings = report.get("missing_bindings") or []
    bindings_ready = not requires_bindings or not missing_bindings
    targets_ready = int(targets_count or 0) > 0

    if not requires_runtime:
        runtime_status = "not_required"
        runtime_ready = True
    elif syntax_check is None:
        runtime_status = "not_checked"
        runtime_ready = False
    elif syntax_check.get("passed") is True:
        runtime_status = "passed"
        runtime_ready = True
    elif syntax_check.get("passed") is False:
        runtime_status = "failed"
        runtime_ready = False
    else:
        runtime_status = str(syntax_check.get("status") or "skipped")
        runtime_ready = False

    execution_ready = static_ready and bindings_ready and runtime_ready and targets_ready
    return {
        "static": {"status": "passed" if static_ready else "failed", "ready": static_ready},
        "runtime": {"status": runtime_status, "ready": runtime_ready},
        "bindings": {
            "status": "not_required" if not requires_bindings else ("complete" if bindings_ready else "missing"),
            "ready": bindings_ready,
            "missing": list(missing_bindings),
        },
        "targets": {"status": "ready" if targets_ready else "missing", "ready": targets_ready},
        "execution": {"status": "ready" if execution_ready else "blocked", "ready": execution_ready},
    }


def enforce_runtime_digest_match(
    syntax_check: dict[str, Any],
    fingerprint: dict[str, Any],
    *,
    message: str,
) -> tuple[dict[str, Any], bool]:
    expected = str(fingerprint.get("runtime_digest") or "")
    mismatch = fingerprint.get("method") == "isolated-validator" and (
        not expected or syntax_check.get("runtime_digest") != expected
    )
    if not mismatch:
        return syntax_check, False
    return {**syntax_check, "status": "failed", "passed": False, "message": message}, True


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


def validate_playbook_syntax(
    playbook_yaml: str,
    *,
    allow_dependency_setup: bool = True,
    project_files: Mapping[str, bytes] | None = None,
    project_entrypoint: str = "playbook.yml",
) -> dict[str, Any]:
    if validator_socket_path():
        try:
            return validate_with_isolated_service(
                playbook_yaml,
                project_files=project_files,
                project_entrypoint=project_entrypoint,
            )
        except AnsibleValidatorError as exc:
            return {"status": "failed", "passed": False, "message": str(exc), "method": "isolated-validator"}
    detection = detect_ansible()
    if not detection.get("available"):
        return {"status": "skipped", "passed": None, "message": detection.get("message") or "Ansible unavailable"}
    required_collections = _required_managed_collections(playbook_yaml)
    collection_setup = (
        _ensure_managed_collections(detection, required_collections)
        if allow_dependency_setup
        else {
            "status": "not_modified",
            "installed": [],
            "required": required_collections,
            "message": "Validation does not install dependencies",
        }
    )
    if collection_setup.get("status") == "failed":
        return {
            "status": "failed",
            "passed": False,
            "message": collection_setup.get("message") or "Required Ansible collection setup failed",
            "method": detection.get("method"),
            "collection_setup": collection_setup,
        }
    workdir = create_ansible_workdir()
    try:
        try:
            entrypoint = materialize_ansible_project(
                workdir,
                playbook_yaml=playbook_yaml,
                project_files=project_files,
                entrypoint=project_entrypoint,
            )
        except ValueError as exc:
            return {"status": "failed", "passed": False, "message": str(exc)[:1000]}
        (workdir / "inventory.ini").write_text("localhost ansible_connection=local\n", encoding="utf-8")
        _build_ansible_cfg(workdir)
        method = str(detection.get("method") or "")
        env = os.environ.copy()
        env["ANSIBLE_CONFIG"] = str(workdir / "ansible.cfg")
        env["ANSIBLE_FORCE_COLOR"] = "0"
        env["ANSIBLE_NOCOLOR"] = "1"
        if method == "native":
            command = [detection["binary"], "--syntax-check", "-i", "inventory.ini", entrypoint]
            cwd = str(workdir)
        elif method == "wsl":
            wsl_dir = _to_wsl_path(workdir)
            command = [
                "wsl",
                "-e",
                "bash",
                "-lc",
                f"cd {shlex_quote(wsl_dir)} && ANSIBLE_CONFIG=./ansible.cfg ansible-playbook "
                f"--syntax-check -i inventory.ini {shlex_quote(entrypoint)}",
            ]
            cwd = None
        elif method == "docker":
            image, ready = resolve_docker_ansible_image(str(detection.get("binary") or "docker"))
            if not ready:
                return {"status": "skipped", "passed": None, "message": f"Ansible image is not ready: {image}"}
            try:
                command = build_isolated_docker_command(
                    docker=str(detection.get("binary") or "docker"),
                    image=image,
                    workdir=workdir,
                    ansible_args=["ansible-playbook", "--syntax-check", "-i", "inventory.ini", entrypoint],
                )
            except AnsibleIsolationError as exc:
                return {"status": "failed", "passed": False, "message": str(exc)}
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
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
