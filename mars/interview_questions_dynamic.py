from __future__ import annotations

import re
from typing import Any

QUESTION_KIND_CHOICES = {"textarea", "choice_text", "multi_choice_text"}


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
    if _contains_any(
        text, ("api", "backend", "django", "fastapi", "endpoint", "бэк", "сервер", "database", "db", "postgres")
    ):
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
        success_options = [
            "Ошибка не повторяется",
            "Есть понятный фикс",
            "Добавлен регрессионный тест",
            "Показана причина",
        ]
        scope_options = [
            "Найти причину",
            "Исправить минимально",
            "Добавить тест",
            "Проверить UI",
            "Обновить текст ошибки",
        ]
    elif "game" in domains:
        success_options = ["Играбельный прототип", "Полноценный MVP", "Красивый playable demo", "Только core gameplay"]
        scope_options = ["Игровой цикл", "Счет и рекорд", "Пауза/рестарт", "Звуки/эффекты", "Меню", "Адаптив"]
    elif "dashboard" in domains:
        success_options = ["Рабочий dashboard", "Понятные графики", "Фильтры и таблица", "Готовый отчетный экран"]
        scope_options = ["KPI cards", "Графики", "Фильтры", "Таблица", "Экспорт", "Empty/loading states"]
    elif "backend" in domains:
        success_options = [
            "API работает",
            "Контракт покрыт тестами",
            "Безопасная интеграция",
            "Документированное поведение",
        ]
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
                [
                    "Только проблемный компонент",
                    "API contract",
                    "Тесты",
                    "Стили",
                    "State management",
                    "Минимальный diff",
                ],
            ),
            _question(
                "bug_regression",
                "Какой регрессии нельзя допустить?",
                "multi_choice_text",
                [
                    "Не ломать существующий flow",
                    "Не менять публичный API",
                    "Не менять auth",
                    "Не трогать данные",
                    "Не добавлять зависимости",
                ],
            ),
        ]

    if "backend" in domains:
        return [
            _question(
                "api_contract",
                f"Какой контракт нужен для «{subject}»?",
                "multi_choice_text",
                [
                    "GET endpoint",
                    "POST/PATCH action",
                    "Validation errors",
                    "Permissions",
                    "Audit event",
                    "Pagination/filtering",
                ],
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
                [
                    "Ownership check",
                    "Feature gate",
                    "No secrets in response",
                    "Idempotent action",
                    "Transaction safety",
                ],
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
    verification_options = [
        "npm run build",
        "npm run test",
        "Playwright smoke",
        "Скриншот в браузере",
        "Ручная проверка",
    ]
    if "backend" in domains:
        verification_options = ["pytest", "API smoke", "Permission test", "Django check", "No migration drift"]
    elif "game" in domains:
        verification_options = [
            "npm run build",
            "Playwright smoke",
            "Проверить управление",
            "Проверить проигрыш/рестарт",
            "Скриншот",
        ]
    elif "bugfix" in domains:
        verification_options = ["Регрессионный тест", "Повторить repro", "npm run test", "pytest", "Скриншот до/после"]

    return [
        _question(
            "constraints",
            f"Что MARS не должен менять при работе над «{subject}»?",
            "multi_choice_text",
            [
                "Не трогать auth/settings",
                "Без новых зависимостей",
                "Без backend",
                "Не менять API",
                "Можно добавить библиотеки",
            ],
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
