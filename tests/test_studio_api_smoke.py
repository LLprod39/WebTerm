import json
import uuid
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings

from core_ui.models import UserAppPermission
from servers.models import Server
from studio.models import MCPServerPool, Pipeline, PipelineRun, PipelineTemplate


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _llm_node(node_id: str) -> dict:
    return {
        "id": node_id,
        "type": "agent/llm_query",
        "position": {"x": 0, "y": 0},
        "data": {"prompt": "Summarize output", "provider": "gemini"},
    }


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


@pytest.mark.django_db
def test_studio_pipeline_trigger_template_and_servers_endpoints(monkeypatch):
    user = User.objects.create_user(username="studio-user", password="x")
    _grant_feature(user, "studio", "studio_pipelines", "studio_runs", "agents")
    server = Server.objects.create(user=user, name="studio-srv", host="10.0.0.55", username="root")
    client = Client()
    client.force_login(user)

    monkeypatch.setattr("studio.views._launch_pipeline_run_async", lambda _run: None)

    create = client.post(
        "/api/studio/pipelines/",
        data=_json(
            {
                "name": "Ops Flow",
                "nodes": [
                    {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
                    {
                        "id": "webhook",
                        "type": "trigger/webhook",
                        "position": {"x": 0, "y": 100},
                        "data": {"label": "Webhook", "webhook_payload_map": {"branch": "git.ref"}},
                    },
                    _llm_node("manual_task"),
                    _llm_node("webhook_task"),
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
    assert any(item["id"] == pipeline_id for item in pipelines.json())

    detail = client.get(f"/api/studio/pipelines/{pipeline_id}/")
    assert detail.status_code == 200
    assert detail.json()["id"] == pipeline_id

    update = client.put(
        f"/api/studio/pipelines/{pipeline_id}/",
        data=_json({"name": "Ops Flow Updated", "description": "updated"}),
        content_type="application/json",
    )
    assert update.status_code == 200
    assert update.json()["name"] == "Ops Flow Updated"

    run = client.post(
        f"/api/studio/pipelines/{pipeline_id}/run/",
        data=_json({"context": {"branch": "main"}}),
        content_type="application/json",
    )
    assert run.status_code == 202
    run_id = run.json()["id"]
    assert run.json()["entry_node_id"] == "manual"

    pipeline_runs = client.get(f"/api/studio/pipelines/{pipeline_id}/runs/")
    assert pipeline_runs.status_code == 200
    assert any(item["id"] == run_id for item in pipeline_runs.json())

    runs = client.get("/api/studio/runs/")
    assert runs.status_code == 200
    assert any(item["id"] == run_id for item in runs.json())

    clone = client.post(f"/api/studio/pipelines/{pipeline_id}/clone/")
    assert clone.status_code == 201
    assert clone.json()["name"].endswith("(copy)")

    triggers = client.get(f"/api/studio/triggers/?pipeline_id={pipeline_id}")
    assert triggers.status_code == 200
    webhook_trigger = next(item for item in triggers.json() if item["trigger_type"] == "webhook")
    trigger_id = webhook_trigger["id"]

    trigger_update = client.put(
        f"/api/studio/triggers/{trigger_id}/",
        data=_json({"name": "Updated trigger", "is_active": True}),
        content_type="application/json",
    )
    assert trigger_update.status_code == 200
    assert trigger_update.json()["name"] == "Updated trigger"

    trigger_token = trigger_update.json()["webhook_token"]
    receive = client.post(
        f"/api/studio/triggers/{trigger_token}/receive/",
        data=_json({"git": {"ref": "refs/heads/release"}}),
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
    assert any(item["slug"] == template.slug for item in templates.json())

    use_template = client.post(f"/api/studio/templates/{template.slug}/use/")
    assert use_template.status_code == 201
    assert use_template.json()["name"] == "Unit Template"

    studio_servers = client.get("/api/studio/servers/")
    assert studio_servers.status_code == 200
    assert any(item["id"] == server.id for item in studio_servers.json())

    delete = client.delete(f"/api/studio/pipelines/{pipeline_id}/")
    assert delete.status_code == 200
    assert delete.json()["ok"] is True


@pytest.mark.django_db
def test_pipeline_assistant_accepts_history_and_graph_edit_patch(monkeypatch):
    user = User.objects.create_user(username="studio-assistant-user", password="x")
    _grant_feature(user, "studio", "studio_pipelines")
    client = Client()
    client.force_login(user)

    captured: dict[str, str] = {}

    async def fake_stream_chat(self, prompt: str, model: str = "auto", purpose: str = "chat", **kwargs):
        captured["prompt"] = prompt
        yield json.dumps(
            {
                "reply": "Обновил граф.",
                "target_node_id": None,
                "node_patch": {},
                "graph_patch": {
                    "anchor_node_id": "manual_start",
                    "nodes": [],
                    "edges": [],
                    "update_nodes": [
                        {
                            "node_id": "notify",
                            "data": {"message": "Краткий отчет в Telegram"},
                        }
                    ],
                    "remove_node_ids": ["old_wait"],
                    "remove_edge_ids": ["edge_old_wait_notify"],
                },
                "warnings": ["Проверьте токен Telegram."],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)

    response = client.post(
        "/api/studio/pipelines/assistant/",
        data=_json(
            {
                "pipeline_name": "Assistant Flow",
                "nodes": [
                    {"id": "manual_start", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual Start"}},
                    {"id": "notify", "type": "output/telegram", "position": {"x": 240, "y": 0}, "data": {"label": "Notify"}},
                    {"id": "old_wait", "type": "logic/wait", "position": {"x": 120, "y": 120}, "data": {"label": "Old Wait"}},
                ],
                "edges": [
                    {"id": "edge_manual_notify", "source": "manual_start", "target": "notify"},
                    {"id": "edge_old_wait_notify", "source": "old_wait", "target": "notify"},
                ],
                "selected_node": {
                    "id": "notify",
                    "type": "output/telegram",
                    "position": {"x": 240, "y": 0},
                    "data": {"label": "Notify"},
                },
                "history": [
                    {"role": "user", "content": "Собери пайплайн для уведомлений."},
                    {"role": "assistant", "content": "Готов помочь."},
                ],
                "user_message": "Сделай уведомление короче и убери лишний wait.",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"] == "Обновил граф."
    assert payload["graph_patch"]["update_nodes"] == [
        {"node_id": "notify", "data": {"message": "Краткий отчет в Telegram"}}
    ]
    assert payload["graph_patch"]["remove_node_ids"] == ["old_wait"]
    assert payload["graph_patch"]["remove_edge_ids"] == ["edge_old_wait_notify"]
    assert payload["validation"]["ok"] is True
    assert payload["risk"]["level"] == "safe"
    assert payload["patch_summary"]
    assert "Собери пайплайн для уведомлений." in captured["prompt"]
    assert "Сделай уведомление короче и убери лишний wait." in captured["prompt"]


@pytest.mark.django_db
def test_pipeline_assistant_validates_preview_and_flags_dangerous_ssh(monkeypatch):
    user = User.objects.create_user(username="studio-assistant-risk-user", password="x")
    _grant_feature(user, "studio", "studio_pipelines")
    server = Server.objects.create(user=user, name="prod-srv", host="10.0.0.61", username="root")
    client = Client()
    client.force_login(user)

    async def fake_stream_chat(self, prompt: str, model: str = "auto", purpose: str = "chat", **kwargs):
        yield json.dumps(
            {
                "reply": "Собрал черновик, но команда опасная.",
                "target_node_id": None,
                "node_patch": {},
                "graph_patch": {
                    "anchor_node_id": None,
                    "nodes": [
                        {"ref": "manual_start", "type": "trigger/manual", "label": "Manual Start", "data": {"is_active": True}},
                        {
                            "ref": "wipe_step",
                            "type": "agent/ssh_cmd",
                            "label": "Wipe temp",
                            "data": {"server_id": server.id, "command": "rm -rf /tmp/app-cache"},
                            "x_offset": 260,
                        },
                        {"ref": "bad_node", "type": "agent/not_real", "label": "Bad Node", "data": {}, "x_offset": 520},
                    ],
                    "edges": [
                        {"source": "manual_start", "target": "wipe_step"},
                        {"source": "wipe_step", "target": "bad_node"},
                    ],
                    "update_nodes": [],
                    "remove_node_ids": [],
                    "remove_edge_ids": [],
                },
                "warnings": [],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)

    response = client.post(
        "/api/studio/pipelines/assistant/",
        data=_json(
            {
                "pipeline_name": "Risk Draft",
                "nodes": [],
                "edges": [],
                "selected_node": None,
                "intent": "create",
                "draft_mode": True,
                "last_validation_errors": ["previous error"],
                "user_message": "Собери опасный тестовый workflow.",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["validation"]["ok"] is False
    assert not any("unknown type" in item for item in payload["validation"]["errors"])
    assert any("Policy guard" in item and "wipe_step" in item for item in payload["validation"]["errors"])
    assert any("bad_node" in item and "dropped" in item for item in payload["warnings"])
    assert payload["risk"]["level"] == "dangerous"
    assert payload["risk"]["items"][0]["node_id"] == "wipe_step"
    assert payload["suggested_next_actions"]


@pytest.mark.django_db
def test_pipeline_assistant_repairs_common_ai_node_draft_mistakes(monkeypatch):
    user = User.objects.create_user(username="studio-assistant-repair-user", password="x")
    _grant_feature(user, "studio", "studio_pipelines")
    client = Client()
    client.force_login(user)

    async def fake_stream_chat(self, prompt: str, model: str = "auto", purpose: str = "chat", **kwargs):
        yield json.dumps(
            {
                "reply": "Собрал Telegram recheck flow.",
                "target_node_id": None,
                "node_patch": {},
                "graph_patch": {
                    "anchor_node_id": None,
                    "nodes": [
                        {"ref": "manual_start", "type": "trigger/manual", "label": "Manual Start", "data": {"is_active": True}},
                        {
                            "ref": "telegram_trigger",
                            "type": "trigger/telegram_input",
                            "label": "Ask Telegram",
                            "data": {"message": "Нужна повторная проверка?"},
                        },
                        {
                            "ref": "recheck_to_report",
                            "type": "edge_placeholder",
                            "data": {},
                        },
                        {"ref": "report", "type": "output/report", "label": "Report", "data": {"template": "Done"}},
                    ],
                    "edges": [
                        {"source": "manual_start", "target": "telegram_trigger"},
                        {"source": "telegram_trigger", "target": "report", "source_handle": "out"},
                    ],
                },
                "warnings": [],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)

    response = client.post(
        "/api/studio/pipelines/assistant/",
        data=_json(
            {
                "pipeline_name": "Repair Draft",
                "nodes": [],
                "edges": [],
                "selected_node": None,
                "intent": "create",
                "draft_mode": True,
                "user_message": "Собери telegram recheck flow.",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    node_types = {item["ref"]: item["type"] for item in payload["graph_patch"]["nodes"]}
    assert node_types["telegram_trigger"] == "logic/telegram_input"
    assert "recheck_to_report" not in node_types
    assert any(
        edge["source"] == "telegram_trigger"
        and edge["target"] == "report"
        and edge["source_handle"] == "received"
        for edge in payload["graph_patch"]["edges"]
    )
    assert payload["validation"]["ok"] is True
    assert any("trigger/telegram_input" in item and "logic/telegram_input" in item for item in payload["warnings"])
    assert any("edge placeholder" in item for item in payload["warnings"])


@pytest.mark.django_db
def test_pipeline_assistant_repairs_screenshot_like_recheck_branch(monkeypatch):
    user = User.objects.create_user(username="studio-assistant-recheck-user", password="x")
    _grant_feature(user, "studio", "studio_pipelines")
    client = Client()
    client.force_login(user)

    async def fake_stream_chat(self, prompt: str, model: str = "auto", purpose: str = "chat", **kwargs):
        yield json.dumps(
            {
                "reply": "Добавил ветку повторной проверки.",
                "target_node_id": None,
                "node_patch": {},
                "graph_patch": {
                    "anchor_node_id": "telegram_input_request",
                    "nodes": [
                        {"ref": "recheck_ssh_24", "type": "agent/ssh_cmd", "label": "Recheck SSH 24", "data": {"command": "tail -n 100 /var/log/syslog"}},
                        {"ref": "recheck_ssh_31", "type": "agent/ssh_cmd", "label": "Recheck SSH 31", "data": {"command": "tail -n 100 /var/log/syslog"}},
                        {"ref": "recheck_merge", "type": "logic/merge", "label": "Merge Recheck", "data": {}},
                        {"ref": "recheck_telegram", "type": "output/telegram", "label": "Send Recheck", "data": {"message": "Recheck done"}},
                    ],
                    "edges": [
                        {"source": "recheck_parallel", "target": "recheck_24"},
                        {"source": "recheck_parallel", "target": "recheck_31"},
                        {"source": "recheck_24", "target": "recheck_merge"},
                        {"source": "recheck_merge", "target": "recheck_telegram"},
                    ],
                },
                "warnings": [],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)

    response = client.post(
        "/api/studio/pipelines/assistant/",
        data=_json(
            {
                "pipeline_name": "Daily Logs",
                "nodes": [
                    {"id": "manual_start", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
                    {
                        "id": "telegram_input_request",
                        "type": "logic/telegram_input",
                        "position": {"x": 260, "y": 0},
                        "data": {"label": "Telegram Input", "message": "Recheck?"},
                    },
                ],
                "edges": [
                    {"id": "edge_manual_tg", "source": "manual_start", "target": "telegram_input_request", "sourceHandle": "out"},
                ],
                "selected_node": None,
                "intent": "edit",
                "draft_mode": True,
                "user_message": "Добавь ветку повторной проверки как на скрине.",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    node_types = {item["ref"]: item["type"] for item in payload["graph_patch"]["nodes"]}
    assert node_types["recheck_parallel"] == "logic/parallel"
    assert payload["validation"]["ok"] is True
    assert any(
        edge["source"] == "telegram_input_request"
        and edge["target"] == "recheck_parallel"
        and edge["source_handle"] == "received"
        for edge in payload["graph_patch"]["edges"]
    )
    assert any(edge["source"] == "recheck_parallel" and edge["target"] == "recheck_ssh_24" for edge in payload["graph_patch"]["edges"])
    assert any(edge["source"] == "recheck_parallel" and edge["target"] == "recheck_ssh_31" for edge in payload["graph_patch"]["edges"])
    assert any(edge["source"] == "recheck_ssh_31" and edge["target"] == "recheck_merge" for edge in payload["graph_patch"]["edges"])
    assert any("created 'logic/parallel'" in item for item in payload["warnings"])


@pytest.mark.django_db
def test_pipeline_assistant_drops_cycle_edges_from_ai_drafts(monkeypatch):
    user = User.objects.create_user(username="studio-assistant-cycle-user", password="x")
    _grant_feature(user, "studio", "studio_pipelines")
    client = Client()
    client.force_login(user)

    async def fake_stream_chat(self, prompt: str, model: str = "auto", purpose: str = "chat", **kwargs):
        yield json.dumps(
            {
                "reply": "Собрал daily report flow с Telegram task branch.",
                "target_node_id": None,
                "node_patch": {},
                "graph_patch": {
                    "anchor_node_id": None,
                    "nodes": [
                        {"ref": "daily_3pm_schedule", "type": "trigger/schedule", "label": "Daily 3PM", "data": {"cron_expression": "0 15 * * *"}},
                        {"ref": "collect_logs_multi", "type": "agent/multi", "label": "Collect Logs", "data": {"goal": "Collect logs"}},
                        {"ref": "summarize_report_llm", "type": "agent/llm_query", "label": "Summarize", "data": {"prompt": "Summarize health"}},
                        {"ref": "telegram_report_output", "type": "output/telegram", "label": "Telegram Report", "data": {"message": "Daily report"}},
                        {"ref": "telegram_input", "type": "logic/telegram_input", "label": "Telegram Input", "data": {"message": "Need extra checks?"}},
                        {"ref": "route_tasks_to_monitors", "type": "agent/llm_query", "label": "Route Tasks", "data": {"prompt": "Route operator task"}},
                    ],
                    "edges": [
                        {"source": "daily_3pm_schedule", "target": "collect_logs_multi"},
                        {"source": "collect_logs_multi", "target": "summarize_report_llm", "source_handle": "success"},
                        {"source": "summarize_report_llm", "target": "telegram_report_output", "source_handle": "success"},
                        {"source": "telegram_report_output", "target": "telegram_input", "source_handle": "success"},
                        {"source": "telegram_input", "target": "route_tasks_to_monitors", "source_handle": "received"},
                        {"source": "route_tasks_to_monitors", "target": "summarize_report_llm", "source_handle": "success"},
                    ],
                },
                "warnings": [],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)

    response = client.post(
        "/api/studio/pipelines/assistant/",
        data=_json(
            {
                "pipeline_name": "Daily Logs",
                "nodes": [],
                "edges": [],
                "selected_node": None,
                "intent": "create",
                "draft_mode": True,
                "user_message": "Сделай ежедневный отчет и Telegram задачи.",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["validation"]["ok"] is True
    assert not any("cycle" in item.lower() for item in payload["validation"]["errors"])
    assert not any(
        edge["source"] == "route_tasks_to_monitors" and edge["target"] == "summarize_report_llm"
        for edge in payload["graph_patch"]["edges"]
    )
    assert any("would create a cycle" in item for item in payload["warnings"])


@pytest.mark.django_db
def test_pipeline_assistant_inserts_merge_for_existing_shared_target_and_fills_ai_prompts(monkeypatch):
    user = User.objects.create_user(username="studio-assistant-merge-user", password="x")
    _grant_feature(user, "studio", "studio_pipelines")
    client = Client()
    client.force_login(user)

    async def fake_stream_chat(self, prompt: str, model: str = "auto", purpose: str = "chat", **kwargs):
        yield json.dumps(
            {
                "reply": "Добавил Telegram chat branch.",
                "target_node_id": None,
                "node_patch": {},
                "graph_patch": {
                    "anchor_node_id": "telegram_result_report",
                    "nodes": [
                        {"ref": "telegram_chat_webhook", "type": "trigger/webhook", "label": "Telegram Chat Start", "data": {"is_active": True}},
                        {"ref": "telegram_chat_processor", "type": "agent/llm_query", "label": "Telegram Chat Processor", "data": {}},
                    ],
                    "edges": [
                        {"source": "telegram_chat_webhook", "target": "telegram_chat_processor"},
                        {"source": "telegram_chat_processor", "target": "telegram_result_report", "source_handle": "success"},
                    ],
                },
                "warnings": [],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)

    response = client.post(
        "/api/studio/pipelines/assistant/",
        data=_json(
            {
                "pipeline_name": "Telegram Agent",
                "nodes": [
                    {"id": "manual_start", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
                    {
                        "id": "telegram_cmd_executor",
                        "type": "agent/ssh_cmd",
                        "position": {"x": 260, "y": 0},
                        "data": {"label": "Telegram Command Executor", "server_id": "", "command": "uptime"},
                    },
                    {
                        "id": "telegram_result_report",
                        "type": "output/telegram",
                        "position": {"x": 520, "y": 0},
                        "data": {"label": "Telegram Result"},
                    },
                ],
                "edges": [
                    {"id": "edge_manual_cmd", "source": "manual_start", "target": "telegram_cmd_executor", "sourceHandle": "out"},
                    {
                        "id": "edge_cmd_result",
                        "source": "telegram_cmd_executor",
                        "target": "telegram_result_report",
                        "sourceHandle": "success",
                    },
                ],
                "selected_node": None,
                "intent": "edit",
                "draft_mode": True,
                "user_message": "Добавь возможность писать ИИ агенту через Telegram в любое время.",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["validation"]["ok"] is True
    assert "edge_cmd_result" in payload["graph_patch"]["remove_edge_ids"]
    node_types = {item["ref"]: item["type"] for item in payload["graph_patch"]["nodes"]}
    merge_refs = [ref for ref, node_type in node_types.items() if node_type == "logic/merge"]
    assert merge_refs
    merge_ref = merge_refs[0]
    edges = payload["graph_patch"]["edges"]
    assert any(edge["source"] == "telegram_cmd_executor" and edge["target"] == merge_ref for edge in edges)
    assert any(edge["source"] == "telegram_chat_processor" and edge["target"] == merge_ref for edge in edges)
    assert any(edge["source"] == merge_ref and edge["target"] == "telegram_result_report" for edge in edges)
    processor = next(item for item in payload["graph_patch"]["nodes"] if item["ref"] == "telegram_chat_processor")
    assert processor["data"]["prompt"]
    assert processor["data"]["system_prompt"]
    assert any("inserted merge" in item for item in payload["warnings"])


@pytest.mark.django_db
@override_settings(PIPELINE_ACTIVE_RUNS_PER_USER_LIMIT=1, PIPELINE_ACTIVE_RUNS_GLOBAL_LIMIT=0)
def test_pipeline_run_enforces_user_active_run_limit(monkeypatch):
    user = User.objects.create_user(username="studio-limit-user", password="x")
    _grant_feature(user, "studio", "studio_pipelines", "studio_runs", "agents")
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
        "studio.views._launch_pipeline_run_async",
        lambda _run: pytest.fail("_launch_pipeline_run_async should not be called when the active-run limit is hit"),
    )

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=_json({"context": {}}),
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
        data=_json(
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
    assert any(item["id"] == mcp_id for item in mcp_list.json())

    mcp_detail = client.get(f"/api/studio/mcp/{mcp_id}/")
    assert mcp_detail.status_code == 200
    assert mcp_detail.json()["name"] == "Demo MCP"

    mcp_update = client.put(
        f"/api/studio/mcp/{mcp_id}/",
        data=_json({"name": "Demo MCP Updated", "url": "http://127.0.0.1:8765/sse"}),
        content_type="application/json",
    )
    assert mcp_update.status_code == 200
    assert mcp_update.json()["name"] == "Demo MCP Updated"

    monkeypatch.setattr("studio.views._test_mcp_connection", lambda _mcp: (True, None))
    mcp_test = client.post(f"/api/studio/mcp/{mcp_id}/test/")
    assert mcp_test.status_code == 200
    assert mcp_test.json()["ok"] is True

    async def fake_inspect_mcp_server(_mcp):
        return {"server": {"name": "Demo MCP"}, "tools": [{"name": "ping"}]}

    monkeypatch.setattr("studio.views.inspect_mcp_server", fake_inspect_mcp_server)
    mcp_tools = client.get(f"/api/studio/mcp/{mcp_id}/tools/")
    assert mcp_tools.status_code == 200
    assert mcp_tools.json()["server"]["name"] == "Demo MCP"

    mcp_templates = client.get("/api/studio/mcp/templates/")
    assert mcp_templates.status_code == 200
    assert any(item["slug"] == "filesystem" for item in mcp_templates.json())

    agent_create = client.post(
        "/api/studio/agents/",
        data=_json(
            {
                "name": "Studio Agent",
                "model": "gemini-2.0-flash-exp",
                "allowed_tools": ["report", "ask_user"],
                "skill_slugs": ["keycloak-safety"],
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
    assert any(item["id"] == agent_id for item in agents.json())

    agent_detail = client.get(f"/api/studio/agents/{agent_id}/")
    assert agent_detail.status_code == 200
    assert agent_detail.json()["id"] == agent_id
    assert agent_detail.json()["mcp_servers"][0]["id"] == mcp_id

    agent_update = client.put(
        f"/api/studio/agents/{agent_id}/",
        data=_json({"skill_slugs": ["keycloak-safety", "keycloak-test-profile"]}),
        content_type="application/json",
    )
    assert agent_update.status_code == 200
    assert "keycloak-test-profile" in agent_update.json()["skill_slugs"]

    skills = client.get("/api/studio/skills/")
    assert skills.status_code == 200
    assert any(item["slug"] == "keycloak-safety" for item in skills.json())

    skill_detail = client.get("/api/studio/skills/keycloak-safety/")
    assert skill_detail.status_code == 200
    assert skill_detail.json()["slug"] == "keycloak-safety"

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
    monkeypatch.setattr("studio.views._NOTIF_CONFIG_PATH", temp_config)

    save = client.post(
        "/api/studio/notifications/",
        data=_json(
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
    _grant_feature(user, "studio")
    client = Client()
    client.force_login(user)

    mcp_list = client.get("/api/studio/mcp/")
    assert mcp_list.status_code == 403

    mcp_create = client.post(
        "/api/studio/mcp/",
        data=_json({"name": "Blocked MCP", "transport": "stdio", "command": "echo"}),
        content_type="application/json",
    )
    assert mcp_create.status_code == 403

    notif_get = client.get("/api/studio/notifications/")
    assert notif_get.status_code == 403

    notif_post = client.post(
        "/api/studio/notifications/",
        data=_json({"notify_email": "ops@example.com"}),
        content_type="application/json",
    )
    assert notif_post.status_code == 403

    scaffold = client.post(
        "/api/studio/skills/scaffold/",
        data=_json({"name": "Blocked Skill", "description": "should fail"}),
        content_type="application/json",
    )
    assert scaffold.status_code == 403

    workspace = client.get("/api/studio/skills/keycloak-safety/workspace/")
    assert workspace.status_code == 403

    validate = client.post(
        "/api/studio/skills/validate/",
        data=_json({"slugs": ["keycloak-safety"]}),
        content_type="application/json",
    )
    assert validate.status_code == 403
