"""Guided Ansible recipes for non-experts.

Extracted from ansible_engine.py to keep modules under the size limit.
Public API (list_guided_recipes, generate_from_recipe) is re-exported from
servers.services.ansible_engine for backward compatibility.
"""
from __future__ import annotations

from typing import Any

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
