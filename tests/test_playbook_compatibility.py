from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from servers.models import Playbook, PlaybookCompatibilityRevision, Server
from servers.services.playbook_compatibility_ai import adapt_playbook_with_ai
from servers.services.playbook_compatibility_analysis import (
    analyze_playbook_compatibility,
    compare_semantics,
)
from servers.services.playbook_compatibility_inventory import compile_runtime_playbook_yaml

SOURCE = """
- name: Deploy web
  hosts: web
  vars:
    package_name: nginx
  tasks:
    - name: Install package
      ansible.builtin.apt:
        name: "{{ package_name }}"
        state: present
    - name: Restart service
      ansible.builtin.service:
        name: nginx
        state: restarted
"""


def test_analysis_requires_inventory_binding_but_preserves_declared_vars():
    report = analyze_playbook_compatibility(SOURCE)
    assert report["status"] == "needs_binding"
    assert report["host_selectors"] == ["web"]
    assert report["missing_bindings"] == ["web"]
    assert report["required_variables"] == []


def test_semantic_guard_rejects_task_changes_but_allows_host_and_vars_changes():
    compatible = SOURCE.replace("hosts: web", "hosts: replacement").replace(
        "package_name: nginx", "package_name: nginx-core"
    )
    guard = compare_semantics(SOURCE, compatible)
    assert guard["passed"] is True

    changed_logic = SOURCE.replace("state: restarted", "state: stopped")
    rejected = compare_semantics(SOURCE, changed_logic)
    assert rejected["passed"] is False
    assert rejected["violations"]


def test_runtime_compiler_changes_only_hosts_and_emits_bound_group():
    runtime_yaml, groups = compile_runtime_playbook_yaml(SOURCE, {"web": [10, 11]})
    assert "hosts: wt_web_" in runtime_yaml
    assert list(groups.values()) == [[10, 11]]
    assert compare_semantics(SOURCE, runtime_yaml)["passed"] is True


def test_ai_proposal_that_changes_task_logic_is_rejected(monkeypatch):
    async def fake_call(_prompt, _system_prompt):
        return json.dumps(
            {
                "edits": [
                    {
                        "old_text": "state: restarted",
                        "new_text": "state: stopped",
                        "reason": "changed service state",
                    }
                ],
                "assumptions": [],
            }
        )

    monkeypatch.setattr("servers.services.playbook_compatibility_ai._call_llm", fake_call)
    proposal = adapt_playbook_with_ai(
        SOURCE,
        bindings={"web": {"server_ids": [1], "group_ids": []}},
        user_instruction="adapt",
    )
    assert proposal["method"] == "ai_rejected"
    assert proposal["adapted_yaml"] == ""
    assert proposal["semantic_guard"]["passed"] is False


def test_ai_applies_only_exact_local_edits(monkeypatch):
    async def fake_call(_prompt, _system_prompt):
        return json.dumps(
            {
                "edits": [
                    {
                        "old_text": "hosts: web",
                        "new_text": "hosts: all",
                        "reason": "Use runtime inventory",
                    }
                ],
                "assumptions": [],
            }
        )

    monkeypatch.setattr("servers.services.playbook_compatibility_ai._call_llm", fake_call)
    proposal = adapt_playbook_with_ai(SOURCE, user_instruction="adapt")
    assert proposal["method"] == "ai"
    assert proposal["adapted_yaml"] == SOURCE.replace("hosts: web", "hosts: all")
    assert proposal["changes"] == ["Use runtime inventory"]
    assert proposal["semantic_guard"]["passed"] is True


def test_literal_secret_in_play_vars_blocks_ai_egress():
    source = SOURCE.replace("package_name: nginx", "package_name: nginx\n    db_password: cleartext")
    report = analyze_playbook_compatibility(source)
    assert any(issue["code"] == "literal_secret" for issue in report["issues"])


@pytest.mark.django_db
def test_compatibility_api_apply_and_run_binding(monkeypatch):
    syntax_ok = {"status": "passed", "passed": True, "message": "ok", "method": "test"}
    monkeypatch.setattr(
        "servers.views.server_playbook_compatibility_views.validate_playbook_syntax",
        lambda _yaml: syntax_ok,
    )
    monkeypatch.setattr(
        "servers.views.server_playbook_run_views.validate_playbook_syntax",
        lambda _yaml: syntax_ok,
    )
    user = User.objects.create_user(username="compat_user", password="pass123")
    server = Server.objects.create(
        user=user,
        name="web-01",
        host="127.0.0.1",
        port=22,
        username="root",
        auth_method="key",
        is_active=True,
    )
    playbook = Playbook.objects.create(
        user=user,
        name="Imported",
        kind=Playbook.KIND_ANSIBLE,
        source_yaml=SOURCE,
        tasks=[],
    )
    client = Client()
    client.force_login(user)
    binding = {"web": {"server_ids": [server.id], "group_ids": []}}

    analyze = client.post(
        f"/servers/api/playbooks/{playbook.id}/compatibility/analyze/",
        data=json.dumps({"inventory_bindings": binding}),
        content_type="application/json",
    )
    assert analyze.status_code == 200
    assert analyze.json()["report"]["ready"] is True

    applied = client.post(
        f"/servers/api/playbooks/{playbook.id}/compatibility/apply/",
        data=json.dumps({"adapted_yaml": SOURCE, "inventory_bindings": binding, "changes": ["Bound inventory"]}),
        content_type="application/json",
    )
    assert applied.status_code == 200, applied.content
    revision = PlaybookCompatibilityRevision.objects.get(playbook=playbook)
    assert revision.status == PlaybookCompatibilityRevision.STATUS_VALIDATED
    playbook.refresh_from_db()
    assert playbook.active_compatibility_revision_id == revision.id

    captured: list[int] = []

    def fake_start(run_id, *, master_password=""):
        captured.append(run_id)

    monkeypatch.setattr("servers.views.server_playbook_run_views.start_playbook_run_async", fake_start)
    run = client.post(
        f"/servers/api/playbooks/{playbook.id}/run/",
        data=json.dumps(
            {
                "server_ids": [server.id],
                "inventory_bindings": binding,
                "engine": "ansible",
            }
        ),
        content_type="application/json",
    )
    assert run.status_code == 200, run.content
    payload = run.json()["run"]
    assert captured == [payload["id"]]
    snapshot = payload["playbook_snapshot"]
    assert "hosts: wt_web_" in snapshot["source_yaml"]
    assert snapshot["source_yaml_original"].strip() == SOURCE.strip()
