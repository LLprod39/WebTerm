import json
from concurrent.futures import Future
from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.utils import timezone

from app.runtime_limits import get_terminal_session_limit_error
from core_ui.models import UserAppPermission
from servers.agent_engine import AgentEngine
from servers.models import (
    AgentRun,
    Server,
    ServerAgent,
    ServerAlert,
    ServerConnection,
    ServerHealthCheck,
)


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _csrf_token(client: Client) -> str:
    response = client.get("/api/auth/csrf/")
    assert response.status_code == 200
    return client.cookies["csrftoken"].value


def _create_server(user: User, **kwargs) -> Server:
    return Server.objects.create(
        user=user,
        name=kwargs.pop("name", "srv-01"),
        host=kwargs.pop("host", "10.0.0.11"),
        username=kwargs.pop("username", "root"),
        auth_method=kwargs.pop("auth_method", "password"),
        **kwargs,
    )


def _make_public_key_record() -> dict[str, str]:
    import asyncssh

    private_key = asyncssh.generate_private_key("ssh-ed25519")
    public_key = private_key.export_public_key("openssh")
    if isinstance(public_key, bytes):
        public_key = public_key.decode("utf-8")
    parsed_key = asyncssh.import_public_key(public_key)
    return {
        "public_key": public_key.strip(),
        "algorithm": parsed_key.get_algorithm(),
        "fingerprint_sha256": parsed_key.get_fingerprint("sha256"),
        "trusted_at": "2026-03-12T00:00:00+00:00",
    }


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


@pytest.mark.django_db
def test_group_server_and_context_crud_endpoints():
    user = User.objects.create_user(username="servers-user", password="x")
    teammate = User.objects.create_user(username="teammate", password="x")
    client = Client()
    client.force_login(user)

    create_group = client.post(
        "/servers/api/groups/create/",
        data=_json({"name": "prod", "description": "production"}),
        content_type="application/json",
    )
    assert create_group.status_code == 200
    group_id = create_group.json()["group_id"]

    bootstrap_with_empty_group = client.get("/servers/api/frontend/bootstrap/")
    assert bootstrap_with_empty_group.status_code == 200
    bootstrap_groups = bootstrap_with_empty_group.json()["groups"]
    created_group = next(group for group in bootstrap_groups if group["id"] == group_id)
    assert created_group["server_count"] == 0
    assert created_group["description"] == "production"
    assert created_group["color"] == "#3b82f6"
    assert created_group["role"] == "owner"
    assert created_group["can_edit"] is True

    update_group = client.post(
        f"/servers/api/groups/{group_id}/update/",
        data=_json({"name": "prod-updated", "color": "#111111"}),
        content_type="application/json",
    )
    assert update_group.status_code == 200
    assert update_group.json()["success"] is True

    add_member = client.post(
        f"/servers/api/groups/{group_id}/add-member/",
        data=_json({"user": teammate.username, "role": "member"}),
        content_type="application/json",
    )
    assert add_member.status_code == 200
    assert add_member.json()["success"] is True

    teammate_client = Client()
    teammate_client.force_login(teammate)
    teammate_bootstrap = teammate_client.get("/servers/api/frontend/bootstrap/")
    assert teammate_bootstrap.status_code == 200
    teammate_group = next(group for group in teammate_bootstrap.json()["groups"] if group["id"] == group_id)
    assert teammate_group["role"] == "member"
    assert teammate_group["can_edit"] is False

    remove_member = client.post(
        f"/servers/api/groups/{group_id}/remove-member/",
        data=_json({"user_id": teammate.id}),
        content_type="application/json",
    )
    assert remove_member.status_code == 200
    assert remove_member.json()["success"] is True

    subscribe = client.post(
        f"/servers/api/groups/{group_id}/subscribe/",
        data=_json({"kind": "favorite"}),
        content_type="application/json",
    )
    assert subscribe.status_code == 200
    assert subscribe.json()["success"] is True

    create_server = client.post(
        "/servers/api/create/",
        data=_json(
            {
                "name": "web-01",
                "host": "10.0.0.21",
                "port": 22,
                "username": "root",
                "group_id": group_id,
                "server_type": "ssh",
                "auth_method": "password",
            }
        ),
        content_type="application/json",
    )
    assert create_server.status_code == 200
    server_id = create_server.json()["server_id"]

    bootstrap = client.get("/servers/api/frontend/bootstrap/")
    assert bootstrap.status_code == 200
    assert bootstrap.json()["success"] is True
    assert any(item["id"] == server_id for item in bootstrap.json()["servers"])

    details = client.get(f"/servers/api/{server_id}/get/")
    assert details.status_code == 200
    assert details.json()["name"] == "web-01"

    update_server = client.post(
        f"/servers/api/{server_id}/update/",
        data=_json(
            {
                "name": "web-01-updated",
                "network_config": {"proxy": {"http_proxy": "http://proxy.local:8080"}},
                "tags": "prod,ssh",
            }
        ),
        content_type="application/json",
    )
    assert update_server.status_code == 200
    assert update_server.json()["success"] is True

    bulk_update = client.post(
        "/servers/api/bulk-update/",
        data=_json({"server_ids": [server_id], "tags": "prod,critical", "is_active": True}),
        content_type="application/json",
    )
    assert bulk_update.status_code == 200
    assert bulk_update.json()["success"] is True

    save_global = client.post(
        "/servers/api/global-context/save/",
        data=_json({"rules": "Do backups", "forbidden_commands": ["rm -rf /"]}),
        content_type="application/json",
    )
    assert save_global.status_code == 200
    assert save_global.json()["success"] is True

    global_ctx = client.get("/servers/api/global-context/")
    assert global_ctx.status_code == 200
    assert global_ctx.json()["rules"] == "Do backups"

    save_group_ctx = client.post(
        f"/servers/api/groups/{group_id}/context/save/",
        data=_json({"rules": "Only change in maintenance window", "forbidden_commands": ["reboot"]}),
        content_type="application/json",
    )
    assert save_group_ctx.status_code == 200
    assert save_group_ctx.json()["success"] is True

    group_ctx = client.get(f"/servers/api/groups/{group_id}/context/")
    assert group_ctx.status_code == 200
    assert group_ctx.json()["rules"] == "Only change in maintenance window"

    delete_server = client.post(f"/servers/api/{server_id}/delete/")
    assert delete_server.status_code == 200
    assert delete_server.json()["success"] is True

    delete_group = client.post(f"/servers/api/groups/{group_id}/delete/")
    assert delete_group.status_code == 200
    assert delete_group.json()["success"] is True


@pytest.mark.django_db
def test_share_master_password_and_knowledge_endpoints(monkeypatch):
    owner = User.objects.create_user(username="owner", password="x")
    teammate = User.objects.create_user(username="shared-user", password="x")
    client = Client()
    client.force_login(owner)

    server = _create_server(owner, name="share-me", server_type="ssh", port=22)

    create_share = client.post(
        f"/servers/api/{server.id}/share/",
        data=_json({"user": teammate.username, "share_context": True}),
        content_type="application/json",
    )
    assert create_share.status_code == 200
    share_id = create_share.json()["share"]["id"]

    shares = client.get(f"/servers/api/{server.id}/shares/")
    assert shares.status_code == 200
    assert len(shares.json()["shares"]) == 1

    revoke = client.post(f"/servers/api/{server.id}/shares/{share_id}/revoke/")
    assert revoke.status_code == 200
    assert revoke.json()["success"] is True

    set_mp = client.post(
        "/servers/api/master-password/set/",
        data=_json({"master_password": "master-secret"}),
        content_type="application/json",
    )
    assert set_mp.status_code == 200
    assert set_mp.json()["success"] is True

    has_mp = client.get("/servers/api/master-password/check/")
    assert has_mp.status_code == 200
    assert has_mp.json()["has_master_password"] is True

    clear_mp = client.post("/servers/api/master-password/clear/")
    assert clear_mp.status_code == 200
    assert clear_mp.json()["success"] is True

    create_knowledge = client.post(
        f"/servers/api/{server.id}/knowledge/create/",
        data=_json({"title": "Nginx path", "content": "/etc/nginx/nginx.conf", "category": "config"}),
        content_type="application/json",
    )
    assert create_knowledge.status_code == 200
    knowledge_id = create_knowledge.json()["id"]

    list_knowledge = client.get(f"/servers/api/{server.id}/knowledge/")
    assert list_knowledge.status_code == 200
    assert list_knowledge.json()["success"] is True
    assert len(list_knowledge.json()["items"]) == 1

    update_knowledge = client.post(
        f"/servers/api/{server.id}/knowledge/{knowledge_id}/update/",
        data=_json({"title": "Nginx main config", "is_active": False, "confidence": 0.6}),
        content_type="application/json",
    )
    assert update_knowledge.status_code == 200
    assert update_knowledge.json()["success"] is True

    delete_knowledge = client.post(
        f"/servers/api/{server.id}/knowledge/{knowledge_id}/delete/",
        content_type="application/json",
    )
    assert delete_knowledge.status_code == 200
    assert delete_knowledge.json()["success"] is True

    server.auth_method = "password"
    server.encrypted_password = "ciphertext"
    server.salt = b"12345678"
    server.save(update_fields=["auth_method", "encrypted_password", "salt"])

    monkeypatch.setattr(
        "servers.views.PasswordEncryption.decrypt_password",
        lambda *_args, **_kwargs: "plain-password",
    )
    reveal = client.post(
        f"/servers/api/{server.id}/reveal-password/",
        data=_json({"master_password": "master-secret"}),
        content_type="application/json",
    )
    assert reveal.status_code == 200
    assert reveal.json()["success"] is True
    assert reveal.json()["password"] == "plain-password"


@pytest.mark.django_db
def test_server_test_and_execute_endpoints_use_mocked_ssh(monkeypatch):
    user = User.objects.create_user(username="ssh-user", password="x")
    client = Client()
    client.force_login(user)
    server = _create_server(user, name="ssh-node", server_type="ssh", port=22)

    async def fake_connect(*_args, **_kwargs):
        return "conn-1"

    async def fake_disconnect(_conn_id):
        return None

    async def fake_execute(self, conn_id, command, allow_destructive=False):
        assert conn_id == "conn-1"
        assert command == "uname -a"
        assert allow_destructive is False
        return {"stdout": "Linux test\n", "stderr": "", "exit_code": 0, "success": True}

    monkeypatch.setattr("servers.views.ssh_manager.connect", fake_connect)
    monkeypatch.setattr("servers.views.ssh_manager.disconnect", fake_disconnect)
    monkeypatch.setattr("app.tools.ssh_tools.SSHExecuteTool.execute", fake_execute)
    monkeypatch.setattr("servers.views.ServerCommandHistory.objects.create", lambda *args, **kwargs: None)

    test_connection = client.post(
        f"/servers/api/{server.id}/test/",
        data=_json({}),
        content_type="application/json",
    )
    assert test_connection.status_code == 200
    assert test_connection.json()["success"] is True

    execute = client.post(
        f"/servers/api/{server.id}/execute/",
        data=_json({"command": "uname -a"}),
        content_type="application/json",
    )
    assert execute.status_code == 200
    assert execute.json()["success"] is True
    assert execute.json()["output"]["exit_code"] == 0


@pytest.mark.django_db
def test_monitoring_alerts_and_ai_analyze_endpoints(monkeypatch):
    user = User.objects.create_user(username="monitor-user", password="x")
    staff = User.objects.create_user(username="monitor-staff", password="x", is_staff=True)
    client = Client()
    client.force_login(user)
    server = _create_server(user, name="monitored", server_type="ssh")

    existing_check = ServerHealthCheck.objects.create(
        server=server,
        status=ServerHealthCheck.STATUS_WARNING,
        cpu_percent=81.0,
        memory_percent=72.0,
        disk_percent=66.0,
    )
    alert = ServerAlert.objects.create(
        server=server,
        alert_type=ServerAlert.TYPE_CPU,
        severity=ServerAlert.SEVERITY_WARNING,
        title="CPU high",
        message="CPU usage above warning threshold",
    )

    dashboard = client.get("/servers/api/monitoring/dashboard/")
    assert dashboard.status_code == 200
    assert dashboard.json()["success"] is True

    history = client.get(f"/servers/api/{server.id}/health/?hours=24")
    assert history.status_code == 200
    assert history.json()["success"] is True
    assert history.json()["checks"][0]["id"] == existing_check.id

    async def fake_check_server(_target_server, deep=False):
        return SimpleNamespace(
            id=999,
            status=ServerHealthCheck.STATUS_HEALTHY,
            cpu_percent=30.0,
            memory_percent=45.0,
            disk_percent=40.0,
            load_1m=0.2,
            is_deep=deep,
            response_time_ms=12,
            checked_at=timezone.now(),
        )

    monkeypatch.setattr("servers.monitor.check_server", fake_check_server)

    check_now = client.post(
        f"/servers/api/{server.id}/health/check/",
        data=_json({"deep": True}),
        content_type="application/json",
    )
    assert check_now.status_code == 200
    assert check_now.json()["success"] is True
    assert check_now.json()["check"]["status"] == ServerHealthCheck.STATUS_HEALTHY

    list_alerts = client.get("/servers/api/alerts/")
    assert list_alerts.status_code == 200
    assert list_alerts.json()["success"] is True
    assert any(item["id"] == alert.id for item in list_alerts.json()["alerts"])

    resolve = client.post(f"/servers/api/alerts/{alert.id}/resolve/")
    assert resolve.status_code == 200
    assert resolve.json()["success"] is True

    async def fake_stream_chat(self, prompt: str, model: str = "auto", purpose: str = "chat"):
        assert "Проанализируй сервер" in prompt
        yield "## Резюме\nСервер стабилен."

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)

    ai = client.post(f"/servers/api/{server.id}/ai-analyze/", data=_json({}), content_type="application/json")
    assert ai.status_code == 200
    assert ai.json()["success"] is True
    assert "Резюме" in ai.json()["analysis"]

    staff_client = Client()
    staff_client.force_login(staff)

    mon_cfg_get = staff_client.get("/servers/api/monitoring/config/")
    assert mon_cfg_get.status_code == 200
    assert mon_cfg_get.json()["success"] is True

    mon_cfg_post = staff_client.post(
        "/servers/api/monitoring/config/",
        data=_json({"thresholds": {"cpu_warn": 75, "cpu_crit": 90}}),
        content_type="application/json",
    )
    assert mon_cfg_post.status_code == 200
    assert mon_cfg_post.json()["success"] is True


@pytest.mark.django_db
def test_servers_mutation_endpoints_require_csrf_when_enforced():
    user = User.objects.create_user(username="servers-csrf-user", password="x")
    _grant_feature(user, "servers")
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)

    rejected = client.post(
        "/servers/api/groups/create/",
        data=_json({"name": "prod", "description": "production"}),
        content_type="application/json",
    )
    assert rejected.status_code == 403

    token = _csrf_token(client)
    accepted = client.post(
        "/servers/api/groups/create/",
        data=_json({"name": "prod", "description": "production"}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert accepted.status_code == 200
    assert accepted.json()["success"] is True


@pytest.mark.django_db
def test_full_agent_run_launches_in_background(monkeypatch):
    user = User.objects.create_user(username="full-agent-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user)
    agent = ServerAgent.objects.create(
        user=user,
        name="Full Agent",
        mode=ServerAgent.MODE_FULL,
        agent_type=ServerAgent.TYPE_CUSTOM,
        goal="Inspect the server",
        ai_prompt="Check the host",
    )
    agent.servers.set([server])

    captured: dict[str, object] = {}

    def fake_launch(run_id: int, agent_id: int, server_ids: list[int], user_id: int, *, plan_only: bool = False):
        captured.update({
            "run_id": run_id,
            "agent_id": agent_id,
            "server_ids": server_ids,
            "user_id": user_id,
            "plan_only": plan_only,
        })

    monkeypatch.setattr("servers.views.launch_agent_run_background", fake_launch)

    response = client.post(
        f"/servers/api/agents/{agent.id}/run/",
        data=_json({}),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["run_id"] == payload["runs"][0]["run_id"]
    assert payload["status"] == AgentRun.STATUS_PENDING

    run = AgentRun.objects.get(pk=payload["run_id"])
    assert run.status == AgentRun.STATUS_PENDING
    assert captured == {
        "run_id": run.id,
        "agent_id": agent.id,
        "server_ids": [server.id],
        "user_id": user.id,
        "plan_only": False,
    }

    duplicate = client.post(
        f"/servers/api/agents/{agent.id}/run/",
        data=_json({}),
        content_type="application/json",
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["success"] is False


@pytest.mark.django_db
@override_settings(AGENT_ACTIVE_RUNS_PER_USER_LIMIT=1, AGENT_ACTIVE_RUNS_GLOBAL_LIMIT=0)
def test_full_agent_run_enforces_user_active_run_limit(monkeypatch):
    user = User.objects.create_user(username="agent-limit-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user)
    first_agent = ServerAgent.objects.create(
        user=user,
        name="First Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect server",
    )
    second_agent = ServerAgent.objects.create(
        user=user,
        name="Second Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect another server",
    )
    first_agent.servers.set([server])
    second_agent.servers.set([server])

    AgentRun.objects.create(
        agent=first_agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_RUNNING,
    )

    monkeypatch.setattr(
        "servers.views.launch_agent_run_background",
        lambda **_kwargs: pytest.fail("launch_agent_run_background should not run when the active-run limit is hit"),
    )

    response = client.post(
        f"/servers/api/agents/{second_agent.id}/run/",
        data=_json({}),
        content_type="application/json",
    )

    assert response.status_code == 429
    payload = response.json()
    assert payload["success"] is False
    assert payload["code"] == "agent_user_limit_reached"
    assert payload["limit"] == 1
    assert payload["active"] == 1


@pytest.mark.django_db
@override_settings(SSH_TERMINAL_SESSIONS_PER_USER_LIMIT=1, SSH_TERMINAL_SESSIONS_GLOBAL_LIMIT=0)
def test_terminal_session_limit_helper_enforces_user_limit():
    user = User.objects.create_user(username="terminal-limit-user", password="x")
    server = _create_server(user, name="term-limit-srv")
    ServerConnection.objects.create(
        server=server,
        user=user,
        connection_id="term-existing-1",
        status="connected",
    )

    error = get_terminal_session_limit_error(user)

    assert error is not None
    assert error["code"] == "terminal_user_limit_reached"
    assert error["scope"] == "user"
    assert error["limit"] == 1


@pytest.mark.django_db
def test_multi_agent_approve_plan_launches_in_background(monkeypatch):
    user = User.objects.create_user(username="multi-approve-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user)
    agent = ServerAgent.objects.create(
        user=user,
        name="Multi Agent",
        mode=ServerAgent.MODE_MULTI,
        agent_type=ServerAgent.TYPE_MULTI_HEALTH,
        goal="Check all systems",
        ai_prompt="Prepare a plan",
        allow_multi_server=True,
    )
    agent.servers.set([server])

    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_PLAN_REVIEW,
        plan_tasks=[{"id": 1, "name": "Check logs", "description": "Inspect logs", "status": "pending"}],
    )

    captured: dict[str, object] = {}

    def fake_launch(run_id: int, agent_id: int, server_ids: list[int], user_id: int):
        captured.update({
            "run_id": run_id,
            "agent_id": agent_id,
            "server_ids": server_ids,
            "user_id": user_id,
        })

    monkeypatch.setattr("servers.views.launch_plan_execution_background", fake_launch)

    response = client.post(f"/servers/api/agents/runs/{run.id}/approve-plan/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["run_id"] == run.id
    assert payload["status"] == AgentRun.STATUS_PENDING

    run.refresh_from_db()
    assert run.status == AgentRun.STATUS_PENDING
    assert captured == {
        "run_id": run.id,
        "agent_id": agent.id,
        "server_ids": [server.id],
        "user_id": user.id,
    }


@pytest.mark.django_db
def test_agent_endpoints_crud_run_and_control_flow(monkeypatch):
    user = User.objects.create_user(username="agent-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)
    server = _create_server(user, name="agent-srv", server_type="ssh")

    templates = client.get("/servers/api/agents/templates/")
    assert templates.status_code == 200
    assert templates.json()["success"] is True

    create_agent = client.post(
        "/servers/api/agents/create/",
        data=_json(
            {
                "mode": "mini",
                "agent_type": "custom",
                "name": "Ops Agent",
                "commands": ["uname -a"],
                "server_ids": [server.id],
            }
        ),
        content_type="application/json",
    )
    assert create_agent.status_code == 200
    assert create_agent.json()["success"] is True
    agent_id = create_agent.json()["id"]

    list_agents = client.get("/servers/api/agents/")
    assert list_agents.status_code == 200
    assert list_agents.json()["success"] is True
    assert any(item["id"] == agent_id for item in list_agents.json()["agents"])

    update_agent = client.post(
        f"/servers/api/agents/{agent_id}/update/",
        data=_json({"name": "Ops Agent v2", "max_iterations": 25}),
        content_type="application/json",
    )
    assert update_agent.status_code == 200
    assert update_agent.json()["success"] is True

    def _build_run(status: str) -> AgentRun:
        return AgentRun.objects.create(
            agent_id=agent_id,
            server=server,
            user=user,
            status=status,
            ai_analysis="ok",
            commands_output=[{"cmd": "uname -a", "stdout": "Linux"}],
        )

    completed_run = _build_run(AgentRun.STATUS_COMPLETED)

    async def fake_run_agent_on_all_servers(_agent, _user):
        return [completed_run]

    monkeypatch.setattr("servers.agents.run_agent_on_all_servers", fake_run_agent_on_all_servers)

    run_agent = client.post(
        f"/servers/api/agents/{agent_id}/run/",
        data=_json({}),
        content_type="application/json",
    )
    assert run_agent.status_code == 200
    assert run_agent.json()["success"] is True
    run_id = run_agent.json()["runs"][0]["run_id"]

    runs = client.get(f"/servers/api/agents/{agent_id}/runs/")
    assert runs.status_code == 200
    assert runs.json()["success"] is True

    run_detail = client.get(f"/servers/api/agents/runs/{run_id}/")
    assert run_detail.status_code == 200
    assert run_detail.json()["success"] is True

    run_log = client.get(f"/servers/api/agents/runs/{run_id}/log/")
    assert run_log.status_code == 200
    assert run_log.json()["success"] is True

    waiting_run = _build_run(AgentRun.STATUS_WAITING)
    waiting_run.pending_question = "Need approval?"
    waiting_run.save(update_fields=["pending_question"])

    reply = client.post(
        f"/servers/api/agents/runs/{waiting_run.id}/reply/",
        data=_json({"answer": "Proceed"}),
        content_type="application/json",
    )
    assert reply.status_code == 200
    assert reply.json()["success"] is True
    waiting_run.refresh_from_db()
    assert waiting_run.runtime_control["reply_nonce"] == 1
    assert waiting_run.runtime_control["reply_ack_nonce"] == 0
    assert waiting_run.runtime_control["reply_text"] == "Proceed"
    assert waiting_run.status == AgentRun.STATUS_RUNNING
    assert waiting_run.pending_question == ""

    running_run = _build_run(AgentRun.STATUS_RUNNING)
    stop = client.post(f"/servers/api/agents/{agent_id}/stop/")
    assert stop.status_code == 200
    assert stop.json()["success"] is True
    running_run.refresh_from_db()
    assert running_run.status == AgentRun.STATUS_STOPPED
    assert running_run.runtime_control["stop_requested"] is True
    assert running_run.runtime_control["pause_requested"] is False

    editable_run = _build_run(AgentRun.STATUS_PLAN_REVIEW)
    editable_run.plan_tasks = [
        {"id": 1, "name": "Check logs", "description": "Inspect journalctl", "status": "pending"}
    ]
    editable_run.save(update_fields=["plan_tasks"])

    update_task = client.post(
        f"/servers/api/agents/runs/{editable_run.id}/tasks/1/update/",
        data=_json({"action": "update", "name": "Check logs and disk"}),
        content_type="application/json",
    )
    assert update_task.status_code == 200
    assert update_task.json()["success"] is True
    assert update_task.json()["plan_tasks"][0]["name"] == "Check logs and disk"

    async def fake_stream_chat(self, prompt: str, model: str = "auto", purpose: str = "chat"):
        assert "Верни ТОЛЬКО JSON-объект" in prompt
        yield '{"name":"Refined task","description":"Updated by AI"}'

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)

    refine_task = client.post(
        f"/servers/api/agents/runs/{editable_run.id}/tasks/1/ai-refine/",
        data=_json({"instruction": "Сделай задачу точнее"}),
        content_type="application/json",
    )
    assert refine_task.status_code == 200
    assert refine_task.json()["success"] is True
    assert refine_task.json()["task"]["name"] == "Refined task"

    dashboard = client.get("/servers/api/agents/dashboard/")
    assert dashboard.status_code == 200
    assert dashboard.json()["success"] is True

    delete_agent = client.post(f"/servers/api/agents/{agent_id}/delete/")
    assert delete_agent.status_code == 200
    assert delete_agent.json()["success"] is True


@pytest.mark.django_db
def test_agent_engine_syncs_reply_from_runtime_control():
    user = User.objects.create_user(username="runtime-sync-user", password="x")
    server = _create_server(user, name="sync-srv", server_type="ssh")
    agent = ServerAgent.objects.create(
        user=user,
        name="Sync Agent",
        mode=ServerAgent.MODE_FULL,
        agent_type=ServerAgent.TYPE_CUSTOM,
        goal="Wait for user input",
        ai_prompt="Wait",
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_WAITING,
        pending_question="Continue?",
        runtime_control={
            "stop_requested": False,
            "pause_requested": False,
            "reply_nonce": 1,
            "reply_ack_nonce": 0,
            "reply_text": "Proceed",
        },
    )

    engine = AgentEngine(agent, [server], user)
    engine.run_record = run
    engine.session = SimpleNamespace(user_reply_future=Future())

    async_to_sync(engine._sync_runtime_control)()

    assert engine.session.user_reply_future.done() is True
    assert engine.session.user_reply_future.result() == "Proceed"

    run.refresh_from_db()
    assert run.runtime_control["reply_ack_nonce"] == 1
    assert run.runtime_control["reply_text"] == ""


@pytest.mark.django_db
def test_agent_control_paths_do_not_require_live_engine(monkeypatch):
    user = User.objects.create_user(username="agent-no-engine-user", password="x")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="agent-no-engine-srv", server_type="ssh")
    agent = ServerAgent.objects.create(
        user=user,
        name="No Engine Agent",
        mode=ServerAgent.MODE_FULL,
        agent_type=ServerAgent.TYPE_CUSTOM,
        goal="Wait for input",
        ai_prompt="Wait",
    )
    agent.servers.set([server])

    waiting_run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_WAITING,
        pending_question="Continue?",
    )
    running_run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_RUNNING,
    )

    monkeypatch.setattr("servers.views.get_engine_for_run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("servers.views.get_engine_for_agent", lambda *_args, **_kwargs: None)

    reply = client.post(
        f"/servers/api/agents/runs/{waiting_run.id}/reply/",
        data=_json({"answer": "Proceed without local engine"}),
        content_type="application/json",
    )
    assert reply.status_code == 200
    waiting_run.refresh_from_db()
    assert waiting_run.status == AgentRun.STATUS_RUNNING
    assert waiting_run.runtime_control["reply_nonce"] == 1
    assert waiting_run.runtime_control["reply_ack_nonce"] == 0
    assert waiting_run.runtime_control["reply_text"] == "Proceed without local engine"

    stop = client.post(f"/servers/api/agents/{agent.id}/stop/")
    assert stop.status_code == 200
    assert stop.json()["stop_signal_sent"] is False
    running_run.refresh_from_db()
    assert running_run.status == AgentRun.STATUS_STOPPED
    assert running_run.runtime_control["stop_requested"] is True
    assert running_run.runtime_control["pause_requested"] is False


@pytest.mark.django_db
def test_agent_stop_can_target_specific_run():
    user = User.objects.create_user(username="agent-stop-target-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="agent-stop-target-srv", server_type="ssh")
    agent = ServerAgent.objects.create(
        user=user,
        name="Targeted Stop Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Stop only selected run",
    )
    agent.servers.set([server])

    target_run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_RUNNING,
    )
    other_run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_WAITING,
        pending_question="Continue?",
    )

    response = client.post(
        f"/servers/api/agents/{agent.id}/stop/",
        data=_json({"run_id": target_run.id}),
        content_type="application/json",
    )

    assert response.status_code == 200
    target_run.refresh_from_db()
    other_run.refresh_from_db()
    assert target_run.status == AgentRun.STATUS_STOPPED
    assert target_run.runtime_control["stop_requested"] is True
    assert other_run.status == AgentRun.STATUS_WAITING
    assert other_run.runtime_control.get("stop_requested", False) is False


@pytest.mark.django_db
def test_server_update_clears_trusted_host_keys_when_address_changes():
    user = User.objects.create_user(username="ssh-update-owner", password="x")
    client = Client()
    client.force_login(user)

    server = _create_server(
        user,
        host="10.0.0.11",
        port=22,
        auth_method="key",
        key_path="/tmp/id_ed25519",
        trusted_host_keys=[_make_public_key_record()],
    )

    response = client.post(
        f"/servers/api/{server.id}/update/",
        data=_json({"host": "10.0.0.99"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    server.refresh_from_db()
    assert server.trusted_host_keys == []


@pytest.mark.django_db
def test_server_test_connection_passes_server_to_ssh_manager(monkeypatch):
    user = User.objects.create_user(username="ssh-test-owner", password="x")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="ssh-check", host="10.0.0.25", port=2222, auth_method="password")
    calls: dict[str, object] = {}

    async def fake_connect(**kwargs):
        calls.update(kwargs)
        return "conn-1"

    async def fake_disconnect(conn_id: str):
        calls["disconnect_conn_id"] = conn_id

    monkeypatch.setattr("servers.views.ssh_manager.connect", fake_connect)
    monkeypatch.setattr("servers.views.ssh_manager.disconnect", fake_disconnect)

    response = client.post(
        f"/servers/api/{server.id}/test/",
        data=_json({}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert calls["server"] == server
    assert calls["network_config"] == {}
    assert calls["disconnect_conn_id"] == "conn-1"


@pytest.mark.django_db
def test_shared_user_cannot_refresh_trusted_host_key():
    owner = User.objects.create_user(username="ssh-owner-share", password="x")
    teammate = User.objects.create_user(username="ssh-shared-user", password="x")
    server = _create_server(owner, name="shared-ssh", auth_method="password")
    from servers.models import ServerShare

    ServerShare.objects.create(server=server, user=teammate, shared_by=owner, share_context=True)

    client = Client()
    client.force_login(teammate)
    response = client.post(
        f"/servers/api/{server.id}/test/",
        data=_json({"refresh_host_key": True}),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert "Only owner can refresh" in response.json()["error"]


@pytest.mark.django_db
def test_shared_user_server_detail_hides_saved_secret_and_context_flags():
    owner = User.objects.create_user(username="shared-detail-owner", password="x")
    teammate = User.objects.create_user(username="shared-detail-user", password="x")
    server = _create_server(
        owner,
        name="shared-detail-srv",
        auth_method="password",
        notes="owner notes",
        corporate_context="secret corp context",
        network_config={"proxy": {"http_proxy": "http://proxy.local:8080"}},
    )
    server.encrypted_password = "ciphertext"
    server.salt = b"12345678"
    server.save(update_fields=["encrypted_password", "salt"])

    from servers.models import ServerShare

    ServerShare.objects.create(server=server, user=teammate, shared_by=owner, share_context=False)

    client = Client()
    client.force_login(teammate)
    response = client.get(f"/servers/api/{server.id}/get/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["notes"] == ""
    assert payload["corporate_context"] == ""
    assert payload["network_config"] == {}
    assert payload["share_context_enabled"] is False
    assert payload["has_saved_password"] is False
    assert payload["can_view_password"] is False


@pytest.mark.django_db
def test_reveal_password_requires_master_password_or_session():
    owner = User.objects.create_user(username="reveal-owner", password="x")
    server = _create_server(owner, name="reveal-srv", auth_method="password")
    server.encrypted_password = "ciphertext"
    server.salt = b"12345678"
    server.save(update_fields=["encrypted_password", "salt"])

    client = Client()
    client.force_login(owner)
    response = client.post(
        f"/servers/api/{server.id}/reveal-password/",
        data=_json({}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "Master password is required" in response.json()["error"]


@pytest.mark.django_db
def test_group_member_cannot_read_group_environment_vars():
    owner = User.objects.create_user(username="group-owner", password="x")
    teammate = User.objects.create_user(username="group-member", password="x")
    client = Client()
    client.force_login(owner)

    create_group = client.post(
        "/servers/api/groups/create/",
        data=_json({"name": "secure-group"}),
        content_type="application/json",
    )
    assert create_group.status_code == 200
    group_id = create_group.json()["group_id"]

    add_member = client.post(
        f"/servers/api/groups/{group_id}/add-member/",
        data=_json({"user": teammate.username, "role": "member"}),
        content_type="application/json",
    )
    assert add_member.status_code == 200

    save_group_ctx = client.post(
        f"/servers/api/groups/{group_id}/context/save/",
        data=_json(
            {
                "rules": "Use maintenance window",
                "forbidden_commands": ["reboot"],
                "environment_vars": {"VPN_PROFILE": "prod-admin"},
            }
        ),
        content_type="application/json",
    )
    assert save_group_ctx.status_code == 200

    member_client = Client()
    member_client.force_login(teammate)
    group_ctx = member_client.get(f"/servers/api/groups/{group_id}/context/")

    assert group_ctx.status_code == 200
    assert group_ctx.json()["rules"] == "Use maintenance window"
    assert group_ctx.json()["environment_vars"] == {}
