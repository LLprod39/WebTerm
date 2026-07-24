import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from tests.studio_api_smoke_harness import grant_feature, json_payload


@pytest.mark.django_db
def test_pipeline_assistant_drops_cycle_edges_from_ai_drafts(monkeypatch):
    user = User.objects.create_user(username="studio-assistant-cycle-user", password="x")
    grant_feature(user, "studio", "studio_pipelines")
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
                        {
                            "ref": "daily_3pm_schedule",
                            "type": "trigger/schedule",
                            "label": "Daily 3PM",
                            "data": {"cron_expression": "0 15 * * *"},
                        },
                        {
                            "ref": "collect_logs_multi",
                            "type": "agent/multi",
                            "label": "Collect Logs",
                            "data": {"goal": "Collect logs"},
                        },
                        {
                            "ref": "summarize_report_llm",
                            "type": "agent/llm_query",
                            "label": "Summarize",
                            "data": {"prompt": "Summarize health"},
                        },
                        {
                            "ref": "telegram_report_output",
                            "type": "output/telegram",
                            "label": "Telegram Report",
                            "data": {"message": "Daily report"},
                        },
                        {
                            "ref": "telegram_input",
                            "type": "logic/telegram_input",
                            "label": "Telegram Input",
                            "data": {"message": "Need extra checks?"},
                        },
                        {
                            "ref": "route_tasks_to_monitors",
                            "type": "agent/llm_query",
                            "label": "Route Tasks",
                            "data": {"prompt": "Route operator task"},
                        },
                    ],
                    "edges": [
                        {"source": "daily_3pm_schedule", "target": "collect_logs_multi"},
                        {"source": "collect_logs_multi", "target": "summarize_report_llm", "source_handle": "success"},
                        {
                            "source": "summarize_report_llm",
                            "target": "telegram_report_output",
                            "source_handle": "success",
                        },
                        {"source": "telegram_report_output", "target": "telegram_input", "source_handle": "success"},
                        {"source": "telegram_input", "target": "route_tasks_to_monitors", "source_handle": "received"},
                        {
                            "source": "route_tasks_to_monitors",
                            "target": "summarize_report_llm",
                            "source_handle": "success",
                        },
                    ],
                },
                "warnings": [],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)

    response = client.post(
        "/api/studio/pipelines/assistant/",
        data=json_payload(
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
    grant_feature(user, "studio", "studio_pipelines")
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
                        {
                            "ref": "telegram_chat_webhook",
                            "type": "trigger/webhook",
                            "label": "Telegram Chat Start",
                            "data": {"is_active": True},
                        },
                        {
                            "ref": "telegram_chat_processor",
                            "type": "agent/llm_query",
                            "label": "Telegram Chat Processor",
                            "data": {},
                        },
                    ],
                    "edges": [
                        {"source": "telegram_chat_webhook", "target": "telegram_chat_processor"},
                        {
                            "source": "telegram_chat_processor",
                            "target": "telegram_result_report",
                            "source_handle": "success",
                        },
                    ],
                },
                "warnings": [],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)

    response = client.post(
        "/api/studio/pipelines/assistant/",
        data=json_payload(
            {
                "pipeline_name": "Telegram Agent",
                "nodes": [
                    {
                        "id": "manual_start",
                        "type": "trigger/manual",
                        "position": {"x": 0, "y": 0},
                        "data": {"label": "Manual"},
                    },
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
                    {
                        "id": "edge_manual_cmd",
                        "source": "manual_start",
                        "target": "telegram_cmd_executor",
                        "sourceHandle": "out",
                    },
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
