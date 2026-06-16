from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import transaction

from mars.git_config import ensure_git_config, run_git
from mars.models import MarsRun, MarsRunEvent, MarsSession, MarsWorkspace, default_deny_globs
from mars.orchestrator import merge_runtime_orchestration
from mars.policy import MarsPolicyError, build_workspace_policy, git_status
from mars.skill_catalog import recommend_task_skills
from mars.subprocess_compat import run_process_capture

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


def _command_prefix(value: Any, default: str) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item)]
    raw = str(value or default).strip()
    return [raw] if raw else [default]


def _command_uses_wsl_windows_exe(command: list[str]) -> bool:
    if os.name != "posix" or not command:
        return False
    executable = command[0].replace("\\", "/").lower()
    return executable.startswith("/mnt/") and executable.endswith(".exe")


def _wsl_path_to_windows(path: Path) -> str:
    raw = str(path.resolve(strict=False)).replace("\\", "/")
    if not raw.startswith("/mnt/") or len(raw) < 7:
        return str(path)
    drive = raw[5].upper()
    rest = raw[7:].replace("/", "\\")
    return f"{drive}:\\{rest}"


def cli_path_for_command(command: list[str], path: str | Path) -> str:
    resolved = Path(path).expanduser().resolve(strict=False)
    return _wsl_path_to_windows(resolved) if _command_uses_wsl_windows_exe(command) else str(resolved)


def _command_is_codex(command: list[str]) -> bool:
    if not command:
        return False
    executable = command[0].replace("\\", "/").lower()
    return executable.endswith("/codex") or executable.endswith("/codex.exe") or executable == "codex"


def _codex_home_candidates() -> list[Path]:
    candidates: list[Path] = []
    raw_env_home = os.environ.get("CODEX_HOME")
    if raw_env_home:
        candidates.append(Path(raw_env_home).expanduser())
    candidates.append(Path.home() / ".codex")
    wsl_users_root = Path("/mnt/c/Users")
    if wsl_users_root.exists():
        for user_dir in wsl_users_root.iterdir():
            candidates.append(user_dir / ".codex")
    return candidates


def ensure_mars_codex_home(command: list[str]) -> Path | None:
    if not _command_is_codex(command):
        return None
    configured = Path(getattr(settings, "MARS_CODEX_HOME", Path(settings.MEDIA_ROOT) / "mars_codex_home")).expanduser()
    if _command_uses_wsl_windows_exe(command) and str(configured) == str(Path.home() / ".mars_codex_home"):
        for candidate_home in _codex_home_candidates():
            try:
                if str(candidate_home).replace("\\", "/").startswith("/mnt/c/Users/") and (candidate_home / "auth.json").exists():
                    configured = candidate_home.parent / ".mars_codex_home"
                    break
            except OSError:
                continue
    if not configured.is_absolute():
        configured = Path(settings.BASE_DIR) / configured
    home = configured.resolve(strict=False)
    home.mkdir(parents=True, exist_ok=True)

    config_path = home / "config.toml"
    if not config_path.exists():
        config_path.write_text(
            "# Isolated Codex home for MARS. Keep plugins and MCP servers out of this runtime.\n",
            encoding="utf-8",
        )

    auth_target = home / "auth.json"
    if not auth_target.exists():
        for candidate_home in _codex_home_candidates():
            auth_source = candidate_home / "auth.json"
            try:
                if auth_source.exists():
                    shutil.copy2(auth_source, auth_target)
                    break
            except OSError:
                continue
    return home


def subprocess_env_for_cli(command: list[str]) -> dict[str, str]:
    env = os.environ.copy()
    codex_home = ensure_mars_codex_home(command)
    if codex_home is not None:
        if _command_uses_wsl_windows_exe(command):
            env["CODEX_HOME"] = str(codex_home)
            existing_wslenv = env.get("WSLENV", "")
            entries = [item for item in existing_wslenv.split(":") if item]
            if "CODEX_HOME/p" not in entries:
                entries.append("CODEX_HOME/p")
            env["WSLENV"] = ":".join(entries)
        else:
            env["CODEX_HOME"] = str(codex_home)
    return env


def mars_agent_uses_docker() -> bool:
    runtime = str(getattr(settings, "MARS_AGENT_RUNTIME", "host") or "host").strip().lower()
    return runtime in {"docker", "container", "containers"}


def docker_workspace_path() -> str:
    workdir = str(getattr(settings, "MARS_AGENT_DOCKER_WORKDIR", "/workspace") or "/workspace").strip()
    return workdir if workdir.startswith("/") else "/workspace"


def _docker_host_path(path: str | Path) -> str:
    resolved = Path(path).expanduser().resolve(strict=False)
    container_prefix = str(getattr(settings, "MARS_DOCKER_CONTAINER_PATH_PREFIX", "") or "").replace("\\", "/").rstrip("/")
    host_prefix = str(getattr(settings, "MARS_DOCKER_HOST_PATH_PREFIX", "") or "").strip()
    normalized = str(resolved).replace("\\", "/")
    if container_prefix and host_prefix and (normalized == container_prefix or normalized.startswith(f"{container_prefix}/")):
        suffix = normalized[len(container_prefix) :].lstrip("/")
        clean_host_prefix = host_prefix.rstrip("\\/")
        if ":" in clean_host_prefix[:4] or "\\" in clean_host_prefix:
            return clean_host_prefix + (("\\" + suffix.replace("/", "\\")) if suffix else "")
        host_base = Path(clean_host_prefix).expanduser()
        return str((host_base / PurePosixPath(suffix)).resolve(strict=False)) if suffix else str(host_base.resolve(strict=False))
    return str(resolved)


def _docker_volume_arg(source: str | Path, target: str, mode: str) -> str:
    safe_mode = "ro" if mode == "ro" else "rw"
    return f"{_docker_host_path(source)}:{target}:{safe_mode}"


def _docker_named_volume_mount(volume_name: str, target: str, readonly: bool = False) -> str:
    clean_name = volume_name.strip()
    if not clean_name or any(char in clean_name for char in " ,"):
        raise MarsPolicyError("Invalid Docker volume name for MARS agent runtime.")
    parts = ["type=volume", f"src={clean_name}", f"dst={target}"]
    if readonly:
        parts.append("readonly")
    return ",".join(parts)


def docker_container_child_path(container_root: str, host_root: str | Path, host_child: str | Path) -> str:
    root = Path(host_root).expanduser().resolve(strict=False)
    child = Path(host_child).expanduser().resolve(strict=False)
    rel = child.relative_to(root)
    return str(PurePosixPath(container_root) / PurePosixPath(rel.as_posix()))


def _docker_env_passthrough() -> list[str]:
    names = [
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_CLOUD_PROJECT",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
    ]
    args: list[str] = []
    for name in names:
        if os.environ.get(name):
            args.extend(["-e", name])
    return args


def build_mars_agent_docker_command(
    *,
    phase: str,
    workspace_root: str | Path,
    workspace_mode: str,
    inner_command: list[str],
    extra_mounts: list[tuple[str | Path, str, str]] | None = None,
    include_codex_home: bool = False,
    include_gemini_home: bool = False,
) -> list[str]:
    workspace = Path(workspace_root).expanduser().resolve(strict=False)
    docker_command = str(getattr(settings, "MARS_AGENT_DOCKER_COMMAND", "docker") or "docker")
    image = str(getattr(settings, "MARS_AGENT_DOCKER_IMAGE", "webterm-mars-agent:latest") or "").strip()
    if not image:
        raise MarsPolicyError("MARS_AGENT_DOCKER_IMAGE is not configured.")

    command = [
        docker_command,
        "run",
        "--rm",
        "--interactive",
        "--workdir",
        docker_workspace_path(),
        "--network",
        str(getattr(settings, "MARS_AGENT_DOCKER_NETWORK", "bridge") or "bridge"),
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=512m",
        "--label",
        f"webtrerm.mars.phase={phase}",
        "-v",
        _docker_volume_arg(workspace, docker_workspace_path(), workspace_mode),
    ]

    cpus = str(getattr(settings, "MARS_AGENT_DOCKER_CPUS", "") or "").strip()
    memory = str(getattr(settings, "MARS_AGENT_DOCKER_MEMORY", "") or "").strip()
    pids_limit = int(getattr(settings, "MARS_AGENT_DOCKER_PIDS_LIMIT", 0) or 0)
    if cpus:
        command.extend(["--cpus", cpus])
    if memory:
        command.extend(["--memory", memory])
    if pids_limit > 0:
        command.extend(["--pids-limit", str(pids_limit)])

    for source, target, mode in extra_mounts or []:
        command.extend(["-v", _docker_volume_arg(source, target, mode)])

    if include_codex_home:
        command.extend(["-e", "CODEX_HOME=/codex-home"])
        codex_home_volume = str(getattr(settings, "MARS_AGENT_DOCKER_CODEX_HOME_VOLUME", "") or "").strip()
        if codex_home_volume:
            command.extend(["--mount", _docker_named_volume_mount(codex_home_volume, "/codex-home")])
            ensure_mars_codex_home(["codex"])
        else:
            codex_home = ensure_mars_codex_home(["codex"])
            if codex_home is not None:
                command.extend(["-v", _docker_volume_arg(codex_home, "/codex-home", "rw")])

    if include_gemini_home:
        gemini_home_volume = str(getattr(settings, "MARS_AGENT_DOCKER_GEMINI_HOME_VOLUME", "") or "").strip()
        gemini_home = Path(getattr(settings, "MARS_GEMINI_HOME", Path.home() / ".gemini")).expanduser().resolve(strict=False)
        if gemini_home_volume:
            command.extend(["--mount", _docker_named_volume_mount(gemini_home_volume, "/home/node/.gemini", readonly=True)])
        elif gemini_home.exists():
            command.extend(["-v", _docker_volume_arg(gemini_home, "/home/node/.gemini", "ro")])

    command.extend(_docker_env_passthrough())
    command.append(image)
    command.extend(inner_command)
    return command


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


def _build_codex_interview_prompt(task_brief: str, workspace_root: Path, selected_skills: list[str] | None = None) -> str:
    safe_task = re.sub(r"\s+", " ", (task_brief or "").strip())[:2500]
    skills = ", ".join(selected_skills or CURATED_SKILLS)
    return "\n\n".join(
        [
            MARS_INTERVIEW_SYSTEM_PROMPT,
            "You are the real Codex CLI interview step for MARS.",
            "Generate the questions yourself for this exact task; do not reuse generic templates.",
            "Do not modify files. Do not run destructive commands. Read-only workspace inspection is allowed only if useful.",
            f"Workspace root: {workspace_root}",
            f"Available instruction-pack skills: {skills}",
            "User task:",
            safe_task,
            "Return JSON only. The final response must validate against the provided output schema.",
        ]
    )


def _extract_codex_final_text(stdout_text: str, output_text: str) -> str:
    if output_text.strip():
        return output_text
    candidates: list[str] = []
    for line in stdout_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            candidates.append(line)
            continue
        if isinstance(event, dict):
            for key in ("message", "content", "text", "final_output", "last_message"):
                value = event.get(key)
                if isinstance(value, str) and value.strip():
                    candidates.append(value)
            if isinstance(event.get("payload"), dict):
                payload = event["payload"]
                for key in ("message", "content", "text"):
                    value = payload.get(key)
                    if isinstance(value, str) and value.strip():
                        candidates.append(value)
    return "\n".join(candidates[-3:])


async def _run_codex_interview_process(
    *,
    task_brief: str,
    workspace_root: Path,
    selected_skills: list[str] | None = None,
) -> list[dict[str, Any]]:
    interview_dir = Path(settings.MEDIA_ROOT) / "mars_interviews"
    interview_dir.mkdir(parents=True, exist_ok=True)
    timeout_seconds = int(getattr(settings, "MARS_INTERVIEW_CODEX_TIMEOUT_SECONDS", 180))
    command = _command_prefix(
        getattr(settings, "MARS_AGENT_DOCKER_CODEX_COMMAND", "codex")
        if mars_agent_uses_docker()
        else getattr(settings, "MARS_INTERVIEW_CODEX_COMMAND", None) or getattr(settings, "MARS_CODEX_COMMAND", None),
        "codex",
    )

    with tempfile.TemporaryDirectory(prefix="interview_", dir=interview_dir) as tmp_name:
        tmp_dir = Path(tmp_name)
        schema_path = tmp_dir / "interview-schema.json"
        output_path = tmp_dir / "codex-interview.json"
        schema_path.write_text(json.dumps(MARS_INTERVIEW_OUTPUT_SCHEMA, ensure_ascii=False), encoding="utf-8")

        workspace_cli_path = docker_workspace_path() if mars_agent_uses_docker() else cli_path_for_command(command, workspace_root)
        schema_cli_path = (
            docker_container_child_path("/mars-interview", tmp_dir, schema_path)
            if mars_agent_uses_docker()
            else cli_path_for_command(command, schema_path)
        )
        output_cli_path = (
            docker_container_child_path("/mars-interview", tmp_dir, output_path)
            if mars_agent_uses_docker()
            else cli_path_for_command(command, output_path)
        )
        codex_inner_cmd = command + [
            "--ask-for-approval",
            "never",
            "exec",
            "--ignore-user-config",
            "--ignore-rules",
            "--json",
            "--cd",
            workspace_cli_path,
            "--sandbox",
            "read-only",
            "--output-schema",
            schema_cli_path,
            "--output-last-message",
            output_cli_path,
            "-",
        ]
        codex_cmd = (
            build_mars_agent_docker_command(
                phase="interview",
                workspace_root=workspace_root,
                workspace_mode="ro",
                inner_command=codex_inner_cmd,
                extra_mounts=[(tmp_dir, "/mars-interview", "rw")],
                include_codex_home=True,
            )
            if mars_agent_uses_docker()
            else codex_inner_cmd
        )
        prompt = _build_codex_interview_prompt(task_brief, workspace_root, selected_skills)

        try:
            returncode, stdout_text, stderr_text = await run_process_capture(
                codex_cmd,
                cwd=str(workspace_root),
                env=None if mars_agent_uses_docker() else subprocess_env_for_cli(command),
                stdin_text=prompt,
                timeout_seconds=timeout_seconds,
            )
        except OSError as exc:
            raise MarsInterviewError(f"Codex CLI is not available for MARS interview: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise MarsInterviewError("Codex CLI interview timed out.") from exc

        if returncode != 0:
            combined_output = "\n".join(
                part for part in [stderr_text.strip(), stdout_text.strip()] if part
            ) or "No Codex output."
            details = combined_output.strip().splitlines()
            raise MarsInterviewError(f"Codex CLI interview failed: {' '.join(details[-3:])[:600]}")

        output_text = output_path.read_text(encoding="utf-8", errors="replace") if output_path.exists() else ""
        raw_text = _extract_codex_final_text(stdout_text, output_text)
        questions = _normalize_interview_questions(_extract_json_object(raw_text), task_brief, min_count=5)
        if len(questions) < 5:
            raise MarsInterviewError("Codex CLI did not return valid interview JSON.")
        return questions


def _build_codex_interview_questions(
    task_brief: str,
    *,
    workspace_root: str | Path,
    selected_skills: list[str] | None = None,
) -> list[dict[str, Any]]:
    root = Path(workspace_root).expanduser().resolve(strict=False)
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            _run_codex_interview_process(
                task_brief=task_brief,
                workspace_root=root,
                selected_skills=selected_skills,
            )
        )
    finally:
        loop.close()


def mars_user_workspaces_base() -> Path:
    configured = Path(getattr(settings, "MARS_USER_WORKSPACES_ROOT", "agent_projects/mars_workspaces")).expanduser()
    if not configured.is_absolute():
        configured = Path(settings.BASE_DIR) / configured
    return configured.resolve(strict=False)


def personal_workspace_root(user) -> Path:
    if not getattr(user, "id", None):
        raise MarsPolicyError("Authenticated user is required for a personal workspace.")
    return (mars_user_workspaces_base() / f"user_{user.id}").resolve(strict=False)


def ensure_personal_workspace_directory(user) -> Path:
    root = personal_workspace_root(user)
    base = mars_user_workspaces_base()
    try:
        root.relative_to(base)
    except ValueError as exc:
        raise MarsPolicyError("Personal workspace root escaped the configured base directory.") from exc

    root.mkdir(parents=True, exist_ok=True)
    if not (root / ".git").exists():
        init = subprocess.run(["git", "init", str(root)], capture_output=True, text=True, timeout=20, check=False)
        if init.returncode != 0:
            raise MarsPolicyError((init.stderr or init.stdout or "Unable to initialize personal workspace.").strip())

    ensure_git_config(root, "user.email", f"mars-user-{user.id}@local.invalid")
    ensure_git_config(root, "user.name", f"MARS User {user.id}")

    has_head = run_git(root, "rev-parse", "--verify", "HEAD", check=False).returncode == 0
    if not has_head:
        readme = root / "README.md"
        if not readme.exists():
            readme.write_text(
                "# MARS personal workspace\n\nFiles created by MARS for this user stay in this repository.\n",
                encoding="utf-8",
            )
        run_git(root, "add", "README.md")
        commit = run_git(root, "commit", "-m", "Initialize MARS personal workspace", check=False)
        if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr).lower():
            raise MarsPolicyError((commit.stderr or commit.stdout or "Unable to initialize personal workspace.").strip())
    return root


def existing_personal_workspace(user) -> MarsWorkspace | None:
    for workspace in MarsWorkspace.objects.filter(user=user, name=PERSONAL_WORKSPACE_NAME):
        if workspace_is_personal(user, workspace):
            return workspace
    return None


def ensure_personal_workspace(user) -> MarsWorkspace:
    root = ensure_personal_workspace_directory(user)
    data = {
        "root_path": str(root),
        "read_allow_roots": [str(root)],
        "write_allow_roots": [str(root)],
        "deny_globs": default_deny_globs(),
        "enabled": True,
    }
    workspace, _ = MarsWorkspace.objects.get_or_create(
        user=user,
        name=PERSONAL_WORKSPACE_NAME,
        defaults=data,
    )
    changed_fields: list[str] = []
    for field, value in data.items():
        if getattr(workspace, field) != value:
            setattr(workspace, field, value)
            changed_fields.append(field)
    if changed_fields:
        workspace.save(update_fields=changed_fields + ["updated_at"])
    return workspace


def workspace_is_personal(user, workspace: MarsWorkspace) -> bool:
    expected_root = personal_workspace_root(user)
    try:
        actual_root = Path(workspace.root_path).expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        return False
    return workspace.user_id == user.id and actual_root == expected_root and workspace.name == PERSONAL_WORKSPACE_NAME


def require_personal_workspace(user, workspace: MarsWorkspace) -> None:
    if not workspace_is_personal(user, workspace):
        raise MarsPolicyError("MARS can only run inside the user's personal workspace.")


def serialize_workspace(workspace: MarsWorkspace) -> dict[str, Any]:
    return {
        "id": workspace.id,
        "name": workspace.name,
        "root_path": workspace.root_path,
        "read_allow_roots": workspace.read_allow_roots or [],
        "write_allow_roots": workspace.write_allow_roots or [],
        "deny_globs": workspace.deny_globs or [],
        "enabled": workspace.enabled,
        "created_at": workspace.created_at.isoformat() if workspace.created_at else None,
        "updated_at": workspace.updated_at.isoformat() if workspace.updated_at else None,
    }


def serialize_session(session: MarsSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "workspace_id": session.workspace_id,
        "workspace": serialize_workspace(session.workspace),
        "task_brief": session.task_brief,
        "answers": session.answers or {},
        "interview_questions": session.interview_questions or [],
        "selected_skill_slugs": [],
        "generated_plan": session.generated_plan,
        "status": session.status,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


def _public_runtime_control(runtime_control: dict[str, Any] | None) -> dict[str, Any]:
    control = dict(runtime_control or {})
    control.pop("orchestration", None)
    control.pop("skill_routing", None)
    control.pop("skill_catalog", None)
    return control


def serialize_run(run: MarsRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "session_id": run.session_id,
        "workspace_id": run.workspace_id,
        "workspace": serialize_workspace(run.workspace),
        "cli_roles": {},
        "status": run.status,
        "runtime_control": _public_runtime_control(run.runtime_control),
        "allow_dirty": run.allow_dirty,
        "final_report": run.final_report,
        "codex_summary": run.codex_summary,
        "gemini_review": run.gemini_review,
        "test_output": run.test_output,
        "git_before": run.git_before,
        "git_after": run.git_after,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def serialize_event(event: MarsRunEvent) -> dict[str, Any]:
    payload = dict(event.payload or {})
    payload.pop("command", None)
    return {
        "id": event.id,
        "run_id": event.run_id,
        "event_type": event.event_type,
        "message": event.message,
        "payload": payload,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def normalize_workspace_payload(payload: dict[str, Any]) -> dict[str, Any]:
    root_path = str(payload.get("root_path") or "").strip()
    root = build_workspace_policy(
        root_path=root_path,
        read_allow_roots=list(payload.get("read_allow_roots") or [root_path]),
        write_allow_roots=list(payload.get("write_allow_roots") or [root_path]),
        deny_globs=list(payload.get("deny_globs") or default_deny_globs()),
    ).root
    name = str(payload.get("name") or Path(root).name or "Workspace").strip()[:160]
    deny_globs = list(payload.get("deny_globs") or default_deny_globs())
    return {
        "name": name,
        "root_path": str(root),
        "read_allow_roots": [str(item) for item in payload.get("read_allow_roots") or [str(root)]],
        "write_allow_roots": [str(item) for item in payload.get("write_allow_roots") or [str(root)]],
        "deny_globs": deny_globs,
        "enabled": bool(payload.get("enabled", True)),
    }


def recommend_skills(task_brief: str) -> list[str]:
    return recommend_task_skills(task_brief)


def build_interview_questions(
    task_brief: str,
    *,
    workspace_root: str | Path,
    selected_skills: list[str] | None = None,
) -> list[dict[str, Any]]:
    return _build_codex_interview_questions(
        task_brief,
        workspace_root=workspace_root,
        selected_skills=selected_skills,
    )


def generate_plan(session: MarsSession) -> str:
    answers = session.answers or {}
    skills = session.selected_skill_slugs or recommend_skills(session.task_brief)
    goal = str(answers.get("success_criteria") or session.task_brief or "Not specified yet.").strip()
    question_lines = []
    for question in session.interview_questions or []:
        question_id = str(question.get("id") or "")
        answer = str(answers.get(question_id) or "").strip()
        if answer:
            question_lines.append(f"- {question.get('question')}: {answer}")
    return "\n".join(
        [
            "# MARS execution plan",
            "",
            "## Goal",
            goal,
            "",
            "## Execution checklist",
            "1. Lock the personal workspace policy and inspect only files inside that root.",
            "2. Use selected skill instructions: " + ", ".join(skills) + ".",
            "3. Build the smallest complete version that satisfies the approved goal.",
            "4. Run the requested verification checks or explain why a check is not available.",
            "5. Ask Gemini CLI for a read-only review of the produced diff.",
            "6. Return a final report with changed files, verification output, and remaining risk.",
            "",
            "## Task brief",
            session.task_brief,
            "",
            "## Interview answers",
            "\n".join(question_lines) or "No interview answers yet.",
        ]
    )


def record_event(run: MarsRun, event_type: str, message: str = "", payload: dict[str, Any] | None = None) -> MarsRunEvent:
    event = MarsRunEvent.objects.create(
        run=run,
        event_type=event_type,
        message=message,
        payload=payload or {},
    )
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"mars_run_{run.id}",
            {"type": "mars.event", "event": serialize_event(event)},
        )
    return event


def claim_next_run() -> MarsRun | None:
    with transaction.atomic():
        run = (
            MarsRun.objects.select_for_update(skip_locked=True)
            .filter(status=MarsRun.STATUS_QUEUED)
            .select_related("session", "workspace", "user")
            .order_by("created_at", "id")
            .first()
        )
        if run is None:
            return None
        run.status = MarsRun.STATUS_RUNNING
        run.save(update_fields=["status"])
        return run


def create_run_for_session(session: MarsSession, *, allow_dirty: bool, test_command: str = "") -> MarsRun:
    require_personal_workspace(session.user, session.workspace)
    dirty_status = git_status(session.workspace.root_path)
    if dirty_status and not allow_dirty:
        raise MarsPolicyError("Workspace has uncommitted changes. Confirm dirty worktree before running MARS.")
    runtime_control = merge_runtime_orchestration(
        {"stop_requested": False, "test_command": test_command[:500]},
        selected_skills=session.selected_skill_slugs,
    )
    run = MarsRun.objects.create(
        session=session,
        workspace=session.workspace,
        user=session.user,
        allow_dirty=allow_dirty,
        runtime_control=runtime_control,
        git_before=dirty_status,
    )
    session.status = MarsSession.STATUS_RUNNING
    session.save(update_fields=["status", "updated_at"])
    record_event(run, "mars_run_queued", "MARS run queued", {"allow_dirty": allow_dirty})
    return run
