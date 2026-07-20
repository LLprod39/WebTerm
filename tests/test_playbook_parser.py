"""Unit tests for Ansible → runbook parser (no Django DB)."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_parser_module():
    path = Path(__file__).resolve().parents[1] / "servers" / "services" / "playbook_parser.py"
    spec = importlib.util.spec_from_file_location("playbook_parser_standalone", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parse_shell_and_template_fidelity():
    mod = _load_parser_module()
    content = """
- name: Demo
  hosts: web
  tasks:
    - name: Hello
      shell: echo hello
    - name: Template
      template:
        src: a.j2
        dest: /tmp/a
    - name: Restart
      systemd:
        name: nginx
        state: restarted
"""
    result = mod.parse_ansible_playbook(content, "demo.yml")
    assert result["name"] == "Demo"
    assert result["fidelity"]["total"] == 3
    assert result["fidelity"]["runnable"] == 2
    assert "template" in result["fidelity"]["unsupported_modules"]
    assert any("systemctl" in t["command"] for t in result["tasks"])


def test_parse_json_playbook():
    mod = _load_parser_module()
    content = """
[
  {
    "name": "JSON PB",
    "hosts": "all",
    "tasks": [
      {"name": "Uptime", "command": "uptime"}
    ]
  }
]
"""
    result = mod.parse_ansible_playbook(content, "demo.json")
    assert result["name"] == "JSON PB"
    assert result["fidelity"]["score"] == 1.0
    assert result["tasks"][0]["command"] == "uptime"


def test_inventory_ini():
    mod = _load_parser_module()
    inv = mod.build_inventory_ini(
        [
            {"id": 1, "name": "app-01", "host": "10.0.0.1", "port": 22, "username": "deploy", "detected_os": "linux"},
            {"id": 2, "name": "db-01", "host": "10.0.0.2", "port": 22, "username": "deploy"},
        ],
        {"web": [1], "db": [2]},
    )
    assert "app-01 ansible_host=10.0.0.1" in inv
    assert "[web]" in inv
    assert "ansible_connection=ssh" in inv


def test_role_only_playbook_is_kept_for_real_ansible_validation():
    mod = _load_parser_module()
    result = mod.parse_ansible_playbook(
        """
- name: Role based deploy
  hosts: web
  roles:
    - geerlingguy.nginx
""",
        "roles.yml",
    )
    assert result["kind"] == "ansible"
    assert result["tasks"] == []
    assert "roles" in result["fidelity"]["unsupported_modules"]
