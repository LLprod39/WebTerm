"""API tests for Automation / Playbooks."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from core_ui.models import UserAppPermission
from core_ui.views.access_views import _apply_access_profile
from servers.models import BackgroundWorkerState, Playbook, PlaybookRun, Server
from servers.services.playbooks.target_identity import target_connection_identity_hashes


@pytest.fixture
def user(db):
    value = User.objects.create_user(username="pb_user", password="testpass123")
    UserAppPermission.objects.create(user=value, feature="automation", allowed=True)
    return value


@pytest.fixture
def auth_client(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def server(user):
    return Server.objects.create(
        user=user,
        name="target-1",
        host="127.0.0.1",
        port=22,
        username="root",
        auth_method="key",
        is_active=True,
    )


@pytest.mark.django_db
def test_playbook_surface_requires_automation_but_staff_is_allowed():
    pilot = User.objects.create_user(username="pb_pilot", password="testpass123")
    _apply_access_profile(pilot, "pilot_user")
    pilot_client = Client()
    pilot_client.force_login(pilot)

    denied = pilot_client.get("/servers/api/playbooks/")
    assert denied.status_code == 403

    staff = User.objects.create_user(username="pb_staff", password="testpass123", is_staff=True)
    staff_client = Client()
    staff_client.force_login(staff)
    allowed = staff_client.get("/servers/api/playbooks/")
    assert allowed.status_code == 200


@pytest.mark.django_db
def test_restricted_pilot_playbooks_require_exact_pilot_operator_profile(monkeypatch):
    monkeypatch.setenv("PILOT_RESTRICTED_MODE", "true")
    custom = User.objects.create_user(username="pb_custom_automation", password="testpass123")
    UserAppPermission.objects.create(user=custom, feature="automation", allowed=True)
    staff = User.objects.create_user(username="pb_restricted_staff", password="testpass123", is_staff=True)
    operator = User.objects.create_user(username="pb_pilot_operator", password="testpass123")
    _apply_access_profile(operator, "pilot_operator")

    for denied_user in (custom, staff):
        denied_client = Client()
        denied_client.force_login(denied_user)
        assert denied_client.get("/servers/api/playbooks/").status_code == 403

    operator_client = Client()
    operator_client.force_login(operator)
    assert operator_client.get("/servers/api/playbooks/").status_code == 200


@pytest.mark.django_db
def test_playbook_crud_and_templates(auth_client, user):
    # list empty
    r = auth_client.get("/servers/api/playbooks/")
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["playbooks"] == []

    # templates
    r = auth_client.get("/servers/api/playbooks/templates/")
    assert r.status_code == 200
    templates = r.json()["templates"]
    assert len(templates) >= 1
    slug = templates[0]["slug"]

    # install template
    r = auth_client.post(f"/servers/api/playbooks/templates/{slug}/install/")
    assert r.status_code == 200
    pb = r.json()["playbook"]
    assert pb["name"]
    assert pb["task_count"] >= 1
    assert Playbook.objects.filter(user=user).count() == 1

    # create custom
    r = auth_client.post(
        "/servers/api/playbooks/create/",
        data=json.dumps(
            {
                "name": "Custom RB",
                "description": "test",
                "kind": "runbook",
                "category": "diagnose",
                "tasks": [{"id": "t1", "command": "uptime", "description": "up", "continue_on_error": False}],
            }
        ),
        content_type="application/json",
    )
    assert r.status_code == 200
    created = r.json()["playbook"]
    assert created["id"]

    # update
    r = auth_client.post(
        f"/servers/api/playbooks/{created['id']}/update/",
        data=json.dumps(
            {
                "name": "Custom RB2",
                "tasks": [{"id": "t1", "command": "hostname", "description": "", "continue_on_error": False}],
            }
        ),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.json()["playbook"]["name"] == "Custom RB2"

    # import ansible
    yaml_pb = """
- name: Imp
  hosts: all
  tasks:
    - name: Echo
      shell: echo ok
"""
    r = auth_client.post(
        "/servers/api/playbooks/import/",
        data=json.dumps({"content": yaml_pb, "filename": "imp.yml", "save": True}),
        content_type="application/json",
    )
    assert r.status_code == 200
    imported = r.json()["playbook"]
    assert imported["kind"] in ("runbook", "ansible")
    assert imported["fidelity"]["runnable"] >= 1


@pytest.mark.django_db
def test_playbook_create_accepts_ansible_source_without_command_tasks(auth_client, user):
    source_yaml = """- name: Source-only playbook
  hosts: all
  gather_facts: false
  tasks:
    - name: Show a message
      ansible.builtin.debug:
        msg: hello
"""

    response = auth_client.post(
        "/servers/api/playbooks/create/",
        data=json.dumps(
            {
                "name": "Source only",
                "kind": "ansible",
                "category": "custom",
                "source_yaml": source_yaml,
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    payload = response.json()["playbook"]
    assert payload["kind"] == "ansible"
    assert payload["source_yaml"] == source_yaml
    assert payload["tasks"] == []
    stored = Playbook.objects.get(id=payload["id"], user=user)
    assert stored.source_yaml == source_yaml
    assert stored.tasks == []


@pytest.mark.django_db
def test_playbook_update_accepts_source_only_and_keeps_yaml_as_execution_source(auth_client, user):
    playbook = Playbook.objects.create(
        user=user,
        name="Editable YAML",
        kind=Playbook.KIND_ANSIBLE,
        category=Playbook.CATEGORY_CUSTOM,
        tasks=[],
        source_yaml="- hosts: all\n  tasks: []\n",
    )
    next_source = """- name: Edited
  hosts: all
  tasks:
    - ansible.builtin.command: hostname
"""

    response = auth_client.post(
        f"/servers/api/playbooks/{playbook.id}/update/",
        data=json.dumps({"name": "Edited YAML", "source_yaml": next_source}),
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    payload = response.json()["playbook"]
    assert payload["kind"] == "ansible"
    assert payload["source_yaml"] == next_source
    assert payload["tasks"] == []
    playbook.refresh_from_db()
    assert playbook.source_yaml == next_source
    assert playbook.tasks == []


@pytest.mark.django_db
def test_playbook_create_still_rejects_empty_executable_content(auth_client):
    response = auth_client.post(
        "/servers/api/playbooks/create/",
        data=json.dumps({"name": "Empty", "kind": "ansible", "tasks": [], "source_yaml": "  "}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "YAML" in response.json()["error"]


@pytest.mark.django_db(transaction=True)
def test_playbook_run_dry_run(auth_client, user, server, monkeypatch):
    pb = Playbook.objects.create(
        user=user,
        name="Dry",
        kind=Playbook.KIND_RUNBOOK,
        category=Playbook.CATEGORY_DIAGNOSE,
        tasks=[{"id": "t1", "command": "uptime", "description": "up", "continue_on_error": False}],
    )

    # Force synchronous execution path by calling execute directly after create via run endpoint
    from servers.services import playbook_runner

    calls = []

    def fake_start(run_id, *, master_password=""):
        calls.append(run_id)
        playbook_runner.execute_playbook_run(run_id, master_password=master_password)

    monkeypatch.setattr(playbook_runner, "start_playbook_run_async", fake_start)
    # Patch the reference used by the run view (lives in server_playbook_run_views,
    # split out from server_playbooks for size limits).
    import servers.views.server_playbook_run_views as run_views_mod

    monkeypatch.setattr(run_views_mod, "start_playbook_run_async", fake_start)

    r = auth_client.post(
        f"/servers/api/playbooks/{pb.id}/run/",
        data=json.dumps(
            {
                "server_ids": [server.id],
                "dry_run": True,
                "concurrency": 2,
                # Force shell path so unit tests don't require real ansible-playbook/docker.
                "engine": "shell",
            }
        ),
        content_type="application/json",
    )
    assert r.status_code == 200, r.content
    run_payload = r.json()["run"]
    run_id = run_payload["id"]
    assert calls == [run_id]

    run = PlaybookRun.objects.get(pk=run_id)
    assert run.status == PlaybookRun.STATUS_COMPLETED
    assert run.options.get("dry_run") is True
    hosts = run.host_results
    assert len(hosts) == 1
    assert hosts[0]["task_results"][0]["status"] == "success"
    assert "dry-run" in (hosts[0]["task_results"][0]["output"] or "").lower()


@pytest.mark.django_db(transaction=True)
def test_playbook_run_shell_live_progress(auth_client, user, server, monkeypatch):
    """Shell engine persists live_log and per-task progress while executing."""
    from servers.services import playbook_runner

    pb = Playbook.objects.create(
        user=user,
        name="Live",
        kind=Playbook.KIND_RUNBOOK,
        category=Playbook.CATEGORY_DIAGNOSE,
        tasks=[
            {"id": "t1", "command": "uptime", "description": "Uptime", "continue_on_error": False},
            {"id": "t2", "command": "df -h", "description": "Disk", "continue_on_error": False},
        ],
    )

    class FakeExecuteTool:
        async def execute(self, *, conn_id, command, sudo_auth_mode=None, sudo_password=None):
            return {"stdout": f"ran {command}", "stderr": "", "exit_code": 0}

    class FakeSSHManager:
        async def connect(self, **kwargs):
            return "conn-1"

        async def disconnect(self, conn_id):
            return None

    # Per-server execution lives in playbook_runner_support (split out for size limits).
    monkeypatch.setattr("servers.services.playbook_runner_support.SSHExecuteTool", FakeExecuteTool)
    monkeypatch.setattr("servers.services.playbook_runner_support.ssh_manager", FakeSSHManager())

    run = PlaybookRun.objects.create(
        playbook=pb,
        user=user,
        status=PlaybookRun.STATUS_PENDING,
        playbook_snapshot={
            "id": pb.id,
            "name": pb.name,
            "tasks": pb.tasks,
            "source_yaml": "",
            "target_connection_identities": target_connection_identity_hashes([server]),
        },
        target_server_ids=[server.id],
        options={"engine": "shell", "concurrency": 1},
    )
    playbook_runner.execute_playbook_run(run.id)

    run.refresh_from_db()
    assert run.status == PlaybookRun.STATUS_COMPLETED
    assert "TASK [Uptime]" in run.live_log
    assert f"ok: [{server.name}]" in run.live_log
    assert run.progress.get("finished") is True
    assert run.progress.get("engine") == "shell"
    assert run.progress.get("tasks_done") == 2
    assert run.host_results[0]["task_results"][0]["status"] == "success"
    assert "ran uptime" in run.host_results[0]["task_results"][0]["output"]

    # serialized run exposes progress + live_log
    r = auth_client.get(f"/servers/api/playbooks/runs/{run.id}/")
    assert r.status_code == 200
    payload = r.json()["run"]
    assert payload["progress"]["finished"] is True
    assert "TASK [Uptime]" in payload["live_log"]


@pytest.mark.django_db
def test_inventory_preview(auth_client, server):
    r = auth_client.post(
        "/servers/api/playbooks/inventory/preview/",
        data=json.dumps({"server_ids": [server.id]}),
        content_type="application/json",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert "ansible_host" in body["inventory"]


@pytest.mark.django_db
def test_ansible_status_uses_isolated_control_plane(auth_client, monkeypatch):
    monkeypatch.setenv("WEBTERM_ANSIBLE_VALIDATOR_SOCKET", "/run/playbook-validator/validator.sock")
    monkeypatch.setattr("servers.views.server_playbooks.validator_runtime_available", lambda: True)
    BackgroundWorkerState.objects.create(
        worker_kind="playbook_execution",
        worker_key="test-worker",
        status=BackgroundWorkerState.STATUS_RUNNING,
        lease_expires_at=timezone.now() + timedelta(minutes=1),
    )

    response = auth_client.get("/servers/api/playbooks/ansible/status/")

    assert response.status_code == 200
    status = response.json()["ansible"]
    assert status["available"] is True
    assert status["method"] == "isolated-worker"
    assert status["worker_ready"] is True
