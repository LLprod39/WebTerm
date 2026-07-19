from __future__ import annotations

LOCAL_WEBHOOK_TARGET = "http://127.0.0.1:9000/api/health/"
TELEGRAM_INPUT_TARGET_ID = "telegram_input_probe"

STANDARD_BRANCH_TARGET_IDS = [
    "ssh_probe",
    "react_probe",
    "multi_probe",
    "llm_probe",
    "mcp_probe",
    "webhook_probe",
    "email_probe",
    "telegram_probe",
    "server_snapshot_probe",
    "log_query_probe",
    "file_action_probe",
    "package_action_probe",
    "disk_cleanup_probe",
    "backup_restore_check_probe",
    "service_action_probe",
    "docker_action_probe",
    "process_action_probe",
    "http_check_probe",
    "alert_update_probe",
]


def build_probe_nodes(
    *,
    primary_server_ids: list[int],
    multi_server_ids: list[int],
    ssh_server_id: int | None,
    mcp_server_id: int | None,
) -> list[dict]:
    return [
        {
            "id": "ssh_probe",
            "type": "agent/ssh_cmd",
            "position": {"x": 20, "y": 920},
            "data": {
                "label": "SSH Probe",
                "label_ru": "Проверка SSH",
                "server_id": ssh_server_id,
                "command": "echo '[all-nodes-smoke]'; whoami; hostname || uname -n; pwd",
                "preflight_commands": ["date"],
                "verification_commands": ["echo '[all-nodes-smoke verified]'"],
                "on_failure": "continue",
            },
        },
        {
            "id": "react_probe",
            "type": "agent/react",
            "position": {"x": 180, "y": 920},
            "data": {
                "label": "ReAct Read-Only Agent",
                "label_ru": "ReAct агент только для чтения",
                "goal": (
                    "Smoke-проверка только для чтения. Ничего не изменяй. "
                    "Используй только безопасные команды проверки вроде whoami, hostname, pwd, date, uname -a, "
                    "после чего дай краткое резюме в 3 пунктах."
                ),
                "system_prompt": (
                    "Ты осторожный QA-агент. Без записи, без установок, без рестартов и без изменений файлов. "
                    "Держи запуск коротким и используй не больше двух безопасных проверок."
                ),
                "server_ids": primary_server_ids,
                "permission_mode": "PLAN",
                # ask_user намеренно исключён: пайплайн имеет unattended-триггеры
                # (schedule/webhook/monitoring), рантайм запрещает ask_user в таком режиме.
                "allowed_tools": ["ssh_execute", "read_console", "wait_for_output", "report", "analyze_output"],
                "max_iterations": 2,
                "on_failure": "continue",
            },
        },
        {
            "id": "multi_probe",
            "type": "agent/multi",
            "position": {"x": 340, "y": 920},
            "data": {
                "label": "Multi-Agent Read-Only",
                "label_ru": "Multi-Agent только для чтения",
                "goal": (
                    "Smoke-проверка multi-agent только для чтения. Сравни указанные цели, используя только безопасные команды, "
                    "а затем подготовь короткое сравнение без каких-либо действий по исправлению."
                ),
                "system_prompt": (
                    "Ты QA-координатор. Без записи, без установок, без рестартов. "
                    "Собери только минимальный read-only контекст и кратко опиши различия."
                ),
                "server_ids": multi_server_ids,
                "permission_mode": "PLAN",
                # ask_user намеренно исключён: см. комментарий у react_probe.
                "allowed_tools": ["ssh_execute", "read_console", "wait_for_output", "report", "analyze_output"],
                "max_iterations": 2,
                "on_failure": "continue",
            },
        },
        {
            "id": "llm_probe",
            "type": "agent/llm_query",
            "position": {"x": 500, "y": 920},
            "data": {
                "label": "LLM Briefing",
                "label_ru": "Краткая сводка LLM",
                "provider": "gemini",
                "prompt": (
                    "Верни краткую сводку по smoke-проверке на основе входных данных пайплайна. "
                    "Начни ответ с фразы 'ПАЙПЛАЙН ГОТОВ'."
                ),
                "include_all_outputs": True,
                "on_failure": "continue",
            },
        },
        {
            "id": "mcp_probe",
            "type": "agent/mcp_call",
            "position": {"x": 660, "y": 920},
            "data": {
                "label": "MCP Workspace Snapshot",
                "label_ru": "Снимок рабочего пространства MCP",
                "mcp_server_id": mcp_server_id,
                "tool_name": "workspace_snapshot",
                "arguments": {
                    "root": ".",
                    "max_files": 20,
                },
                "on_failure": "continue",
            },
        },
        {
            "id": "webhook_probe",
            "type": "output/webhook",
            "position": {"x": 820, "y": 920},
            "data": {
                "label": "Local Webhook POST",
                "label_ru": "Локальный webhook POST",
                "url": LOCAL_WEBHOOK_TARGET,
                "extra_payload": {
                    "kind": "all_nodes_smoke",
                },
                "on_failure": "continue",
            },
        },
        {
            "id": "email_probe",
            "type": "output/email",
            "position": {"x": 980, "y": 920},
            "data": {
                "label": "Email Node (Disabled Safe)",
                "label_ru": "Email-узел (безопасно отключен)",
                "to_email": "smoke@example.test",
                "subject": "Smoke-проверка всех узлов",
                "body": "Этот email-узел намеренно отключен для безопасной проверки.\n\nКонтекст:\n{all_outputs}",
                "on_failure": "continue",
            },
        },
        {
            "id": "telegram_probe",
            "type": "output/telegram",
            "position": {"x": 1140, "y": 920},
            "data": {
                "label": "Telegram Node (Disabled Safe)",
                "label_ru": "Telegram-узел (безопасно отключен)",
                "bot_token": " ",
                "chat_id": " ",
                "message": "Этот Telegram-узел намеренно отключен для безопасной проверки.\n\n{all_outputs}",
                "on_failure": "continue",
            },
        },
        {
            "id": TELEGRAM_INPUT_TARGET_ID,
            "type": "logic/telegram_input",
            "position": {"x": 1300, "y": 920},
            "data": {
                "label": "Telegram Input (Disabled Safe)",
                "label_ru": "Telegram-ввод (безопасно отключен)",
                "tg_bot_token": " ",
                "tg_chat_id": " ",
                "message": "Этот Telegram input намеренно отключен для безопасной smoke-проверки.\n\n{all_outputs}",
                "timeout_minutes": 1,
            },
        },
        {
            "id": "server_snapshot_probe",
            "type": "ops/server_snapshot",
            "position": {"x": 1460, "y": 920},
            "data": {
                "label": "Server Snapshot (Context Safe)",
                "label_ru": "Снимок сервера (context)",
                "server_id_context_key": "server_id",
                "sections": ["overview", "services", "docker", "disk"],
                "on_failure": "continue",
            },
        },
        {
            "id": "log_query_probe",
            "type": "ops/log_query",
            "position": {"x": 1540, "y": 920},
            "data": {
                "label": "Log Query (Context Safe)",
                "label_ru": "Запрос логов (context)",
                "server_id_context_key": "server_id",
                "source": "journal",
                "lines": 80,
                "filter_text": "",
                "on_failure": "continue",
            },
        },
        {
            "id": "file_action_probe",
            "type": "ops/file_action",
            "position": {"x": 1620, "y": 920},
            "data": {
                "label": "File Read (Context Safe)",
                "label_ru": "Чтение файла (context)",
                "server_id_context_key": "server_id",
                "action": "read",
                "path": "/etc/os-release",
                "max_bytes": 65536,
                "on_failure": "continue",
            },
        },
        {
            "id": "package_action_probe",
            "type": "ops/package_action",
            "position": {"x": 1700, "y": 920},
            "data": {
                "label": "Package Updates (Read-Only)",
                "label_ru": "Обновления пакетов (read-only)",
                "server_id_context_key": "server_id",
                "action": "list_updates",
                "packages": [],
                "on_failure": "continue",
            },
        },
        {
            "id": "disk_cleanup_probe",
            "type": "ops/disk_cleanup",
            "position": {"x": 1780, "y": 920},
            "data": {
                "label": "Disk Cleanup Inspect",
                "label_ru": "Disk cleanup inspect",
                "server_id_context_key": "server_id",
                "action": "inspect",
                "dry_run": True,
                "on_failure": "continue",
            },
        },
        {
            "id": "backup_restore_check_probe",
            "type": "ops/backup_restore_check",
            "position": {"x": 1860, "y": 920},
            "data": {
                "label": "Backup Check (Read-Only)",
                "label_ru": "Проверка backup (read-only)",
                "server_id_context_key": "server_id",
                "action": "inspect",
                "path": "/var/backups",
                "max_depth": 2,
                "max_files": 10,
                "max_age_hours": 24,
                "on_failure": "continue",
            },
        },
        {
            "id": "service_action_probe",
            "type": "ops/service_action",
            "position": {"x": 2020, "y": 920},
            "data": {
                "label": "Service Action (Context Safe)",
                "label_ru": "Service action (context)",
                "server_id_context_key": "server_id",
                "service": "",
                "action": "reload",
                "verify": True,
                "on_failure": "continue",
            },
        },
        {
            "id": "docker_action_probe",
            "type": "ops/docker_action",
            "position": {"x": 2180, "y": 920},
            "data": {
                "label": "Docker Action (Context Safe)",
                "label_ru": "Docker action (context)",
                "server_id_context_key": "server_id",
                "container": "",
                "action": "restart",
                "include_logs": False,
                "verify": True,
                "on_failure": "continue",
            },
        },
        {
            "id": "process_action_probe",
            "type": "ops/process_action",
            "position": {"x": 2340, "y": 920},
            "data": {
                "label": "Process Action (Context Safe)",
                "label_ru": "Process action (context)",
                "server_id_context_key": "server_id",
                "pid_context_key": "pid",
                "action": "terminate",
                "on_failure": "continue",
            },
        },
        {
            "id": "http_check_probe",
            "type": "ops/http_check",
            "position": {"x": 2500, "y": 920},
            "data": {
                "label": "HTTP Health Check",
                "label_ru": "HTTP health check",
                "url": LOCAL_WEBHOOK_TARGET,
                "method": "GET",
                "expected_status": [200, 204, 404],
                "timeout_seconds": 5,
                "on_failure": "continue",
            },
        },
        {
            "id": "alert_update_probe",
            "type": "ops/alert_update",
            "position": {"x": 2660, "y": 920},
            "data": {
                "label": "Alert Update (Context Safe)",
                "label_ru": "Alert update (context)",
                "alert_id_context_key": "alert_id",
                "action": "resolve",
                "note": "Smoke path only resolves when alert_id is explicitly provided.",
                "on_failure": "continue",
            },
        },
    ]
