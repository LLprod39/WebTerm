import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from servers.models import Server
from tests.studio_api_smoke_harness import grant_feature, json_payload


@pytest.mark.django_db
def test_pipeline_assistant_accepts_history_and_graph_edit_patch(monkeypatch):
    user = User.objects.create_user(username="studio-assistant-user", password="x")
    grant_feature(user, "studio", "studio_pipelines")
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
        data=json_payload(
            {
                "pipeline_name": "Assistant Flow",
                "nodes": [
                    {
                        "id": "manual_start",
                        "type": "trigger/manual",
                        "position": {"x": 0, "y": 0},
                        "data": {"label": "Manual Start"},
                    },
                    {
                        "id": "notify",
                        "type": "output/telegram",
                        "position": {"x": 240, "y": 0},
                        "data": {"label": "Notify"},
                    },
                    {
                        "id": "old_wait",
                        "type": "logic/wait",
                        "position": {"x": 120, "y": 120},
                        "data": {"label": "Old Wait"},
                    },
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
    grant_feature(user, "studio", "studio_pipelines")
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
                        {
                            "ref": "manual_start",
                            "type": "trigger/manual",
                            "label": "Manual Start",
                            "data": {"is_active": True},
                        },
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
        data=json_payload(
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
    grant_feature(user, "studio", "studio_pipelines")
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
                        {
                            "ref": "manual_start",
                            "type": "trigger/manual",
                            "label": "Manual Start",
                            "data": {"is_active": True},
                        },
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
        data=json_payload(
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
        edge["source"] == "telegram_trigger" and edge["target"] == "report" and edge["source_handle"] == "received"
        for edge in payload["graph_patch"]["edges"]
    )
    assert payload["validation"]["ok"] is True
    assert any("trigger/telegram_input" in item and "logic/telegram_input" in item for item in payload["warnings"])
    assert any("edge placeholder" in item for item in payload["warnings"])


@pytest.mark.django_db
def test_pipeline_assistant_repairs_screenshot_like_recheck_branch(monkeypatch):
    user = User.objects.create_user(username="studio-assistant-recheck-user", password="x")
    grant_feature(user, "studio", "studio_pipelines")
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
                        {
                            "ref": "recheck_ssh_24",
                            "type": "agent/ssh_cmd",
                            "label": "Recheck SSH 24",
                            "data": {"command": "tail -n 100 /var/log/syslog"},
                        },
                        {
                            "ref": "recheck_ssh_31",
                            "type": "agent/ssh_cmd",
                            "label": "Recheck SSH 31",
                            "data": {"command": "tail -n 100 /var/log/syslog"},
                        },
                        {"ref": "recheck_merge", "type": "logic/merge", "label": "Merge Recheck", "data": {}},
                        {
                            "ref": "recheck_telegram",
                            "type": "output/telegram",
                            "label": "Send Recheck",
                            "data": {"message": "Recheck done"},
                        },
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
        data=json_payload(
            {
                "pipeline_name": "Daily Logs",
                "nodes": [
                    {
                        "id": "manual_start",
                        "type": "trigger/manual",
                        "position": {"x": 0, "y": 0},
                        "data": {"label": "Manual"},
                    },
                    {
                        "id": "telegram_input_request",
                        "type": "logic/telegram_input",
                        "position": {"x": 260, "y": 0},
                        "data": {"label": "Telegram Input", "message": "Recheck?"},
                    },
                ],
                "edges": [
                    {
                        "id": "edge_manual_tg",
                        "source": "manual_start",
                        "target": "telegram_input_request",
                        "sourceHandle": "out",
                    },
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
    assert any(
        edge["source"] == "recheck_parallel" and edge["target"] == "recheck_ssh_24"
        for edge in payload["graph_patch"]["edges"]
    )
    assert any(
        edge["source"] == "recheck_parallel" and edge["target"] == "recheck_ssh_31"
        for edge in payload["graph_patch"]["edges"]
    )
    assert any(
        edge["source"] == "recheck_ssh_31" and edge["target"] == "recheck_merge"
        for edge in payload["graph_patch"]["edges"]
    )
    assert any("created 'logic/parallel'" in item for item in payload["warnings"])


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
