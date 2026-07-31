from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from servers.models import Playbook, PlaybookCompatibilityRevision, PlaybookDraft, Server
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


def test_semantic_guard_allows_host_binding_only_and_rejects_variable_changes():
    compatible = SOURCE.replace("hosts: web", "hosts: replacement")
    guard = compare_semantics(SOURCE, compatible)
    assert guard["passed"] is True

    changed_variable = SOURCE.replace("package_name: nginx", "package_name: nginx-core")
    assert compare_semantics(SOURCE, changed_variable)["passed"] is False

    changed_logic = SOURCE.replace("state: restarted", "state: stopped")
    rejected = compare_semantics(SOURCE, changed_logic)
    assert rejected["passed"] is False
    assert rejected["violations"]


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("no_log: true", "no_log: false"),
        ("DEPLOY_ENV: production", "DEPLOY_ENV: staging"),
        ("vars_files:\n    - vars/prod.yml", "vars_files:\n    - vars/dev.yml"),
    ],
)
def test_semantic_guard_rejects_secret_hiding_and_execution_context_changes(before, after):
    source = """- hosts: web
  vars_files:
    - vars/prod.yml
  tasks:
    - name: guarded
      ansible.builtin.command: hostname
      no_log: true
      environment:
        DEPLOY_ENV: production
"""
    assert before in source
    assert compare_semantics(source, source.replace(before, after))["passed"] is False


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


@pytest.mark.parametrize(
    ("source", "expected_code"),
    [
        (
            """- hosts: web
  connection: local
  tasks:
    - ansible.builtin.shell: id
""",
            "controller_connection_forbidden",
        ),
        (
            """- hosts: localhost
  tasks:
    - ansible.builtin.shell: id
""",
            "controller_hosts_forbidden",
        ),
        (
            """- hosts: web
  tasks:
    - local_action: ansible.builtin.command id
""",
            "controller_local_action_forbidden",
        ),
        (
            """- hosts: web
  tasks:
    - ansible.builtin.command: id
      delegate_to: 127.0.0.1
""",
            "controller_delegate_forbidden",
        ),
        (
            """- hosts: web
  tasks:
    - ansible.builtin.command: id
      delegate_to: "{{ controller_host }}"
""",
            "controller_delegate_dynamic",
        ),
        (
            """- hosts: web
  tasks:
    - ansible.builtin.command: id
      delegate_to: 192.0.2.10
""",
            "controller_delegate_unbound",
        ),
        (
            """- hosts: web
  vars_files:
    - ../../controller-secrets.yml
  tasks: []
""",
            "controller_path_forbidden",
        ),
        (
            """- hosts: web
  tasks:
    - ansible.builtin.debug:
        msg: ready
      with_file:
        - /etc/passwd
""",
            "controller_iterator_forbidden",
        ),
        (
            """- hosts: web
  tasks:
    - ansible.builtin.add_host:
        name: extra-host
        groups: runtime_targets
""",
            "controller_dynamic_inventory_forbidden",
        ),
    ],
)
def test_controller_execution_constructs_are_fail_closed(source, expected_code):
    report = analyze_playbook_compatibility(
        source,
        bindings={"web": {"server_ids": [1], "group_ids": []}},
    )

    assert report["status"] == "blocked"
    assert expected_code in {issue["code"] for issue in report["issues"]}


@pytest.mark.parametrize("function_name", ["lookup", "query", "q"])
@pytest.mark.parametrize("plugin", ["pipe", "env", "file", "url", "password", "config", "ini"])
def test_controller_lookup_plugins_are_blocked(function_name, plugin):
    source = f"""- hosts: web
  tasks:
    - ansible.builtin.debug:
        msg: "{{{{ {function_name}('{plugin}', 'value') }}}}"
"""

    report = analyze_playbook_compatibility(
        source,
        bindings={"web": {"server_ids": [1], "group_ids": []}},
    )

    assert report["status"] == "blocked"
    issue = next(item for item in report["issues"] if item["code"] == "controller_lookup_forbidden")
    assert issue["details"] == {"plugin": plugin}


def test_unknown_collection_lookup_is_fail_closed():
    source = """- hosts: web
  tasks:
    - ansible.builtin.debug:
        msg: "{{ lookup('vendor.collection.controller_plugin', 'value') }}"
"""

    report = analyze_playbook_compatibility(
        source,
        bindings={"web": {"server_ids": [1], "group_ids": []}},
    )

    issue = next(item for item in report["issues"] if item["code"] == "controller_lookup_forbidden")
    assert issue["details"] == {"plugin": "controller_plugin"}


def test_safe_remote_task_has_no_controller_policy_blocker():
    source = """- hosts: web
  gather_facts: false
  tasks:
    - ansible.builtin.command: uname -a
"""

    report = analyze_playbook_compatibility(
        source,
        bindings={"web": {"server_ids": [1], "group_ids": []}},
    )

    assert report["status"] == "ready"
    assert not any(issue["code"].startswith("controller_") for issue in report["issues"])


@pytest.mark.django_db
def test_compatibility_api_apply_and_run_binding(monkeypatch):
    syntax_ok = {"status": "passed", "passed": True, "message": "ok", "method": "test"}
    monkeypatch.setattr(
        "servers.views.server_playbook_compatibility_views.validate_playbook_syntax",
        lambda _yaml, **_kwargs: syntax_ok,
    )
    monkeypatch.setattr(
        "servers.views.server_playbook_run_views.validate_playbook_syntax",
        lambda _yaml: syntax_ok,
    )
    monkeypatch.setattr(
        "servers.services.playbooks.validation.validate_playbook_syntax",
        lambda _yaml, **_kwargs: syntax_ok,
    )
    fingerprint = {
        "method": "test",
        "available": True,
        "ansible_version": "test",
        "python_version": "test",
        "image": "",
        "image_ready": None,
        "config_hash": "test",
        "analyzer_version": 2,
    }
    monkeypatch.setattr(
        "servers.services.playbooks.validation.runtime_fingerprint",
        lambda: fingerprint,
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
    assert applied.json()["result_revision_id"] == revision.result_revision_id
    assert applied.json()["content_revision"]["id"] == revision.result_revision_id
    assert applied.json()["content_revision"]["source_yaml"].strip() == SOURCE.strip()
    playbook.refresh_from_db()
    assert playbook.active_compatibility_revision_id == revision.id
    assert playbook.published_revision_id == playbook.origin_revision_id
    assert playbook.published_revision_id == revision.source_revision_id
    assert playbook.published_revision_id != revision.result_revision_id
    draft = PlaybookDraft.objects.get(playbook=playbook)
    assert draft.base_revision_id == revision.result_revision_id
    assert draft.source_yaml.strip() == SOURCE.strip()

    publish_before_validation = client.post(
        f"/servers/api/playbooks/{playbook.id}/revisions/{revision.result_revision_id}/publish/",
        data="{}",
        content_type="application/json",
    )
    assert publish_before_validation.status_code == 400
    publish_error = publish_before_validation.json()
    assert publish_error["code"] == "playbook_publish_failed"
    assert "must pass standard revision validation" in publish_error["error"]
    validation = client.post(
        f"/servers/api/playbooks/{playbook.id}/revisions/{revision.result_revision_id}/validate/",
        data=json.dumps(
            {
                "server_ids": [server.id],
                "inventory_bindings": binding,
            }
        ),
        content_type="application/json",
    )
    assert validation.status_code == 200, validation.content
    assert validation.json()["validation"]["status"] == "ready"
    published = client.post(
        f"/servers/api/playbooks/{playbook.id}/revisions/{revision.result_revision_id}/publish/",
        data="{}",
        content_type="application/json",
    )
    assert published.status_code == 200, published.content
    playbook.refresh_from_db()
    assert playbook.published_revision_id == revision.result_revision_id

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
