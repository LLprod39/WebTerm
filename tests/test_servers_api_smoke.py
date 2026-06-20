import json
import os
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.utils import timezone

from app.runtime_limits import get_terminal_session_limit_error
from core_ui.models import UserAppPermission
from servers.models import (
    AgentRun,
    AgentRunEvent,
    Server,
    ServerAgent,
    ServerAlert,
    ServerConnection,
    ServerHealthCheck,
    ServerKnowledge,
    ServerMemoryEpisode,
    ServerMemoryEvent,
    ServerMemoryRevalidation,
    ServerMemorySnapshot,
    ServerWatcherDraft,
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


def _make_private_key_text() -> str:
    import asyncssh

    private_key = asyncssh.generate_private_key("ssh-ed25519")
    exported = private_key.export_private_key(format_name="openssh")
    if isinstance(exported, bytes):
        return exported.decode("utf-8")
    return exported


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
def test_server_create_accepts_uploaded_ssh_private_key(tmp_path):
    user = User.objects.create_user(username="ssh-key-user", password="x")
    _grant_feature(user, "servers")

    client = Client()
    client.force_login(user)
    key_text = _make_private_key_text()

    with override_settings(SSH_PRIVATE_KEYS_DIR=tmp_path / "ssh_keys"):
        response = client.post(
            "/servers/api/create/",
            data=_json(
                {
                    "name": "keyed-srv",
                    "host": "10.0.0.44",
                    "port": 22,
                    "username": "ubuntu",
                    "server_type": "ssh",
                    "auth_method": "key",
                    "ssh_private_key": key_text,
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        server = Server.objects.get(id=response.json()["server_id"])
        assert server.key_path
        assert str(server.key_path).startswith(str(tmp_path / "ssh_keys"))
        assert os.path.exists(server.key_path)
        with open(server.key_path, encoding="utf-8") as stored_key:
            assert stored_key.read() == key_text.strip() + "\n"


@pytest.mark.django_db
def test_server_memory_purge_user_clears_ai_memory_everywhere():
    from servers.adapters.memory_store import DjangoServerMemoryStore

    owner = User.objects.create_user(username="purge-owner", password="x")
    owner.is_staff = True
    owner.save(update_fields=["is_staff"])
    _grant_feature(owner, "servers")
    client = Client()
    client.force_login(owner)

    server = _create_server(owner, name="forget-me", server_type="ssh", port=22)
    store = DjangoServerMemoryStore()

    manual_knowledge = ServerKnowledge.objects.create(
        server=server,
        category="config",
        title="Manual note",
        content="Keep this manual note",
        source="manual",
        is_active=True,
        created_by=owner,
    )
    store._sync_manual_knowledge_snapshot_sync(manual_knowledge.id)

    ai_knowledge = ServerKnowledge.objects.create(
        server=server,
        category="issues",
        title="AI note",
        content="Delete this AI note",
        source="ai_auto",
        is_active=True,
        created_by=owner,
    )
    store._sync_manual_knowledge_snapshot_sync(ai_knowledge.id)

    canonical_snapshot = ServerMemorySnapshot.objects.create(
        server=server,
        created_by=owner,
        memory_key="profile",
        layer=ServerMemorySnapshot.LAYER_CANONICAL,
        title="Canonical profile",
        content="Ephemeral AI memory",
        source_kind="dream",
        source_ref="dream:test",
        version_group_id="purge-profile",
        version=1,
        is_active=True,
    )
    ServerMemoryRevalidation.objects.create(
        server=server,
        source_snapshot=canonical_snapshot,
        memory_key="profile",
        title="Review profile",
        reason="stale",
    )
    ServerMemoryEpisode.objects.create(
        server=server,
        episode_kind=ServerMemoryEpisode.KIND_AGENT,
        source_kind="agent_run",
        source_ref="run:123",
        session_id="run:123",
        title="AI episode",
        summary="Summarized AI history",
        event_count=2,
        is_active=True,
    )
    ServerMemoryEvent.objects.create(
        server=server,
        actor_user=owner,
        source_kind=ServerMemoryEvent.SOURCE_AGENT_RUN,
        actor_kind=ServerMemoryEvent.ACTOR_AGENT,
        source_ref="run:123",
        session_id="run:123",
        event_type="run_completed",
        raw_text_redacted="temporary AI payload",
    )

    purge_response = client.post(f"/servers/api/{server.id}/memory/purge/")
    assert purge_response.status_code == 200
    payload = purge_response.json()
    assert payload["success"] is True
    assert payload["deleted"]["snapshots"] >= 2
    assert payload["deleted"]["episodes"] >= 1
    assert payload["deleted"]["events"] >= 1
    assert payload["deleted"]["revalidations"] >= 1
    assert payload["deleted"]["knowledge"] >= 1

    assert ServerKnowledge.objects.filter(pk=manual_knowledge.id, server=server).exists() is True
    assert ServerMemorySnapshot.objects.filter(server=server, memory_key=f"manual_note:{manual_knowledge.id}").exists() is True
    assert ServerKnowledge.objects.filter(pk=ai_knowledge.id, server=server).exists() is False
    assert ServerMemorySnapshot.objects.filter(server=server, memory_key="profile").exists() is False
    assert ServerMemorySnapshot.objects.filter(server=server, memory_key=f"knowledge_note:{ai_knowledge.id}").exists() is False
    assert ServerMemoryEpisode.objects.filter(server=server).exists() is False
    assert ServerMemoryEvent.objects.filter(server=server).exists() is False
    assert ServerMemoryRevalidation.objects.filter(server=server).exists() is False

    overview = client.get(f"/servers/api/{server.id}/memory/overview/")
    assert overview.status_code == 200
    overview_payload = overview.json()
    assert overview_payload["success"] is True
    assert overview_payload["stats"]["episodes"] == 0
    assert overview_payload["stats"]["archive"] == 0


@pytest.mark.django_db
def test_server_memory_snapshot_actions_promote_archive_and_skill_scaffold(tmp_path):
    from studio.models import StudioSkillAccess
    from studio.skill_registry import get_skill

    owner = User.objects.create_user(username="memory-owner", password="x")
    owner.is_staff = True
    owner.save(update_fields=["is_staff"])
    _grant_feature(owner, "servers", "studio_skills")
    client = Client()
    client.force_login(owner)
    server = _create_server(owner, name="memory-srv", server_type="ssh", port=22)

    pattern_snapshot = ServerMemorySnapshot.objects.create(
        server=server,
        created_by=owner,
        memory_key="pattern_candidate:demo1234",
        layer=ServerMemorySnapshot.LAYER_CANONICAL,
        title="Learned Pattern: diagnostics :: uptime && free -h",
        content="- Команда: uptime && free -h\n- Intent: diagnostics\n- Повторяемость: 4 запусков\n- Успех: 4/4 (100%)",
        source_kind="dream",
        source_ref="episode:1",
        version_group_id="pattern-demo1234",
        version=1,
        is_active=True,
        importance_score=0.64,
        stability_score=0.72,
        confidence=0.91,
        metadata={
            "intent": "diagnostics",
            "display_command": "uptime && free -h",
            "occurrences": 4,
            "successful_runs": 4,
            "measured_runs": 4,
            "success_rate": 1.0,
            "actor_kinds": ["human"],
            "source_kinds": ["terminal"],
        },
    )
    automation_snapshot = ServerMemorySnapshot.objects.create(
        server=server,
        created_by=owner,
        memory_key="automation_candidate:demo5678",
        layer=ServerMemorySnapshot.LAYER_CANONICAL,
        title="Automation Candidate: service :: systemctl restart nginx",
        content="- Базовая команда: systemctl restart nginx\n- Intent: service\n- Шаг 2: проверить `systemctl is-active nginx`.",
        source_kind="dream",
        source_ref="episode:2",
        version_group_id="automation-demo5678",
        version=1,
        is_active=True,
        importance_score=0.72,
        stability_score=0.8,
        confidence=0.94,
        metadata={
            "intent": "service",
            "display_command": "systemctl restart nginx",
            "occurrences": 5,
            "successful_runs": 5,
            "measured_runs": 5,
            "success_rate": 1.0,
            "actor_kinds": ["human"],
            "source_kinds": ["terminal"],
        },
    )
    skill_snapshot = ServerMemorySnapshot.objects.create(
        server=server,
        created_by=owner,
        memory_key="skill_draft:demo9012",
        layer=ServerMemorySnapshot.LAYER_CANONICAL,
        title="Skill Draft: service :: systemctl restart nginx -> systemctl is-active nginx",
        content=(
            "# Skill Draft: service\n"
            "- Trigger: задачи, где нужен workflow `systemctl restart nginx -> systemctl is-active nginx`.\n"
            "- Reuse signal: 4 повторений, успех 100%.\n"
            "- Workflow:\n"
            "  - Step 1: systemctl restart nginx\n"
            "  - Step 2: systemctl is-active nginx\n"
            "- Verification: последний шаг workflow уже выступает как verification; нужно проверить его exit code и сигнал результата.\n"
            "- Success signals: active (running) | nginx.service active\n"
        ),
        source_kind="dream",
        source_ref="episode:3",
        version_group_id="skill-demo9012",
        version=1,
        is_active=True,
        importance_score=0.76,
        stability_score=0.84,
        confidence=0.96,
        metadata={
            "intent": "service",
            "display_command": "systemctl restart nginx -> systemctl is-active nginx",
            "pattern_kind": "sequence",
            "commands": ["systemctl restart nginx", "systemctl is-active nginx"],
            "occurrences": 4,
            "successful_runs": 4,
            "measured_runs": 4,
            "success_rate": 1.0,
            "has_verification_step": True,
            "verification_rate": 1.0,
            "sample_outputs": ["active (running)", "nginx.service active"],
            "common_cwds": ["/etc/nginx", "/srv/app"],
            "actor_kinds": ["human"],
            "source_kinds": ["terminal"],
        },
    )

    promote_note = client.post(
        f"/servers/api/{server.id}/memory/snapshots/{pattern_snapshot.id}/promote-note/",
        data=_json({}),
        content_type="application/json",
    )
    assert promote_note.status_code == 200
    promote_note_payload = promote_note.json()
    assert promote_note_payload["success"] is True
    assert promote_note_payload["knowledge_id"] > 0
    assert "manual" in promote_note_payload["overview"]
    assert "worker_states" in promote_note_payload["overview"]
    pattern_snapshot.refresh_from_db()
    assert pattern_snapshot.is_active is False
    assert pattern_snapshot.layer == ServerMemorySnapshot.LAYER_ARCHIVE

    archive_response = client.post(
        f"/servers/api/{server.id}/memory/snapshots/{automation_snapshot.id}/archive/",
        data=_json({}),
        content_type="application/json",
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["success"] is True
    assert "worker_states" in archive_response.json()["overview"]
    automation_snapshot.refresh_from_db()
    assert automation_snapshot.is_active is False
    assert automation_snapshot.layer == ServerMemorySnapshot.LAYER_ARCHIVE

    with override_settings(STUDIO_SKILLS_DIRS=[str(tmp_path)]):
        promote_skill = client.post(
            f"/servers/api/{server.id}/memory/snapshots/{skill_snapshot.id}/promote-skill/",
            data=_json({}),
            content_type="application/json",
        )
        assert promote_skill.status_code == 200
        promote_skill_payload = promote_skill.json()
        assert promote_skill_payload["success"] is True
        skill_slug = promote_skill_payload["skill"]["slug"]
        skill = get_skill(skill_slug)
        assert skill.slug == skill_slug
        assert "Derived Draft" in skill.content
        assert "Derived Workflow" in skill.content
        assert "Success Signals" in skill.content
        assert promote_skill_payload["knowledge_id"] > 0
        assert "worker_states" in promote_skill_payload["overview"]
        assert ServerKnowledge.objects.filter(server=server, id=promote_skill_payload["knowledge_id"], is_active=True).exists()
        assert StudioSkillAccess.objects.filter(slug=skill_slug, owner=owner).exists()

    skill_snapshot.refresh_from_db()
    assert skill_snapshot.is_active is False
    assert skill_snapshot.layer == ServerMemorySnapshot.LAYER_ARCHIVE


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

    async def fake_execute(self, conn_id, command, allow_destructive=False, sudo_auth_mode=None, sudo_password=None):
        assert conn_id == "conn-1"
        assert command == "uname -a"
        assert allow_destructive is False
        assert sudo_auth_mode == "none"
        assert sudo_password == ""
        return {"stdout": "Linux test\n", "stderr": "", "exit_code": 0, "success": True}

    monkeypatch.setattr("servers.views.ssh_manager.connect", fake_connect)
    monkeypatch.setattr("servers.views.ssh_manager.disconnect", fake_disconnect)
    monkeypatch.setattr("app.tools.ssh_tools.SSHExecuteTool.execute", fake_execute)
    monkeypatch.setattr("servers.views.ServerCommandHistory.objects.create", lambda *args, **kwargs: None)
    monkeypatch.setattr("servers.os_detect_service.schedule_os_detect_for_server_ids", lambda *_args, **_kwargs: None)

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
    assert execute.json()["success"] is True, execute.json()
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

    status = client.get("/servers/api/monitoring/status/")
    assert status.status_code == 200
    body = status.json()
    assert body["success"] is True
    assert len(body["servers"]) == 1
    assert body["servers"][0]["server_id"] == server.id
    assert body["servers"][0]["status"] == ServerHealthCheck.STATUS_WARNING

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
def test_watcher_scan_endpoint_returns_drafts_for_health_alerts_and_failed_runs():
    user = User.objects.create_user(username="watcher-user", password="x")
    _grant_feature(user, "servers")
    client = Client()
    client.force_login(user)

    critical_server = _create_server(user, name="critical-node", server_type="ssh")
    failed_run_server = _create_server(user, name="failed-run-node", host="10.0.0.77", server_type="ssh")

    ServerHealthCheck.objects.create(
        server=critical_server,
        status=ServerHealthCheck.STATUS_CRITICAL,
        cpu_percent=96.0,
        disk_percent=97.0,
    )
    ServerAlert.objects.create(
        server=critical_server,
        alert_type=ServerAlert.TYPE_SERVICE,
        severity=ServerAlert.SEVERITY_CRITICAL,
        title="nginx is down",
        message="Service health check failed",
    )
    agent = ServerAgent.objects.create(
        user=user,
        name="Deploy Operator",
        mode=ServerAgent.MODE_FULL,
        agent_type=ServerAgent.TYPE_DEPLOY_WATCHER,
        commands=[],
    )
    AgentRun.objects.create(
        agent=agent,
        server=failed_run_server,
        user=user,
        status=AgentRun.STATUS_FAILED,
        ai_analysis="Rollout failed after restart",
    )

    response = client.get("/servers/api/watchers/scan/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["summary"]["critical"] == 1
    assert payload["summary"]["warning"] == 1
    assert payload["summary"]["drafts"] == 2
    assert [draft["server_name"] for draft in payload["drafts"]] == ["critical-node", "failed-run-node"]

    critical_draft = payload["drafts"][0]
    assert critical_draft["severity"] == "critical"
    assert critical_draft["recommended_role"] == "incident_commander"
    assert any("nginx is down" in reason for reason in critical_draft["reasons"])

    filtered = client.post(
        "/servers/api/watchers/scan/",
        data=_json({"server_ids": [failed_run_server.id], "limit": 5}),
        content_type="application/json",
    )
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert filtered_payload["summary"]["drafts"] == 1
    assert filtered_payload["requested_server_ids"] == [failed_run_server.id]
    assert filtered_payload["drafts"][0]["server_id"] == failed_run_server.id
    assert filtered_payload["drafts"][0]["recommended_role"] == "post_change_verifier"

    persisted = client.post(
        "/servers/api/watchers/scan/",
        data=_json({"persist": True}),
        content_type="application/json",
    )
    assert persisted.status_code == 200
    persisted_payload = persisted.json()
    assert persisted_payload["persisted_scan"] is True
    assert persisted_payload["persisted"]["created"] == 2
    assert ServerWatcherDraft.objects.count() == 2

    drafts = client.get("/servers/api/watchers/drafts/")
    assert drafts.status_code == 200
    drafts_payload = drafts.json()
    assert drafts_payload["success"] is True
    assert drafts_payload["summary"]["open"] == 2
    draft_id = drafts_payload["drafts"][0]["id"]

    ack = client.post(f"/servers/api/watchers/drafts/{draft_id}/ack/")
    assert ack.status_code == 200
    assert ack.json()["success"] is True
    assert ack.json()["draft"]["status"] == "acknowledged"

    acknowledged = client.get("/servers/api/watchers/drafts/?status=acknowledged")
    assert acknowledged.status_code == 200
    assert acknowledged.json()["summary"]["acknowledged"] == 1
    assert acknowledged.json()["drafts"][0]["id"] == draft_id


@pytest.mark.django_db
def test_watcher_launch_endpoint_creates_run_and_updates_draft(monkeypatch):
    user = User.objects.create_user(username="watcher-launch-user", password="x")
    _grant_feature(user, "servers", "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="ops-node")
    draft = ServerWatcherDraft.objects.create(
        server=server,
        fingerprint="watcher-launch-001",
        severity=ServerAlert.SEVERITY_WARNING,
        recommended_role="incident_commander",
        objective="Investigate nginx downtime and recent deploy drift",
        reasons=["nginx alert", "deploy failed"],
        memory_excerpt=["Last deploy restarted nginx 3 minutes ago"],
    )

    captured: dict[str, object] = {}

    def fake_launch(run_id: int, agent_id: int, server_ids: list[int], user_id: int, *, plan_only: bool = False):
        captured.update(
            {
                "run_id": run_id,
                "agent_id": agent_id,
                "server_ids": server_ids,
                "user_id": user_id,
                "plan_only": plan_only,
            }
        )

    monkeypatch.setattr("servers.agent_launch.launch_agent_run_background", fake_launch)

    response = client.post(f"/servers/api/watchers/drafts/{draft.id}/launch/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["status"] == AgentRun.STATUS_PENDING
    assert payload["draft"]["status"] == ServerWatcherDraft.STATUS_ACKNOWLEDGED

    run = AgentRun.objects.get(pk=payload["run_id"])
    agent = ServerAgent.objects.get(pk=payload["agent_id"])
    draft.refresh_from_db()

    assert run.agent_id == agent.id
    assert run.server_id == server.id
    assert run.status == AgentRun.STATUS_PENDING
    assert agent.user_id == user.id
    assert agent.mode == ServerAgent.MODE_FULL
    assert agent.name.startswith("Watcher · ops-node")
    assert "[ROLE=incident_commander]" in agent.goal
    assert draft.status == ServerWatcherDraft.STATUS_ACKNOWLEDGED
    assert draft.acknowledged_by_id == user.id
    assert draft.metadata["last_launch_run_id"] == run.id
    assert draft.metadata["last_launch_agent_id"] == agent.id
    assert draft.metadata["launch_count"] == 1
    assert captured == {
        "run_id": run.id,
        "agent_id": agent.id,
        "server_ids": [server.id],
        "user_id": user.id,
        "plan_only": False,
    }

@pytest.mark.django_db
def test_agent_run_events_endpoint_returns_persisted_events():
    user = User.objects.create_user(username="events-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="events-node")
    agent = ServerAgent.objects.create(
        user=user,
        name="Eventful Agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect the server",
    )
    agent.servers.set([server])
    run = AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_RUNNING,
    )
    AgentRunEvent.objects.create(
        run=run,
        event_type="agent_background_started",
        message="Background worker started",
        payload={"server_ids": [server.id]},
    )
    AgentRunEvent.objects.create(
        run=run,
        event_type="agent_task_start",
        task_id=7,
        message="Check nginx",
        payload={"task_id": 7, "name": "Check nginx"},
    )

    response = client.get(f"/servers/api/agents/runs/{run.id}/events/?limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["total"] == 2
    assert [item["event_type"] for item in payload["events"]] == [
        "agent_background_started",
        "agent_task_start",
    ]
    assert payload["events"][1]["task_id"] == 7
    assert payload["events"][1]["message"] == "Check nginx"


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

    monkeypatch.setattr("servers.agent_launch.launch_agent_run_background", fake_launch)

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
        "servers.agent_launch.launch_agent_run_background",
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
def test_multi_agent_run_launches_without_plan_only(monkeypatch):
    user = User.objects.create_user(username="multi-launch-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user)
    agent = ServerAgent.objects.create(
        user=user,
        name="Cluster Health",
        mode=ServerAgent.MODE_MULTI,
        agent_type=ServerAgent.TYPE_MULTI_HEALTH,
        goal="Inspect the cluster",
        ai_prompt="Run cluster-wide checks",
        allow_multi_server=True,
    )
    agent.servers.set([server])

    captured: dict[str, object] = {}

    def fake_launch(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("servers.agent_launch.launch_agent_run_background", fake_launch)

    response = client.post(
        f"/servers/api/agents/{agent.id}/run/",
        data=_json({}),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["status"] == AgentRun.STATUS_PENDING
    assert captured["plan_only"] is False


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

    monkeypatch.setattr("servers.agent_service.launch_plan_execution_background", fake_launch)

    response = client.post(f"/servers/api/agents/runs/{run.id}/approve-plan/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["run_id"] == run.id
    assert payload["status"] == AgentRun.STATUS_PENDING

    run.refresh_from_db()
    assert run.status == AgentRun.STATUS_PENDING
    assert AgentRunEvent.objects.filter(run=run, event_type="agent_plan_approved").exists()
    assert captured == {
        "run_id": run.id,
        "agent_id": agent.id,
        "server_ids": [server.id],
        "user_id": user.id,
    }


@pytest.mark.django_db
def test_agent_schedule_overview_and_dispatch_api(monkeypatch):
    user = User.objects.create_user(username="agent-schedule-user", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    server = _create_server(user, name="agent-schedule-srv", server_type="ssh")
    agent = ServerAgent.objects.create(
        user=user,
        name="Scheduled Deploy Operator",
        mode=ServerAgent.MODE_FULL,
        agent_type=ServerAgent.TYPE_DEPLOY_WATCHER,
        goal="Verify deploy health",
        schedule_minutes=15,
        is_enabled=True,
        last_run_at=timezone.now() - timedelta(minutes=20),
    )
    agent.servers.set([server])

    captured: dict[str, object] = {}

    def fake_launch(run_id: int, agent_id: int, server_ids: list[int], user_id: int, *, plan_only: bool = False):
        captured.update(
            {
                "run_id": run_id,
                "agent_id": agent_id,
                "server_ids": server_ids,
                "user_id": user_id,
                "plan_only": plan_only,
            }
        )

    monkeypatch.setattr("servers.agent_launch.launch_agent_run_background", fake_launch)

    overview = client.get("/servers/api/agents/schedules/")
    assert overview.status_code == 200
    overview_payload = overview.json()
    assert overview_payload["success"] is True
    assert "execution_plane" in overview_payload
    assert overview_payload["summary"]["total_scheduled"] == 1
    assert overview_payload["summary"]["due_now"] == 1
    scheduled_agent = overview_payload["scheduled_agents"][0]
    assert scheduled_agent["id"] == agent.id
    assert scheduled_agent["schedule_state"] == "due"
    assert scheduled_agent["due_now"] is True
    assert scheduled_agent["next_due_at"] is not None

    dispatch = client.post(
        "/servers/api/agents/schedules/dispatch/",
        data=_json({"limit": 10}),
        content_type="application/json",
    )
    assert dispatch.status_code == 200
    dispatch_payload = dispatch.json()
    assert dispatch_payload["success"] is True
    assert dispatch_payload["summary"]["launched_agents"] == 1
    assert dispatch_payload["summary"]["runs_created"] == 1

    run = AgentRun.objects.get(agent=agent)
    assert run.status == AgentRun.STATUS_PENDING
    assert AgentRunEvent.objects.filter(run=run, event_type="agent_scheduled_dispatch").exists()
    assert captured == {
        "run_id": run.id,
        "agent_id": agent.id,
        "server_ids": [server.id],
        "user_id": user.id,
        "plan_only": False,
    }
