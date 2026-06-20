from __future__ import annotations


def build_preapproval_nodes(
    *,
    server_id: int,
    container_name: str,
    server_name: str,
    snapshot_command: str,
) -> list[dict]:
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
                "permission_mode": "PLAN", "allowed_tools": ["ssh_execute", "read_console"],
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
    ]

