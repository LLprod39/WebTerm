from __future__ import annotations

from .mcp_showcase import ensure_demo_mcp_server
from .models import CURRENT_PIPELINE_GRAPH_VERSION, MCPServerPool, Pipeline
from .services import get_first_owned_server_id, list_owned_server_ids

ALL_NODES_SMOKE_PIPELINE_NAME = "All Nodes Smoke Test"
ALL_NODES_SMOKE_DESCRIPTION = (
    "Большой smoke-пайплайн Studio V2 со всеми встроенными типами узлов. "
    "Он предназначен для ручной проверки, использует только read-only проверки серверов, "
    "локальный webhook POST, короткие ожидания и безопасно отключенные email/telegram-узлы без реальных изменений."
)
ALL_NODES_SMOKE_TAGS = ["studio", "smoke", "all-nodes", "safe", "qa"]
LOCAL_WEBHOOK_TARGET = "http://127.0.0.1:9000/api/health/"


def _resolve_server_ids(user, *, limit: int = 2) -> list[int]:
    return list_owned_server_ids(user, limit=limit, order_by="id")


def _resolve_ssh_server_id(user) -> int | None:
    return get_first_owned_server_id(user, order_by="id")


def _resolve_mcp_server_id(user) -> int | None:
    if getattr(user, "is_staff", False):
        return ensure_demo_mcp_server(user).id
    return MCPServerPool.objects.filter(owner=user).order_by("id").values_list("id", flat=True).first()


def build_all_nodes_smoke_nodes(
    *,
    server_ids: list[int] | None = None,
    ssh_server_id: int | None = None,
    mcp_server_id: int | None = None,
) -> list[dict]:
    bounded_server_ids = [int(server_id) for server_id in (server_ids or []) if server_id]
    primary_server_ids = bounded_server_ids[:1]
    multi_server_ids = bounded_server_ids[:2]
    return [
        {
            "id": "manual_start",
            "type": "trigger/manual",
            "position": {"x": 320, "y": 20},
            "data": {
                "label": "Manual Start",
                "label_ru": "Ручной запуск",
                "is_active": True,
            },
        },
        {
            "id": "webhook_start",
            "type": "trigger/webhook",
            "position": {"x": 80, "y": 20},
            "data": {
                "label": "Webhook Start",
                "label_ru": "Webhook запуск",
                "is_active": True,
                "webhook_payload_map": {
                    "ticket": "ticket",
                    "source": "source",
                    "note": "note",
                },
            },
        },
        {
            "id": "schedule_start",
            "type": "trigger/schedule",
            "position": {"x": 560, "y": 20},
            "data": {
                "label": "Scheduled Start",
                "label_ru": "Запуск по расписанию",
                "is_active": True,
                "cron_expression": "*/30 * * * *",
            },
        },
        {
            "id": "trigger_merge",
            "type": "logic/merge",
            "position": {"x": 320, "y": 140},
            "data": {
                "label": "Any Trigger Entry",
                "label_ru": "Вход из любого триггера",
                "mode": "any",
            },
        },
        {
            "id": "entry_report",
            "type": "output/report",
            "position": {"x": 320, "y": 260},
            "data": {
                "label": "Entry Snapshot",
                "label_ru": "Стартовый отчет",
                "template": (
                    "# Smoke-проверка всех узлов\n\n"
                    "Пайплайн запущен и находится в рабочем состоянии.\n\n"
                    "- ticket: {ticket}\n"
                    "- source: {source}\n"
                    "- note: {note}\n\n"
                    "Следующий этап: условие и подтверждение оператора перед проверкой дополнительных веток."
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "condition_gate",
            "type": "logic/condition",
            "position": {"x": 320, "y": 380},
            "data": {
                "label": "Condition Gate",
                "label_ru": "Условие",
                "source_node_id": "entry_report",
                "check_type": "always_true",
            },
        },
        {
            "id": "approval_gate",
            "type": "logic/human_approval",
            "position": {"x": 170, "y": 500},
            "data": {
                "label": "Approve Full Smoke Run",
                "label_ru": "Подтверждение smoke-запуска",
                "timeout_minutes": 30,
                "base_url": "http://127.0.0.1:9000",
                "to_email": " ",
                "tg_bot_token": " ",
                "tg_chat_id": " ",
                "message": (
                    "Smoke-проверка всех узлов ожидает подтверждения.\n\n"
                    "{all_outputs}\n\n"
                    "Одобрить: {approve_url}\nОтклонить: {reject_url}"
                ),
                "telegram_message": (
                    "🔔 *Требуется подтверждение пайплайна*\n\n"
                    "*Пайплайн:* {pipeline_name}\n"
                    "*Запуск:* {run_id}\n\n"
                    "{all_outputs}\n\n"
                    "Нажмите кнопку ниже, чтобы одобрить или отклонить шаг прямо в Telegram."
                ),
            },
        },
        {
            "id": "bypass_report",
            "type": "output/report",
            "position": {"x": 470, "y": 500},
            "data": {
                "label": "Condition False Branch",
                "label_ru": "Ложная ветка условия",
                "template": (
                    "# Ложная ветка условия\n\n"
                    "Условие перевело выполнение в ложную ветку.\n"
                    "Этот узел нужен, чтобы вручную проверить альтернативный путь выполнения."
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "rejected_report",
            "type": "output/report",
            "position": {"x": 20, "y": 620},
            "data": {
                "label": "Approval Rejected",
                "label_ru": "Подтверждение отклонено",
                "template": (
                    "# Smoke-запуск отклонен\n\n"
                    "Оператор отклонил шаг подтверждения.\n\n"
                    "{approval_gate_error}"
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "timeout_report",
            "type": "output/report",
            "position": {"x": 170, "y": 620},
            "data": {
                "label": "Approval Timed Out",
                "label_ru": "Истекло время подтверждения",
                "template": (
                    "# Истекло время ожидания подтверждения\n\n"
                    "До истечения таймаута решение по шагу подтверждения не было принято.\n\n"
                    "{approval_gate_error}"
                ),
                "on_failure": "continue",
            },
        },
        {
            "id": "post_condition_merge",
            "type": "logic/merge",
            "position": {"x": 320, "y": 560},
            "data": {
                "label": "Continue After Gate",
                "label_ru": "Продолжить после подтверждения",
                "mode": "any",
            },
        },
        {
            "id": "wait_short",
            "type": "logic/wait",
            "position": {"x": 320, "y": 620},
            "data": {
                "label": "Short Wait",
                "label_ru": "Короткая пауза",
                "wait_minutes": 0.1,
            },
        },
        {
            "id": "parallel_fanout",
            "type": "logic/parallel",
            "position": {"x": 320, "y": 760},
            "data": {
                "label": "Parallel Node Fan-Out",
                "label_ru": "Параллельный запуск узлов",
            },
        },
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
                "to_email": " ",
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
            "id": "branch_merge",
            "type": "logic/merge",
            "position": {"x": 600, "y": 1100},
            "data": {
                "label": "Collect Branch Results",
                "label_ru": "Собрать результаты веток",
                "mode": "all",
            },
        },
        {
            "id": "final_report",
            "type": "output/report",
            "position": {"x": 600, "y": 1240},
            "data": {
                "label": "Final Smoke Report",
                "label_ru": "Финальный smoke-отчет",
                "on_failure": "continue",
            },
        },
    ]


def build_all_nodes_smoke_edges() -> list[dict]:
    branch_targets = [
        "ssh_probe",
        "react_probe",
        "multi_probe",
        "llm_probe",
        "mcp_probe",
        "webhook_probe",
        "email_probe",
        "telegram_probe",
    ]
    edges = [
        {"id": "e_manual_merge", "source": "manual_start", "target": "trigger_merge", "sourceHandle": "out", "animated": True},
        {"id": "e_webhook_merge", "source": "webhook_start", "target": "trigger_merge", "sourceHandle": "out", "animated": True},
        {"id": "e_schedule_merge", "source": "schedule_start", "target": "trigger_merge", "sourceHandle": "out", "animated": True},
        {"id": "e_merge_entry", "source": "trigger_merge", "target": "entry_report", "sourceHandle": "out", "animated": True},
        {"id": "e_entry_condition", "source": "entry_report", "target": "condition_gate", "sourceHandle": "success", "animated": True},
        {"id": "e_condition_true", "source": "condition_gate", "target": "approval_gate", "sourceHandle": "true", "animated": True, "label": "true"},
        {"id": "e_condition_false", "source": "condition_gate", "target": "bypass_report", "sourceHandle": "false", "animated": True, "label": "false"},
        {"id": "e_approval_approved", "source": "approval_gate", "target": "post_condition_merge", "sourceHandle": "approved", "animated": True, "label": "approved"},
        {"id": "e_approval_rejected", "source": "approval_gate", "target": "rejected_report", "sourceHandle": "rejected", "animated": True, "label": "rejected"},
        {"id": "e_approval_timeout", "source": "approval_gate", "target": "timeout_report", "sourceHandle": "timeout", "animated": True, "label": "timeout"},
        {"id": "e_bypass_wait", "source": "bypass_report", "target": "post_condition_merge", "sourceHandle": "success", "animated": True},
        {"id": "e_gate_merge_wait", "source": "post_condition_merge", "target": "wait_short", "sourceHandle": "out", "animated": True},
        {"id": "e_wait_parallel", "source": "wait_short", "target": "parallel_fanout", "sourceHandle": "done", "animated": True},
    ]
    for node_id in branch_targets:
        edges.append(
            {
                "id": f"e_parallel_{node_id}",
                "source": "parallel_fanout",
                "target": node_id,
                "sourceHandle": "out",
                "animated": True,
            }
        )
        edges.append(
            {
                "id": f"e_{node_id}_success_merge",
                "source": node_id,
                "target": "branch_merge",
                "sourceHandle": "success",
                "animated": True,
            }
        )
        edges.append(
            {
                "id": f"e_{node_id}_error_merge",
                "source": node_id,
                "target": "branch_merge",
                "sourceHandle": "error",
                "animated": True,
            }
        )
    edges.append(
        {
            "id": "e_branch_merge_report",
            "source": "branch_merge",
            "target": "final_report",
            "sourceHandle": "out",
            "animated": True,
        }
    )
    return edges


def ensure_all_nodes_smoke_pipeline(user) -> Pipeline:
    server_ids = _resolve_server_ids(user, limit=2)
    ssh_server_id = _resolve_ssh_server_id(user)
    mcp_server_id = _resolve_mcp_server_id(user)
    pipeline, _ = Pipeline.objects.update_or_create(
        owner=user,
        name=ALL_NODES_SMOKE_PIPELINE_NAME,
        defaults={
            "description": ALL_NODES_SMOKE_DESCRIPTION,
            "icon": "🧰",
            "tags": list(ALL_NODES_SMOKE_TAGS),
            "nodes": build_all_nodes_smoke_nodes(
                server_ids=server_ids,
                ssh_server_id=ssh_server_id,
                mcp_server_id=mcp_server_id,
            ),
            "edges": build_all_nodes_smoke_edges(),
            "graph_version": CURRENT_PIPELINE_GRAPH_VERSION,
            "is_shared": False,
        },
    )
    pipeline.sync_triggers_from_nodes()
    return pipeline
