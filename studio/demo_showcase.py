"""
Demo showcase pipelines for Agent Studio — safe, visually impressive, easy to run.

Все пайплайны построены только на безопасных узлах:
  - trigger/manual, trigger/webhook
  - agent/llm_query (только LLM, без SSH/exec)
  - logic/condition, logic/parallel, logic/merge, logic/human_approval
  - output/report (только текст в UI), output/webhook → локальный /api/health/

Никаких SSH-команд, записи файлов, MCP-серверов или destructive-действий.
Каждый пайплайн — самодостаточная "вау"-демка на нодовой системе:

  1. "AI Incident Triage Showcase" — AI-классификация инцидента → условие →
     human approval для P0 → параллельная рассылка по мок-каналам → финальный AI-summary.
  2. "AI Content Studio Showcase" — AI-бриф → параллельный fan-out на трёх
     AI-писателей (Twitter / LinkedIn / Blog) → AI-редактор → финальный контент-пак.
  3. "AI Data Detective Showcase" — параллельный аудит тремя AI-экспертами
     (Risk / Optimization / UX) → AI-синтез → условие confidence → итоговый бриф.
"""
from __future__ import annotations

from .models import CURRENT_PIPELINE_GRAPH_VERSION, Pipeline

LOCAL_WEBHOOK_TARGET = "http://127.0.0.1:9000/api/health/"

DEMO_SHOWCASE_TAGS = ["demo", "showcase", "safe", "llm", "studio"]

# ---------------------------------------------------------------------------
# 1. AI Incident Triage Showcase
# ---------------------------------------------------------------------------

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
                "template": (
                    "# 💬 Slack (мок)\n\n"
                    "*#incidents*: `{title}` @ `{service}`\n"
                    "{ai_classifier_output}"
                ),
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
                    "# 📊 Statuspage (мок)\n\n"
                    "**Investigating — {service}**\n\n"
                    "{summary}\n\n"
                    "{ai_classifier_output}"
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
                    "На основе данных ниже предложи 3 первых шага runbook (bullet-ы, без кода).\n\n"
                    "{all_outputs}"
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
        {"id": "i_e4", "source": "payload_echo", "target": "ai_classifier", "sourceHandle": "success", "animated": True},
        {"id": "i_e5", "source": "ai_classifier", "target": "severity_gate", "sourceHandle": "success", "animated": True},
        {"id": "i_e6", "source": "severity_gate", "target": "human_gate", "sourceHandle": "true", "animated": True, "label": "P0"},
        {"id": "i_e7", "source": "severity_gate", "target": "auto_handled_report", "sourceHandle": "false", "animated": True, "label": "P1/P2"},
        {"id": "i_e8", "source": "human_gate", "target": "gate_merge", "sourceHandle": "approved", "animated": True, "label": "approved"},
        {"id": "i_e9", "source": "human_gate", "target": "rejected_report", "sourceHandle": "rejected", "animated": True, "label": "rejected"},
        {"id": "i_e10", "source": "human_gate", "target": "rejected_report", "sourceHandle": "timeout", "animated": True, "label": "timeout"},
        {"id": "i_e11", "source": "auto_handled_report", "target": "gate_merge", "sourceHandle": "success", "animated": True},
        {"id": "i_e12", "source": "rejected_report", "target": "gate_merge", "sourceHandle": "success", "animated": True},
        {"id": "i_e13", "source": "gate_merge", "target": "channels_parallel", "sourceHandle": "out", "animated": True},
        {"id": "i_e14", "source": "channels_parallel", "target": "channel_slack", "sourceHandle": "out", "animated": True},
        {"id": "i_e15", "source": "channels_parallel", "target": "channel_status", "sourceHandle": "out", "animated": True},
        {"id": "i_e16", "source": "channels_parallel", "target": "channel_runbook", "sourceHandle": "out", "animated": True},
        {"id": "i_e17", "source": "channel_slack", "target": "channels_merge", "sourceHandle": "success", "animated": True},
        {"id": "i_e18", "source": "channel_status", "target": "channels_merge", "sourceHandle": "success", "animated": True},
        {"id": "i_e19", "source": "channel_runbook", "target": "channels_merge", "sourceHandle": "success", "animated": True},
        {"id": "i_e20", "source": "channels_merge", "target": "final_summary", "sourceHandle": "out", "animated": True},
        {"id": "i_e21", "source": "final_summary", "target": "final_report", "sourceHandle": "success", "animated": True},
    ]


# ---------------------------------------------------------------------------
# 2. AI Content Studio Showcase
# ---------------------------------------------------------------------------

CONTENT_PIPELINE_NAME = "AI Content Studio Showcase"
CONTENT_PIPELINE_DESCRIPTION = (
    "Демо параллельной AI-фабрики контента. По одной теме запускает трёх AI-писателей одновременно "
    "(Twitter/X, LinkedIn, Blog intro), потом AI-редактор оценивает и собирает единый контент-пак. "
    "Наглядно показывает fan-out, параллельное выполнение и AI-оценку качества."
)

CONTENT_DEFAULT_TOPIC = "Умная автоматизация инфраструктуры с AI-агентами"


def build_content_nodes() -> list[dict]:
    return [
        {
            "id": "content_manual",
            "type": "trigger/manual",
            "position": {"x": 200, "y": 40},
            "data": {
                "label": "Start Content Run",
                "label_ru": "Запустить контент-прогон",
                "is_active": True,
            },
        },
        {
            "id": "content_webhook",
            "type": "trigger/webhook",
            "position": {"x": 440, "y": 40},
            "data": {
                "label": "Webhook (optional)",
                "label_ru": "Webhook (опционально)",
                "is_active": True,
                "webhook_payload_map": {"topic": "topic", "audience": "audience"},
            },
        },
        {
            "id": "content_merge_in",
            "type": "logic/merge",
            "position": {"x": 320, "y": 170},
            "data": {"label": "Any Trigger", "label_ru": "Любой триггер", "mode": "any"},
        },
        {
            "id": "brief",
            "type": "agent/llm_query",
            "position": {"x": 320, "y": 300},
            "data": {
                "label": "AI Creative Brief",
                "label_ru": "AI creative brief",
                "system_prompt": (
                    "Ты опытный контент-стратег. Делаешь короткий творческий бриф "
                    "с 3 ключевыми углами подачи темы."
                ),
                "prompt": (
                    f"Тема: {{topic}} (если пусто — используй '{CONTENT_DEFAULT_TOPIC}').\n"
                    "Аудитория: {audience} (если пусто — tech-руководители и SRE).\n\n"
                    "Сформируй бриф строго в формате:\n"
                    "TOPIC: <финальная тема>\n"
                    "AUDIENCE: <описание>\n"
                    "ANGLE_1: <короткий тезис>\n"
                    "ANGLE_2: <короткий тезис>\n"
                    "ANGLE_3: <короткий тезис>\n"
                    "TONE: <3 прилагательных через запятую>\n"
                ),
                "include_all_outputs": False,
                "on_failure": "continue",
            },
        },
        {
            "id": "content_parallel",
            "type": "logic/parallel",
            "position": {"x": 320, "y": 450},
            "data": {"label": "Parallel Writers", "label_ru": "Параллельные писатели"},
        },
        {
            "id": "writer_twitter",
            "type": "agent/llm_query",
            "position": {"x": 80, "y": 590},
            "data": {
                "label": "Twitter/X Writer",
                "label_ru": "Twitter/X писатель",
                "system_prompt": "Ты пишешь цепляющие твиты до 280 символов, с одним эмодзи и без хэштегов.",
                "prompt": (
                    "Используя бриф ниже, напиши 1 твит (до 280 символов).\n\n{all_outputs}\n\n"
                    "Строго только текст твита, без комментариев."
                ),
                "include_all_outputs": True,
                "on_failure": "continue",
            },
        },
        {
            "id": "writer_linkedin",
            "type": "agent/llm_query",
            "position": {"x": 320, "y": 590},
            "data": {
                "label": "LinkedIn Writer",
                "label_ru": "LinkedIn писатель",
                "system_prompt": "Ты пишешь профессиональные LinkedIn-посты (150-220 слов) с конкретикой и CTA в конце.",
                "prompt": (
                    "Используя бриф ниже, напиши LinkedIn-пост.\n\n{all_outputs}\n\n"
                    "Структура: зацепка → 2 абзаца по сути → 1 строка CTA."
                ),
                "include_all_outputs": True,
                "on_failure": "continue",
            },
        },
        {
            "id": "writer_blog",
            "type": "agent/llm_query",
            "position": {"x": 560, "y": 590},
            "data": {
                "label": "Blog Intro Writer",
                "label_ru": "Blog intro писатель",
                "system_prompt": "Ты пишешь сильные интро для tech-блога. Без воды, с конкретикой.",
                "prompt": (
                    "Используя бриф ниже, напиши вступление к блог-статье (2 абзаца).\n\n{all_outputs}\n\n"
                    "В конце добавь строку `HOOK: <одно предложение главного обещания статьи>`."
                ),
                "include_all_outputs": True,
                "on_failure": "continue",
            },
        },
        {
            "id": "content_merge_out",
            "type": "logic/merge",
            "position": {"x": 320, "y": 740},
            "data": {"label": "Writers Done", "label_ru": "Писатели готовы", "mode": "all"},
        },
        {
            "id": "editor",
            "type": "agent/llm_query",
            "position": {"x": 320, "y": 870},
            "data": {
                "label": "AI Senior Editor",
                "label_ru": "AI senior editor",
                "system_prompt": (
                    "Ты строгий senior editor. Оцениваешь контент по 5 критериям "
                    "(tone-match, clarity, hook, CTA, value) от 1 до 5 и даёшь одну рекомендацию по улучшению."
                ),
                "prompt": (
                    "Оцени три фрагмента ниже и дай отчёт.\n\n{all_outputs}\n\n"
                    "Формат:\n"
                    "TWITTER_SCORE: X/5 — короткий комментарий\n"
                    "LINKEDIN_SCORE: X/5 — короткий комментарий\n"
                    "BLOG_SCORE: X/5 — короткий комментарий\n"
                    "TOP_FIX: <одна конкретная правка>\n"
                ),
                "include_all_outputs": True,
                "on_failure": "continue",
            },
        },
        {
            "id": "content_report",
            "type": "output/report",
            "position": {"x": 320, "y": 1020},
            "data": {
                "label": "Content Pack Report",
                "label_ru": "Отчёт контент-пака",
                "template": (
                    "# ✍️ Контент-пак готов\n\n"
                    "## Creative brief\n{brief_output}\n\n"
                    "## Twitter / X\n{writer_twitter_output}\n\n"
                    "## LinkedIn\n{writer_linkedin_output}\n\n"
                    "## Blog intro\n{writer_blog_output}\n\n"
                    "## Editor review\n{editor_output}\n"
                ),
                "on_failure": "continue",
            },
        },
    ]


def build_content_edges() -> list[dict]:
    return [
        {"id": "c_e1", "source": "content_manual", "target": "content_merge_in", "sourceHandle": "out", "animated": True},
        {"id": "c_e2", "source": "content_webhook", "target": "content_merge_in", "sourceHandle": "out", "animated": True},
        {"id": "c_e3", "source": "content_merge_in", "target": "brief", "sourceHandle": "out", "animated": True},
        {"id": "c_e4", "source": "brief", "target": "content_parallel", "sourceHandle": "success", "animated": True},
        {"id": "c_e5", "source": "content_parallel", "target": "writer_twitter", "sourceHandle": "out", "animated": True},
        {"id": "c_e6", "source": "content_parallel", "target": "writer_linkedin", "sourceHandle": "out", "animated": True},
        {"id": "c_e7", "source": "content_parallel", "target": "writer_blog", "sourceHandle": "out", "animated": True},
        {"id": "c_e8", "source": "writer_twitter", "target": "content_merge_out", "sourceHandle": "success", "animated": True},
        {"id": "c_e9", "source": "writer_linkedin", "target": "content_merge_out", "sourceHandle": "success", "animated": True},
        {"id": "c_e10", "source": "writer_blog", "target": "content_merge_out", "sourceHandle": "success", "animated": True},
        {"id": "c_e11", "source": "content_merge_out", "target": "editor", "sourceHandle": "out", "animated": True},
        {"id": "c_e12", "source": "editor", "target": "content_report", "sourceHandle": "success", "animated": True},
    ]


# ---------------------------------------------------------------------------
# 3. AI Data Detective Showcase
# ---------------------------------------------------------------------------

DETECTIVE_PIPELINE_NAME = "AI Data Detective Showcase"
DETECTIVE_PIPELINE_DESCRIPTION = (
    "Демо многоугольного AI-анализа. По одному брифу продукта три AI-эксперта параллельно "
    "анализируют его с разных сторон (риски, оптимизация, UX), затем AI-синтезатор сводит всё "
    "в единый план. В конце пайплайн проверяет уровень уверенности и выдаёт один из двух отчётов."
)

DETECTIVE_DEFAULT_BRIEF = (
    "Онбординг в SaaS-продукте: 40% новых пользователей не доходят до первого ценного действия "
    "за 7 дней. Команда хочет поднять activation rate до 60% за квартал."
)


def build_detective_nodes() -> list[dict]:
    return [
        {
            "id": "dt_manual",
            "type": "trigger/manual",
            "position": {"x": 220, "y": 40},
            "data": {"label": "Start Analysis", "label_ru": "Запустить анализ", "is_active": True},
        },
        {
            "id": "dt_webhook",
            "type": "trigger/webhook",
            "position": {"x": 460, "y": 40},
            "data": {
                "label": "Webhook (optional)",
                "label_ru": "Webhook (опционально)",
                "is_active": True,
                "webhook_payload_map": {"brief": "brief", "goal": "goal"},
            },
        },
        {
            "id": "dt_merge_in",
            "type": "logic/merge",
            "position": {"x": 340, "y": 170},
            "data": {"label": "Any Trigger", "label_ru": "Любой триггер", "mode": "any"},
        },
        {
            "id": "dt_intake",
            "type": "output/report",
            "position": {"x": 340, "y": 290},
            "data": {
                "label": "Case Intake",
                "label_ru": "Входящий кейс",
                "template": (
                    "# 🔍 Входящий кейс\n\n"
                    f"- **brief:** {{brief}} (если пусто — будет использован дефолт: "
                    f"'{DETECTIVE_DEFAULT_BRIEF}')\n"
                    "- **goal:** {goal}\n"
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "dt_parallel",
            "type": "logic/parallel",
            "position": {"x": 340, "y": 430},
            "data": {"label": "Parallel Experts", "label_ru": "Параллельные эксперты"},
        },
        {
            "id": "expert_risk",
            "type": "agent/llm_query",
            "position": {"x": 80, "y": 570},
            "data": {
                "label": "Risk Analyst",
                "label_ru": "Risk-аналитик",
                "system_prompt": "Ты опытный risk-аналитик продукта. Видишь то, что может пойти не так.",
                "prompt": (
                    f"Бриф: {{brief}} (если пусто — используй дефолт: '{DETECTIVE_DEFAULT_BRIEF}')\n"
                    "Цель: {goal} (если пусто — 'поднять activation rate').\n\n"
                    "Найди 3 главных риска. Формат:\n"
                    "RISK_1: <описание> | IMPACT: H/M/L | MITIGATION: <идея>\n"
                    "RISK_2: ...\n"
                    "RISK_3: ...\n"
                ),
                "include_all_outputs": False,
                "on_failure": "continue",
            },
        },
        {
            "id": "expert_opt",
            "type": "agent/llm_query",
            "position": {"x": 340, "y": 570},
            "data": {
                "label": "Optimization Expert",
                "label_ru": "Эксперт по оптимизации",
                "system_prompt": "Ты head of growth. Ищешь быстрые и измеримые рычаги роста.",
                "prompt": (
                    f"Бриф: {{brief}} (если пусто — используй дефолт: '{DETECTIVE_DEFAULT_BRIEF}')\n"
                    "Цель: {goal} (если пусто — 'поднять activation rate').\n\n"
                    "Предложи 3 конкретных рычага роста. Формат:\n"
                    "LEVER_1: <что сделать> | EXPECTED_LIFT: <%> | EFFORT: S/M/L\n"
                    "LEVER_2: ...\n"
                    "LEVER_3: ...\n"
                ),
                "include_all_outputs": False,
                "on_failure": "continue",
            },
        },
        {
            "id": "expert_ux",
            "type": "agent/llm_query",
            "position": {"x": 600, "y": 570},
            "data": {
                "label": "UX Auditor",
                "label_ru": "UX-аудитор",
                "system_prompt": "Ты принципиальный UX-аудитор. Видишь friction в onboarding и формах.",
                "prompt": (
                    f"Бриф: {{brief}} (если пусто — используй дефолт: '{DETECTIVE_DEFAULT_BRIEF}')\n\n"
                    "Найди 3 проблемы UX и предложи фикс. Формат:\n"
                    "UX_1: <проблема> → FIX: <решение>\n"
                    "UX_2: ...\n"
                    "UX_3: ...\n"
                ),
                "include_all_outputs": False,
                "on_failure": "continue",
            },
        },
        {
            "id": "dt_merge_out",
            "type": "logic/merge",
            "position": {"x": 340, "y": 720},
            "data": {"label": "Experts Done", "label_ru": "Эксперты готовы", "mode": "all"},
        },
        {
            "id": "dt_synth",
            "type": "agent/llm_query",
            "position": {"x": 340, "y": 850},
            "data": {
                "label": "AI Synthesizer",
                "label_ru": "AI-синтезатор",
                "system_prompt": (
                    "Ты принципал-консультант. Сводишь мнения трёх экспертов в один план "
                    "с приоритизацией ICE (Impact, Confidence, Ease)."
                ),
                "prompt": (
                    "Сведи отчёты трёх экспертов в один план действий.\n\n{all_outputs}\n\n"
                    "Структура ответа:\n"
                    "TOP_3_ACTIONS:\n"
                    "  1. <действие> — ICE: I=?/10, C=?/10, E=?/10\n"
                    "  2. ...\n"
                    "  3. ...\n"
                    "OVERALL_CONFIDENCE: <HIGH|MEDIUM|LOW>\n"
                    "NEXT_STEP: <одно предложение>\n"
                ),
                "include_all_outputs": True,
                "on_failure": "continue",
            },
        },
        {
            "id": "confidence_gate",
            "type": "logic/condition",
            "position": {"x": 340, "y": 1000},
            "data": {
                "label": "Confidence HIGH?",
                "label_ru": "Высокая уверенность?",
                "source_node_id": "dt_synth",
                "check_type": "contains",
                "check_value": "OVERALL_CONFIDENCE: HIGH",
            },
        },
        {
            "id": "green_light_report",
            "type": "output/report",
            "position": {"x": 140, "y": 1140},
            "data": {
                "label": "Green-Light Brief",
                "label_ru": "Green-light бриф",
                "template": (
                    "# 🟢 Go: рекомендуем запускать\n\n"
                    "AI-анализ показал высокий уровень уверенности.\n\n"
                    "## План\n{dt_synth_output}\n\n"
                    "## Подробности по экспертам\n"
                    "### Risks\n{expert_risk_output}\n\n"
                    "### Levers\n{expert_opt_output}\n\n"
                    "### UX\n{expert_ux_output}\n"
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "needs_more_report",
            "type": "output/report",
            "position": {"x": 540, "y": 1140},
            "data": {
                "label": "Needs-More-Data Brief",
                "label_ru": "Нужно больше данных",
                "template": (
                    "# 🟡 Требуются дополнительные данные\n\n"
                    "Уверенность синтеза ниже HIGH — стоит собрать ещё сигналов.\n\n"
                    "## Текущий план\n{dt_synth_output}\n\n"
                    "## Что ещё стоит проверить\n"
                    "- Поговорить с 5 новыми пользователями, которые отвалились на онбординге.\n"
                    "- Проверить события воронки в продуктовой аналитике за последние 30 дней.\n"
                    "- Запустить A/B на самом слабом шаге воронки.\n"
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "dt_final_merge",
            "type": "logic/merge",
            "position": {"x": 340, "y": 1290},
            "data": {"label": "Brief Ready", "label_ru": "Бриф готов", "mode": "any"},
        },
        {
            "id": "dt_final",
            "type": "output/report",
            "position": {"x": 340, "y": 1410},
            "data": {
                "label": "Final Detective Report",
                "label_ru": "Финальный отчёт детектива",
                "template": (
                    "# 🕵️ Data Detective — итог\n\n"
                    "{dt_intake_output}\n\n"
                    "## Синтез\n{dt_synth_output}\n"
                ),
                "on_failure": "continue",
            },
        },
    ]


def build_detective_edges() -> list[dict]:
    return [
        {"id": "d_e1", "source": "dt_manual", "target": "dt_merge_in", "sourceHandle": "out", "animated": True},
        {"id": "d_e2", "source": "dt_webhook", "target": "dt_merge_in", "sourceHandle": "out", "animated": True},
        {"id": "d_e3", "source": "dt_merge_in", "target": "dt_intake", "sourceHandle": "out", "animated": True},
        {"id": "d_e4", "source": "dt_intake", "target": "dt_parallel", "sourceHandle": "success", "animated": True},
        {"id": "d_e5", "source": "dt_parallel", "target": "expert_risk", "sourceHandle": "out", "animated": True},
        {"id": "d_e6", "source": "dt_parallel", "target": "expert_opt", "sourceHandle": "out", "animated": True},
        {"id": "d_e7", "source": "dt_parallel", "target": "expert_ux", "sourceHandle": "out", "animated": True},
        {"id": "d_e8", "source": "expert_risk", "target": "dt_merge_out", "sourceHandle": "success", "animated": True},
        {"id": "d_e9", "source": "expert_opt", "target": "dt_merge_out", "sourceHandle": "success", "animated": True},
        {"id": "d_e10", "source": "expert_ux", "target": "dt_merge_out", "sourceHandle": "success", "animated": True},
        {"id": "d_e11", "source": "dt_merge_out", "target": "dt_synth", "sourceHandle": "out", "animated": True},
        {"id": "d_e12", "source": "dt_synth", "target": "confidence_gate", "sourceHandle": "success", "animated": True},
        {"id": "d_e13", "source": "confidence_gate", "target": "green_light_report", "sourceHandle": "true", "animated": True, "label": "HIGH"},
        {"id": "d_e14", "source": "confidence_gate", "target": "needs_more_report", "sourceHandle": "false", "animated": True, "label": "other"},
        {"id": "d_e15", "source": "green_light_report", "target": "dt_final_merge", "sourceHandle": "success", "animated": True},
        {"id": "d_e16", "source": "needs_more_report", "target": "dt_final_merge", "sourceHandle": "success", "animated": True},
        {"id": "d_e17", "source": "dt_final_merge", "target": "dt_final", "sourceHandle": "out", "animated": True},
    ]


# ---------------------------------------------------------------------------
# Ensure helpers
# ---------------------------------------------------------------------------


def _ensure_pipeline(
    user,
    *,
    name: str,
    description: str,
    icon: str,
    extra_tags: list[str],
    nodes: list[dict],
    edges: list[dict],
) -> Pipeline:
    pipeline, _ = Pipeline.objects.update_or_create(
        owner=user,
        name=name,
        defaults={
            "description": description,
            "icon": icon,
            "tags": list({*DEMO_SHOWCASE_TAGS, *extra_tags}),
            "nodes": nodes,
            "edges": edges,
            "graph_version": CURRENT_PIPELINE_GRAPH_VERSION,
            "is_shared": False,
        },
    )
    pipeline.sync_triggers_from_nodes()
    return pipeline


def ensure_incident_pipeline(user) -> Pipeline:
    return _ensure_pipeline(
        user,
        name=INCIDENT_PIPELINE_NAME,
        description=INCIDENT_PIPELINE_DESCRIPTION,
        icon="🚨",
        extra_tags=["incident", "triage", "ai"],
        nodes=build_incident_nodes(),
        edges=build_incident_edges(),
    )


def ensure_content_pipeline(user) -> Pipeline:
    return _ensure_pipeline(
        user,
        name=CONTENT_PIPELINE_NAME,
        description=CONTENT_PIPELINE_DESCRIPTION,
        icon="✍️",
        extra_tags=["content", "marketing", "ai"],
        nodes=build_content_nodes(),
        edges=build_content_edges(),
    )


def ensure_detective_pipeline(user) -> Pipeline:
    return _ensure_pipeline(
        user,
        name=DETECTIVE_PIPELINE_NAME,
        description=DETECTIVE_PIPELINE_DESCRIPTION,
        icon="🕵️",
        extra_tags=["analysis", "product", "ai"],
        nodes=build_detective_nodes(),
        edges=build_detective_edges(),
    )


def ensure_all_demo_showcase_pipelines(user) -> list[Pipeline]:
    return [
        ensure_incident_pipeline(user),
        ensure_content_pipeline(user),
        ensure_detective_pipeline(user),
    ]
