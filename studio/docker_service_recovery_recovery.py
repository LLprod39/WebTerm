from __future__ import annotations

from .docker_service_recovery_commands import RESTRICTED_AGENT_TOOLS


def build_recovery_loop_nodes(
    *,
    server_id: int,
    verify_command: str,
) -> list[dict]:
    return [
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

