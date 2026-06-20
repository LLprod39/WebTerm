import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from core_ui.models import UserAppPermission
from studio.keycloak_provisioning import ensure_keycloak_mcp_server
from studio.models import MCPServerPool, Pipeline, PipelineDraftSession


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )

@pytest.mark.django_db
def test_pipeline_assistant_returns_reply_and_patch(monkeypatch):
    user = User.objects.create_user(username="pipeline-assistant", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    async def fake_stream_chat(self, prompt: str, model: str = "auto", purpose: str = "chat", **kwargs):
        yield json.dumps(
            {
                "reply": "Use the upstream node as the condition source and check for the word error.",
                "target_node_id": "node_2",
                "node_patch": {
                    "source_node_id": "node_1",
                    "check_type": "contains",
                    "check_value": "error",
                },
                "graph_patch": {
                    "anchor_node_id": "node_2",
                    "nodes": [
                        {
                            "ref": "notify_ops",
                            "type": "output/telegram",
                            "label": "Notify Ops",
                            "data": {"message": "Alert: {node_1_output}"},
                            "x_offset": 280,
                            "y_offset": 120,
                        }
                    ],
                    "edges": [
                        {"source": "node_2", "target": "notify_ops", "label": "true"},
                    ],
                },
                "warnings": ["Verify the downstream true/false branches."],
            }
        )

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)

    response = client.post(
        "/api/studio/pipelines/assistant/",
        data=json.dumps(
            {
                "pipeline_name": "Health Check",
                "nodes": [
                    {"id": "node_1", "type": "agent/ssh_cmd", "position": {"x": 0, "y": 0}, "data": {"label": "Check disk"}},
                    {"id": "node_2", "type": "logic/condition", "position": {"x": 100, "y": 0}, "data": {}},
                ],
                "edges": [{"id": "e1", "source": "node_1", "target": "node_2"}],
                "user_message": "Configure this condition node from the upstream output.",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert "upstream node" in payload["reply"]
    assert payload["target_node_id"] == "node_2"
    assert payload["node_patch"]["source_node_id"] == "node_1"
    assert payload["node_patch"]["check_type"] == "contains"
    assert payload["graph_patch"]["anchor_node_id"] == "node_2"
    assert payload["graph_patch"]["nodes"][0]["ref"] == "notify_ops"
    assert payload["graph_patch"]["edges"][0]["target"] == "notify_ops"
    assert "Verify the downstream true/false branches." in payload["warnings"]


@pytest.mark.django_db
def test_pipeline_assistant_draft_create_and_apply(monkeypatch):
    user = User.objects.create_user(username="pipeline-drafter", password="x")
    _grant_feature(user, "studio_pipelines", "studio_agents", "studio_mcp", "studio_skills")
    client = Client()
    client.force_login(user)

    async def fake_stream_chat(self, prompt: str, model: str = "auto", purpose: str = "chat", **kwargs):
        yield json.dumps(
            {
                "reply": "Собран daily health-check draft.",
                "requirements": ["Daily manual health-check pipeline"],
                "assumptions": ["Manual trigger is enough for the first draft"],
                "questions": [],
                "resource_plan": {
                    "servers": [],
                    "mcp_servers": [],
                    "skills": [],
                    "missing": [],
                    "notes": ["No MCP required for this simple draft"],
                },
                "target_node_id": None,
                "node_patch": {},
                "graph_patch": {
                    "anchor_node_id": None,
                    "nodes": [
                        {
                            "ref": "manual_start",
                            "type": "trigger/manual",
                            "label": "Manual Start",
                            "data": {"is_active": True},
                        },
                        {
                            "ref": "summarize",
                            "type": "agent/llm_query",
                            "label": "Summarize Task",
                            "data": {
                                "prompt": "Summarize the operator task and return concise markdown.",
                                "system_prompt": "You are an ops runbook summarizer.",
                            },
                        },
                        {
                            "ref": "report",
                            "type": "output/report",
                            "label": "Report",
                            "data": {"template": "## Result\n{summarize_output}"},
                        },
                    ],
                    "edges": [
                        {"source": "manual_start", "target": "summarize", "source_handle": "out"},
                        {"source": "summarize", "target": "report", "source_handle": "success"},
                    ],
                    "update_nodes": [],
                    "remove_node_ids": [],
                    "remove_edge_ids": [],
                },
                "node_explanations": {"summarize": "Turns run output into a report."},
                "confidence": 0.9,
                "warnings": [],
                "patch_summary": "Starter health-check DAG",
                "suggested_next_actions": ["Create pipeline"],
            }
        )

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)

    create_response = client.post(
        "/api/studio/assistant/drafts/",
        data=json.dumps(
            {
                "pipeline_name": "Daily health draft",
                "nodes": [],
                "edges": [],
                "user_message": "Собери ежедневный health-check.",
                "intent": "create",
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 201
    draft_payload = create_response.json()
    assert draft_payload["status"] == PipelineDraftSession.STATUS_READY
    assert draft_payload["latest_revision"]["response"]["requirements"] == ["Daily manual health-check pipeline"]
    assert draft_payload["latest_revision"]["response"]["resource_plan"]["available"]
    assert draft_payload["latest_revision"]["preview_nodes"][0]["type"] == "trigger/manual"

    pipeline_count_before_validate = Pipeline.objects.count()
    validate_response = client.post(f"/api/studio/assistant/drafts/{draft_payload['id']}/validate/")
    assert validate_response.status_code == 200
    validated = validate_response.json()
    assert validated["validation"]["ok"] is True
    assert validated["dry_run"]["executed"] is False
    assert validated["dry_run"]["mode"] == "validate_only"
    assert validated["draft"]["latest_revision"]["response"]["dry_run"]["executed"] is False
    assert Pipeline.objects.count() == pipeline_count_before_validate

    apply_response = client.post(
        f"/api/studio/assistant/drafts/{draft_payload['id']}/apply/",
        data=json.dumps({"create_new": True, "name": "Daily health pipeline"}),
        content_type="application/json",
    )

    assert apply_response.status_code == 200
    applied = apply_response.json()
    assert applied["pipeline"]["name"] == "Daily health pipeline"
    assert len(applied["pipeline"]["nodes"]) == 3
    assert applied["draft"]["status"] == PipelineDraftSession.STATUS_APPLIED

    repeat_apply_response = client.post(
        f"/api/studio/assistant/drafts/{draft_payload['id']}/apply/",
        data=json.dumps({"create_new": True, "name": "Duplicate"}),
        content_type="application/json",
    )
    assert repeat_apply_response.status_code == 400
    assert "already applied" in repeat_apply_response.json()["error"]

    revise_applied_response = client.post(
        f"/api/studio/assistant/drafts/{draft_payload['id']}/revise/",
        data=json.dumps({"user_message": "Измени уже примененный draft."}),
        content_type="application/json",
    )
    assert revise_applied_response.status_code == 400
    assert "already closed" in revise_applied_response.json()["error"]

    discard_applied_response = client.delete(f"/api/studio/assistant/drafts/{draft_payload['id']}/")
    assert discard_applied_response.status_code == 400
    assert "cannot be discarded" in discard_applied_response.json()["error"]


@pytest.mark.django_db
def test_pipeline_assistant_draft_uses_local_fallback_when_provider_errors(monkeypatch):
    user = User.objects.create_user(username="pipeline-fallback", password="x")
    _grant_feature(user, "studio_pipelines")
    client = Client()
    client.force_login(user)

    async def fake_stream_chat(self, prompt: str, model: str = "auto", purpose: str = "chat", **kwargs):
        yield (
            'Error from Grok API: 403 - {"code":"permission_denied",'
            '"error":"Your team has used all available credits."}'
        )

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)

    create_response = client.post(
        "/api/studio/assistant/drafts/",
        data=json.dumps(
            {
                "pipeline_name": "Webhook fallback draft",
                "nodes": [],
                "edges": [],
                "user_message": "Webhook для задач оператора: принять payload, запустить agent, отправить summary",
                "intent": "create",
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 201
    draft_payload = create_response.json()
    revision = draft_payload["latest_revision"]
    response = revision["response"]

    assert draft_payload["status"] == PipelineDraftSession.STATUS_READY
    assert response["validation"]["ok"] is True
    assert response["warnings"]
    assert "generated a safe starter DAG locally" in response["warnings"][0]
    assert len(revision["preview_nodes"]) == 3
    assert revision["preview_nodes"][0]["type"] == "trigger/webhook"
    assert len(revision["preview_edges"]) == 2


@pytest.mark.django_db
def test_pipeline_assistant_fallback_builds_keycloak_mcp_workflow(monkeypatch):
    user = User.objects.create_user(username="pipeline-keycloak-fallback", password="x", is_staff=True)
    other_user = User.objects.create_user(username="pipeline-keycloak-other", password="x")
    ensure_keycloak_mcp_server(other_user)
    _grant_feature(user, "studio_pipelines", "studio_mcp", "studio_skills")
    server = ensure_keycloak_mcp_server(user)
    client = Client()
    client.force_login(user)

    async def fake_stream_chat(self, prompt: str, model: str = "auto", purpose: str = "chat", **kwargs):
        yield 'Error from Grok API: 403 - {"error":"Your team has used all available credits."}'

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)

    create_response = client.post(
        "/api/studio/assistant/drafts/",
        data=json.dumps(
            {
                "pipeline_name": "Keycloak tasks",
                "nodes": [],
                "edges": [],
                "user_message": "Выполнение задач заявок киклока и отчетность в телеграм",
                "intent": "create",
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 201
    draft_payload = create_response.json()
    revision = draft_payload["latest_revision"]
    response = revision["response"]
    nodes = {node["id"]: node for node in revision["preview_nodes"]}

    assert draft_payload["status"] == PipelineDraftSession.STATUS_READY
    assert response["validation"]["ok"] is True
    assert response["patch_summary"] == "Keycloak MCP ticket workflow with approval and Telegram reporting"
    assert response["resource_plan"]["mcp_servers"][0]["id"] == server.id
    assert any(item["slug"] == "keycloak-safety" for item in response["resource_plan"]["skills"])
    assert nodes["environment_preflight"]["data"]["mcp_server_id"] == server.id
    assert nodes["environment_preflight"]["data"]["tool_name"] == "keycloak_current_environment"
    assert nodes["execute_keycloak_task"]["data"]["mcp_server_ids"] == [server.id]
    assert "keycloak-safety" in nodes["execute_keycloak_task"]["data"]["skill_slugs"]
    assert nodes["telegram_report"]["type"] == "output/telegram"


@pytest.mark.django_db
def test_pipeline_assistant_fallback_uses_matching_pilot_template(monkeypatch):
    user = User.objects.create_user(username="pipeline-template-fallback", password="x", is_staff=True)
    _grant_feature(user, "studio_pipelines", "studio_mcp", "studio_skills")
    mcp = MCPServerPool.objects.create(
        owner=user,
        name="GitLab MCP",
        description="GitLab merge request and CI pipeline automation",
        transport=MCPServerPool.TRANSPORT_STDIO,
    )
    client = Client()
    client.force_login(user)

    async def fake_stream_chat(self, prompt: str, model: str = "auto", purpose: str = "chat", **kwargs):
        yield 'Error from Grok API: 403 - {"error":"Your team has used all available credits."}'

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)

    create_response = client.post(
        "/api/studio/assistant/drafts/",
        data=json.dumps(
            {
                "pipeline_name": "GitLab CI support",
                "nodes": [],
                "edges": [],
                "user_message": (
                    "GitLab failed pipeline project 42 pipeline 987 branch main commit deadbeef: "
                    "собрать причину, подготовить MR и проверить pipeline"
                ),
                "intent": "create",
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 201
    draft_payload = create_response.json()
    revision = draft_payload["latest_revision"]
    response = revision["response"]
    nodes = {node["id"]: node for node in revision["preview_nodes"]}

    assert draft_payload["status"] == PipelineDraftSession.STATUS_READY
    assert response["validation"]["ok"] is True
    assert response["patch_summary"] == "Pilot template skeleton: Pilot: GitLab Failed Pipeline To MR"
    assert "pilot-gitlab-failed-pipeline-mr" in response["assumptions"][0]
    assert response["resource_plan"]["mcp_servers"][0]["id"] == mcp.id
    assert nodes["webhook"]["type"] == "trigger/webhook"
    assert nodes["inspect"]["data"]["tool_name"] == "gitlab_get_pipeline_failure"
    assert nodes["inspect"]["data"]["mcp_server_id"] == mcp.id
    assert nodes["inspect"]["data"]["arguments"]["project_id"] == "42"
    assert nodes["inspect"]["data"]["arguments"]["pipeline_id"] == "987"
    assert nodes["inspect"]["data"]["arguments"]["commit_sha"] == "deadbeef"
    assert nodes["create_mr"]["data"]["mcp_server_id"] == mcp.id
    assert nodes["create_mr"]["data"]["arguments"]["source_branch"] == "ops-fix/987"
    assert nodes["create_mr"]["data"]["arguments"]["target_branch"] == "main"
    assert nodes["create_mr"]["data"]["permission_mode"] == "ASSISTED"
    assert nodes["verify"]["data"]["permission_mode"] == "READ_ONLY"


@pytest.mark.django_db
def test_pipeline_assistant_draft_can_use_provider_free_pilot_compiler(monkeypatch):
    user = User.objects.create_user(username="pipeline-template-compiler", password="x", is_staff=True)
    _grant_feature(user, "studio_pipelines", "studio_mcp", "studio_skills")
    mcp = MCPServerPool.objects.create(
        owner=user,
        name="Kubernetes MCP",
        description="Kubernetes rollout and workload diagnostics",
        transport=MCPServerPool.TRANSPORT_STDIO,
    )
    client = Client()
    client.force_login(user)
    provider_called = False

    async def fail_if_called(self, prompt: str, model: str = "auto", purpose: str = "chat", **kwargs):
        nonlocal provider_called
        provider_called = True
        yield json.dumps({"error": "LLM should not be called in deterministic compiler mode"})

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fail_if_called, raising=False)

    create_response = client.post(
        "/api/studio/assistant/drafts/",
        data=json.dumps(
            {
                "pipeline_name": "K8s rollout compiler",
                "nodes": [],
                "edges": [],
                "user_message": "K8s cluster prod namespace payments rollout restart deployment api-gateway",
                "intent": "create",
                "compiler_mode": "deterministic",
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 201
    assert provider_called is False
    draft_payload = create_response.json()
    revision = draft_payload["latest_revision"]
    response = revision["response"]
    nodes = {node["id"]: node for node in revision["preview_nodes"]}

    assert draft_payload["status"] == PipelineDraftSession.STATUS_READY
    assert response["selected_template"]["slug"] == "pilot-kubernetes-rollout"
    assert response["selected_template"]["source"] == "pilot_template_compiler"
    assert response["validation"]["ok"] is True
    assert response["resource_plan"]["mcp_servers"][0]["id"] == mcp.id
    assert nodes["inspect"]["data"]["mcp_server_id"] == mcp.id
    assert nodes["inspect"]["data"]["input_schema"]["properties"]["namespace"]["type"] == "string"
    assert nodes["inspect"]["data"]["arguments"]["namespace"] == "payments"
    assert nodes["rollout"]["data"]["operation_kind"] == "kubernetes.rollout_restart"
    assert nodes["rollout"]["data"]["requires_approval"] is True
