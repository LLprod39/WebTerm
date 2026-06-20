from __future__ import annotations

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
