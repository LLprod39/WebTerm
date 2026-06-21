from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from servers.models import (
    AgentRun,
    ServerAgent,
    ServerAlert,
    ServerHealthCheck,
    ServerWatcherDraft,
)
from tests.servers_api_smoke_harness import (
    create_server as _create_server,
)
from tests.servers_api_smoke_harness import (
    grant_feature as _grant_feature,
)
from tests.servers_api_smoke_harness import (
    json_payload as _json,
)


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
