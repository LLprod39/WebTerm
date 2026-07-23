from __future__ import annotations

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
                "template": ("# 🕵️ Data Detective — итог\n\n{dt_intake_output}\n\n## Синтез\n{dt_synth_output}\n"),
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
        {
            "id": "d_e13",
            "source": "confidence_gate",
            "target": "green_light_report",
            "sourceHandle": "true",
            "animated": True,
            "label": "HIGH",
        },
        {
            "id": "d_e14",
            "source": "confidence_gate",
            "target": "needs_more_report",
            "sourceHandle": "false",
            "animated": True,
            "label": "other",
        },
        {
            "id": "d_e15",
            "source": "green_light_report",
            "target": "dt_final_merge",
            "sourceHandle": "success",
            "animated": True,
        },
        {
            "id": "d_e16",
            "source": "needs_more_report",
            "target": "dt_final_merge",
            "sourceHandle": "success",
            "animated": True,
        },
        {"id": "d_e17", "source": "dt_final_merge", "target": "dt_final", "sourceHandle": "out", "animated": True},
    ]
