"""Real Ansible execution engine for WebTerm playbooks.

Uses ansible-playbook via:
1) native binary on PATH
2) WSL (Windows)
3) Docker image (fallback)

Inventory and credentials are written to a temporary workdir and cleaned up after run.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

from servers.secret_utils import get_server_auth_secret, get_server_sudo_secret

logger = logging.getLogger(__name__)

# Prefer project image (built via docker/ansible-runner). Override with WEBTERM_ANSIBLE_IMAGE.
LOCAL_ANSIBLE_IMAGE = os.environ.get("WEBTERM_ANSIBLE_IMAGE_LOCAL", "webterm-ansible:latest")
FALLBACK_ANSIBLE_IMAGE = os.environ.get("WEBTERM_ANSIBLE_IMAGE_FALLBACK", "cytopia/ansible:latest-tools")
DOCKER_IMAGE = os.environ.get("WEBTERM_ANSIBLE_IMAGE", LOCAL_ANSIBLE_IMAGE)
ANSIBLE_TIMEOUT_SEC = int(os.environ.get("WEBTERM_ANSIBLE_TIMEOUT", "1800"))

# Do NOT use stdout_callback=json — it is NOT built into ansible-core and causes:
#   [ERROR]: Could not load 'json' callback plugin.
# We use the default callback + PLAY RECAP parsing (always available).


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
    native = shutil.which("ansible-playbook")
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
            try:
                os.chmod(key_dest, 0o600)
            except OSError:
                pass
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
                parts.append("ansible_ssh_common_args='-o PreferredAuthentications=password -o PubkeyAuthentication=no'")

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


_STATUS_SEVERITY = {"pending": 0, "skipped": 1, "success": 2, "changed": 2, "error": 3}


class AnsibleLiveParser:
    """Incremental parser for the default Ansible stdout callback.

    Feed lines as they stream from ansible-playbook; exposes a progress
    snapshot (current play/task, counters) and per-host task results that can
    be persisted while the run is still active.
    """

    _RE_PLAY = re.compile(r"^PLAY \[(?P<name>.*)\] \*+\s*$")
    _RE_TASK = re.compile(r"^(?:TASK|RUNNING HANDLER) \[(?P<name>.*)\] \*+\s*$")
    _RE_RESULT = re.compile(
        r"^(?P<verb>ok|changed|failed|fatal|skipping|unreachable): \[(?P<host>[^\]\s]+)\](?P<rest>.*)$"
    )
    _RE_RECAP_HOST = re.compile(
        r"^(?P<host>\S+)\s*:\s*ok=(?P<ok>\d+)\s+changed=(?P<changed>\d+)\s+"
        r"unreachable=(?P<unreach>\d+)\s+failed=(?P<failed>\d+)"
    )

    def __init__(self, servers: list[Any], *, tasks_total: int = 0):
        self._servers = servers
        self._by_alias = {_safe_host_name(getattr(s, "name", ""), int(s.id)): s for s in servers}
        self._by_host = {str(getattr(s, "host", "")): s for s in servers}
        self.tasks_total = int(tasks_total or 0)
        self.current_play = ""
        self.current_task = ""
        self.task_seq = 0
        self.play_count = 0
        self.counts = {"ok": 0, "changed": 0, "failed": 0, "skipped": 0, "unreachable": 0}
        self.in_recap = False
        self.recap: dict[str, dict[str, int]] = {}
        # host_key -> {"tasks": [{"seq", "name", "status", "note"}]}
        self._hosts: dict[str, dict[str, Any]] = {}

    def feed(self, raw_line: str) -> None:
        line = (raw_line or "").rstrip()
        if not line:
            return
        m = self._RE_PLAY.match(line)
        if m:
            self.current_play = m.group("name")
            self.play_count += 1
            self.in_recap = False
            return
        if line.startswith("PLAY RECAP"):
            self.in_recap = True
            return
        m = self._RE_TASK.match(line)
        if m:
            self.current_task = m.group("name")
            self.task_seq += 1
            self.in_recap = False
            return
        if self.in_recap:
            m = self._RE_RECAP_HOST.match(line)
            if m:
                self.recap[m.group("host")] = {
                    "ok": int(m.group("ok")),
                    "changed": int(m.group("changed")),
                    "unreachable": int(m.group("unreach")),
                    "failed": int(m.group("failed")),
                }
            return
        m = self._RE_RESULT.match(line)
        if not m:
            return
        verb = m.group("verb")
        host_key = m.group("host")
        rest = m.group("rest") or ""
        unreachable = verb == "unreachable" or (verb == "fatal" and "UNREACHABLE" in rest.upper())
        if verb in ("ok",):
            status = "success"
        elif verb == "changed":
            status = "success"
            self.counts["changed"] += 1
        elif verb == "skipping":
            status = "skipped"
        else:  # failed / fatal / unreachable
            status = "error"
        if status == "success":
            self.counts["ok"] += 1
        elif status == "skipped":
            self.counts["skipped"] += 1
        elif unreachable:
            self.counts["unreachable"] += 1
        else:
            self.counts["failed"] += 1

        note = ""
        if status == "error":
            note = rest.lstrip(" :=>").strip()[:4000]
        state = self._hosts.setdefault(host_key, {"tasks": []})
        tasks: list[dict[str, Any]] = state["tasks"]
        # Item results (`=> (item=...)`) repeat per task+host — merge by task_seq keeping the worst status
        if tasks and tasks[-1]["seq"] == self.task_seq:
            entry = tasks[-1]
            if _STATUS_SEVERITY.get(status, 0) > _STATUS_SEVERITY.get(entry["status"], 0):
                entry["status"] = status
                if note:
                    entry["note"] = note
        else:
            tasks.append(
                {
                    "seq": self.task_seq,
                    "name": self.current_task or f"Task {self.task_seq}",
                    "status": status,
                    "note": note,
                }
            )

    def snapshot(self) -> dict[str, Any]:
        return {
            "engine": "ansible",
            "play": self.current_play,
            "plays": self.play_count,
            "task": self.current_task,
            "task_number": self.task_seq,
            "tasks_total": self.tasks_total or None,
            "counts": dict(self.counts),
            "hosts_seen": len(self._hosts),
            "hosts_total": len(self._servers),
            "recap_seen": bool(self.recap),
        }

    def build_host_results(self, *, final: bool = False) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen_ids: set[int] = set()
        for host_key, state in self._hosts.items():
            server = self._by_alias.get(host_key) or self._by_host.get(host_key)
            sid = int(server.id) if server is not None else 0
            if sid:
                seen_ids.add(sid)
            task_results = [
                {
                    "task_id": f"{host_key}_{t['seq']}",
                    "command": t["name"],
                    "description": t["name"],
                    "status": t["status"],
                    "output": t.get("note") or "",
                    "exit_code": 1 if t["status"] == "error" else 0,
                }
                for t in state["tasks"]
            ]
            recap = self.recap.get(host_key)
            has_error = any(t["status"] == "error" for t in state["tasks"])
            has_success = any(t["status"] == "success" for t in state["tasks"])
            if recap:
                if recap["failed"] or recap["unreachable"]:
                    status = "partial" if (recap["ok"] and not recap["unreachable"]) else "error"
                elif recap["ok"] or recap["changed"]:
                    status = "success"
                else:
                    status = "skipped"
            elif final:
                status = "partial" if (has_error and has_success) else ("error" if has_error else "success")
            else:
                status = "error" if has_error else "running"
            results.append(
                {
                    "server_id": sid,
                    "server_name": getattr(server, "name", host_key) if server else host_key,
                    "host": getattr(server, "host", host_key) if server else host_key,
                    "status": status,
                    "task_results": task_results,
                }
            )
        for s in self._servers:
            if int(s.id) not in seen_ids:
                results.append(
                    {
                        "server_id": int(s.id),
                        "server_name": s.name,
                        "host": s.host,
                        "status": "skipped" if final else "pending",
                        "task_results": [],
                    }
                )
        return results

    @property
    def has_events(self) -> bool:
        return any(state["tasks"] for state in self._hosts.values())


def _terminate_process(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _stream_command(
    cmd: list[str],
    *,
    cwd: str | None,
    env: dict[str, str] | None,
    timeout: int,
    cancel_check: Callable[[], bool] | None = None,
    on_line: Callable[[str], None] | None = None,
) -> tuple[int, str, bool, bool]:
    """Run a command streaming merged stdout/stderr line by line.

    Returns (exit_code, combined_output, cancelled, timed_out). Unlike
    subprocess.run this checks cancel_check while the process runs and kills
    the process on cancel or timeout.
    """
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    lines_q: queue.Queue[str | None] = queue.Queue()

    def _reader() -> None:
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                lines_q.put(line)
        except Exception:
            pass
        finally:
            lines_q.put(None)

    threading.Thread(target=_reader, name="ansible-stream-reader", daemon=True).start()

    lines: list[str] = []
    cancelled = False
    timed_out = False
    killed = False
    deadline = time.monotonic() + max(30, int(timeout))
    last_cancel_probe = 0.0

    while True:
        try:
            item = lines_q.get(timeout=0.5)
        except queue.Empty:
            item = ""
        if item is None:
            break
        if item:
            line = item.rstrip("\r\n")
            lines.append(line)
            if on_line:
                try:
                    on_line(line)
                except Exception:
                    logger.debug("ansible on_line callback failed", exc_info=True)
        if killed:
            continue
        now = time.monotonic()
        if cancel_check and now - last_cancel_probe >= 1.0:
            last_cancel_probe = now
            try:
                if cancel_check():
                    cancelled = True
            except Exception:
                pass
        if cancelled or now > deadline:
            timed_out = not cancelled and now > deadline
            killed = True
            _terminate_process(proc)

    try:
        exit_code = proc.wait(timeout=30)
    except Exception:
        exit_code = 1
    if cancelled:
        exit_code = 130
    elif timed_out:
        exit_code = 124
    return exit_code, "\n".join(lines), cancelled, timed_out


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
        inv_path, _cleanup_keys = _write_inventory(workdir, servers, master_password=master_password)
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
                f"ANSIBLE_CONFIG=./ansible.cfg "
                + " ".join(shlex_quote(a) for a in ansible_args),
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
                if use_host_net or ("microsoft" not in release and "wsl" not in release):
                    if os.name == "posix":
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
        if "Could not load 'json' callback" in combined or "Could not load \"json\" callback" in combined:
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
        try:
            shutil.rmtree(workdir, ignore_errors=True)
        except Exception:
            pass


def shlex_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _to_wsl_path(path: Path) -> str:
    resolved = str(path.resolve())
    # C:\foo\bar -> /mnt/c/foo/bar
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", resolved)
    if not m:
        return resolved.replace("\\", "/")
    drive = m.group(1).lower()
    rest = m.group(2).replace("\\", "/")
    return f"/mnt/{drive}/{rest}"


def parse_play_recap(text: str, *, servers: list[Any]) -> list[dict[str, Any]]:
    """Parse classic Ansible PLAY RECAP into host_results.

    Example line:
      app-01  : ok=3    changed=1    unreachable=0    failed=0    skipped=0
    """
    if not text:
        return []
    recap_idx = text.upper().rfind("PLAY RECAP")
    if recap_idx < 0:
        return []
    section = text[recap_idx:]
    pattern = re.compile(
        r"^(?P<host>\S+)\s*:\s*"
        r"ok=(?P<ok>\d+)\s+"
        r"changed=(?P<changed>\d+)\s+"
        r"unreachable=(?P<unreach>\d+)\s+"
        r"failed=(?P<failed>\d+)",
        re.MULTILINE,
    )
    by_alias = {_safe_host_name(s.name, s.id): s for s in servers}
    by_host = {str(s.host): s for s in servers}
    results: list[dict[str, Any]] = []
    found: set[int] = set()

    for match in pattern.finditer(section):
        host_key = match.group("host")
        if host_key.lower() in ("play", "recap"):
            continue
        ok_n = int(match.group("ok"))
        failed_n = int(match.group("failed"))
        unreach_n = int(match.group("unreach"))
        changed_n = int(match.group("changed"))
        if unreach_n or failed_n:
            status = "error"
        elif ok_n or changed_n:
            status = "success"
        else:
            status = "skipped"
        server = by_alias.get(host_key) or by_host.get(host_key)
        sid = int(server.id) if server is not None else 0
        if sid:
            found.add(sid)
        output = (
            f"PLAY RECAP {host_key}: ok={ok_n} changed={changed_n} "
            f"unreachable={unreach_n} failed={failed_n}"
        )
        results.append(
            {
                "server_id": sid,
                "server_name": getattr(server, "name", host_key) if server else host_key,
                "host": getattr(server, "host", host_key) if server else host_key,
                "status": status,
                "task_results": [
                    {
                        "task_id": f"recap_{host_key}",
                        "command": "ansible-playbook",
                        "description": "PLAY RECAP",
                        "status": "error" if status == "error" else "success",
                        "output": output,
                        "exit_code": 1 if status == "error" else 0,
                    }
                ],
            }
        )

    # Include full log on first result for context
    if results:
        log_snip = text[-12_000:]
        results[0]["task_results"].append(
            {
                "task_id": "ansible_full_log",
                "command": "ansible-playbook",
                "description": "Ansible log (tail)",
                "status": results[0]["status"] if results[0]["status"] != "partial" else "success",
                "output": log_snip,
                "exit_code": None,
            }
        )

    for s in servers:
        if s.id not in found:
            results.append(
                {
                    "server_id": s.id,
                    "server_name": s.name,
                    "host": s.host,
                    "status": "skipped",
                    "task_results": [
                        {
                            "task_id": f"missing_{s.id}",
                            "command": "ansible",
                            "description": "Not in PLAY RECAP",
                            "status": "skipped",
                            "output": "Host did not appear in PLAY RECAP",
                            "exit_code": None,
                        }
                    ],
                }
            )
    return results


def parse_ansible_json_output(stdout: str, *, servers: list[Any]) -> list[dict[str, Any]]:
    """Parse ansible json callback stdout into WebTerm host_results."""
    text = (stdout or "").strip()
    if not text:
        return []

    # Callback may print non-json noise; find last JSON object
    data = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON blob
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                data = None
    if not isinstance(data, dict):
        return []

    plays = data.get("plays") or []
    # Map inventory hostname -> server
    by_alias: dict[str, Any] = {}
    by_host: dict[str, Any] = {}
    for s in servers:
        by_alias[_safe_host_name(s.name, s.id)] = s
        by_host[str(s.host)] = s

    # Collect per-host tasks
    host_tasks: dict[str, list[dict[str, Any]]] = {}
    host_status: dict[str, str] = {}

    for play in plays:
        for task in play.get("tasks") or []:
            task_name = ""
            if isinstance(task.get("task"), dict):
                task_name = str(task["task"].get("name") or "")
            hosts_map = task.get("hosts") or {}
            if not isinstance(hosts_map, dict):
                continue
            for host_key, result in hosts_map.items():
                if not isinstance(result, dict):
                    continue
                tr_status = "success"
                if result.get("failed") or result.get("unreachable"):
                    tr_status = "error"
                    host_status[host_key] = "error"
                elif result.get("skipped"):
                    tr_status = "skipped"
                else:
                    host_status.setdefault(host_key, "success")

                stdout_bits = []
                for key in ("stdout", "stderr", "msg", "reason"):
                    val = result.get(key)
                    if val:
                        stdout_bits.append(str(val))
                if result.get("diff"):
                    stdout_bits.append(json.dumps(result.get("diff"), ensure_ascii=False)[:4000])
                output = "\n".join(stdout_bits).strip()
                rc = result.get("rc")
                if rc is None:
                    rc = 1 if tr_status == "error" else 0

                host_tasks.setdefault(host_key, []).append(
                    {
                        "task_id": f"{host_key}_{len(host_tasks.get(host_key, []))}",
                        "command": task_name or "ansible task",
                        "description": task_name,
                        "status": tr_status,
                        "output": output[:50_000],
                        "exit_code": rc,
                    }
                )

    # stats section
    stats = data.get("stats") or {}
    if isinstance(stats, dict):
        for host_key, st in stats.items():
            if not isinstance(st, dict):
                continue
            if st.get("unreachable") or st.get("failures"):
                host_status[host_key] = "error"
            elif host_key not in host_status:
                host_status[host_key] = "success"

    results: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for host_key, tasks in host_tasks.items():
        server = by_alias.get(host_key) or by_host.get(host_key)
        sid = int(server.id) if server is not None else 0
        if sid:
            seen_ids.add(sid)
        status = host_status.get(host_key, "success")
        if any(t["status"] == "error" for t in tasks) and any(t["status"] == "success" for t in tasks):
            status = "partial"
        elif any(t["status"] == "error" for t in tasks):
            status = "error"
        results.append(
            {
                "server_id": sid,
                "server_name": getattr(server, "name", host_key) if server else host_key,
                "host": getattr(server, "host", host_key) if server else host_key,
                "status": status,
                "task_results": tasks,
            }
        )

    # Ensure all target servers appear
    for s in servers:
        if s.id not in seen_ids:
            results.append(
                {
                    "server_id": s.id,
                    "server_name": s.name,
                    "host": s.host,
                    "status": "skipped",
                    "task_results": [
                        {
                            "task_id": f"missing_{s.id}",
                            "command": "ansible",
                            "description": "No task results for host",
                            "status": "skipped",
                            "output": "Host did not appear in Ansible JSON output",
                            "exit_code": None,
                        }
                    ],
                }
            )

    return results


def _summarize_hosts(host_results: list[dict[str, Any]]) -> dict[str, Any]:
    hosts_total = len(host_results)
    hosts_ok = sum(1 for h in host_results if h.get("status") == "success")
    hosts_failed = sum(1 for h in host_results if h.get("status") in ("error", "failed"))
    hosts_partial = sum(1 for h in host_results if h.get("status") == "partial")
    tasks_ok = tasks_failed = tasks_skipped = 0
    for h in host_results:
        for t in h.get("task_results") or []:
            if t.get("status") == "success":
                tasks_ok += 1
            elif t.get("status") == "error":
                tasks_failed += 1
            elif t.get("status") == "skipped":
                tasks_skipped += 1
    return {
        "hosts_total": hosts_total,
        "hosts_ok": hosts_ok,
        "hosts_failed": hosts_failed,
        "hosts_partial": hosts_partial,
        "tasks_ok": tasks_ok,
        "tasks_failed": tasks_failed,
        "tasks_skipped": tasks_skipped,
        "engine": "ansible",
    }


# --- Guided recipes for non-experts ---

GUIDED_RECIPES: list[dict[str, Any]] = [
    {
        "slug": "install-package",
        "name": "Install package",
        "description": "Установить пакет (apt/yum/dnf) на Linux-серверах",
        "category": "patch",
        "icon": "package",
        "fields": [
            {"key": "package", "label": "Package name", "placeholder": "nginx", "required": True},
            {
                "key": "state",
                "label": "State",
                "type": "select",
                "options": ["present", "latest", "absent"],
                "default": "present",
            },
        ],
    },
    {
        "slug": "manage-service",
        "name": "Manage service",
        "description": "Start / stop / restart / reload systemd-сервиса",
        "category": "deploy",
        "icon": "service",
        "fields": [
            {"key": "service", "label": "Service name", "placeholder": "nginx", "required": True},
            {
                "key": "state",
                "label": "State",
                "type": "select",
                "options": ["started", "stopped", "restarted", "reloaded"],
                "default": "restarted",
            },
            {"key": "enabled", "label": "Enable on boot", "type": "checkbox", "default": True},
        ],
    },
    {
        "slug": "run-commands",
        "name": "Run commands",
        "description": "Выполнить 1–5 shell-команд через Ansible shell module",
        "category": "custom",
        "icon": "terminal",
        "fields": [
            {
                "key": "commands",
                "label": "Commands (one per line)",
                "type": "textarea",
                "placeholder": "uptime\ndf -h\nfree -h",
                "required": True,
            },
        ],
    },
    {
        "slug": "update-system",
        "name": "Update packages",
        "description": "apt update/upgrade или yum/dnf update",
        "category": "patch",
        "icon": "update",
        "fields": [
            {
                "key": "family",
                "label": "Package manager",
                "type": "select",
                "options": ["auto", "apt", "dnf", "yum"],
                "default": "auto",
            },
        ],
    },
    {
        "slug": "health-check",
        "name": "Health check",
        "description": "Собрать uptime, disk, memory, failed units (read-only)",
        "category": "diagnose",
        "icon": "heart",
        "fields": [],
    },
    {
        "slug": "docker-prune",
        "name": "Docker cleanup",
        "description": "Безопасный docker prune без volumes",
        "category": "maintenance",
        "icon": "docker",
        "fields": [],
    },
]


def list_guided_recipes() -> list[dict[str, Any]]:
    return [
        {
            "slug": r["slug"],
            "name": r["name"],
            "description": r["description"],
            "category": r["category"],
            "icon": r.get("icon") or "play",
            "fields": r.get("fields") or [],
        }
        for r in GUIDED_RECIPES
    ]


def generate_from_recipe(slug: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Generate real Ansible YAML + task list from a guided recipe."""
    params = params or {}
    recipe = next((r for r in GUIDED_RECIPES if r["slug"] == slug), None)
    if not recipe:
        raise ValueError(f"Unknown recipe: {slug}")

    name = recipe["name"]
    category = recipe["category"]
    yaml = ""
    tasks: list[dict[str, Any]] = []

    if slug == "install-package":
        pkg = str(params.get("package") or "").strip()
        if not pkg:
            raise ValueError("Package name is required")
        state = str(params.get("state") or "present")
        name = f"Install {pkg}"
        yaml = f"""- name: {name}
  hosts: all
  become: true
  gather_facts: true
  tasks:
    - name: Install package via apt
      ansible.builtin.apt:
        name: {pkg}
        state: {state}
        update_cache: true
      when: ansible_os_family == "Debian"
    - name: Install package via dnf
      ansible.builtin.dnf:
        name: {pkg}
        state: {state}
      when: ansible_os_family == "RedHat" and ansible_pkg_mgr == "dnf"
    - name: Install package via yum
      ansible.builtin.yum:
        name: {pkg}
        state: {state}
      when: ansible_os_family == "RedHat" and ansible_pkg_mgr != "dnf"
"""
        tasks = [
            {"id": "t1", "command": f"# ansible apt/dnf/yum name={pkg} state={state}", "description": f"Install {pkg}", "continue_on_error": False}
        ]

    elif slug == "manage-service":
        svc = str(params.get("service") or "").strip()
        if not svc:
            raise ValueError("Service name is required")
        state = str(params.get("state") or "restarted")
        enabled = bool(params.get("enabled", True))
        name = f"Service {svc} → {state}"
        yaml = f"""- name: {name}
  hosts: all
  become: true
  gather_facts: false
  tasks:
    - name: Manage systemd service
      ansible.builtin.systemd:
        name: {svc}
        state: {state}
        enabled: {str(enabled).lower()}
        daemon_reload: false
"""
        systemctl_action = {
            "started": "start",
            "stopped": "stop",
            "restarted": "restart",
            "reloaded": "reload",
        }.get(state, state)
        tasks = [
            {
                "id": "t1",
                "command": f"systemctl {systemctl_action} {svc}",
                "description": f"{state} {svc}",
                "continue_on_error": False,
            }
        ]

    elif slug == "run-commands":
        raw = str(params.get("commands") or "").strip()
        if not raw:
            raise ValueError("At least one command is required")
        cmds = [c.strip() for c in raw.splitlines() if c.strip()]
        name = "Run shell commands"
        task_yaml = []
        for i, cmd in enumerate(cmds, start=1):
            safe = cmd.replace("\\", "\\\\").replace('"', '\\"')
            task_yaml.append(
                f"""    - name: Command {i}
      ansible.builtin.shell: "{safe}"
      args:
        executable: /bin/bash
      register: cmd_{i}
"""
            )
            tasks.append({"id": f"t{i}", "command": cmd, "description": f"Command {i}", "continue_on_error": False})
        yaml = f"""- name: {name}
  hosts: all
  become: true
  gather_facts: false
  tasks:
{''.join(task_yaml)}"""

    elif slug == "update-system":
        family = str(params.get("family") or "auto")
        name = "Update system packages"
        if family == "apt":
            yaml = """- name: Update system packages (apt)
  hosts: all
  become: true
  gather_facts: false
  tasks:
    - name: apt update & upgrade
      ansible.builtin.apt:
        update_cache: true
        upgrade: dist
"""
        elif family in ("dnf", "yum"):
            mod = "dnf" if family == "dnf" else "yum"
            yaml = f"""- name: Update system packages ({mod})
  hosts: all
  become: true
  gather_facts: false
  tasks:
    - name: {mod} update
      ansible.builtin.{mod}:
        name: "*"
        state: latest
"""
        else:
            yaml = """- name: Update system packages
  hosts: all
  become: true
  gather_facts: true
  tasks:
    - name: apt upgrade
      ansible.builtin.apt:
        update_cache: true
        upgrade: dist
      when: ansible_os_family == "Debian"
    - name: dnf upgrade
      ansible.builtin.dnf:
        name: "*"
        state: latest
      when: ansible_os_family == "RedHat"
"""
        tasks = [{"id": "t1", "command": "# package update", "description": "Update packages", "continue_on_error": False}]

    elif slug == "health-check":
        name = "Health check"
        yaml = """- name: Health check
  hosts: all
  become: false
  gather_facts: true
  tasks:
    - name: Uptime and load
      ansible.builtin.shell: uptime; cat /proc/loadavg; nproc
      args:
        executable: /bin/bash
      changed_when: false
    - name: Memory
      ansible.builtin.command: free -h
      changed_when: false
    - name: Disk
      ansible.builtin.shell: df -hT -x tmpfs -x devtmpfs
      args:
        executable: /bin/bash
      changed_when: false
    - name: Failed units
      ansible.builtin.shell: systemctl --failed --no-pager || true
      args:
        executable: /bin/bash
      changed_when: false
      failed_when: false
"""
        tasks = [
            {"id": "t1", "command": "uptime", "description": "Uptime", "continue_on_error": False},
            {"id": "t2", "command": "free -h", "description": "Memory", "continue_on_error": False},
            {"id": "t3", "command": "df -h", "description": "Disk", "continue_on_error": False},
            {"id": "t4", "command": "systemctl --failed", "description": "Failed units", "continue_on_error": True},
        ]

    elif slug == "docker-prune":
        name = "Docker cleanup"
        yaml = """- name: Docker cleanup
  hosts: all
  become: true
  gather_facts: false
  tasks:
    - name: Docker available
      ansible.builtin.command: docker info
      changed_when: false
    - name: Disk before
      ansible.builtin.command: docker system df
      changed_when: false
    - name: Prune containers
      ansible.builtin.command: docker container prune -f
    - name: Prune images
      ansible.builtin.command: docker image prune -f
    - name: Prune networks
      ansible.builtin.command: docker network prune -f
    - name: Disk after
      ansible.builtin.command: docker system df
      changed_when: false
"""
        tasks = [
            {"id": "t1", "command": "docker container prune -f", "description": "Prune containers", "continue_on_error": False},
            {"id": "t2", "command": "docker image prune -f", "description": "Prune images", "continue_on_error": False},
        ]
    else:
        raise ValueError(f"Unhandled recipe: {slug}")

    return {
        "name": name,
        "description": recipe["description"],
        "kind": "ansible",
        "category": category,
        "tags": ["guided", slug, "ansible"],
        "source_yaml": yaml.strip() + "\n",
        "tasks": tasks,
        "fidelity": {"runnable": len(tasks), "total": len(tasks), "score": 1.0, "engine": "ansible"},
    }
