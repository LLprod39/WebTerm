from __future__ import annotations

import json
import zipfile
from io import BytesIO

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.auth.models import User
from django.test import Client, override_settings

from servers.models import Playbook, PlaybookCompatibilityRevision, PlaybookDraft, Server
from servers.services.playbook_compatibility_ai import PlaybookAdaptationError, adapt_playbook_with_ai
from servers.services.playbook_compatibility_analysis import (
    analyze_playbook_compatibility,
    compare_semantics,
)
from servers.services.playbook_compatibility_inventory import compile_runtime_playbook_yaml
from servers.services.playbooks.bundles import commit_project_bundle

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


def test_semantic_guard_allows_play_level_compatibility_fields_but_rejects_task_logic_changes():
    compatible = SOURCE.replace("hosts: web", "hosts: replacement")
    guard = compare_semantics(SOURCE, compatible)
    assert guard["passed"] is True

    changed_variable = SOURCE.replace("package_name: nginx", "package_name: nginx-core")
    assert compare_semantics(SOURCE, changed_variable)["passed"] is True

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
    async def fake_call(_prompt, _system_prompt, _execution_context):
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
    async def fake_call(_prompt, _system_prompt, _execution_context):
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


def test_ai_adaptation_supports_nested_asgiref_thread_sensitive_calls(monkeypatch):
    async def fake_call(_prompt, _system_prompt, _execution_context):
        return await sync_to_async(
            lambda: json.dumps({"edits": [], "assumptions": []}),
            thread_sensitive=True,
        )()

    async def invoke_from_asgi_bridge():
        return await sync_to_async(adapt_playbook_with_ai, thread_sensitive=True)(
            SOURCE,
            user_instruction="adapt",
        )

    monkeypatch.setattr("servers.services.playbook_compatibility_ai._call_llm", fake_call)
    proposal = async_to_sync(invoke_from_asgi_bridge)()

    assert proposal["method"] == "ai"
    assert proposal["adapted_yaml"] == SOURCE
    assert proposal["semantic_guard"]["passed"] is True


def test_ai_adaptation_rejects_bare_provider_token_before_llm_call(monkeypatch):
    called = False

    async def fake_call(_prompt, _system_prompt, _execution_context):
        nonlocal called
        called = True
        return "{}"

    monkeypatch.setattr("servers.services.playbook_compatibility_ai._call_llm", fake_call)
    unsafe = SOURCE.replace("name: Restart service", "name: glpat-0123456789abcdefghij")

    with pytest.raises(PlaybookAdaptationError, match="safety validation"):
        adapt_playbook_with_ai(unsafe, user_instruction="adapt")
    assert called is False


def test_ai_play_var_parameterization_is_not_rejected_by_semantic_guard(monkeypatch):
    async def fake_call(_prompt, _system_prompt, _execution_context):
        return json.dumps(
            {
                "edits": [
                    {
                        "old_text": "package_name: nginx",
                        "new_text": 'package_name: "{{ webterm_package_name }}"',
                        "reason": "Expose environment-specific package as a required runtime value",
                    }
                ],
                "assumptions": [],
            }
        )

    monkeypatch.setattr("servers.services.playbook_compatibility_ai._call_llm", fake_call)
    proposal = adapt_playbook_with_ai(
        SOURCE,
        bindings={"web": {"server_ids": [1], "group_ids": []}},
        user_instruction="parameterize environment-specific configuration",
    )

    assert proposal["method"] == "ai"
    assert proposal["semantic_guard"]["passed"] is True
    assert "webterm_package_name" in proposal["adapted_yaml"]


@pytest.mark.django_db
def test_unsaved_source_can_be_analyzed_and_adapted_before_save(monkeypatch):
    user = User.objects.create_user(username="unsaved_compat_user", password="pass123")
    from core_ui.views.access_views import _apply_access_profile

    _apply_access_profile(user, "pilot_operator")
    client = Client()
    client.force_login(user)
    syntax_ok = {"status": "passed", "passed": True, "message": "ok", "method": "test"}
    monkeypatch.setattr(
        "servers.views.server_playbook_compatibility_views.validate_playbook_syntax",
        lambda _yaml, **_kwargs: syntax_ok,
    )
    adapted = SOURCE.replace("package_name: nginx", 'package_name: "{{ webterm_package_name }}"')
    proposal = {
        "method": "ai",
        "adapted_yaml": adapted,
        "changes": ["Parameterize package name"],
        "assumptions": [],
        "semantic_guard": {"passed": True, "violations": []},
        "report": {"status": "needs_binding", "ready": False, "issues": []},
    }
    monkeypatch.setattr(
        "servers.views.server_playbook_compatibility_views.adapt_playbook_with_ai",
        lambda *_args, **_kwargs: proposal,
    )
    monkeypatch.setattr(
        "servers.views.server_playbook_compatibility_views.operational_provider_binding",
        lambda *_args, **_kwargs: None,
    )

    analyzed = client.post(
        "/servers/api/playbooks/compatibility/analyze/",
        data=json.dumps({"source_yaml": SOURCE, "syntax_check": True}),
        content_type="application/json",
    )
    assert analyzed.status_code == 200, analyzed.content
    assert analyzed.json()["report"]["syntax_check"]["passed"] is True

    adapted_response = client.post(
        "/servers/api/playbooks/compatibility/adapt/",
        data=json.dumps({"source_yaml": SOURCE}),
        content_type="application/json",
    )
    assert adapted_response.status_code == 200, adapted_response.content
    assert adapted_response.json()["proposal"] == proposal


@pytest.mark.django_db
def test_runtime_syntax_failure_blocks_combined_compatibility_report(monkeypatch):
    user = User.objects.create_user(username="syntax_failure_user", password="pass123")
    from core_ui.views.access_views import _apply_access_profile

    _apply_access_profile(user, "pilot_operator")
    client = Client()
    client.force_login(user)
    monkeypatch.setattr(
        "servers.views.server_playbook_compatibility_views.validate_playbook_syntax",
        lambda _yaml, **_kwargs: {
            "status": "failed",
            "passed": False,
            "message": "unbalanced jinja2 block or quotes",
            "method": "test",
        },
    )

    response = client.post(
        "/servers/api/playbooks/compatibility/analyze/",
        data=json.dumps({"source_yaml": SOURCE, "syntax_check": True}),
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    report = response.json()["report"]
    assert report["status"] == "blocked"
    assert report["ready"] is False
    assert report["syntax_check"]["passed"] is False
    assert any(issue["code"] == "ansible_syntax_failed" for issue in report["issues"])


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
            """- hosts: web
  connection: community.docker.docker
  tasks: []
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
        (
            """- hosts: web
  tasks:
    - action:
        module: copy
        args:
          src: /etc/passwd
          dest: /tmp/copied
""",
            "controller_path_forbidden",
        ),
        (
            """- hosts: web
  tasks:
    - action: copy src=/etc/passwd dest=/tmp/copied
""",
            "controller_path_forbidden",
        ),
        (
            """- hosts: web
  tasks:
    - ansible.builtin.copy:
      args:
        src: /etc/passwd
        dest: /tmp/copied
""",
            "controller_path_forbidden",
        ),
        (
            """- hosts: web
  tasks:
    - ansible.builtin.template: src=/etc/passwd dest=/tmp/copied
""",
            "controller_path_forbidden",
        ),
        (
            """- hosts: web
  tasks:
    - ansible.builtin.include_role:
        name: web
        tasks_from: ../../controller-task
""",
            "controller_path_forbidden",
        ),
        (
            """- hosts: web
  tasks:
    - ansible.builtin.copy:
        src: extra_vars.json
        dest: /tmp/exfil.json
""",
            "controller_path_forbidden",
        ),
        (
            """- hosts: web
  tasks:
    - copy: src=.\\inventory.ini dest=/tmp/inventory.ini
""",
            "controller_path_forbidden",
        ),
        (
            """- hosts: web
  tasks:
    - action: copy src=./key_42 dest=/tmp/key
""",
            "controller_path_forbidden",
        ),
        (
            """- hosts: web
  tasks:
    - action:
        module: copy src=known_hosts dest=/tmp/known_hosts
""",
            "controller_path_forbidden",
        ),
        (
            """- hosts: web
  tasks:
    - ansible.builtin.template:
        src: .
        dest: /tmp/runtime
""",
            "controller_path_forbidden",
        ),
        (
            """- hosts: web
  tasks:
    - action: copy src=./ dest=/tmp/runtime
""",
            "controller_path_forbidden",
        ),
        (
            """- hosts: web
  tasks:
    - ansible.builtin.copy:
      args:
        src: ./key_7
        dest: /tmp/key
""",
            "controller_path_forbidden",
        ),
        (
            """- hosts: web
  tasks:
    - ansible.builtin.unarchive: src=extra_vars.json dest=/tmp/unpacked remote_src=no
""",
            "controller_path_forbidden",
        ),
        (
            """- hosts: web
  tasks:
    - ansible.builtin.include_tasks:
        file: inventory.ini
""",
            "controller_path_forbidden",
        ),
        (
            """- hosts: web
  tasks:
    - ansible.builtin.script: known_hosts
""",
            "controller_path_forbidden",
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
    assert "details" not in issue
    assert plugin not in issue["message"]


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
    assert "controller_plugin" not in json.dumps(issue)


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
    from core_ui.views.access_views import _apply_access_profile

    _apply_access_profile(user, "pilot_operator")
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
    base = analyze.json()["base"]
    assert base["draft_version"] == base["version"]
    assert "bundle_hash" in base
    assert base["base_revision_id"]
    adapted_source = "# Compatibility checked\n" + SOURCE
    stale = client.post(
        f"/servers/api/playbooks/{playbook.id}/compatibility/apply/",
        data=json.dumps(
            {
                "adapted_yaml": adapted_source,
                "inventory_bindings": binding,
                "base_path": base["path"],
                "base_content_hash": "0" * 64,
                "base_bundle_hash": base["bundle_hash"],
                "base_version": base["version"],
            }
        ),
        content_type="application/json",
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "playbook_compatibility_stale"
    assert not PlaybookCompatibilityRevision.objects.filter(playbook=playbook).exists()

    applied = client.post(
        f"/servers/api/playbooks/{playbook.id}/compatibility/apply/",
        data=json.dumps(
            {
                "adapted_yaml": adapted_source,
                "inventory_bindings": binding,
                "changes": ["Record compatibility review"],
                "path": base["path"],
                "expected_content_hash": base["content_hash"],
                "expected_bundle_hash": base["bundle_hash"],
                "expected_draft_version": base["draft_version"],
                "base_revision_id": base["base_revision_id"],
            }
        ),
        content_type="application/json",
    )
    assert applied.status_code == 200, applied.content
    revision = PlaybookCompatibilityRevision.objects.get(playbook=playbook)
    assert revision.status == PlaybookCompatibilityRevision.STATUS_VALIDATED
    assert revision.result_revision_id is None
    assert applied.json()["draft"]["source_yaml"].strip() == adapted_source.strip()
    playbook.refresh_from_db()
    assert playbook.active_compatibility_revision_id is None
    assert playbook.published_revision_id == playbook.origin_revision_id
    assert playbook.published_revision_id == revision.source_revision_id
    assert playbook.source_yaml.strip() == SOURCE.strip()
    draft = PlaybookDraft.objects.get(playbook=playbook)
    assert draft.base_revision_id == revision.source_revision_id
    assert draft.source_yaml.strip() == adapted_source.strip()
    assert draft.asset_bundle_id is not None
    assert revision.source_revision.asset_bundle_id is None
    assert playbook.published_revision_id == playbook.origin_revision_id

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


@pytest.mark.django_db
def test_compatibility_applies_selected_role_yaml_with_bundle_clone_on_write(tmp_path):
    user = User.objects.create_user(username="compat_bundle", password="pass123", is_staff=True)
    output = BytesIO()
    role_source = "- name: Report role state\n  ansible.builtin.debug:\n    msg: ready\n"
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "playbook.yml",
            "- name: Deploy\n  hosts: all\n  gather_facts: false\n  tasks:\n    - ansible.builtin.debug:\n        msg: ready\n",
        )
        archive.writestr("roles/web/tasks/main.yml", role_source)

    with override_settings(PLAYBOOK_BUNDLE_STORAGE_ROOT=tmp_path / "bundles"):
        imported = commit_project_bundle(output.getvalue(), actor=user)
        original_asset_id = imported.asset_bundle.id
        client = Client()
        client.force_login(user)
        analyzed = client.post(
            f"/servers/api/playbooks/{imported.playbook.id}/compatibility/analyze/",
            data=json.dumps({"path": "roles/web/tasks/main.yml"}),
            content_type="application/json",
        )
        assert analyzed.status_code == 200, analyzed.content
        base = analyzed.json()["base"]
        assert base["bundle_hash"] == imported.revision.bundle_hash

        adapted = role_source.replace("Report role state", "Report current role state")
        applied = client.post(
            f"/servers/api/playbooks/{imported.playbook.id}/compatibility/apply/",
            data=json.dumps(
                {
                    "path": base["path"],
                    "expected_content_hash": base["content_hash"],
                    "expected_bundle_hash": base["bundle_hash"],
                    "expected_draft_version": base["draft_version"],
                    "base_revision_id": base["base_revision_id"],
                    "adapted_yaml": adapted,
                }
            ),
            content_type="application/json",
        )
        assert applied.status_code == 200, applied.content

    draft = PlaybookDraft.objects.get(playbook=imported.playbook)
    assert draft.asset_bundle_id != original_asset_id
    imported.revision.refresh_from_db()
    assert imported.revision.asset_bundle_id == original_asset_id
    assert imported.revision.bundle_hash == base["bundle_hash"]


@pytest.mark.django_db
def test_compatibility_legacy_alias_requires_bundle_hash_and_detects_other_file_change(tmp_path):
    user = User.objects.create_user(username="compat_bundle_stale", password="pass123", is_staff=True)
    output = BytesIO()
    role_source = "- name: Report role state\n  ansible.builtin.debug:\n    msg: ready\n"
    other_source = "- name: Other role\n  ansible.builtin.debug:\n    msg: ready\n"
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "playbook.yml",
            "- hosts: all\n  tasks:\n    - ansible.builtin.debug:\n        msg: ready\n",
        )
        archive.writestr("roles/web/tasks/main.yml", role_source)
        archive.writestr("roles/other/tasks/main.yml", other_source)

    with override_settings(PLAYBOOK_BUNDLE_STORAGE_ROOT=tmp_path / "bundles"):
        imported = commit_project_bundle(output.getvalue(), actor=user)
        client = Client()
        client.force_login(user)
        analyzed = client.post(
            f"/servers/api/playbooks/{imported.playbook.id}/compatibility/analyze/",
            data=json.dumps({"path": "roles/web/tasks/main.yml"}),
            content_type="application/json",
        )
        assert analyzed.status_code == 200, analyzed.content
        base = analyzed.json()["base"]
        missing_bundle = client.post(
            f"/servers/api/playbooks/{imported.playbook.id}/compatibility/apply/",
            data=json.dumps(
                {
                    "base_path": base["path"],
                    "base_content_hash": base["content_hash"],
                    "base_revision_id": base["base_revision_id"],
                    "adapted_yaml": role_source,
                }
            ),
            content_type="application/json",
        )
        assert missing_bundle.status_code == 400
        assert missing_bundle.json()["code"] == "playbook_compatibility_base_required"

        tree = client.get(f"/servers/api/playbooks/{imported.playbook.id}/draft/files/").json()["tree"]
        changed = client.patch(
            f"/servers/api/playbooks/{imported.playbook.id}/draft/file/",
            data=json.dumps(
                {
                    "path": "roles/other/tasks/main.yml",
                    "content": other_source.replace("Other role", "Changed other role"),
                    "expected_draft_version": tree["draft_version"],
                    "expected_bundle_hash": tree["bundle_hash"],
                }
            ),
            content_type="application/json",
        )
        assert changed.status_code == 200, changed.content
        stale = client.post(
            f"/servers/api/playbooks/{imported.playbook.id}/compatibility/apply/",
            data=json.dumps(
                {
                    "base_path": base["path"],
                    "base_content_hash": base["content_hash"],
                    "base_bundle_hash": base["bundle_hash"],
                    "base_revision_id": base["base_revision_id"],
                    "adapted_yaml": role_source,
                }
            ),
            content_type="application/json",
        )

    assert stale.status_code == 409
    assert stale.json()["code"] == "playbook_compatibility_stale"
    assert stale.json()["details"]["current"]["content_hash"] == base["content_hash"]
    assert stale.json()["details"]["current"]["base_revision_id"] == base["base_revision_id"]
    assert stale.json()["details"]["current"]["bundle_hash"] != base["bundle_hash"]
