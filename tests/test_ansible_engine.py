"""Unit tests for real Ansible engine helpers (no ansible binary required)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load():
    path = Path(__file__).resolve().parents[1] / "servers" / "services" / "ansible_engine.py"
    spec = importlib.util.spec_from_file_location("ansible_engine_standalone", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_generate_install_package_yaml():
    mod = _load()
    out = mod.generate_from_recipe("install-package", {"package": "nginx", "state": "present"})
    assert out["kind"] == "ansible"
    assert "ansible.builtin.apt" in out["source_yaml"]
    assert "nginx" in out["source_yaml"]
    assert out["name"]


def test_generate_manage_service():
    mod = _load()
    out = mod.generate_from_recipe("manage-service", {"service": "nginx", "state": "restarted", "enabled": True})
    assert "ansible.builtin.systemd" in out["source_yaml"]
    assert "nginx" in out["source_yaml"]


def test_tasks_to_ansible_yaml():
    mod = _load()
    yaml = mod.tasks_to_ansible_yaml(
        name="Demo",
        tasks=[
            {"command": "uptime", "description": "Up", "continue_on_error": False},
            {"command": "df -h", "description": "Disk", "continue_on_error": True},
        ],
    )
    assert "ansible.builtin.shell" in yaml
    assert "ignore_errors: true" in yaml
    assert "uptime" in yaml


def test_parse_ansible_json_output():
    mod = _load()
    servers = [SimpleNamespace(id=1, name="app-01", host="10.0.0.1")]
    payload = {
        "plays": [
            {
                "tasks": [
                    {
                        "task": {"name": "Uptime"},
                        "hosts": {
                            "app-01": {
                                "stdout": "up 1 day",
                                "rc": 0,
                                "failed": False,
                            }
                        },
                    }
                ]
            }
        ],
        "stats": {"app-01": {"ok": 1, "failures": 0, "unreachable": 0}},
    }
    import json

    results = mod.parse_ansible_json_output(json.dumps(payload), servers=servers)
    assert len(results) == 1
    assert results[0]["server_id"] == 1
    assert results[0]["task_results"][0]["status"] == "success"
    assert "up 1 day" in results[0]["task_results"][0]["output"]


def test_list_guided_recipes():
    mod = _load()
    recipes = mod.list_guided_recipes()
    assert any(r["slug"] == "health-check" for r in recipes)


def test_parse_play_recap():
    mod = _load()
    servers = [SimpleNamespace(id=1, name="app-01", host="10.0.0.1")]
    text = """
PLAY [Health] ******************************************************************
TASK [Uptime] ******************************************************************
ok: [app-01]

PLAY RECAP *********************************************************************
app-01                     : ok=2    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
"""
    results = mod.parse_play_recap(text, servers=servers)
    assert results
    assert results[0]["server_id"] == 1
    assert results[0]["status"] == "success"


def test_live_parser_tracks_progress_and_hosts():
    mod = _load()
    servers = [
        SimpleNamespace(id=1, name="app-01", host="10.0.0.1"),
        SimpleNamespace(id=2, name="db-01", host="10.0.0.2"),
    ]
    parser = mod.AnsibleLiveParser(servers, tasks_total=3)
    lines = [
        "PLAY [Health] ******************************************************************",
        "",
        "TASK [Gathering Facts] *********************************************************",
        "ok: [app-01]",
        'fatal: [db-01]: UNREACHABLE! => {"changed": false, "msg": "ssh timeout"}',
        "",
        "TASK [Uptime] ******************************************************************",
        "changed: [app-01]",
    ]
    for line in lines:
        parser.feed(line)

    snap = parser.snapshot()
    assert snap["play"] == "Health"
    assert snap["task"] == "Uptime"
    assert snap["task_number"] == 2
    assert snap["tasks_total"] == 3
    assert snap["counts"]["ok"] == 2
    assert snap["counts"]["unreachable"] == 1

    live = parser.build_host_results()
    by_id = {h["server_id"]: h for h in live}
    assert by_id[1]["status"] == "running"
    assert by_id[2]["status"] == "error"
    assert "ssh timeout" in by_id[2]["task_results"][0]["output"]

    parser.feed("PLAY RECAP *********************************************************************")
    parser.feed("app-01                     : ok=2    changed=1    unreachable=0    failed=0    skipped=0")
    parser.feed("db-01                      : ok=0    changed=0    unreachable=1    failed=0    skipped=0")
    final = parser.build_host_results(final=True)
    by_id = {h["server_id"]: h for h in final}
    assert by_id[1]["status"] == "success"
    assert by_id[2]["status"] == "error"


def test_estimate_total_tasks():
    mod = _load()
    yaml = """- name: Demo
  hosts: all
  gather_facts: true
  tasks:
    - name: One
      ansible.builtin.shell: uptime
    - name: Two
      ansible.builtin.shell: df -h
"""
    assert mod.estimate_total_tasks(yaml) == 3  # 2 tasks + gathering facts


def test_manage_service_shell_fallback_command():
    mod = _load()
    out = mod.generate_from_recipe("manage-service", {"service": "nginx", "state": "stopped"})
    assert out["tasks"][0]["command"] == "systemctl stop nginx"


def test_ansible_cfg_has_no_json_callback():
    mod = _load()
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        cfg = mod._build_ansible_cfg(Path(tmp))
        content = cfg.read_text(encoding="utf-8")
        assert "stdout_callback = default" in content
        assert "stdout_callback = json" not in content
