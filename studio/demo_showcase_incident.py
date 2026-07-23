from __future__ import annotations

INCIDENT_PIPELINE_NAME = "AI Incident Triage Showcase"
INCIDENT_PIPELINE_DESCRIPTION = (
    "Демо автоматической классификации инцидентов. Принимает payload (webhook или ручной запуск), "
    "AI определяет серьёзность (P0/P1/P2), в случае P0 запрашивает подтверждение оператора, "
    "параллельно готовит уведомления в три канала и собирает финальный AI-отчёт. "
    "Ничего не делает на ПК — только LLM, логика и отчёты."
)

INCIDENT_DEMO_PAYLOAD = {
    "title": "High latency on checkout API",
    "severity_hint": "high",
    "service": "checkout-api",
    "summary": "p95 latency jumped from 180ms to 1.8s over last 5 minutes, error rate 4%.",
}


def build_incident_nodes() -> list[dict]:
    return [
        {
            "id": "trigger_webhook",
            "type": "trigger/webhook",
            "position": {"x": 80, "y": 40},
            "data": {
                "label": "Webhook Trigger",
                "label_ru": "Webhook запуск",
                "is_active": True,
                "webhook_payload_map": {
                    "title": "title",
                    "severity_hint": "severity_hint",
                    "service": "service",
                    "summary": "summary",
                },
            },
        },
        {
            "id": "trigger_manual",
            "type": "trigger/manual",
            "position": {"x": 360, "y": 40},
            "data": {
                "label": "Manual Demo Run",
                "label_ru": "Ручной демо-запуск",
                "is_active": True,
            },
        },
        {
            "id": "trigger_merge",
            "type": "logic/merge",
            "position": {"x": 220, "y": 170},
            "data": {"label": "Any Trigger", "label_ru": "Любой триггер", "mode": "any"},
        },
        {
            "id": "payload_echo",
            "type": "output/report",
            "position": {"x": 220, "y": 290},
            "data": {
                "label": "Incoming Payload",
                "label_ru": "Входящий payload",
                "template": (
                    "# 🚨 Инцидент принят\n\n"
                    "- **title:** {title}\n"
                    "- **service:** {service}\n"
                    "- **severity hint:** {severity_hint}\n\n"
                    "## Summary\n{summary}\n\n"
                    "Если параметры пустые — значит пайплайн запущен вручную без webhook-payload. "
                    "Для демо можно подставить тестовые значения в контекст запуска."
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "ai_classifier",
            "type": "agent/llm_query",
            "position": {"x": 220, "y": 430},
            "data": {
                "label": "AI Severity Classifier",
                "label_ru": "AI-классификатор серьёзности",
                "system_prompt": (
                    "Ты SRE on-call классификатор. По описанию инцидента аккуратно выбираешь "
                    "один уровень: P0 (прод лежит / выручка падает), P1 (серьёзная деградация), "
                    "P2 (мелочь / наблюдение). Отвечай строго и кратко."
                ),
                "prompt": (
                    "Классифицируй инцидент на основе payload.\n\n"
                    "Payload:\n"
                    "- title: {title}\n"
                    "- service: {service}\n"
                    "- severity hint: {severity_hint}\n"
                    "- summary: {summary}\n\n"
                    "Предыдущие выводы пайплайна:\n{all_outputs}\n\n"
                    "Формат ответа СТРОГО такой:\n"
                    "SEVERITY: <P0|P1|P2>\n"
                    "REASON: <одно предложение>\n"
                    "RECOMMENDED_ACTION: <одно предложение>\n"
                ),
                "include_all_outputs": True,
                "on_failure": "continue",
            },
        },
        {
            "id": "severity_gate",
            "type": "logic/condition",
            "position": {"x": 220, "y": 570},
            "data": {
                "label": "Is P0 Critical?",
                "label_ru": "Это P0?",
                "source_node_id": "ai_classifier",
                "check_type": "contains",
                "check_value": "SEVERITY: P0",
            },
        },
        {
            "id": "human_gate",
            "type": "logic/human_approval",
            "position": {"x": 60, "y": 700},
            "data": {
                "label": "Approve P0 Response",
                "label_ru": "Подтвердить P0",
                "timeout_minutes": 30,
                "base_url": "http://127.0.0.1:9000",
                "to_email": " ",
                "tg_bot_token": " ",
                "tg_chat_id": " ",
                "message": (
                    "Классифицирован P0-инцидент. Требуется подтверждение оператора.\n\n"
                    "{all_outputs}\n\n"
                    "Одобрить: {approve_url}\nОтклонить: {reject_url}"
                ),
            },
        },
        {
            "id": "auto_handled_report",
            "type": "output/report",
            "position": {"x": 380, "y": 700},
            "data": {
                "label": "Auto-Handled (P1/P2)",
                "label_ru": "Обработано автоматически",
                "template": (
                    "# ✅ Автоматическая обработка\n\n"
                    "Инцидент классифицирован как P1/P2 — подтверждение оператора не требуется.\n\n"
                    "### AI-вывод\n{ai_classifier_output}"
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "human_failure_merge",
            "type": "logic/merge",
            "position": {"x": -100, "y": 780},
            "data": {"label": "Rejected Or Timed Out", "label_ru": "Отклонено или timeout", "mode": "any"},
        },
        {
            "id": "rejected_report",
            "type": "output/report",
            "position": {"x": -100, "y": 830},
            "data": {
                "label": "P0 Rejected",
                "label_ru": "P0 отклонено",
                "template": (
                    "# ❌ Оператор отклонил автоматический ответ\n\n"
                    "{human_gate_error}\n\n"
                    "Контекст:\n{ai_classifier_output}"
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "gate_merge",
            "type": "logic/merge",
            "position": {"x": 220, "y": 840},
            "data": {"label": "Continue After Gate", "label_ru": "После решения", "mode": "any"},
        },
        {
            "id": "channels_parallel",
            "type": "logic/parallel",
            "position": {"x": 220, "y": 970},
            "data": {"label": "Prepare Channels", "label_ru": "Подготовка каналов"},
        },
        {
            "id": "channel_slack",
            "type": "output/report",
            "position": {"x": 20, "y": 1110},
            "data": {
                "label": "Slack Draft",
                "label_ru": "Черновик Slack",
                "template": ("# 💬 Slack (мок)\n\n*#incidents*: `{title}` @ `{service}`\n{ai_classifier_output}"),
                "on_failure": "continue",
            },
        },
        {
            "id": "channel_status",
            "type": "output/report",
            "position": {"x": 220, "y": 1110},
            "data": {
                "label": "Statuspage Draft",
                "label_ru": "Черновик Statuspage",
                "template": (
                    "# 📊 Statuspage (мок)\n\n**Investigating — {service}**\n\n{summary}\n\n{ai_classifier_output}"
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "channel_runbook",
            "type": "agent/llm_query",
            "position": {"x": 420, "y": 1110},
            "data": {
                "label": "AI Runbook Hint",
                "label_ru": "AI-подсказка runbook",
                "system_prompt": "Ты on-call engineer. Пишешь 3 конкретных первых шага для разбора инцидента.",
                "prompt": (
                    "На основе данных ниже предложи 3 первых шага runbook (bullet-ы, без кода).\n\n{all_outputs}"
                ),
                "include_all_outputs": True,
                "on_failure": "continue",
            },
        },
        {
            "id": "channels_merge",
            "type": "logic/merge",
            "position": {"x": 220, "y": 1260},
            "data": {"label": "Channels Ready", "label_ru": "Каналы готовы", "mode": "all"},
        },
        {
            "id": "final_summary",
            "type": "agent/llm_query",
            "position": {"x": 220, "y": 1390},
            "data": {
                "label": "AI Executive Summary",
                "label_ru": "AI executive summary",
                "system_prompt": "Ты head of SRE. Пишешь краткий executive summary для руководства.",
                "prompt": (
                    "Собери единый executive summary по инциденту. Используй все предыдущие шаги.\n\n"
                    "{all_outputs}\n\n"
                    "Структура ответа:\n"
                    "1. Что случилось (1 строка)\n"
                    "2. Серьёзность и решение оператора\n"
                    "3. Подготовленные каналы оповещения\n"
                    "4. Рекомендованные первые 3 шага\n"
                    "Будь кратким и деловым."
                ),
                "include_all_outputs": True,
                "on_failure": "continue",
            },
        },
        {
            "id": "final_report",
            "type": "output/report",
            "position": {"x": 220, "y": 1530},
            "data": {
                "label": "Final Incident Report",
                "label_ru": "Финальный отчёт по инциденту",
                "template": (
                    "# 🎯 Incident Triage — финальный отчёт\n\n"
                    "## Payload\n{payload_echo_output}\n\n"
                    "## AI-классификация\n{ai_classifier_output}\n\n"
                    "## Каналы оповещения\n"
                    "### Slack\n{channel_slack_output}\n\n"
                    "### Statuspage\n{channel_status_output}\n\n"
                    "### Runbook hint\n{channel_runbook_output}\n\n"
                    "## Executive summary\n{final_summary_output}\n"
                ),
                "on_failure": "continue",
            },
        },
    ]


def build_incident_edges() -> list[dict]:
    return [
        {"id": "i_e1", "source": "trigger_webhook", "target": "trigger_merge", "sourceHandle": "out", "animated": True},
        {"id": "i_e2", "source": "trigger_manual", "target": "trigger_merge", "sourceHandle": "out", "animated": True},
        {"id": "i_e3", "source": "trigger_merge", "target": "payload_echo", "sourceHandle": "out", "animated": True},
        {
            "id": "i_e4",
            "source": "payload_echo",
            "target": "ai_classifier",
            "sourceHandle": "success",
            "animated": True,
        },
        {
            "id": "i_e5",
            "source": "ai_classifier",
            "target": "severity_gate",
            "sourceHandle": "success",
            "animated": True,
        },
        {
            "id": "i_e6",
            "source": "severity_gate",
            "target": "human_gate",
            "sourceHandle": "true",
            "animated": True,
            "label": "P0",
        },
        {
            "id": "i_e7",
            "source": "severity_gate",
            "target": "auto_handled_report",
            "sourceHandle": "false",
            "animated": True,
            "label": "P1/P2",
        },
        {
            "id": "i_e8",
            "source": "human_gate",
            "target": "gate_merge",
            "sourceHandle": "approved",
            "animated": True,
            "label": "approved",
        },
        {
            "id": "i_e9",
            "source": "human_gate",
            "target": "human_failure_merge",
            "sourceHandle": "rejected",
            "animated": True,
            "label": "rejected",
        },
        {
            "id": "i_e10",
            "source": "human_gate",
            "target": "human_failure_merge",
            "sourceHandle": "timeout",
            "animated": True,
            "label": "timeout",
        },
        {
            "id": "i_e10b",
            "source": "human_failure_merge",
            "target": "rejected_report",
            "sourceHandle": "out",
            "animated": True,
        },
        {
            "id": "i_e11",
            "source": "auto_handled_report",
            "target": "gate_merge",
            "sourceHandle": "success",
            "animated": True,
        },
        {
            "id": "i_e12",
            "source": "rejected_report",
            "target": "gate_merge",
            "sourceHandle": "success",
            "animated": True,
        },
        {"id": "i_e13", "source": "gate_merge", "target": "channels_parallel", "sourceHandle": "out", "animated": True},
        {
            "id": "i_e14",
            "source": "channels_parallel",
            "target": "channel_slack",
            "sourceHandle": "out",
            "animated": True,
        },
        {
            "id": "i_e15",
            "source": "channels_parallel",
            "target": "channel_status",
            "sourceHandle": "out",
            "animated": True,
        },
        {
            "id": "i_e16",
            "source": "channels_parallel",
            "target": "channel_runbook",
            "sourceHandle": "out",
            "animated": True,
        },
        {
            "id": "i_e17",
            "source": "channel_slack",
            "target": "channels_merge",
            "sourceHandle": "success",
            "animated": True,
        },
        {
            "id": "i_e18",
            "source": "channel_status",
            "target": "channels_merge",
            "sourceHandle": "success",
            "animated": True,
        },
        {
            "id": "i_e19",
            "source": "channel_runbook",
            "target": "channels_merge",
            "sourceHandle": "success",
            "animated": True,
        },
        {"id": "i_e20", "source": "channels_merge", "target": "final_summary", "sourceHandle": "out", "animated": True},
        {
            "id": "i_e21",
            "source": "final_summary",
            "target": "final_report",
            "sourceHandle": "success",
            "animated": True,
        },
    ]
