from __future__ import annotations

from collections.abc import Iterable


def build_entry_nodes(*, primary_server_ids: list[int]) -> list[dict]:
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
            "id": "monitoring_start",
            "type": "trigger/monitoring",
            "position": {"x": 800, "y": 20},
            "data": {
                "label": "Monitoring Alert Start",
                "label_ru": "Запуск по alert",
                "is_active": True,
                "server_ids": primary_server_ids,
                "severities": ["critical"],
                "alert_types": ["service"],
                "monitoring_filters": {
                    "server_ids": primary_server_ids,
                    "severities": ["critical"],
                    "alert_types": ["service"],
                },
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
                "manual_link_only": True,
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
                    "# Smoke-запуск отклонен\n\nОператор отклонил шаг подтверждения.\n\n{approval_gate_error}"
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
    ]


def build_collector_nodes() -> list[dict]:
    return [
        {
            "id": "branch_merge",
            "type": "logic/merge",
            "position": {"x": 1040, "y": 1100},
            "data": {
                "label": "Collect Branch Results",
                "label_ru": "Собрать результаты веток",
                "mode": "all",
            },
        },
        {
            "id": "final_report",
            "type": "output/report",
            "position": {"x": 1040, "y": 1240},
            "data": {
                "label": "Final Smoke Report",
                "label_ru": "Финальный smoke-отчет",
                "on_failure": "continue",
            },
        },
    ]


def build_smoke_edges(*, standard_branch_targets: Iterable[str], telegram_input_target: str) -> list[dict]:
    edges = [
        {
            "id": "e_manual_merge",
            "source": "manual_start",
            "target": "trigger_merge",
            "sourceHandle": "out",
            "animated": True,
        },
        {
            "id": "e_webhook_merge",
            "source": "webhook_start",
            "target": "trigger_merge",
            "sourceHandle": "out",
            "animated": True,
        },
        {
            "id": "e_schedule_merge",
            "source": "schedule_start",
            "target": "trigger_merge",
            "sourceHandle": "out",
            "animated": True,
        },
        {
            "id": "e_monitoring_merge",
            "source": "monitoring_start",
            "target": "trigger_merge",
            "sourceHandle": "out",
            "animated": True,
        },
        {
            "id": "e_merge_entry",
            "source": "trigger_merge",
            "target": "entry_report",
            "sourceHandle": "out",
            "animated": True,
        },
        {
            "id": "e_entry_condition",
            "source": "entry_report",
            "target": "condition_gate",
            "sourceHandle": "success",
            "animated": True,
        },
        {
            "id": "e_condition_true",
            "source": "condition_gate",
            "target": "approval_gate",
            "sourceHandle": "true",
            "animated": True,
            "label": "true",
        },
        {
            "id": "e_condition_false",
            "source": "condition_gate",
            "target": "bypass_report",
            "sourceHandle": "false",
            "animated": True,
            "label": "false",
        },
        {
            "id": "e_approval_approved",
            "source": "approval_gate",
            "target": "post_condition_merge",
            "sourceHandle": "approved",
            "animated": True,
            "label": "approved",
        },
        {
            "id": "e_approval_rejected",
            "source": "approval_gate",
            "target": "rejected_report",
            "sourceHandle": "rejected",
            "animated": True,
            "label": "rejected",
        },
        {
            "id": "e_approval_timeout",
            "source": "approval_gate",
            "target": "timeout_report",
            "sourceHandle": "timeout",
            "animated": True,
            "label": "timeout",
        },
        {
            "id": "e_gate_merge_wait",
            "source": "post_condition_merge",
            "target": "wait_short",
            "sourceHandle": "out",
            "animated": True,
        },
        {
            "id": "e_wait_parallel",
            "source": "wait_short",
            "target": "parallel_fanout",
            "sourceHandle": "done",
            "animated": True,
        },
    ]
    for node_id in standard_branch_targets:
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
            "id": f"e_parallel_{telegram_input_target}",
            "source": "parallel_fanout",
            "target": telegram_input_target,
            "sourceHandle": "out",
            "animated": True,
        }
    )
    edges.append(
        {
            "id": "e_telegram_input_received_merge",
            "source": telegram_input_target,
            "target": "branch_merge",
            "sourceHandle": "received",
            "animated": True,
        }
    )
    edges.append(
        {
            "id": "e_telegram_input_timeout_merge",
            "source": telegram_input_target,
            "target": "branch_merge",
            "sourceHandle": "timeout",
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
