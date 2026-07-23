"""
Telegram Bot — Server Agent pipeline definition.

Architecture:
  trigger/webhook (Telegram message in)
    → agent/llm_query (parse task & decide if clarification needed)
    → logic/condition (needs clarification?)
      [true]  → output/telegram (ask question)
               → logic/telegram_input (wait reply)
                 [received] → logic/merge (merge_inputs)
                 [timeout]  → logic/merge (merge_results)
      [false] → logic/merge (merge_inputs)
    → agent/multi (execute on servers)
      [success|error] → logic/merge (merge_results)
    → output/telegram (final report)
"""

from __future__ import annotations

from studio.models import CURRENT_PIPELINE_GRAPH_VERSION, Pipeline

TELEGRAM_BOT_PIPELINE_NAME = "Telegram Bot — Server Agent"
TELEGRAM_BOT_DESCRIPTION = (
    "Telegram-управляемый мульти-агент. "
    "Получает задачи через Telegram-вебхук, "
    "выполняет их на серверах и отчитывается обратно в чат. "
    "Поддерживает уточняющие вопросы внутри одного запуска."
)


def build_telegram_bot_nodes() -> list[dict]:
    return [
        {
            "id": "telegram_entry",
            "type": "trigger/webhook",
            "position": {"x": 0, "y": 300},
            "data": {
                "label": "Telegram Message In",
                "is_active": True,
                "webhook_payload_map": {
                    "user_task": "message.text",
                    "tg_chat_id": "message.chat.id",
                    "tg_user_name": "message.from.first_name",
                    "tg_message_id": "message.message_id",
                },
            },
        },
        {
            "id": "understand_task",
            "type": "agent/llm_query",
            "position": {"x": 320, "y": 300},
            "data": {
                "label": "Understand Task",
                "system_prompt": (
                    "You are a task router for a Telegram-controlled server automation system. "
                    "Analyse the user's request and output ONLY valid JSON (no markdown fences):\n"
                    '{"needs_clarification": false, "clarification_question": null, '
                    '"task_summary": "concise one-sentence description of what to do"}\n'
                    "Set needs_clarification=true when the request is vague, "
                    "targets an unknown server, or could be destructive without confirmation."
                ),
                "prompt": (
                    "Incoming Telegram message from {tg_user_name}:\n\n{user_task}\n\nReturn the JSON analysis."
                ),
            },
        },
        {
            "id": "check_clarification",
            "type": "logic/condition",
            "position": {"x": 640, "y": 300},
            "data": {
                "label": "Needs Clarification?",
                "condition_source": "understand_task",
                "condition_field": "needs_clarification",
                "condition_operator": "contains",
                "condition_value": "true",
            },
        },
        {
            "id": "ask_question",
            "type": "output/telegram",
            "position": {"x": 960, "y": 80},
            "data": {
                "label": "Ask Clarifying Question",
                "message": ("🤔 *Уточняющий вопрос*\n\n{all_outputs}\n\n_Ответьте на это сообщение текстом._"),
            },
        },
        {
            "id": "wait_reply",
            "type": "logic/telegram_input",
            "position": {"x": 1280, "y": 80},
            "data": {
                "label": "Wait for Clarification",
                "message": (
                    "⏳ *Ожидание уточнения*\n\nПайплайн: *{pipeline_name}* (#{run_id})\n\nЖду вашего ответа..."
                ),
                "timeout_minutes": 120,
            },
        },
        {
            "id": "merge_inputs",
            "type": "logic/merge",
            "position": {"x": 960, "y": 520},
            "data": {"label": "Merge Task Inputs"},
        },
        {
            "id": "run_task",
            "type": "agent/multi",
            "position": {"x": 1280, "y": 520},
            "data": {
                "label": "Execute on Servers",
                "goal": (
                    "Execute the user's server automation request. "
                    "Original message: {user_task}. "
                    "Full context (analysis + clarification if any): {all_outputs}."
                ),
                "system_prompt": (
                    "You are a careful DevOps automation agent with SSH access to all configured servers. "
                    "Always prefer read-only diagnostics first. "
                    "Avoid destructive commands unless the user's request is explicit. "
                    "Summarise results in clear Russian for the operator."
                ),
                "instructions": (
                    "1. Read the original request from context variable {user_task}.\n"
                    "2. Read the task analysis and any clarification from prior node outputs.\n"
                    "3. Identify the most relevant servers for the task.\n"
                    "4. Start with status / log checks before making changes.\n"
                    "5. Execute the task step by step.\n"
                    "6. Verify the result.\n"
                    "7. Return a concise Russian-language summary: what was done, result, warnings."
                ),
                "expected_output": ("Отчёт о выполнении: что сделано, результат, статус серверов, предупреждения."),
            },
        },
        {
            "id": "merge_results",
            "type": "logic/merge",
            "position": {"x": 1600, "y": 400},
            "data": {"label": "Merge Results"},
        },
        {
            "id": "send_report",
            "type": "output/telegram",
            "position": {"x": 1920, "y": 400},
            "data": {
                "label": "Report to User",
                "message": ("📊 *Отчёт по задаче*\n*Пайплайн:* {pipeline_name} | *Запуск:* #{run_id}\n\n{all_outputs}"),
            },
        },
    ]


def build_telegram_bot_edges() -> list[dict]:
    return [
        {
            "id": "e_entry_parse",
            "source": "telegram_entry",
            "target": "understand_task",
            "sourceHandle": "out",
        },
        {
            "id": "e_parse_check",
            "source": "understand_task",
            "target": "check_clarification",
            "sourceHandle": "out",
        },
        {
            "id": "e_check_ask",
            "source": "check_clarification",
            "target": "ask_question",
            "sourceHandle": "true",
        },
        {
            "id": "e_check_merge",
            "source": "check_clarification",
            "target": "merge_inputs",
            "sourceHandle": "false",
        },
        {
            "id": "e_ask_wait",
            "source": "ask_question",
            "target": "wait_reply",
            "sourceHandle": "out",
        },
        {
            "id": "e_wait_merge",
            "source": "wait_reply",
            "target": "merge_inputs",
            "sourceHandle": "received",
        },
        {
            "id": "e_wait_timeout",
            "source": "wait_reply",
            "target": "merge_results",
            "sourceHandle": "timeout",
        },
        {
            "id": "e_merge_run",
            "source": "merge_inputs",
            "target": "run_task",
            "sourceHandle": "out",
        },
        {
            "id": "e_run_ok",
            "source": "run_task",
            "target": "merge_results",
            "sourceHandle": "success",
        },
        {
            "id": "e_run_err",
            "source": "run_task",
            "target": "merge_results",
            "sourceHandle": "error",
        },
        {
            "id": "e_merge_report",
            "source": "merge_results",
            "target": "send_report",
            "sourceHandle": "out",
        },
    ]


def ensure_telegram_bot_pipeline(user) -> Pipeline:
    pipeline, _ = Pipeline.objects.update_or_create(
        owner=user,
        name=TELEGRAM_BOT_PIPELINE_NAME,
        defaults={
            "description": TELEGRAM_BOT_DESCRIPTION,
            "icon": "🤖",
            "tags": ["telegram", "bot", "multi-agent", "servers"],
            "nodes": build_telegram_bot_nodes(),
            "edges": build_telegram_bot_edges(),
            "graph_version": CURRENT_PIPELINE_GRAPH_VERSION,
            "is_shared": False,
        },
    )
    pipeline.sync_triggers_from_nodes()
    return pipeline
