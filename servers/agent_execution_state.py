from __future__ import annotations

from typing import Any

from app.worker_state import cleanup_stale_background_workers, serialize_background_worker_state

AGENT_EXECUTION_COMMAND = "python manage.py run_agent_execution_plane --worker-key default"
SCHEDULED_AGENTS_COMMAND = "python manage.py run_scheduled_agents --daemon --worker-key default"
AGENT_OPS_SUPERVISOR_COMMAND = "python manage.py run_ops_supervisor --with-scheduled-agents --with-watchers"


def _runtime_commands() -> dict[str, str]:
    return {
        "execution_worker": AGENT_EXECUTION_COMMAND,
        "scheduled_agents_worker": SCHEDULED_AGENTS_COMMAND,
        "ops_supervisor": AGENT_OPS_SUPERVISOR_COMMAND,
    }


def get_agent_execution_readiness() -> dict[str, Any]:
    cleanup_stale_background_workers("agent_execution")
    worker = serialize_background_worker_state("agent_execution")
    status = str(worker.get("status") or "missing")
    is_stale = bool(worker.get("is_stale"))
    ready = status == "running" and not is_stale
    if ready:
        severity = "success"
        title = "Execution worker готов"
        description = "Full/multi-агенты могут быть забраны execution-plane worker."
        next_action = ""
    elif status == "missing":
        severity = "warning"
        title = "Execution worker не запущен"
        description = "Full/multi-агенты будут поставлены в очередь, но не начнут выполняться до запуска worker."
        next_action = f"Запустите worker: {AGENT_EXECUTION_COMMAND}"
    elif is_stale:
        severity = "warning"
        title = "Execution worker heartbeat протух"
        description = "Lease worker истёк; queued full/multi-агенты могут ждать до перезапуска worker."
        next_action = f"Перезапустите worker: {AGENT_EXECUTION_COMMAND}"
    elif status == "error":
        severity = "critical"
        title = "Execution worker в ошибке"
        description = str(worker.get("last_error") or "Worker сообщил ошибку.")
        next_action = f"Проверьте логи и перезапустите worker: {AGENT_EXECUTION_COMMAND}"
    else:
        severity = "warning"
        title = "Execution worker не активен"
        description = f"Статус worker: {status}; full/multi-агенты могут остаться в очереди."
        next_action = f"Запустите worker: {AGENT_EXECUTION_COMMAND}"
    return {
        "required": True,
        "ready": ready,
        "status": status,
        "severity": severity,
        "title": title,
        "description": description,
        "next_action": next_action,
        "supervisor_action": f"Production worker: {AGENT_OPS_SUPERVISOR_COMMAND}" if not ready else "",
        "commands": _runtime_commands(),
        "worker": worker,
    }


def get_agent_execution_readiness_for_mode(mode: str) -> dict[str, Any]:
    if mode == "mini":
        return {
            "required": False,
            "ready": True,
            "status": "not_required",
            "severity": "info",
            "title": "Execution worker не требуется",
            "description": "Mini-агенты выполняются inline и не требуют execution-plane worker.",
            "next_action": "",
            "supervisor_action": "",
            "commands": _runtime_commands(),
            "worker": None,
        }
    return get_agent_execution_readiness()
