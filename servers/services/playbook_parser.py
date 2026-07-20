"""Parse Ansible YAML/JSON into WebTerm runbook tasks with fidelity scoring."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any


def _task_id() -> str:
    return f"t_{uuid.uuid4().hex[:12]}"


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _shell_from_module(task: dict[str, Any]) -> tuple[str, str | None]:
    """Return (command, unsupported_module_or_None)."""
    ignore = {
        "name",
        "when",
        "register",
        "become",
        "become_user",
        "tags",
        "notify",
        "ignore_errors",
        "changed_when",
        "failed_when",
        "loop",
        "with_items",
        "vars",
        "environment",
        "no_log",
        "delegate_to",
        "run_once",
        "block",
        "rescue",
        "always",
        "args",
        "throttle",
        "retries",
        "delay",
        "until",
        "check_mode",
        "diff",
    }

    if isinstance(task.get("shell"), str):
        return str(task["shell"]), None
    if isinstance(task.get("command"), str):
        return str(task["command"]), None
    if isinstance(task.get("raw"), str):
        return str(task["raw"]), None
    if isinstance(task.get("script"), str):
        return str(task["script"]), None
    if isinstance(task.get("shell"), dict):
        cmd = task["shell"].get("cmd") or task["shell"].get("free_form") or ""
        return str(cmd), None
    if isinstance(task.get("command"), dict):
        cmd = task["command"].get("cmd") or task["command"].get("free_form") or ""
        return str(cmd), None

    if "apt" in task:
        apt = task["apt"] if isinstance(task["apt"], dict) else {"name": task["apt"]}
        pkg = apt.get("name") or apt.get("pkg") or ""
        if isinstance(pkg, list):
            pkg = " ".join(str(p) for p in pkg)
        state = str(apt.get("state") or "present")
        action = "remove" if state == "absent" else "install"
        return f"apt-get {action} -y {pkg}".strip(), None

    if "yum" in task or "dnf" in task:
        key = "yum" if "yum" in task else "dnf"
        yum = task[key] if isinstance(task[key], dict) else {"name": task[key]}
        pkg = yum.get("name") or ""
        if isinstance(pkg, list):
            pkg = " ".join(str(p) for p in pkg)
        state = str(yum.get("state") or "present")
        bin_name = "dnf" if key == "dnf" else "yum"
        action = "remove" if state == "absent" else "install"
        return f"{bin_name} {action} -y {pkg}".strip(), None

    if "systemd" in task or "service" in task:
        svc = (task.get("systemd") or task.get("service")) or {}
        if not isinstance(svc, dict):
            svc = {"name": svc}
        name = svc.get("name") or ""
        state = str(svc.get("state") or "started")
        state_map = {
            "started": "start",
            "stopped": "stop",
            "restarted": "restart",
            "reloaded": "reload",
        }
        command = f"systemctl {state_map.get(state, state)} {name}".strip()
        if svc.get("enabled") is True:
            command += f" && systemctl enable {name}"
        return command, None

    if isinstance(task.get("copy"), dict):
        cp = task["copy"]
        if cp.get("content") is not None and cp.get("dest"):
            escaped = str(cp["content"]).replace("'", "'\\''")
            return f"echo '{escaped}' > {cp['dest']}", None
        if cp.get("src") and cp.get("dest"):
            return f"cp {cp['src']} {cp['dest']}", "copy_remote_src"
        return f"# copy: {cp.get('dest') or ''}", "copy"

    if isinstance(task.get("file"), dict):
        f = task["file"]
        path = f.get("path") or f.get("dest") or ""
        state = f.get("state")
        if state == "directory":
            return f"mkdir -p {path}", None
        if state == "absent":
            return f"rm -rf {path}", None
        if f.get("mode"):
            return f"chmod {f['mode']} {path}", None
        return f"# file: {path}", "file"

    if isinstance(task.get("lineinfile"), dict):
        lineinfile = task["lineinfile"]
        path = lineinfile.get("path") or lineinfile.get("dest") or ""
        line = str(lineinfile.get("line") or "").replace("'", "'\\''")
        if path and line:
            return (
                f"grep -qxF '{line}' {path} 2>/dev/null || echo '{line}' >> {path}",
                None,
            )
        return f"# lineinfile: {path}", "lineinfile"

    if isinstance(task.get("template"), dict):
        tmpl = task["template"]
        return f"# template: {tmpl.get('src')} -> {tmpl.get('dest')}", "template"

    if isinstance(task.get("git"), dict):
        g = task["git"]
        dest = g.get("dest") or ""
        repo = g.get("repo") or ""
        version = g.get("version")
        branch = f" -b {version}" if version else ""
        return f"git clone{branch} {repo} {dest}".strip(), None

    if isinstance(task.get("pip"), dict):
        pip = task["pip"]
        if pip.get("requirements"):
            return f"pip install -r {pip['requirements']}", None
        name = pip.get("name") or ""
        if isinstance(name, list):
            name = " ".join(str(n) for n in name)
        return f"pip install {name}".strip(), None

    if isinstance(task.get("docker_container"), dict):
        dc = task["docker_container"]
        return (
            f"# docker_container: {dc.get('name')} image={dc.get('image') or ''} state={dc.get('state') or 'started'}",
            "docker_container",
        )

    if isinstance(task.get("unarchive"), dict):
        u = task["unarchive"]
        return f"tar -xaf {u.get('src') or ''} -C {u.get('dest') or '.'}", None

    if isinstance(task.get("get_url"), dict):
        gu = task["get_url"]
        return f"curl -fsSL -o {gu.get('dest') or ''} {gu.get('url') or ''}", None

    if isinstance(task.get("user"), dict):
        u = task["user"]
        name = u.get("name") or ""
        if u.get("state") == "absent":
            return f"userdel {name}", None
        return f"id {name} >/dev/null 2>&1 || useradd {name}", None

    if isinstance(task.get("cron"), dict):
        return "# cron module (use crontab -e manually)", "cron"

    if "debug" in task:
        msg = task["debug"]
        if isinstance(msg, dict):
            msg = msg.get("msg", "")
        return f"echo {json.dumps(str(msg))}", None

    module_keys = [k for k in task if k not in ignore]
    if module_keys:
        mod = module_keys[0]
        val = task[mod]
        preview = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)[:200]
        return f"# ansible.{mod}: {preview}", mod

    return "", None


def parse_ansible_playbook(content: str, filename: str = "playbook.yml") -> dict[str, Any]:
    """Parse Ansible YAML or JSON into a WebTerm playbook payload."""
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ValueError("PyYAML is required to import Ansible playbooks") from exc

    text = (content or "").strip()
    if not text:
        raise ValueError("Empty playbook content")

    try:
        parsed = yaml.safe_load(text)
    except Exception:
        try:
            parsed = json.loads(text)
        except Exception as exc:
            raise ValueError(f"Invalid YAML/JSON: {exc}") from exc

    plays = parsed if isinstance(parsed, list) else [parsed]
    tasks: list[dict[str, Any]] = []
    name = re.sub(r"\.(ya?ml|json)$", "", filename, flags=re.I) or "Imported playbook"
    description = ""
    unsupported: list[str] = []
    hosts_hint = ""
    has_ansible_content = False

    for play in plays:
        if not isinstance(play, dict):
            continue
        if isinstance(play.get("name"), str) and play["name"].strip():
            name = play["name"].strip()
        if isinstance(play.get("hosts"), str):
            hosts_hint = play["hosts"]
            description = f"hosts: {play['hosts']}"
        elif isinstance(play.get("hosts"), list):
            hosts_hint = ",".join(str(h) for h in play["hosts"])
            description = f"hosts: {hosts_hint}"

        if play.get("roles"):
            has_ansible_content = True
            unsupported.append("roles")

        for section in ("pre_tasks", "tasks", "post_tasks", "handlers"):
            if play.get(section):
                has_ansible_content = True
            for raw in _as_list(play.get(section)):
                if not isinstance(raw, dict):
                    continue
                # Expand blocks shallowly
                block_items = raw["block"] if "block" in raw and isinstance(raw["block"], list) else [raw]

                for item in block_items:
                    if not isinstance(item, dict):
                        continue
                    task_name = str(item.get("name") or "").strip()
                    command, unsupported_mod = _shell_from_module(item)
                    continue_on_error = bool(item.get("ignore_errors"))
                    if unsupported_mod:
                        unsupported.append(unsupported_mod)
                    if not command and not task_name:
                        continue
                    runnable = bool(command) and not command.lstrip().startswith("#")
                    tasks.append(
                        {
                            "id": _task_id(),
                            "command": command or f"# {task_name}",
                            "description": task_name,
                            "continue_on_error": continue_on_error,
                            "runnable": runnable,
                            "module": unsupported_mod or ("shell" if runnable else "unknown"),
                        }
                    )

    if not tasks and not has_ansible_content:
        raise ValueError(
            "No tasks found. Use shell/command/apt/yum/systemd/file/git/pip modules, or create a runbook manually."
        )

    runnable_count = sum(1 for t in tasks if t.get("runnable"))
    total = len(tasks)
    fidelity = {
        "runnable": runnable_count,
        "total": total,
        "score": round(runnable_count / total, 2) if total else 0,
        "unsupported_modules": sorted(set(unsupported)),
        "hosts_hint": hosts_hint,
    }

    kind = "runbook" if fidelity["score"] >= 0.85 and not unsupported else "ansible"

    return {
        "name": name,
        "description": description,
        "kind": kind,
        "tasks": [
            {
                "id": t["id"],
                "command": t["command"],
                "description": t["description"],
                "continue_on_error": t["continue_on_error"],
            }
            for t in tasks
        ],
        "source_yaml": text,
        "fidelity": fidelity,
        "tags": ["imported", "ansible"],
    }


def build_inventory_ini(servers: list[dict[str, Any]], groups: dict[str, list[int]] | None = None) -> str:
    """Build a simple ansible inventory INI from WebTerm servers."""
    groups = groups or {}
    lines: list[str] = ["# Generated by WebTerm Automation", ""]

    # ungrouped / all
    lines.append("[all]")
    for s in servers:
        host = str(s.get("host") or "")
        name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", str(s.get("name") or f"server_{s.get('id')}"))
        user = str(s.get("username") or "")
        port = int(s.get("port") or 22)
        line = f"{name} ansible_host={host} ansible_port={port}"
        if user:
            line += f" ansible_user={user}"
        os_kind = str(s.get("detected_os") or s.get("os") or "").strip()
        if os_kind:
            line += f" ansible_os_family={os_kind.split()[0]}"
        lines.append(line)
    lines.append("")

    id_to_name = {
        int(s["id"]): re.sub(r"[^a-zA-Z0-9_\-\.]", "_", str(s.get("name") or f"server_{s['id']}"))
        for s in servers
        if s.get("id") is not None
    }

    for group_name, server_ids in groups.items():
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", group_name) or "group"
        lines.append(f"[{safe}]")
        for sid in server_ids:
            host_name = id_to_name.get(int(sid))
            if host_name:
                lines.append(host_name)
        lines.append("")

    lines.append("[all:vars]")
    lines.append("ansible_connection=ssh")
    lines.append("# Credentials are resolved by WebTerm — not stored in inventory")
    lines.append("")
    return "\n".join(lines)
