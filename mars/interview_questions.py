from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from django.conf import settings

from mars.policy import MarsPolicyError

CURATED_SKILLS = ["frontend-design", "frontend-dev", "react-best-practices", "frontend-testing-debugging"]
PERSONAL_WORKSPACE_NAME = "Personal workspace"

QUESTION_KIND_CHOICES = {"textarea", "choice_text", "multi_choice_text"}
QUESTION_BANK: list[dict[str, Any]] = []
MARS_INTERVIEW_SYSTEM_PROMPT = """You generate a coding-agent clarification interview.
Return only JSON with this shape:
{"questions":[{"id":"short_snake_case","question":"Russian question","kind":"choice_text|multi_choice_text|textarea","options":["2-6 concise Russian options"],"placeholder":"optional Russian placeholder","required":true}]}
Rules:
- Generate 8-10 questions specific to the user's exact software task.
- Do not use generic canned wording if the task gives a concrete domain.
- Each question must help produce an implementation goal, scope, UX, constraints, verification, and risk.
- Options must be task-specific and selectable by a human.
- Keep questions and options short enough for a compact UI.
- No filesystem permissions, secrets, or destructive actions.
"""

MARS_INTERVIEW_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["questions"],
    "properties": {
        "questions": {
            "type": "array",
            "minItems": 5,
            "maxItems": 10,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "question", "kind", "options", "placeholder", "required"],
                "properties": {
                    "id": {"type": "string", "minLength": 2, "maxLength": 56},
                    "question": {"type": "string", "minLength": 8, "maxLength": 180},
                    "kind": {"type": "string", "enum": ["choice_text", "multi_choice_text", "textarea"]},
                    "options": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 6,
                        "items": {"type": "string", "minLength": 1, "maxLength": 80},
                    },
                    "placeholder": {"type": "string", "maxLength": 180},
                    "required": {"type": "boolean"},
                },
            },
        },
    },
}


class MarsInterviewError(MarsPolicyError):
    """Raised when Codex CLI cannot produce a valid MARS interview."""


def _question(
    question_id: str,
    question: str,
    kind: str,
    options: list[str] | tuple[str, ...],
    *,
    required: bool = True,
    placeholder: str = "",
) -> dict[str, Any]:
    return {
        "id": question_id,
        "question": question,
        "kind": kind if kind in QUESTION_KIND_CHOICES else "choice_text",
        "options": list(options)[:6],
        "placeholder": placeholder,
        "required": required,
    }


def _task_subject(task_brief: str) -> str:
    subject = re.sub(r"\s+", " ", (task_brief or "").strip())
    subject = subject.strip(" .,:;!?")
    if not subject:
        return "задача"
    return subject[:90]


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _task_domains(task_brief: str) -> set[str]:
    text = (task_brief or "").lower()
    domains: set[str] = set()
    if _contains_any(text, ("game", "игр", "змей", "snake", "3d", "three", "arcade", "unity")):
        domains.add("game")
    if _contains_any(text, ("bug", "fix", "ошиб", "слом", "не работает", "исправ", "debug", "регресс")):
        domains.add("bugfix")
    if _contains_any(text, ("api", "backend", "django", "fastapi", "endpoint", "бэк", "сервер", "database", "db", "postgres")):
        domains.add("backend")
    if _contains_any(text, ("dashboard", "дашборд", "analytics", "chart", "график", "таблиц", "report", "отчет")):
        domains.add("dashboard")
    if _contains_any(text, ("landing", "лендинг", "site", "website", "страниц", "сайт", "hero", "portfolio")):
        domains.add("website")
    if _contains_any(text, ("mobile", "touch", "android", "ios", "телефон", "мобил", "адаптив")):
        domains.add("mobile")
    if _contains_any(text, ("auth", "login", "sso", "keycloak", "permission", "role", "доступ", "логин")):
        domains.add("auth")
    if not domains:
        domains.add("app")
    return domains


def _base_dynamic_questions(task_brief: str, domains: set[str]) -> list[dict[str, Any]]:
    subject = _task_subject(task_brief)
    if "bugfix" in domains:
        success_options = ["Ошибка не повторяется", "Есть понятный фикс", "Добавлен регрессионный тест", "Показана причина"]
        scope_options = ["Найти причину", "Исправить минимально", "Добавить тест", "Проверить UI", "Обновить текст ошибки"]
    elif "game" in domains:
        success_options = ["Играбельный прототип", "Полноценный MVP", "Красивый playable demo", "Только core gameplay"]
        scope_options = ["Игровой цикл", "Счет и рекорд", "Пауза/рестарт", "Звуки/эффекты", "Меню", "Адаптив"]
    elif "dashboard" in domains:
        success_options = ["Рабочий dashboard", "Понятные графики", "Фильтры и таблица", "Готовый отчетный экран"]
        scope_options = ["KPI cards", "Графики", "Фильтры", "Таблица", "Экспорт", "Empty/loading states"]
    elif "backend" in domains:
        success_options = ["API работает", "Контракт покрыт тестами", "Безопасная интеграция", "Документированное поведение"]
        scope_options = ["Endpoint", "Валидация", "Права доступа", "DB-модель", "Тесты", "Audit/logs"]
    elif "website" in domains:
        success_options = ["Готовая страница", "Красивый first screen", "Адаптивный сайт", "Контент можно заменить"]
        scope_options = ["Hero", "Секции", "CTA", "Форма", "Анимации", "SEO/meta"]
    else:
        success_options = ["Рабочий MVP", "Минимальный прототип", "Полированный UI", "Исправленная проблема"]
        scope_options = ["Основной flow", "UI states", "Тесты", "Документация", "Адаптив", "Интеграции"]

    platform_options = ["Web browser", "Mobile browser", "Responsive web", "Только локальный dev"]
    if "backend" in domains:
        platform_options = ["Django API", "Frontend + API", "Локальный dev", "Production-like path"]
    elif "mobile" in domains:
        platform_options = ["Mobile first", "Touch browser", "Responsive web"]

    return [
        _question(
            "success_criteria",
            f"Какой результат для «{subject}» считаем готовым?",
            "choice_text",
            success_options,
            placeholder="Опишите конкретный видимый результат, если вариантов мало.",
        ),
        _question(
            "first_scope",
            f"Что точно входит в первую версию «{subject}»?",
            "multi_choice_text",
            scope_options,
        ),
        _question(
            "primary_surface",
            "Где это должно работать в первую очередь?",
            "choice_text",
            platform_options,
        ),
    ]


def _domain_dynamic_questions(task_brief: str, domains: set[str]) -> list[dict[str, Any]]:
    subject = _task_subject(task_brief)
    if "game" in domains:
        return [
            _question(
                "game_core_loop",
                f"Какой core loop нужен для «{subject}»?",
                "multi_choice_text",
                ["Движение и сбор предметов", "Рост сложности", "Проигрыш и рестарт", "Очки", "Уровни", "Бонусы"],
            ),
            _question(
                "game_controls",
                "Как игрок должен управлять игрой?",
                "choice_text",
                ["Клавиатура", "Клавиатура + мышь", "Touch controls", "Автовыбор под устройство"],
            ),
            _question(
                "game_camera",
                "Какая камера лучше подходит этой игре?",
                "choice_text",
                ["Вид сверху под углом", "Изометрия", "Следит за персонажем", "Свободная камера"],
            ),
            _question(
                "game_visual_style",
                "Какой визуальный стиль выбрать для первой сборки?",
                "choice_text",
                ["3D low-poly", "Neon arcade", "Clean minimal", "Dark premium", "Pixel/retro"],
            ),
        ]

    if "bugfix" in domains:
        return [
            _question(
                "bug_repro",
                "Как MARS должен воспроизвести проблему?",
                "textarea",
                ["Через текущий UI", "Через API", "Через тест", "По логам"],
                required=True,
                placeholder="Шаги, входные данные, URL, ожидаемый и фактический результат.",
            ),
            _question(
                "bug_scope",
                "Что можно менять для фикса?",
                "multi_choice_text",
                ["Только проблемный компонент", "API contract", "Тесты", "Стили", "State management", "Минимальный diff"],
            ),
            _question(
                "bug_regression",
                "Какой регрессии нельзя допустить?",
                "multi_choice_text",
                ["Не ломать существующий flow", "Не менять публичный API", "Не менять auth", "Не трогать данные", "Не добавлять зависимости"],
            ),
        ]

    if "backend" in domains:
        return [
            _question(
                "api_contract",
                f"Какой контракт нужен для «{subject}»?",
                "multi_choice_text",
                ["GET endpoint", "POST/PATCH action", "Validation errors", "Permissions", "Audit event", "Pagination/filtering"],
            ),
            _question(
                "data_model",
                "Какие данные нужно хранить или читать?",
                "multi_choice_text",
                ["Новая модель", "Существующая модель", "JSON config", "Файлы workspace", "Только read-only"],
            ),
            _question(
                "backend_safety",
                "Какие backend-ограничения важны?",
                "multi_choice_text",
                ["Ownership check", "Feature gate", "No secrets in response", "Idempotent action", "Transaction safety"],
            ),
        ]

    if "dashboard" in domains:
        return [
            _question(
                "dashboard_metrics",
                "Какие показатели должны быть первыми на экране?",
                "multi_choice_text",
                ["Status counts", "Trend chart", "Recent activity", "Errors/risks", "Throughput", "Cost/usage"],
            ),
            _question(
                "dashboard_filters",
                "Какие фильтры нужны сразу?",
                "multi_choice_text",
                ["Дата", "Статус", "Пользователь", "Проект", "Источник", "Без фильтров"],
            ),
            _question(
                "dashboard_density",
                "Какой плотности должен быть интерфейс?",
                "choice_text",
                ["Компактный ops-view", "Средняя плотность", "Крупная презентационная", "Mobile friendly"],
            ),
        ]

    if "website" in domains:
        return [
            _question(
                "site_sections",
                f"Какие секции нужны для «{subject}»?",
                "multi_choice_text",
                ["Hero", "Benefits", "How it works", "Gallery", "Pricing", "Contact/CTA"],
            ),
            _question(
                "site_tone",
                "Какой тон дизайна выбрать?",
                "choice_text",
                ["Premium dark", "Clean SaaS", "Editorial", "Bright product", "Minimal"],
            ),
            _question(
                "site_content",
                "Что делать с контентом?",
                "choice_text",
                ["Сгенерировать черновик", "Оставить placeholders", "Использовать мой текст", "Минимум текста"],
            ),
        ]

    return [
        _question(
            "main_flow",
            f"Какой основной пользовательский flow нужен для «{subject}»?",
            "multi_choice_text",
            ["Создать", "Просмотреть", "Редактировать", "Запустить", "Проверить результат", "Экспортировать"],
        ),
        _question(
            "ui_states",
            "Какие состояния интерфейса нужно продумать?",
            "multi_choice_text",
            ["Loading", "Empty", "Error", "Success", "Disabled", "Mobile"],
        ),
    ]


def _closing_dynamic_questions(task_brief: str, domains: set[str]) -> list[dict[str, Any]]:
    subject = _task_subject(task_brief)
    verification_options = ["npm run build", "npm run test", "Playwright smoke", "Скриншот в браузере", "Ручная проверка"]
    if "backend" in domains:
        verification_options = ["pytest", "API smoke", "Permission test", "Django check", "No migration drift"]
    elif "game" in domains:
        verification_options = ["npm run build", "Playwright smoke", "Проверить управление", "Проверить проигрыш/рестарт", "Скриншот"]
    elif "bugfix" in domains:
        verification_options = ["Регрессионный тест", "Повторить repro", "npm run test", "pytest", "Скриншот до/после"]

    return [
        _question(
            "constraints",
            f"Что MARS не должен менять при работе над «{subject}»?",
            "multi_choice_text",
            ["Не трогать auth/settings", "Без новых зависимостей", "Без backend", "Не менять API", "Можно добавить библиотеки"],
            required=False,
            placeholder="Например: не менять авторизацию, не трогать чужие модули.",
        ),
        _question(
            "verification",
            "Как MARS должен проверить результат?",
            "multi_choice_text",
            verification_options,
        ),
        _question(
            "priority",
            "Что важнее, если придется выбирать?",
            "choice_text",
            ["Качество UI", "Скорость реализации", "Надежная архитектура", "Минимум изменений", "Максимум функционала"],
        ),
    ]


def _build_local_interview_questions(task_brief: str) -> list[dict[str, Any]]:
    domains = _task_domains(task_brief)
    questions = [
        *_base_dynamic_questions(task_brief, domains),
        *_domain_dynamic_questions(task_brief, domains),
        *_closing_dynamic_questions(task_brief, domains),
    ]
    return _normalize_interview_questions({"questions": questions}, task_brief, min_count=8) or questions


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    text = (raw_text or "").strip()
    if not text:
        return {}
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _safe_question_id(raw_value: object, used_ids: set[str], fallback_index: int) -> str:
    raw = re.sub(r"[^a-z0-9_]+", "_", str(raw_value or "").strip().lower()).strip("_")
    if not raw:
        raw = f"ai_question_{fallback_index}"
    raw = raw[:48]
    candidate = raw
    counter = 2
    while candidate in used_ids:
        candidate = f"{raw}_{counter}"[:56]
        counter += 1
    used_ids.add(candidate)
    return candidate


def _string_list(value: object, *, limit: int = 6) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = re.sub(r"\s+", " ", str(item or "").strip())
        if text and text not in result:
            result.append(text[:80])
        if len(result) >= limit:
            break
    return result


def _normalize_interview_questions(raw_value: object, task_brief: str, *, min_count: int = 5) -> list[dict[str, Any]]:
    payload = raw_value if isinstance(raw_value, dict) else {}
    raw_questions = payload.get("questions")
    if not isinstance(raw_questions, list):
        return []

    used_ids: set[str] = set()
    questions: list[dict[str, Any]] = []
    for index, item in enumerate(raw_questions[:12], start=1):
        if not isinstance(item, dict):
            continue
        question_text = re.sub(r"\s+", " ", str(item.get("question") or "").strip())
        if not question_text:
            continue
        kind = str(item.get("kind") or "choice_text").strip()
        if kind not in QUESTION_KIND_CHOICES:
            kind = "multi_choice_text" if "multi" in kind else "choice_text"
        options = _string_list(item.get("options"), limit=6)
        if kind != "textarea" and len(options) < 2:
            continue
        if kind == "textarea" and not options:
            options = ["Написать вручную"]
        question_id = _safe_question_id(item.get("id"), used_ids, index)
        questions.append(
            _question(
                question_id,
                question_text[:180],
                kind,
                options,
                required=bool(item.get("required", True)),
                placeholder=str(item.get("placeholder") or "").strip()[:180],
            )
        )

    if len(questions) < min_count:
        return []
    if not any(question["id"] == "success_criteria" for question in questions):
        questions[0]["id"] = "success_criteria"
    return questions[:10]


async def _call_interview_llm(task_brief: str) -> str:
    from app.agent_kernel.memory.redaction import sanitize_prompt_context_text
    from app.core.llm import LLMProvider

    safe_task = sanitize_prompt_context_text(task_brief).text.strip()[:2500]
    prompt = (
        "Generate a MARS coding-agent interview for this task.\n"
        f"Task: {safe_task}\n\n"
        "Return JSON only. Questions and options must be in Russian and specific to this task."
    )
    provider = LLMProvider()
    chunks: list[str] = []
    async for chunk in provider.stream_chat(
        prompt,
        model="auto",
        purpose="chat",
        system_prompt=MARS_INTERVIEW_SYSTEM_PROMPT,
        json_mode=True,
    ):
        chunks.append(chunk)
    return "".join(chunks)


def _build_llm_interview_questions(task_brief: str) -> list[dict[str, Any]]:
    if not getattr(settings, "MARS_INTERVIEW_LLM_ENABLED", False):
        return []
    loop = asyncio.new_event_loop()
    try:
        raw_response = loop.run_until_complete(_call_interview_llm(task_brief))
    except Exception:
        return []
    finally:
        loop.close()
    if raw_response.strip().lower().startswith("error:"):
        return []
    return _normalize_interview_questions(_extract_json_object(raw_response), task_brief, min_count=8)
