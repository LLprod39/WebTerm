from __future__ import annotations

from typing import Any

from studio.node_manifest import assistant_node_catalog

NODE_TYPE_CATALOG: dict[str, dict[str, Any]] = assistant_node_catalog()

NODE_TYPE_ALIASES = {
    "manual": "trigger/manual",
    "manual_trigger": "trigger/manual",
    "webhook": "trigger/webhook",
    "webhook_trigger": "trigger/webhook",
    "schedule": "trigger/schedule",
    "schedule_trigger": "trigger/schedule",
    "monitoring": "trigger/monitoring",
    "monitoring_trigger": "trigger/monitoring",
    "ssh_cmd": "agent/ssh_cmd",
    "ssh_command": "agent/ssh_cmd",
    "llm_query": "agent/llm_query",
    "mcp_call": "agent/mcp_call",
    "server_snapshot": "ops/server_snapshot",
    "linux_snapshot": "ops/server_snapshot",
    "log_query": "ops/log_query",
    "logs": "ops/log_query",
    "journal": "ops/log_query",
    "service_logs": "ops/log_query",
    "docker_logs": "ops/log_query",
    "file_action": "ops/file_action",
    "file_read": "ops/file_action",
    "file_write": "ops/file_action",
    "config_file": "ops/file_action",
    "package_action": "ops/package_action",
    "package_update": "ops/package_action",
    "package_install": "ops/package_action",
    "apt": "ops/package_action",
    "dnf": "ops/package_action",
    "yum": "ops/package_action",
    "disk_cleanup": "ops/disk_cleanup",
    "journal_vacuum": "ops/disk_cleanup",
    "tmp_cleanup": "ops/disk_cleanup",
    "backup_check": "ops/backup_restore_check",
    "backup_restore_check": "ops/backup_restore_check",
    "restore_check": "ops/backup_restore_check",
    "service_action": "ops/service_action",
    "service_restart": "ops/service_action",
    "systemctl": "ops/service_action",
    "docker_action": "ops/docker_action",
    "docker_restart": "ops/docker_action",
    "process_action": "ops/process_action",
    "http_check": "ops/http_check",
    "health_check": "ops/http_check",
    "resolve_alert": "ops/alert_update",
    "alert_update": "ops/alert_update",
    "condition": "logic/condition",
    "parallel": "logic/parallel",
    "merge": "logic/merge",
    "wait": "logic/wait",
    "human_approval": "logic/human_approval",
    "telegram_input": "logic/telegram_input",
    "trigger/telegram_input": "logic/telegram_input",
    "input/telegram": "logic/telegram_input",
    "telegram/input": "logic/telegram_input",
    "telegram_trigger": "logic/telegram_input",
    "report": "output/report",
    "email": "output/email",
    "telegram": "output/telegram",
    "send_telegram": "output/telegram",
}

EDGE_PLACEHOLDER_TYPES = {
    "edge",
    "edge_placeholder",
    "connection",
    "graph_edge",
    "placeholder/edge",
}

HANDLE_ALIASES = {
    "yes": "true",
    "no": "false",
    "ok": "success",
    "done": "success",
    "approved": "approved",
    "rejected": "rejected",
    "timeout": "timeout",
    "reply": "received",
    "replied": "received",
    "received": "received",
}


def _node_catalog_payload() -> list[dict[str, Any]]:
    return [
        {
            "type": node_type,
            "category": item["category"],
            "purpose": item["purpose"],
            "source_handles": list(item["source_handles"]),
        }
        for node_type, item in NODE_TYPE_CATALOG.items()
    ]
