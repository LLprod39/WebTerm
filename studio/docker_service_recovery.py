from __future__ import annotations

import shlex

from .models import CURRENT_PIPELINE_GRAPH_VERSION, Pipeline
from .services import get_first_owned_server_id, get_owned_server_name, has_owned_server

DOCKER_RECOVERY_PIPELINE_TAGS = [
    "studio",
    "monitoring",
    "docker",
    "incident-response",
    "telegram",
    "recovery",
    "ai-first",
]

RESTRICTED_AGENT_TOOLS = ["ssh_execute", "read_console", "send_ctrl_c"]


def _quote_shell_arg(value: str) -> str:
    return shlex.quote(str(value or "").strip())


def _resolve_server_id(user, requested_server_id: int | None = None) -> int:
    if requested_server_id:
        if not has_owned_server(user, requested_server_id, server_type="ssh"):
            raise ValueError(f"SSH-сервер {requested_server_id} не найден у пользователя {user.username}.")
        return int(requested_server_id)
    server_id = get_first_owned_server_id(user, server_type="ssh", order_by="id")
    if not server_id:
        raise ValueError(f"У пользователя {user.username} нет SSH-серверов для recovery pipeline.")
    return int(server_id)


def _resolve_server_name(user, server_id: int) -> str:
    return get_owned_server_name(user, server_id)


def _build_container_snapshot_command(container_name: str) -> str:
    quoted = _quote_shell_arg(container_name)
    return (
        "echo '[incident-snapshot]'; "
        "date; "
        "hostname || uname -n; "
        f"docker ps -a --filter name={quoted} "
        "--format 'name={{.Names}} state={{.State}} status={{.Status}}'; "
        f"docker inspect -f 'status={{{{.State.Status}}}} running={{{{.State.Running}}}} "
        "exit_code={{{{.State.ExitCode}}}} "
        "health={{{{if .State.Health}}}}{{{{.State.Health.Status}}}}{{{{else}}}}n/a{{{{end}}}} "
        "started={{{{.State.StartedAt}}}} finished={{{{.State.FinishedAt}}}}' "
        f"{quoted} 2>&1 || true; "
        f"docker logs --tail 40 {quoted} 2>&1 || true"
    )


def _build_container_verify_command(container_name: str) -> str:
    quoted = _quote_shell_arg(container_name)
    return (
        f"status=\"$(docker inspect -f '{{{{{{{{.State.Status}}}}}}}}' {quoted} 2>/dev/null || echo missing)\"; "
        f"health=\"$(docker inspect -f '{{{{{{{{if .State.Health}}}}}}}}{{{{{{{{.State.Health.Status}}}}}}}}{{{{{{{{else}}}}}}}}n/a{{{{{{{{end}}}}}}}}' {quoted} 2>/dev/null || echo missing)\"; "
        "echo \"status=$status health=$health\"; "
        "[ \"$status\" = \"running\" ] || exit 1; "
        "[ \"$health\" != \"unhealthy\" ] || exit 1"
    )


def build_docker_service_recovery_nodes(
    *,
    server_id: int,
    container_name: str,
    server_name: str,
) -> list[dict]:
    snapshot_command = _build_container_snapshot_command(container_name)
    verify_command = _build_container_verify_command(container_name)
    return [
        {
            "id": "monitoring_start",
            "type": "trigger/monitoring",
            "position": {"x": 120, "y": 20},
            "data": {
                "label": "Docker Service Alert",
                "label_ru": "Мониторинг Docker-сервиса",
                "is_active": True,
                "server_ids": [server_id],
                "severities": ["critical"],
                "alert_types": ["service"],
                "container_names": [container_name],
                "match_text": "",
                "monitoring_filters": {
                    "server_ids": [server_id],
                    "severities": ["critical"],
                    "alert_types": ["service"],
                    "container_names": [container_name],
                },
            },
        },
        {
            "id": "entry_parallel",
            "type": "logic/parallel",
            "position": {"x": 120, "y": 150},
            "data": {
                "label": "Entry Fan-Out",
                "label_ru": "Разветвить стартовые шаги",
            },
        },
        {
            "id": "incident_report",
            "type": "output/report",
            "position": {"x": -180, "y": 290},
            "data": {
                "label": "Incident Report",
                "label_ru": "Первичный отчет об инциденте",
                "template": (
                    "# Инцидент по Docker-сервису\n\n"
                    "- Сервер: {server_name} ({server_host})\n"
                    "- Контейнер: {container_name}\n"
                    "- Severity: {alert_severity}\n"
                    "- Alert: {alert_title}\n"
                    "- Сообщение: {alert_message}\n\n"
                    "Пайплайн зафиксировал инцидент и запускает AI-диагностику."
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "alert_telegram",
            "type": "output/telegram",
            "position": {"x": 120, "y": 290},
            "data": {
                "label": "Telegram Alert",
                "label_ru": "Сообщить о падении в Telegram",
                "bot_token": "",
                "chat_id": "",
                "parse_mode": "",
                "message": (
                    "Обнаружено падение Docker-сервиса.\n\n"
                    "Пайплайн: {pipeline_name}\n"
                    "Запуск: {run_id}\n"
                    "Сервер: {server_name} ({server_host})\n"
                    "Контейнер: {container_name}\n"
                    "Severity: {alert_severity}\n"
                    "Alert: {alert_title}\n"
                    "Сообщение: {alert_message}\n\n"
                    "Сейчас AI соберет диагностику и подготовит план восстановления."
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "snapshot_probe",
            "type": "agent/ssh_cmd",
            "position": {"x": 420, "y": 290},
            "data": {
                "label": "Snapshot Probe",
                "label_ru": "Снять Docker-снимок",
                "server_id": server_id,
                "command": snapshot_command,
                "on_failure": "continue",
            },
        },
        {
            "id": "investigation_context_merge",
            "type": "logic/merge",
            "position": {"x": 120, "y": 430},
            "data": {
                "label": "Investigation Context",
                "label_ru": "Собрать контекст расследования",
                "mode": "all",
            },
        },
        {
            "id": "investigate_agent",
            "type": "agent/react",
            "position": {"x": 120, "y": 570},
            "data": {
                "label": "AI Investigation",
                "label_ru": "ИИ-расследование",
                "server_ids": [server_id],
                "model": "gemini-2.0-flash-exp",
                "max_iterations": 3,
                "allowed_tools": list(RESTRICTED_AGENT_TOOLS),
                "goal": (
                    "На сервере {server_name} ({server_host}) сработал критический alert по контейнеру {container_name}. "
                    "Нужно провести только диагностику и подготовить техническое заключение.\n\n"
                    "Ограничения:\n"
                    "- это строго read-only этап;\n"
                    "- нельзя выполнять restart/start/stop/rm, docker compose up/down, редактировать файлы или конфиги;\n"
                    "- разрешены только диагностические команды вокруг docker ps/inspect/logs и чтения состояния.\n\n"
                    "В конце дай структурированный вывод:\n"
                    "1. что именно сломалось;\n"
                    "2. чем это подтверждается;\n"
                    "3. вероятная причина;\n"
                    "4. что потребуется для восстановления."
                ),
                "system_prompt": (
                    "Ты инженер расследования Docker-инцидента. Работаешь только на сервере {server_name} "
                    "и только вокруг контейнера {container_name}. Этот этап строго read-only. Любое изменение состояния "
                    "контейнера запрещено. Если восстановление напрашивается, опиши его как рекомендацию, но не выполняй."
                ),
                "instructions": (
                    "Используй предыдущий снимок и alert как исходные данные. Собери только минимально необходимую "
                    "дополнительную диагностику и закончи компактным техническим заключением."
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "plan_ready_merge",
            "type": "logic/merge",
            "position": {"x": 120, "y": 710},
            "data": {
                "label": "Plan Input",
                "label_ru": "Подготовить вход для плана",
                "mode": "any",
            },
        },
        {
            "id": "plan_llm",
            "type": "agent/llm_query",
            "position": {"x": 120, "y": 850},
            "data": {
                "label": "Recovery Plan",
                "label_ru": "План восстановления",
                "provider": "gemini",
                "model": "gemini-2.0-flash-exp",
                "include_all_outputs": True,
                "prompt": (
                    "Ты SRE-лид. Подготовь краткий план восстановления только для контейнера {container_name} "
                    "на сервере {server_name}.\n\n"
                    "Ответ верни строго по шаблону, без таблиц и без длинных объяснений:\n"
                    "Диагноз: одна короткая строка.\n"
                    "План:\n"
                    "1) ...\n"
                    "2) ...\n"
                    "3) ...\n"
                    "Проверка: одна короткая строка.\n"
                    "Эскалация: когда нужен оператор.\n\n"
                    "Максимум 900 символов. Никакой воды и повторов.\n\n"
                    "Контекст:\n{all_outputs}"
                ),
                "system_prompt": "Пиши по-русски, очень коротко, технически точно, без таблиц, markdown-оформления и воды.",
                "on_failure": "continue",
            },
        },
        {
            "id": "plan_result_merge",
            "type": "logic/merge",
            "position": {"x": 120, "y": 990},
            "data": {
                "label": "Plan Result",
                "label_ru": "Собрать результат планирования",
                "mode": "any",
            },
        },
        {
            "id": "plan_report",
            "type": "output/report",
            "position": {"x": 120, "y": 1130},
            "data": {
                "label": "Plan Report",
                "label_ru": "Отчет и план восстановления",
                "template": (
                    "# Краткий план восстановления Docker-сервиса\n\n"
                    "- Сервер: {server_name} ({server_host})\n"
                    "- Контейнер: {container_name}\n"
                    "- Запуск: {run_id}\n\n"
                    "Alert: {alert_title}\n"
                    "Сообщение: {alert_message}\n\n"
                    "## Предлагаемый план\n"
                    "{plan_llm_output}\n"
                    "{plan_llm_error}\n\n"
                    "После подтверждения пайплайн запустит AI-восстановление только для контейнера {container_name}."
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "approval_gate",
            "type": "logic/human_approval",
            "position": {"x": 120, "y": 1280},
            "data": {
                "label": "Approve Recovery",
                "label_ru": "Подтвердить план восстановления",
                "timeout_minutes": 45,
                "to_email": "",
                "tg_bot_token": "",
                "tg_chat_id": "",
                "tg_parse_mode": "",
                "message": (
                    "План восстановления готов.\n\n"
                    "Сервер: {server_name} ({server_host})\n"
                    "Контейнер: {container_name}\n"
                    "Запуск: {run_id}\n\n"
                    "{plan_llm_output}\n"
                    "{plan_llm_error}\n\n"
                    "Одобрить: {approve_url}\n"
                    "Отклонить: {reject_url}"
                ),
                "telegram_message": (
                    "Требуется подтверждение плана восстановления.\n\n"
                    "Пайплайн: {pipeline_name}\n"
                    "Запуск: {run_id}\n"
                    "Сервер: {server_name} ({server_host})\n"
                    "Контейнер: {container_name}\n\n"
                    "{plan_llm_output}\n"
                    "{plan_llm_error}\n\n"
                    "Если план подходит, нажмите кнопку Одобрить. Если нет — Отклонить."
                ),
            },
        },
        {
            "id": "approval_rejected_report",
            "type": "output/report",
            "position": {"x": -260, "y": 1450},
            "data": {
                "label": "Rejected Report",
                "label_ru": "Отчет об отклонении плана",
                "template": (
                    "# План отклонен оператором\n\n"
                    "- Контейнер: {container_name}\n"
                    "- Сервер: {server_name}\n"
                    "- Запуск: {run_id}\n\n"
                    "Оператор отклонил предложенный план восстановления. Автоматический ремонт остановлен."
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "approval_rejected_telegram",
            "type": "output/telegram",
            "position": {"x": -260, "y": 1590},
            "data": {
                "label": "Rejected Telegram",
                "label_ru": "Отправить отклонение в Telegram",
                "bot_token": "",
                "chat_id": "",
                "parse_mode": "",
                "message": (
                    "План восстановления отклонен.\n\n"
                    "Контейнер: {container_name}\n"
                    "Сервер: {server_name}\n"
                    "Запуск: {run_id}\n\n"
                    "{approval_rejected_report_output}"
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "approval_timeout_report",
            "type": "output/report",
            "position": {"x": 0, "y": 1450},
            "data": {
                "label": "Approval Timeout",
                "label_ru": "Таймаут подтверждения",
                "template": (
                    "# Таймаут подтверждения\n\n"
                    "- Контейнер: {container_name}\n"
                    "- Сервер: {server_name}\n"
                    "- Запуск: {run_id}\n\n"
                    "Подтверждение плана не было получено вовремя. Автоматическое восстановление не запускалось."
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "approval_timeout_telegram",
            "type": "output/telegram",
            "position": {"x": 0, "y": 1590},
            "data": {
                "label": "Timeout Telegram",
                "label_ru": "Отправить таймаут в Telegram",
                "bot_token": "",
                "chat_id": "",
                "parse_mode": "",
                "message": (
                    "План восстановления не был подтвержден вовремя.\n\n"
                    "Контейнер: {container_name}\n"
                    "Сервер: {server_name}\n"
                    "Запуск: {run_id}\n\n"
                    "{approval_timeout_report_output}"
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "recovery_started_telegram",
            "type": "output/telegram",
            "position": {"x": 360, "y": 1450},
            "data": {
                "label": "Recovery Started",
                "label_ru": "Сообщить о старте восстановления",
                "bot_token": "",
                "chat_id": "",
                "parse_mode": "",
                "message": (
                    "План подтвержден. Начинаю AI-восстановление.\n\n"
                    "Контейнер: {container_name}\n"
                    "Сервер: {server_name}\n"
                    "Запуск: {run_id}\n\n"
                    "Сначала попробую восстановить сервис в рамках предложенного плана. Если упрусь в проблему, спрошу "
                    "вас обычным сообщением в Telegram."
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "recovery_delivery_merge",
            "type": "logic/merge",
            "position": {"x": 360, "y": 1590},
            "data": {
                "label": "Recovery Delivery",
                "label_ru": "Подготовить старт восстановления",
                "mode": "any",
            },
        },
        {
            "id": "recovery_agent",
            "type": "agent/react",
            "position": {"x": 360, "y": 1730},
            "data": {
                "label": "AI Recovery",
                "label_ru": "ИИ-восстановление",
                "server_ids": [server_id],
                "model": "gemini-2.0-flash-exp",
                "max_iterations": 4,
                "allowed_tools": list(RESTRICTED_AGENT_TOOLS),
                "goal": (
                    "Подтвержденный план восстановления для контейнера {container_name} на сервере {server_name}. "
                    "Нужно попытаться восстановить только этот контейнер и связанные с ним docker-процессы.\n\n"
                    "План:\n{plan_llm_output}\n\n"
                    "Ограничения:\n"
                    "- не трогай другие контейнеры и сервисы;\n"
                    "- не устанавливай новые пакеты;\n"
                    "- не меняй системные настройки вне docker-окружения этого контейнера;\n"
                    "- сначала проверь текущее состояние, затем выполняй минимальные действия;\n"
                    "- если нужен шаг, который затрагивает что-то шире контейнера, остановись и опиши блокер.\n\n"
                    "В конце выдай, что сделал, что изменилось и что нужно проверить."
                ),
                "system_prompt": (
                    "Ты SRE-агент аварийного восстановления Docker-сервиса. Работаешь только на сервере {server_name} "
                    "и только вокруг контейнера {container_name}. Разрешены только минимальные действия, необходимые для "
                    "возврата контейнера в состояние running/healthy. Любое действие шире этого контура запрещено."
                ),
                "instructions": (
                    "Опирайся на утвержденный план, но адаптируйся к фактическому состоянию контейнера. Если восстановление "
                    "не удалось или неясно, что делать дальше, сформулируй конкретный вопрос оператору."
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "recovery_attempt_merge",
            "type": "logic/merge",
            "position": {"x": 360, "y": 1870},
            "data": {
                "label": "Recovery Attempt",
                "label_ru": "Собрать результат первой попытки",
                "mode": "any",
            },
        },
        {
            "id": "verify_after_recovery",
            "type": "agent/ssh_cmd",
            "position": {"x": 360, "y": 2010},
            "data": {
                "label": "Verify Recovery",
                "label_ru": "Проверить восстановление",
                "server_id": server_id,
                "command": verify_command,
                "on_failure": "continue",
            },
        },
        {
            "id": "operator_input_1",
            "type": "logic/telegram_input",
            "position": {"x": 720, "y": 2010},
            "data": {
                "label": "Operator Input 1",
                "label_ru": "Первая подсказка оператора",
                "tg_bot_token": "",
                "tg_chat_id": "",
                "parse_mode": "",
                "timeout_minutes": 90,
                "message": (
                    "Автоматическое восстановление не завершилось успешно.\n\n"
                    "Контейнер: {container_name}\n"
                    "Сервер: {server_name} ({server_host})\n"
                    "Запуск: {run_id}\n\n"
                    "Последняя проверка:\n"
                    "{verify_after_recovery_output}\n"
                    "{verify_after_recovery_error}\n\n"
                    "Ответьте одним сообщением, как действовать дальше в рамках этого контейнера."
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "guided_recovery_1",
            "type": "agent/react",
            "position": {"x": 720, "y": 2170},
            "data": {
                "label": "Guided Recovery 1",
                "label_ru": "Восстановление по первой подсказке",
                "server_ids": [server_id],
                "model": "gemini-2.0-flash-exp",
                "max_iterations": 4,
                "allowed_tools": list(RESTRICTED_AGENT_TOOLS),
                "goal": (
                    "Контейнер {container_name} не восстановился после первой AI-попытки. Оператор прислал уточнение:\n"
                    "{operator_input_1_output}\n\n"
                    "Выполни только действия, относящиеся к контейнеру {container_name}, и попробуй довести его до "
                    "состояния running/healthy. Если инструкция частично опасна или слишком широкая, возьми из нее только "
                    "безопасную часть и явно отрази это в отчете."
                ),
                "system_prompt": (
                    "Ты SRE-агент. Разрешено работать только с контейнером {container_name} на сервере {server_name}. "
                    "Запрещены действия вне этого контейнера. Нужно использовать подсказку оператора как приоритетный контекст."
                ),
                "instructions": (
                    "Сначала кратко сверяй текущее состояние контейнера, затем примени инструкцию оператора. "
                    "В конце дай короткий отчет о проделанных действиях и результате."
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "guided_attempt_1_merge",
            "type": "logic/merge",
            "position": {"x": 720, "y": 2310},
            "data": {
                "label": "Guided Attempt 1",
                "label_ru": "Собрать результат первой подсказки",
                "mode": "any",
            },
        },
        {
            "id": "verify_after_guidance_1",
            "type": "agent/ssh_cmd",
            "position": {"x": 720, "y": 2450},
            "data": {
                "label": "Verify After Guidance 1",
                "label_ru": "Проверить после первой подсказки",
                "server_id": server_id,
                "command": verify_command,
                "on_failure": "continue",
            },
        },
        {
            "id": "operator_input_2",
            "type": "logic/telegram_input",
            "position": {"x": 1080, "y": 2450},
            "data": {
                "label": "Operator Input 2",
                "label_ru": "Вторая подсказка оператора",
                "tg_bot_token": "",
                "tg_chat_id": "",
                "parse_mode": "",
                "timeout_minutes": 90,
                "message": (
                    "Нужна еще одна инструкция оператора: контейнер {container_name} все еще не восстановлен.\n\n"
                    "Сервер: {server_name} ({server_host})\n"
                    "Запуск: {run_id}\n\n"
                    "Последняя проверка:\n"
                    "{verify_after_guidance_1_output}\n"
                    "{verify_after_guidance_1_error}\n\n"
                    "Ответьте обычным текстом. Сообщение будет передано агенту как следующая инструкция."
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "guided_recovery_2",
            "type": "agent/react",
            "position": {"x": 1080, "y": 2610},
            "data": {
                "label": "Guided Recovery 2",
                "label_ru": "Восстановление по второй подсказке",
                "server_ids": [server_id],
                "model": "gemini-2.0-flash-exp",
                "max_iterations": 4,
                "allowed_tools": list(RESTRICTED_AGENT_TOOLS),
                "goal": (
                    "Контейнер {container_name} не восстановился после первой подсказки оператора. Новая инструкция:\n"
                    "{operator_input_2_output}\n\n"
                    "Попробуй еще одну ограниченную попытку восстановления только в рамках этого контейнера. "
                    "Если и после этого контейнер не восстановится, заверши работу четким списком блокеров."
                ),
                "system_prompt": (
                    "Ты SRE-агент последней безопасной попытки восстановления. Никаких действий вне контейнера "
                    "{container_name} на сервере {server_name}. Если для решения нужен более широкий доступ, остановись "
                    "и зафиксируй блокер."
                ),
                "instructions": (
                    "Используй только безопасные действия в docker-контуре контейнера. Отчет должен содержать: "
                    "что сделал, какой был результат, какие блокеры остались."
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "guided_attempt_2_merge",
            "type": "logic/merge",
            "position": {"x": 1080, "y": 2750},
            "data": {
                "label": "Guided Attempt 2",
                "label_ru": "Собрать результат второй подсказки",
                "mode": "any",
            },
        },
        {
            "id": "verify_after_guidance_2",
            "type": "agent/ssh_cmd",
            "position": {"x": 1080, "y": 2890},
            "data": {
                "label": "Verify After Guidance 2",
                "label_ru": "Проверить после второй подсказки",
                "server_id": server_id,
                "command": verify_command,
                "on_failure": "continue",
            },
        },
        {
            "id": "success_merge",
            "type": "logic/merge",
            "position": {"x": 360, "y": 2890},
            "data": {
                "label": "Success Merge",
                "label_ru": "Собрать успешную ветку",
                "mode": "any",
            },
        },
        {
            "id": "success_report",
            "type": "output/report",
            "position": {"x": 360, "y": 3040},
            "data": {
                "label": "Success Report",
                "label_ru": "Отчет об успешном восстановлении",
                "template": (
                    "# Контейнер восстановлен\n\n"
                    "- Сервер: {server_name} ({server_host})\n"
                    "- Контейнер: {container_name}\n"
                    "- Запуск: {run_id}\n\n"
                    "## План\n"
                    "{plan_report_output}\n\n"
                    "## Первая попытка AI\n"
                    "{recovery_agent_output}\n"
                    "{recovery_agent_error}\n\n"
                    "## Ветви с подсказками оператора\n"
                    "{guided_recovery_1_output}\n"
                    "{guided_recovery_1_error}\n"
                    "{guided_recovery_2_output}\n"
                    "{guided_recovery_2_error}\n\n"
                    "## Финальная проверка\n"
                    "{verify_after_recovery_output}\n"
                    "{verify_after_guidance_1_output}\n"
                    "{verify_after_guidance_2_output}\n\n"
                    "Контейнер прошел проверку и считается восстановленным."
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "success_telegram",
            "type": "output/telegram",
            "position": {"x": 360, "y": 3180},
            "data": {
                "label": "Success Telegram",
                "label_ru": "Отправить успешный отчет в Telegram",
                "bot_token": "",
                "chat_id": "",
                "parse_mode": "",
                "message": (
                    "Контейнер восстановлен.\n\n"
                    "Сервер: {server_name}\n"
                    "Контейнер: {container_name}\n"
                    "Запуск: {run_id}\n\n"
                    "Финальная проверка:\n"
                    "{verify_after_guidance_2_output}"
                    "{verify_after_guidance_1_output}"
                    "{verify_after_recovery_output}\n\n"
                    "Сервис снова в рабочем состоянии."
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "failure_merge",
            "type": "logic/merge",
            "position": {"x": 1080, "y": 3040},
            "data": {
                "label": "Failure Merge",
                "label_ru": "Собрать неуспешную ветку",
                "mode": "any",
            },
        },
        {
            "id": "final_failure_report",
            "type": "output/report",
            "position": {"x": 1080, "y": 3180},
            "data": {
                "label": "Failure Report",
                "label_ru": "Отчет о неуспешном восстановлении",
                "template": (
                    "# Восстановление не завершено\n\n"
                    "- Сервер: {server_name} ({server_host})\n"
                    "- Контейнер: {container_name}\n"
                    "- Запуск: {run_id}\n\n"
                    "## План и диагностика\n"
                    "{plan_report_output}\n\n"
                    "## Первая AI-попытка\n"
                    "{recovery_agent_output}\n"
                    "{recovery_agent_error}\n"
                    "{verify_after_recovery_output}\n"
                    "{verify_after_recovery_error}\n\n"
                    "## Первая подсказка оператора\n"
                    "{operator_input_1_output}\n"
                    "{guided_recovery_1_output}\n"
                    "{guided_recovery_1_error}\n"
                    "{verify_after_guidance_1_output}\n"
                    "{verify_after_guidance_1_error}\n\n"
                    "## Вторая подсказка оператора\n"
                    "{operator_input_2_output}\n"
                    "{guided_recovery_2_output}\n"
                    "{guided_recovery_2_error}\n"
                    "{verify_after_guidance_2_output}\n"
                    "{verify_after_guidance_2_error}\n\n"
                    "Требуется дальнейшее ручное решение оператора."
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "final_failure_telegram",
            "type": "output/telegram",
            "position": {"x": 1080, "y": 3320},
            "data": {
                "label": "Failure Telegram",
                "label_ru": "Отправить финальную ошибку в Telegram",
                "bot_token": "",
                "chat_id": "",
                "parse_mode": "",
                "message": (
                    "Автоматическое восстановление не завершено.\n\n"
                    "Сервер: {server_name}\n"
                    "Контейнер: {container_name}\n"
                    "Запуск: {run_id}\n\n"
                    "Последняя проверка:\n"
                    "{verify_after_guidance_2_output}"
                    "{verify_after_guidance_2_error}"
                    "{verify_after_guidance_1_output}"
                    "{verify_after_guidance_1_error}"
                    "{verify_after_recovery_output}"
                    "{verify_after_recovery_error}\n\n"
                    "Нужна ручная диагностика или более широкий план действий."
                ),
                "on_failure": "continue",
            },
        },
    ]


def build_docker_service_recovery_edges() -> list[dict]:
    return [
        {"id": "e_monitoring_parallel", "source": "monitoring_start", "target": "entry_parallel", "sourceHandle": "out", "animated": True},
        {"id": "e_parallel_report", "source": "entry_parallel", "target": "incident_report", "sourceHandle": "out", "animated": True},
        {"id": "e_parallel_tg", "source": "entry_parallel", "target": "alert_telegram", "sourceHandle": "out", "animated": True},
        {"id": "e_parallel_snapshot", "source": "entry_parallel", "target": "snapshot_probe", "sourceHandle": "out", "animated": True},
        {"id": "e_report_ctx_ok", "source": "incident_report", "target": "investigation_context_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_report_ctx_err", "source": "incident_report", "target": "investigation_context_merge", "sourceHandle": "error", "animated": True},
        {"id": "e_tg_ctx_ok", "source": "alert_telegram", "target": "investigation_context_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_tg_ctx_err", "source": "alert_telegram", "target": "investigation_context_merge", "sourceHandle": "error", "animated": True},
        {"id": "e_snapshot_ctx_ok", "source": "snapshot_probe", "target": "investigation_context_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_snapshot_ctx_err", "source": "snapshot_probe", "target": "investigation_context_merge", "sourceHandle": "error", "animated": True},
        {"id": "e_ctx_investigate", "source": "investigation_context_merge", "target": "investigate_agent", "sourceHandle": "out", "animated": True},
        {"id": "e_investigate_plan_ok", "source": "investigate_agent", "target": "plan_ready_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_investigate_plan_err", "source": "investigate_agent", "target": "plan_ready_merge", "sourceHandle": "error", "animated": True},
        {"id": "e_plan_ready_llm", "source": "plan_ready_merge", "target": "plan_llm", "sourceHandle": "out", "animated": True},
        {"id": "e_plan_llm_result_ok", "source": "plan_llm", "target": "plan_result_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_plan_llm_result_err", "source": "plan_llm", "target": "plan_result_merge", "sourceHandle": "error", "animated": True},
        {"id": "e_plan_result_report", "source": "plan_result_merge", "target": "plan_report", "sourceHandle": "out", "animated": True},
        {"id": "e_plan_report_approval", "source": "plan_report", "target": "approval_gate", "sourceHandle": "success", "animated": True},
        {"id": "e_approval_rejected_report", "source": "approval_gate", "target": "approval_rejected_report", "sourceHandle": "rejected", "animated": True},
        {"id": "e_approval_rejected_tg", "source": "approval_rejected_report", "target": "approval_rejected_telegram", "sourceHandle": "success", "animated": True},
        {"id": "e_approval_timeout_report", "source": "approval_gate", "target": "approval_timeout_report", "sourceHandle": "timeout", "animated": True},
        {"id": "e_approval_timeout_tg", "source": "approval_timeout_report", "target": "approval_timeout_telegram", "sourceHandle": "success", "animated": True},
        {"id": "e_approval_started_tg", "source": "approval_gate", "target": "recovery_started_telegram", "sourceHandle": "approved", "animated": True},
        {"id": "e_recovery_started_merge_ok", "source": "recovery_started_telegram", "target": "recovery_delivery_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_recovery_started_merge_err", "source": "recovery_started_telegram", "target": "recovery_delivery_merge", "sourceHandle": "error", "animated": True},
        {"id": "e_recovery_delivery_agent", "source": "recovery_delivery_merge", "target": "recovery_agent", "sourceHandle": "out", "animated": True},
        {"id": "e_recovery_agent_merge_ok", "source": "recovery_agent", "target": "recovery_attempt_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_recovery_agent_merge_err", "source": "recovery_agent", "target": "recovery_attempt_merge", "sourceHandle": "error", "animated": True},
        {"id": "e_recovery_attempt_verify", "source": "recovery_attempt_merge", "target": "verify_after_recovery", "sourceHandle": "out", "animated": True},
        {"id": "e_verify_recovery_success", "source": "verify_after_recovery", "target": "success_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_verify_recovery_operator_1", "source": "verify_after_recovery", "target": "operator_input_1", "sourceHandle": "error", "animated": True},
        {"id": "e_operator_1_guided", "source": "operator_input_1", "target": "guided_recovery_1", "sourceHandle": "received", "animated": True},
        {"id": "e_operator_1_failure", "source": "operator_input_1", "target": "failure_merge", "sourceHandle": "timeout", "animated": True},
        {"id": "e_guided_1_merge_ok", "source": "guided_recovery_1", "target": "guided_attempt_1_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_guided_1_merge_err", "source": "guided_recovery_1", "target": "guided_attempt_1_merge", "sourceHandle": "error", "animated": True},
        {"id": "e_guided_1_verify", "source": "guided_attempt_1_merge", "target": "verify_after_guidance_1", "sourceHandle": "out", "animated": True},
        {"id": "e_verify_1_success", "source": "verify_after_guidance_1", "target": "success_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_verify_1_operator_2", "source": "verify_after_guidance_1", "target": "operator_input_2", "sourceHandle": "error", "animated": True},
        {"id": "e_operator_2_guided", "source": "operator_input_2", "target": "guided_recovery_2", "sourceHandle": "received", "animated": True},
        {"id": "e_operator_2_failure", "source": "operator_input_2", "target": "failure_merge", "sourceHandle": "timeout", "animated": True},
        {"id": "e_guided_2_merge_ok", "source": "guided_recovery_2", "target": "guided_attempt_2_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_guided_2_merge_err", "source": "guided_recovery_2", "target": "guided_attempt_2_merge", "sourceHandle": "error", "animated": True},
        {"id": "e_guided_2_verify", "source": "guided_attempt_2_merge", "target": "verify_after_guidance_2", "sourceHandle": "out", "animated": True},
        {"id": "e_verify_2_success", "source": "verify_after_guidance_2", "target": "success_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_verify_2_failure", "source": "verify_after_guidance_2", "target": "failure_merge", "sourceHandle": "error", "animated": True},
        {"id": "e_success_report", "source": "success_merge", "target": "success_report", "sourceHandle": "out", "animated": True},
        {"id": "e_success_tg", "source": "success_report", "target": "success_telegram", "sourceHandle": "success", "animated": True},
        {"id": "e_failure_report", "source": "failure_merge", "target": "final_failure_report", "sourceHandle": "out", "animated": True},
        {"id": "e_failure_tg", "source": "final_failure_report", "target": "final_failure_telegram", "sourceHandle": "success", "animated": True},
    ]


def ensure_docker_service_recovery_pipeline(
    user,
    *,
    container_name: str,
    server_id: int | None = None,
    name: str | None = None,
) -> Pipeline:
    resolved_server_id = _resolve_server_id(user, server_id)
    resolved_server_name = _resolve_server_name(user, resolved_server_id)
    container_label = str(container_name or "").strip()
    if not container_label:
        raise ValueError("container_name is required")

    pipeline_name = name or f"Docker Recovery: {container_label}"
    pipeline_description = (
        "AI-first monitoring recovery pipeline for a Docker container. "
        "When monitoring reports a critical container failure, the pipeline gathers diagnostics, "
        "runs an AI investigation, prepares a recovery plan, sends it to Telegram for approval, "
        "tries AI-driven recovery, and if needed loops through plain-text Telegram instructions "
        "from the operator before producing a final report."
    )

    pipeline, _ = Pipeline.objects.update_or_create(
        owner=user,
        name=pipeline_name,
        defaults={
            "description": pipeline_description,
            "icon": "🚨",
            "tags": list(DOCKER_RECOVERY_PIPELINE_TAGS),
            "nodes": build_docker_service_recovery_nodes(
                server_id=resolved_server_id,
                container_name=container_label,
                server_name=resolved_server_name,
            ),
            "edges": build_docker_service_recovery_edges(),
            "graph_version": CURRENT_PIPELINE_GRAPH_VERSION,
            "is_shared": False,
        },
    )
    pipeline.sync_triggers_from_nodes()
    return pipeline
