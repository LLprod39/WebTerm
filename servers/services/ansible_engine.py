"""Real Ansible execution engine for WebTerm playbooks.

Uses ansible-playbook via:
1) native binary on PATH
2) WSL (Windows)
3) Docker image (fallback)

Inventory and credentials are written to a temporary workdir and cleaned up after run.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

# ansible_engine.py is the public facade. Helpers live in sibling modules
# (split out to keep each under the architecture size limit) and are re-exported
# here; __all__ below pins the compatibility surface so lint autofix does not
# drop re-exports that this module does not call internally.
from servers.services.ansible_live_parser import AnsibleLiveParser, _stream_command
from servers.services.ansible_output import (
    _summarize_hosts,
    _to_wsl_path,
    parse_ansible_json_output,
    parse_play_recap,
    shlex_quote,
)
from servers.services.ansible_recipes import GUIDED_RECIPES, generate_from_recipe, list_guided_recipes
from servers.services.ansible_setup import (
    FALLBACK_ANSIBLE_IMAGE,
    LOCAL_ANSIBLE_IMAGE,
    _build_ansible_cfg,
    _write_inventory,
    detect_ansible,
    ensure_playbook_yaml,
    estimate_total_tasks,
    resolve_docker_ansible_image,
    tasks_to_ansible_yaml,
)

__all__ = [
    "AnsibleLiveParser",
    "FALLBACK_ANSIBLE_IMAGE",
    "GUIDED_RECIPES",
    "LOCAL_ANSIBLE_IMAGE",
    "detect_ansible",
    "ensure_playbook_yaml",
    "estimate_total_tasks",
    "generate_from_recipe",
    "list_guided_recipes",
    "parse_ansible_json_output",
    "parse_play_recap",
    "resolve_docker_ansible_image",
    "run_ansible_playbook",
    "shlex_quote",
    "tasks_to_ansible_yaml",
]

logger = logging.getLogger(__name__)

DOCKER_IMAGE = os.environ.get("WEBTERM_ANSIBLE_IMAGE", LOCAL_ANSIBLE_IMAGE)
ANSIBLE_TIMEOUT_SEC = int(os.environ.get("WEBTERM_ANSIBLE_TIMEOUT", "1800"))

# Do NOT use stdout_callback=json — it is NOT built into ansible-core and causes:
#   [ERROR]: Could not load 'json' callback plugin.
# We use the default callback + PLAY RECAP parsing (always available).


def run_ansible_playbook(
    *,
    playbook_yaml: str,
    servers: list[Any],
    dry_run: bool = False,
    become: bool = True,
    tags: str = "",
    limit: str = "",
    extra_vars: dict[str, Any] | None = None,
    master_password: str = "",
    forks: int = 5,
    cancel_check=None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    inventory_binding_groups: dict[str, list[int]] | None = None,
) -> dict[str, Any]:
    """Execute ansible-playbook and return structured host results.

    Returns:
      {
        ok: bool,
        method: str,
        raw_stdout: str,
        raw_stderr: str,
        exit_code: int,
        host_results: [...],
        summary: {...},
        inventory_preview: str,
        command: str,
        error: str,
      }
    """
    detection = detect_ansible()
    if not detection.get("available"):
        return {
            "ok": False,
            "method": "none",
            "raw_stdout": "",
            "raw_stderr": "",
            "exit_code": 127,
            "host_results": [],
            "summary": {},
            "inventory_preview": "",
            "command": "",
            "error": detection.get("message") or "Ansible is not available",
        }

    workdir = Path(tempfile.mkdtemp(prefix="webterm_ansible_"))
    try:
        pb_path = workdir / "playbook.yml"
        pb_path.write_text(playbook_yaml, encoding="utf-8")
        inv_path, _cleanup_keys = _write_inventory(
            workdir,
            servers,
            master_password=master_password,
            binding_groups=inventory_binding_groups,
        )
        _build_ansible_cfg(workdir)

        inv_preview = inv_path.read_text(encoding="utf-8")
        # Redact secrets in preview
        inv_preview_safe = re.sub(
            r"(ansible_ssh_pass|ansible_become_password|ansible_ssh_passphrase)=\S+",
            r"\1=***",
            inv_preview,
        )

        ansible_args = [
            "ansible-playbook",
            "-i",
            "inventory.ini",
            "playbook.yml",
            "-f",
            str(max(1, min(int(forks or 5), 25))),
        ]
        if dry_run:
            ansible_args.append("--check")
            ansible_args.append("--diff")
        if become:
            ansible_args.append("--become")
        if tags.strip():
            ansible_args.extend(["--tags", tags.strip()])
        if limit.strip():
            ansible_args.extend(["--limit", limit.strip()])
        if extra_vars:
            ev_path = workdir / "extra_vars.json"
            ev_path.write_text(json.dumps(extra_vars), encoding="utf-8")
            ansible_args.extend(["-e", f"@{ev_path.name}"])

        method = detection["method"]
        env = os.environ.copy()
        env["ANSIBLE_CONFIG"] = str(workdir / "ansible.cfg")
        env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
        # Never set ANSIBLE_STDOUT_CALLBACK=json (breaks ansible-core without ansible.posix)
        env.pop("ANSIBLE_STDOUT_CALLBACK", None)
        env["ANSIBLE_FORCE_COLOR"] = "0"
        env["ANSIBLE_NOCOLOR"] = "1"
        env["LC_ALL"] = "C.UTF-8"

        docker_image_used = ""
        if method == "native":
            cmd = [detection["binary"], *ansible_args[1:]]  # binary already ansible-playbook
            cwd = str(workdir)
        elif method == "wsl":
            wsl_dir = _to_wsl_path(workdir)
            cmd = [
                "wsl",
                "-e",
                "bash",
                "-lc",
                f"cd {shlex_quote(wsl_dir)} && ANSIBLE_HOST_KEY_CHECKING=False ANSIBLE_FORCE_COLOR=0 "
                f"ANSIBLE_CONFIG=./ansible.cfg " + " ".join(shlex_quote(a) for a in ansible_args),
            ]
            cwd = None
        else:  # docker ad-hoc (no long-running agent)
            docker = detection["binary"]
            image, ready = resolve_docker_ansible_image(docker)
            docker_image_used = image
            if not ready:
                # Try pull only for non-local tags; for webterm-ansible ask to build
                if image.startswith("webterm-ansible"):
                    return {
                        "ok": False,
                        "method": "docker",
                        "raw_stdout": "",
                        "raw_stderr": "",
                        "exit_code": 127,
                        "host_results": [],
                        "summary": {},
                        "inventory_preview": inv_preview_safe,
                        "command": f"docker build -t {LOCAL_ANSIBLE_IMAGE} -f docker/ansible-runner/Dockerfile .",
                        "error": (
                            f"Ansible runner image '{image}' not found. Build once:\n"
                            f"  docker build -t {LOCAL_ANSIBLE_IMAGE} -f docker/ansible-runner/Dockerfile .\n"
                            "Or: docker compose --profile ansible build ansible-runner"
                        ),
                    }
                pull = subprocess.run(
                    [docker, "pull", image],
                    capture_output=True,
                    text=True,
                    timeout=600,
                    check=False,
                )
                if pull.returncode != 0:
                    return {
                        "ok": False,
                        "method": "docker",
                        "raw_stdout": pull.stdout or "",
                        "raw_stderr": pull.stderr or "",
                        "exit_code": pull.returncode,
                        "host_results": [],
                        "summary": {},
                        "inventory_preview": inv_preview_safe,
                        "command": f"docker pull {image}",
                        "error": f"Failed to pull Ansible image {image}",
                    }

            workdir_mount = str(workdir.resolve())
            cmd = [docker, "run", "--rm"]
            # host network: Linux only (Docker Desktop on Windows/macOS does not support it well)
            use_host_net = os.environ.get("WEBTERM_ANSIBLE_DOCKER_HOST_NETWORK", "").lower() in (
                "1",
                "true",
                "yes",
            )
            if use_host_net or (os.name == "posix" and not os.environ.get("WEBTERM_ANSIBLE_DOCKER_BRIDGE")):
                try:
                    release = os.uname().release.lower() if hasattr(os, "uname") else ""
                except Exception:
                    release = ""
                if os.name == "posix" and (use_host_net or ("microsoft" not in release and "wsl" not in release)):
                    cmd.extend(["--network", "host"])
            cmd.extend(
                [
                    "-v",
                    f"{workdir_mount}:/ansible:rw",
                    "-w",
                    "/ansible",
                    "-e",
                    "ANSIBLE_HOST_KEY_CHECKING=False",
                    "-e",
                    "ANSIBLE_FORCE_COLOR=0",
                    "-e",
                    "ANSIBLE_NOCOLOR=1",
                    "-e",
                    "ANSIBLE_CONFIG=/ansible/ansible.cfg",
                    image,
                    *ansible_args,
                ]
            )
            cwd = None

        if cancel_check and cancel_check():
            return {
                "ok": False,
                "method": method,
                "raw_stdout": "",
                "raw_stderr": "Cancelled before start",
                "exit_code": 130,
                "host_results": [],
                "summary": {},
                "inventory_preview": inv_preview_safe,
                "command": " ".join(cmd) if isinstance(cmd, list) else str(cmd),
                "error": "Cancelled",
            }

        live_parser = AnsibleLiveParser(servers, tasks_total=estimate_total_tasks(playbook_yaml))

        def _on_line(line: str) -> None:
            live_parser.feed(line)
            if progress_callback:
                progress_callback(
                    {
                        "line": line,
                        "progress": live_parser.snapshot(),
                        "host_results": live_parser.build_host_results(),
                    }
                )

        exit_code, combined, cancelled, timed_out = _stream_command(
            cmd,
            cwd=cwd,
            env=env if method == "native" else None,
            timeout=ANSIBLE_TIMEOUT_SEC,
            cancel_check=cancel_check,
            on_line=_on_line,
        )
        stdout = combined
        stderr = ""

        if cancelled or timed_out:
            host_results = live_parser.build_host_results(final=True) if live_parser.has_events else []
            return {
                "ok": False,
                "method": method,
                "raw_stdout": combined[:200_000],
                "raw_stderr": "",
                "exit_code": exit_code,
                "host_results": host_results,
                "summary": _summarize_hosts(host_results),
                "inventory_preview": inv_preview_safe,
                "command": " ".join(cmd),
                "cancelled": cancelled,
                "error": "Cancelled" if cancelled else f"Ansible timed out after {ANSIBLE_TIMEOUT_SEC}s",
            }

        # Prefer the live parser (per-task detail); then JSON callback; then PLAY RECAP
        host_results = live_parser.build_host_results(final=True) if live_parser.has_events else []
        if not host_results:
            host_results = parse_ansible_json_output(stdout, servers=servers)
        if not host_results:
            host_results = parse_play_recap(combined, servers=servers)
        if not host_results:
            host_results = [
                {
                    "server_id": getattr(s, "id", 0),
                    "server_name": getattr(s, "name", str(s)),
                    "host": getattr(s, "host", ""),
                    "status": "error" if exit_code != 0 else "success",
                    "task_results": [
                        {
                            "task_id": "ansible_log",
                            "command": "ansible-playbook",
                            "description": "Ansible full log",
                            "status": "error" if exit_code != 0 else "success",
                            "output": combined[:50_000],
                            "exit_code": exit_code,
                        }
                    ],
                }
                for s in servers
            ]
        else:
            # Attach truncated log to each host for debugging
            for hr in host_results:
                if not any(t.get("output") for t in (hr.get("task_results") or [])):
                    hr.setdefault("task_results", []).append(
                        {
                            "task_id": "ansible_log",
                            "command": "ansible-playbook",
                            "description": "Ansible log",
                            "status": hr.get("status") or "success",
                            "output": combined[:20_000],
                            "exit_code": exit_code,
                        }
                    )

        # Surface the classic json-callback error clearly if it somehow reappears
        if "Could not load 'json' callback" in combined or 'Could not load "json" callback' in combined:
            return {
                "ok": False,
                "method": method,
                "raw_stdout": stdout[:50_000],
                "raw_stderr": stderr[:50_000],
                "exit_code": exit_code or 2,
                "host_results": host_results,
                "summary": _summarize_hosts(host_results),
                "inventory_preview": inv_preview_safe,
                "command": " ".join(cmd) if isinstance(cmd[0], str) else str(cmd),
                "error": (
                    "Ansible json callback is not available (fixed in WebTerm: use default callback). "
                    "Rebuild/restart backend and re-run. "
                    f"If using Docker, build: docker build -t {LOCAL_ANSIBLE_IMAGE} -f docker/ansible-runner/Dockerfile ."
                ),
            }

        summary = _summarize_hosts(host_results)
        summary["engine"] = "ansible"
        summary["ansible_method"] = method
        if docker_image_used:
            summary["ansible_image"] = docker_image_used
        ok = exit_code == 0 and summary.get("hosts_failed", 0) == 0
        err_line = ""
        if not ok:
            for line in reversed(combined.splitlines()):
                if line.strip():
                    err_line = line.strip()
                    break
        return {
            "ok": ok,
            "method": method,
            "raw_stdout": stdout[:200_000],
            "raw_stderr": stderr[:50_000],
            "exit_code": exit_code,
            "host_results": host_results,
            "summary": summary,
            "inventory_preview": inv_preview_safe,
            "command": " ".join(cmd) if isinstance(cmd[0], str) else str(cmd),
            "error": "" if ok else (err_line or f"exit {exit_code}"),
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "method": detection.get("method") or "unknown",
            "raw_stdout": "",
            "raw_stderr": "Ansible timed out",
            "exit_code": 124,
            "host_results": [],
            "summary": {},
            "inventory_preview": "",
            "command": "",
            "error": f"Ansible timed out after {ANSIBLE_TIMEOUT_SEC}s",
        }
    except Exception as exc:
        logger.exception("Ansible execution failed")
        return {
            "ok": False,
            "method": detection.get("method") or "unknown",
            "raw_stdout": "",
            "raw_stderr": str(exc),
            "exit_code": 1,
            "host_results": [],
            "summary": {},
            "inventory_preview": "",
            "command": "",
            "error": str(exc),
        }
    finally:
        with contextlib.suppress(Exception):
            shutil.rmtree(workdir, ignore_errors=True)


# Guided recipes live in ansible_recipes.py; re-exported for compatibility.
