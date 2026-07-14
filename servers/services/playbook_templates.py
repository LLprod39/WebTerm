"""Built-in operational playbook templates (real Ansible YAML)."""

from __future__ import annotations

from typing import Any
import uuid


def _tid() -> str:
    return f"t_{uuid.uuid4().hex[:10]}"


def _task(command: str, description: str, continue_on_error: bool = False) -> dict[str, Any]:
    return {
        "id": _tid(),
        "command": command,
        "description": description,
        "continue_on_error": continue_on_error,
    }


TEMPLATES: list[dict[str, Any]] = [
    {
        "slug": "health-snapshot",
        "name": "Health snapshot",
        "description": "Uptime, load, disk, memory, failed units — через Ansible modules.",
        "kind": "ansible",
        "category": "diagnose",
        "tags": ["health", "diagnose", "ansible"],
        "source_yaml": """- name: Health snapshot
  hosts: all
  become: false
  gather_facts: true
  tasks:
    - name: Uptime and load
      ansible.builtin.shell: uptime; cat /proc/loadavg; nproc
      args: { executable: /bin/bash }
      changed_when: false
    - name: Memory
      ansible.builtin.command: free -h
      changed_when: false
    - name: Disk
      ansible.builtin.shell: df -hT -x tmpfs -x devtmpfs
      args: { executable: /bin/bash }
      changed_when: false
    - name: Failed units
      ansible.builtin.shell: systemctl --failed --no-pager || true
      args: { executable: /bin/bash }
      changed_when: false
      failed_when: false
""",
        "tasks": [
            _task("uptime", "Uptime and load"),
            _task("free -h", "Memory"),
            _task("df -h", "Disk"),
            _task("systemctl --failed", "Failed units", True),
        ],
    },
    {
        "slug": "nginx-reload",
        "name": "Nginx config test & reload",
        "description": "nginx -t + systemd reload (Ansible systemd module).",
        "kind": "ansible",
        "category": "deploy",
        "tags": ["nginx", "deploy", "ansible"],
        "source_yaml": """- name: Nginx config test and reload
  hosts: all
  become: true
  gather_facts: false
  tasks:
    - name: Test nginx config
      ansible.builtin.command: nginx -t
      changed_when: false
    - name: Reload nginx
      ansible.builtin.systemd:
        name: nginx
        state: reloaded
    - name: Verify nginx active
      ansible.builtin.command: systemctl is-active nginx
      changed_when: false
""",
        "tasks": [
            _task("nginx -t", "Test nginx config"),
            _task("systemctl reload nginx", "Reload nginx"),
            _task("systemctl is-active nginx", "Verify nginx active"),
        ],
    },
    {
        "slug": "apt-security-update",
        "name": "Package update (Debian/Ubuntu)",
        "description": "apt update + upgrade через ansible.builtin.apt.",
        "kind": "ansible",
        "category": "patch",
        "tags": ["patch", "apt", "ansible"],
        "source_yaml": """- name: APT package update
  hosts: all
  become: true
  gather_facts: true
  tasks:
    - name: Update and upgrade apt packages
      ansible.builtin.apt:
        update_cache: true
        upgrade: dist
      when: ansible_os_family == "Debian"
""",
        "tasks": [
            _task("apt-get update && apt-get upgrade -y", "apt update/upgrade"),
        ],
    },
    {
        "slug": "docker-prune-safe",
        "name": "Docker prune (safe)",
        "description": "docker prune без volumes — Ansible command module.",
        "kind": "ansible",
        "category": "maintenance",
        "tags": ["docker", "cleanup", "ansible"],
        "source_yaml": """- name: Docker prune safe
  hosts: all
  become: true
  gather_facts: false
  tasks:
    - name: Docker available
      ansible.builtin.command: docker info
      changed_when: false
    - name: Prune stopped containers
      ansible.builtin.command: docker container prune -f
    - name: Prune dangling images
      ansible.builtin.command: docker image prune -f
    - name: Prune unused networks
      ansible.builtin.command: docker network prune -f
""",
        "tasks": [
            _task("docker container prune -f", "Prune containers"),
            _task("docker image prune -f", "Prune images"),
        ],
    },
    {
        "slug": "ssh-hardening-check",
        "name": "SSH hardening checklist",
        "description": "Read-only audit sshd settings via Ansible.",
        "kind": "ansible",
        "category": "security",
        "tags": ["security", "ssh", "ansible"],
        "source_yaml": """- name: SSH hardening checklist
  hosts: all
  become: true
  gather_facts: false
  tasks:
    - name: Effective sshd settings
      ansible.builtin.shell: |
        sshd -T 2>/dev/null | egrep -i 'permitrootlogin|passwordauthentication|pubkeyauthentication|port |x11forwarding|maxauthtries' \\
          || grep -E '^(PermitRootLogin|PasswordAuthentication|PubkeyAuthentication|Port|X11Forwarding|MaxAuthTries)' /etc/ssh/sshd_config
      args: { executable: /bin/bash }
      changed_when: false
    - name: Recent logins
      ansible.builtin.shell: who; last -n 10 2>/dev/null || true
      args: { executable: /bin/bash }
      changed_when: false
      failed_when: false
""",
        "tasks": [
            _task("sshd -T | head", "sshd settings"),
            _task("last -n 10", "Recent logins", True),
        ],
    },
]


def list_templates() -> list[dict[str, Any]]:
    out = []
    for item in TEMPLATES:
        tasks = item["tasks"]
        out.append(
            {
                "slug": item["slug"],
                "name": item["name"],
                "description": item["description"],
                "kind": item.get("kind") or "ansible",
                "category": item["category"],
                "tags": list(item.get("tags") or []),
                "task_count": len(tasks),
                "tasks_preview": [
                    {"description": t["description"], "command": t["command"]} for t in tasks[:3]
                ],
            }
        )
    return out


def get_template(slug: str) -> dict[str, Any] | None:
    for item in TEMPLATES:
        if item["slug"] == slug:
            return {
                "slug": item["slug"],
                "name": item["name"],
                "description": item["description"],
                "kind": item.get("kind") or "ansible",
                "category": item["category"],
                "tags": list(item.get("tags") or []),
                "source_yaml": item.get("source_yaml") or "",
                "fidelity": {"engine": "ansible", "score": 1.0},
                "tasks": [
                    {
                        "id": _tid(),
                        "command": t["command"],
                        "description": t["description"],
                        "continue_on_error": bool(t.get("continue_on_error")),
                    }
                    for t in item["tasks"]
                ],
            }
    return None
