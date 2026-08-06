from __future__ import annotations

from typing import Any

from django.conf import settings

from app.worker_state import cleanup_stale_background_workers, serialize_background_worker_kind_state

AGENT_EXECUTION_COMMAND = "python manage.py run_agent_execution_plane --worker-key <unique-worker-key>"
SCHEDULED_AGENTS_COMMAND = "python manage.py run_scheduled_agents --daemon --worker-key default"
AGENT_OPS_SUPERVISOR_COMMAND = "docker compose up -d --scale agent-execution=<replicas> agent-execution"


def _runtime_commands() -> dict[str, str]:
    return {
        "execution_worker": AGENT_EXECUTION_COMMAND,
        "scheduled_agents_worker": SCHEDULED_AGENTS_COMMAND,
        "ops_supervisor": AGENT_OPS_SUPERVISOR_COMMAND,
    }


def get_agent_execution_readiness() -> dict[str, Any]:
    cleanup_stale_background_workers("agent_execution")
    worker = serialize_background_worker_kind_state("agent_execution")
    status = str(worker.get("status") or "missing")
    is_stale = bool(worker.get("is_stale"))
    healthy_replicas = int(worker.get("healthy_replica_count") or 0)
    expected_replicas = max(1, int(getattr(settings, "AGENT_EXECUTION_REPLICAS", 1) or 1))
    ready = status == "running" and not is_stale and healthy_replicas >= expected_replicas
    if ready:
        severity = "success"
        title = "Execution worker готов"
        description = f"Готовы worker-реплики: {healthy_replicas}/{expected_replicas}."
        next_action = ""
    elif healthy_replicas > 0:
        severity = "warning"
        title = "Пул execution worker работает не полностью"
        description = f"Готовы только {healthy_replicas} из {expected_replicas} worker-реплик."
        next_action = AGENT_OPS_SUPERVISOR_COMMAND.replace("<replicas>", str(expected_replicas))
    elif status == "missing":
        severity = "warning"
        title = "Execution worker не запущен"
        description = "Агенты будут поставлены в очередь, но не начнут выполняться до запуска worker."
        next_action = f"Запустите worker: {AGENT_EXECUTION_COMMAND}"
    elif is_stale:
        severity = "warning"
        title = "Execution worker heartbeat протух"
        description = "Lease worker истёк; queued-агенты могут ждать до перезапуска worker."
        next_action = f"Перезапустите worker: {AGENT_EXECUTION_COMMAND}"
    elif status == "error":
        severity = "critical"
        title = "Execution worker в ошибке"
        description = str(worker.get("last_error") or "Worker сообщил ошибку.")
        next_action = f"Проверьте логи и перезапустите worker: {AGENT_EXECUTION_COMMAND}"
    else:
        severity = "warning"
        title = "Execution worker не активен"
        description = f"Статус worker: {status}; агенты могут остаться в очереди."
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
        "healthy_replicas": healthy_replicas,
        "expected_replicas": expected_replicas,
    }


def get_agent_execution_readiness_for_mode(mode: str) -> dict[str, Any]:
    # All modes (including mini) use the execution-plane queue.
    _ = mode
    return get_agent_execution_readiness()
