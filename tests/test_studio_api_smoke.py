import uuid
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings

from core_ui.managed_secrets import get_notification_secret
from servers.models import Server
from studio.models import MCPServerPool, Pipeline, PipelineRun, PipelineTemplate
from tests.studio_api_smoke_harness import grant_feature, json_payload, llm_node


@pytest.mark.django_db
def test_studio_pipeline_trigger_template_and_servers_endpoints(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    user = User.objects.create_user(username="studio-user", password="x")
    grant_feature(user, "studio", "studio_pipelines", "studio_runs", "agents")
    server = Server.objects.create(user=user, name="studio-srv", host="10.0.0.55", username="root")
    client = Client()
    client.force_login(user)
    monkeypatch.setattr("studio.views.pipeline_helpers._launch_pipeline_run_async", lambda _run: None)

    create = client.post(
        "/api/studio/pipelines/",
        data=json_payload(
            {
                "name": "Ops Flow",
                "nodes": [
                    {
                        "id": "manual",
                        "type": "trigger/manual",
                        "position": {"x": 0, "y": 0},
                        "data": {"label": "Manual"},
                    },
                    {
                        "id": "webhook",
                        "type": "trigger/webhook",
                        "position": {"x": 0, "y": 100},
                        "data": {"label": "Webhook", "webhook_payload_map": {"branch": "git.ref"}},
                    },
                    llm_node("manual_task"),
                    llm_node("webhook_task"),
                ],
                "edges": [
                    {"id": "e1", "source": "manual", "target": "manual_task"},
                    {"id": "e2", "source": "webhook", "target": "webhook_task"},
                ],
            }
        ),
        content_type="application/json",
    )
    assert create.status_code == 201
    pipeline_id = create.json()["id"]

    pipelines = client.get("/api/studio/pipelines/")
    assert pipelines.status_code == 200
    assert any(item["id"] == pipeline_id for item in pipelines.json()["data"])

    detail = client.get(f"/api/studio/pipelines/{pipeline_id}/")
    assert detail.status_code == 200
    assert detail.json()["id"] == pipeline_id

    update = client.put(
        f"/api/studio/pipelines/{pipeline_id}/",
        data=json_payload({"name": "Ops Flow Updated", "description": "updated"}),
        content_type="application/json",
    )
    assert update.status_code == 200
    assert update.json()["name"] == "Ops Flow Updated"

    run = client.post(
        f"/api/studio/pipelines/{pipeline_id}/run/",
        data=json_payload({"context": {"branch": "main"}}),
        content_type="application/json",
    )
    assert run.status_code == 202
    run_id = run.json()["id"]
    assert run.json()["entry_node_id"] == "manual"

    pipeline_runs = client.get(f"/api/studio/pipelines/{pipeline_id}/runs/")
    assert pipeline_runs.status_code == 200
    assert any(item["id"] == run_id for item in pipeline_runs.json()["data"])

    runs = client.get("/api/studio/runs/")
    assert runs.status_code == 200
    assert any(item["id"] == run_id for item in runs.json()["data"])

    clone = client.post(f"/api/studio/pipelines/{pipeline_id}/clone/")
    assert clone.status_code == 201
    assert clone.json()["name"].endswith("(copy)")

    triggers = client.get(f"/api/studio/triggers/?pipeline_id={pipeline_id}")
    assert triggers.status_code == 200
    webhook_trigger = next(item for item in triggers.json()["data"] if item["trigger_type"] == "webhook")
    trigger_id = webhook_trigger["id"]

    trigger_update = client.put(
        f"/api/studio/triggers/{trigger_id}/",
        data=json_payload({"name": "Updated trigger", "is_active": True}),
        content_type="application/json",
    )
    assert trigger_update.status_code == 200
    assert trigger_update.json()["name"] == "Updated trigger"

    trigger_token = trigger_update.json()["webhook_token"]
    receive = client.post(
        f"/api/studio/triggers/{trigger_token}/receive/",
        data=json_payload({"git": {"ref": "refs/heads/release"}}),
        content_type="application/json",
    )
    assert receive.status_code == 200
    assert receive.json()["ok"] is True
    webhook_run = PipelineRun.objects.get(pk=receive.json()["run_id"])
    assert webhook_run.entry_node_id == "webhook"
    assert webhook_run.context["branch"] == "refs/heads/release"

    template = PipelineTemplate.objects.create(
        slug="unit-template",
        name="Unit Template",
        description="Smoke template",
        category="Tests",
        nodes=[{"id": "start", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Start"}}],
        edges=[],
    )
    templates = client.get("/api/studio/templates/")
    assert templates.status_code == 200
    assert any(item["slug"] == template.slug for item in templates.json()["data"])

    use_template = client.post(f"/api/studio/templates/{template.slug}/use/")
    assert use_template.status_code == 201
    assert use_template.json()["name"] == "Unit Template"

    studio_servers = client.get("/api/studio/servers/")
    assert studio_servers.status_code == 200
    assert any(item["id"] == server.id for item in studio_servers.json()["data"])

    delete = client.delete(f"/api/studio/pipelines/{pipeline_id}/")
    assert delete.status_code == 200
    assert delete.json()["ok"] is True


@pytest.mark.django_db
@override_settings(PIPELINE_ACTIVE_RUNS_PER_USER_LIMIT=1, PIPELINE_ACTIVE_RUNS_GLOBAL_LIMIT=0)
def test_pipeline_run_enforces_user_active_run_limit(monkeypatch):
    user = User.objects.create_user(username="studio-limit-user", password="x")
    grant_feature(user, "studio", "studio_pipelines", "studio_runs", "agents")
    client = Client()
    client.force_login(user)

    pipeline = Pipeline.objects.create(
        name="Limited Flow",
        owner=user,
        nodes=[{"id": "n1", "type": "agent/llm_query", "position": {"x": 0, "y": 0}, "data": {"prompt": "hi"}}],
        edges=[],
    )
    PipelineRun.objects.create(
        pipeline=pipeline,
        triggered_by=user,
        status=PipelineRun.STATUS_RUNNING,
        context={},
    )

    monkeypatch.setattr(
        "studio.views.pipeline_helpers._launch_pipeline_run_async",
        lambda _run: pytest.fail("_launch_pipeline_run_async should not be called when the active-run limit is hit"),
    )

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=json_payload({"context": {}}),
        content_type="application/json",
    )

    assert response.status_code == 429
    payload = response.json()
    assert payload["success"] is False
    assert payload["code"] == "pipeline_user_limit_reached"
    assert payload["limit"] == 1
    assert payload["active"] == 1


@pytest.mark.django_db
def test_studio_agents_skills_and_mcp_crud_endpoints(monkeypatch):
    user = User.objects.create_user(username="studio-admin", password="x", is_staff=True)
    server = Server.objects.create(user=user, name="scope-srv", host="10.0.0.77", username="root")
    client = Client()
    client.force_login(user)

    create_mcp = client.post(
        "/api/studio/mcp/",
        data=json_payload(
            {
                "name": "Demo MCP",
                "transport": MCPServerPool.TRANSPORT_SSE,
                "url": "localhost:8765/sse",
                "description": "demo",
            }
        ),
        content_type="application/json",
    )
    assert create_mcp.status_code == 201
    mcp_id = create_mcp.json()["id"]
    assert create_mcp.json()["url"].startswith("http://")

    mcp_list = client.get("/api/studio/mcp/")
    assert mcp_list.status_code == 200
    assert any(item["id"] == mcp_id for item in mcp_list.json()["data"])

    mcp_detail = client.get(f"/api/studio/mcp/{mcp_id}/")
    assert mcp_detail.status_code == 200
    assert mcp_detail.json()["name"] == "Demo MCP"

    mcp_update = client.put(
        f"/api/studio/mcp/{mcp_id}/",
        data=json_payload({"name": "Demo MCP Updated", "url": "http://127.0.0.1:8765/sse"}),
        content_type="application/json",
    )
    assert mcp_update.status_code == 200
    assert mcp_update.json()["name"] == "Demo MCP Updated"

    monkeypatch.setattr("studio.views.mcp_views._test_mcp_connection", lambda _mcp: (True, None))
    mcp_test = client.post(f"/api/studio/mcp/{mcp_id}/test/")
    assert mcp_test.status_code == 200
    assert mcp_test.json()["ok"] is True

    async def fake_inspect_mcp_server(_mcp):
        return {"server": {"name": "Demo MCP"}, "tools": [{"name": "ping"}]}

    monkeypatch.setattr("studio.views.mcp_views.inspect_mcp_server", fake_inspect_mcp_server)
    mcp_tools = client.get(f"/api/studio/mcp/{mcp_id}/tools/")
    assert mcp_tools.status_code == 200
    assert mcp_tools.json()["server"]["name"] == "Demo MCP"

    mcp_templates = client.get("/api/studio/mcp/templates/")
    assert mcp_templates.status_code == 200
    assert any(item["slug"] == "filesystem" for item in mcp_templates.json()["data"])

    agent_create = client.post(
        "/api/studio/agents/",
        data=json_payload(
            {
                "name": "Studio Agent",
                "model": "gemini-2.0-flash-exp",
                "allowed_tools": ["report", "ask_user"],
                "skill_slugs": ["kubernetes-safety"],
                "mcp_server_ids": [mcp_id],
                "server_scope_ids": [server.id],
            }
        ),
        content_type="application/json",
    )
    assert agent_create.status_code == 201
    agent_id = agent_create.json()["id"]

    agents = client.get("/api/studio/agents/")
    assert agents.status_code == 200
    assert any(item["id"] == agent_id for item in agents.json()["data"])

    agent_detail = client.get(f"/api/studio/agents/{agent_id}/")
    assert agent_detail.status_code == 200
    assert agent_detail.json()["id"] == agent_id
    assert agent_detail.json()["mcp_servers"][0]["id"] == mcp_id

    agent_update = client.put(
        f"/api/studio/agents/{agent_id}/",
        data=json_payload({"skill_slugs": ["kubernetes-safety"]}),
        content_type="application/json",
    )
    assert agent_update.status_code == 200
    assert "kubernetes-safety" in agent_update.json()["skill_slugs"]

    skills = client.get("/api/studio/skills/")
    assert skills.status_code == 200
    assert any(item["slug"] == "kubernetes-safety" for item in skills.json()["data"])

    skill_detail = client.get("/api/studio/skills/kubernetes-safety/")
    assert skill_detail.status_code == 200
    assert skill_detail.json()["slug"] == "kubernetes-safety"

    delete_agent = client.delete(f"/api/studio/agents/{agent_id}/")
    assert delete_agent.status_code == 200
    assert delete_agent.json()["ok"] is True

    delete_mcp = client.delete(f"/api/studio/mcp/{mcp_id}/")
    assert delete_mcp.status_code == 200
    assert delete_mcp.json()["ok"] is True


@pytest.mark.django_db
def test_studio_notification_endpoints_with_mocked_transports(monkeypatch, settings):
    user = User.objects.create_user(username="notif-user", password="x", is_staff=True)
    client = Client()
    client.force_login(user)

    temp_config = Path(settings.BASE_DIR) / ".tmp_notif_tests" / f"config_{uuid.uuid4().hex}.json"
    temp_config.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("studio.views.notification_views._NOTIF_CONFIG_PATH", temp_config)

    save = client.post(
        "/api/studio/notifications/",
        data=json_payload(
            {
                "notify_email": "ops@example.com",
                "smtp_host": "smtp.gmail.com",
                "smtp_port": "587",
                "smtp_user": "ops@example.com",
                "smtp_password": "secret",
                "from_email": "ops@example.com",
                "telegram_bot_token": "123456789:TESTTOKEN",
                "telegram_chat_id": "123456",
            }
        ),
        content_type="application/json",
    )
    assert save.status_code == 200
    assert save.json()["ok"] is True

    get_saved = client.get("/api/studio/notifications/")
    assert get_saved.status_code == 200
    assert get_saved.json()["notify_email"] == "ops@example.com"
    assert "••••" in get_saved.json()["smtp_password"]
    assert get_notification_secret("smtp_password") == "secret"
    assert get_notification_secret("telegram_bot_token") == "123456789:TESTTOKEN"
    saved_config_text = temp_config.read_text(encoding="utf-8")
    assert "secret" not in saved_config_text
    assert "123456789:TESTTOKEN" not in saved_config_text

    class FakeTelegramResponse:
        status_code = 200
        text = "ok"

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *_args, **_kwargs):
            return FakeTelegramResponse()

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)

    telegram = client.post("/api/studio/notifications/test-telegram/")
    assert telegram.status_code == 200
    assert telegram.json()["ok"] is True

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def ehlo(self):
            return None

        def starttls(self):
            return None

        def login(self, *_args):
            return None

        def sendmail(self, *_args):
            return None

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    email = client.post("/api/studio/notifications/test-email/")
    assert email.status_code == 200
    assert email.json()["ok"] is True


@pytest.mark.django_db
def test_non_admin_cannot_manage_global_notifications_or_skill_workspace():
    user = User.objects.create_user(username="studio-non-admin", password="x")
    grant_feature(user, "studio")
    client = Client()
    client.force_login(user)

    mcp_list = client.get("/api/studio/mcp/")
    assert mcp_list.status_code == 403

    mcp_create = client.post(
        "/api/studio/mcp/",
        data=json_payload({"name": "Blocked MCP", "transport": "stdio", "command": "echo"}),
        content_type="application/json",
    )
    assert mcp_create.status_code == 403

    notif_get = client.get("/api/studio/notifications/")
    assert notif_get.status_code == 403

    notif_post = client.post(
        "/api/studio/notifications/",
        data=json_payload({"notify_email": "ops@example.com"}),
        content_type="application/json",
    )
    assert notif_post.status_code == 403

    scaffold = client.post(
        "/api/studio/skills/scaffold/",
        data=json_payload({"name": "Blocked Skill", "description": "should fail"}),
        content_type="application/json",
    )
    assert scaffold.status_code == 403

    workspace = client.get("/api/studio/skills/kubernetes-safety/workspace/")
    assert workspace.status_code == 403

    validate = client.post(
        "/api/studio/skills/validate/",
        data=json_payload({"slugs": ["kubernetes-safety"]}),
        content_type="application/json",
    )
    assert validate.status_code == 403
