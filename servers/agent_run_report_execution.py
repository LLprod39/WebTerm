from typing import Any

from django.utils import timezone

from servers.agent_dispatch import serialize_agent_dispatch
from servers.agent_execution_state import AGENT_EXECUTION_COMMAND, AGENT_OPS_SUPERVISOR_COMMAND
from servers.agent_run_report_base import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    _age_ms,
    _agent_run_stale_seconds_setting,
    _duration_label,
    _json_safe,
    _latest_dispatch,
    _run_severity,
    _select_agent_execution_worker,
    _serialize_worker_row,
    _server_names,
    _severity_rank,
    _status_label,
    _text,
)
from servers.models import AgentRun, AgentRunDispatch, BackgroundWorkerState


def _build_execution_state(run: AgentRun) -> dict[str, Any]:
    now = timezone.now()
    dispatch = _latest_dispatch(run)
    worker = _select_agent_execution_worker(dispatch, now=now)
    worker_payload = _serialize_worker_row(worker, now=now)
    dispatch_payload = serialize_agent_dispatch(dispatch)
    agent_mode = run.agent.mode if run.agent_id and run.agent else "mini"
    dispatch_status = str(getattr(dispatch, "status", "") or "")
    worker_status = str(worker_payload.get("status") or "missing")
    worker_stale = bool(worker_payload.get("is_stale"))
    worker_ready = worker_status == BackgroundWorkerState.STATUS_RUNNING and not worker_stale
    lease_expired = bool(
        dispatch
        and dispatch.status == AgentRunDispatch.STATUS_CLAIMED
        and dispatch.lease_expires_at is not None
        and dispatch.lease_expires_at <= now
    )
    queued_age_ms = _age_ms(dispatch.queued_at, now=now) if dispatch else None
    heartbeat_age_ms = _age_ms(dispatch.heartbeat_at, now=now) if dispatch and dispatch.heartbeat_at else None
    runtime_age_ms = _age_ms(run.started_at, now=now) if run.started_at else None
    stale_after_seconds = _agent_run_stale_seconds_setting()
    stale_after_ms = stale_after_seconds * 1000 if stale_after_seconds > 0 else 0
    is_stale_candidate = bool(
        stale_after_ms
        and runtime_age_ms is not None
        and runtime_age_ms >= stale_after_ms
        and run.completed_at is None
        and run.status in ACTIVE_STATUSES
    )
    command = AGENT_EXECUTION_COMMAND
    supervisor_command = AGENT_OPS_SUPERVISOR_COMMAND

    state = {
        "status": "not_required",
        "severity": "info",
        "title": "Execution worker не требуется",
        "description": "Этот запуск не использует выделенную очередь full/multi-агентов.",
        "next_action": "",
        "dispatch": dispatch_payload,
        "worker": worker_payload,
        "queued_age_ms": queued_age_ms,
        "queued_for": _duration_label(queued_age_ms) if queued_age_ms is not None else "—",
        "heartbeat_age_ms": heartbeat_age_ms,
        "heartbeat_age": _duration_label(heartbeat_age_ms) if heartbeat_age_ms is not None else "—",
        "runtime_age_ms": runtime_age_ms,
        "runtime_age": _duration_label(runtime_age_ms) if runtime_age_ms is not None else "—",
        "stale_after_ms": stale_after_ms,
        "stale_after": _duration_label(stale_after_ms) if stale_after_ms else "—",
        "is_stale_candidate": is_stale_candidate,
        "can_cleanup": is_stale_candidate,
        "lease_expired": lease_expired,
        "worker_ready": worker_ready,
        "commands": {
            "execution_worker": command,
            "ops_supervisor": supervisor_command,
        },
    }

    if run.status in TERMINAL_STATUSES:
        state.update(
            {
                "status": run.status,
                "severity": _run_severity(run),
                "title": f"Запуск {_status_label(run.status).lower()}",
                "description": "Execution-состояние зафиксировано на момент завершения запуска.",
                "next_action": "",
            }
        )
        return state

    if dispatch is None:
        if agent_mode in {"full", "multi"}:
            state.update(
                {
                    "status": "dispatch_missing",
                    "severity": "warning",
                    "title": "Нет dispatch для активного запуска",
                    "description": "Run активен, но в очереди execution-plane нет связанной задачи для worker.",
                    "next_action": "Остановите этот run и запустите агент заново; если повторяется, проверьте создание AgentRunDispatch.",
                }
            )
            return state
        state.update(
            {
                "status": "inline",
                "severity": "info",
                "title": "Mini-агент выполняется inline",
                "description": "Для mini-агента отдельный execution-plane dispatch не создаётся.",
                "next_action": "Дождитесь завершения inline-команд.",
            }
        )
        return state

    if dispatch_status == AgentRunDispatch.STATUS_QUEUED:
        if not worker_ready:
            status = "worker_stale" if worker_stale and worker_status != "missing" else "worker_missing"
            state.update(
                {
                    "status": status,
                    "severity": "warning",
                    "title": "Execution worker не принимает запуск",
                    "description": (
                        f"Dispatch ждёт в очереди {_duration_label(queued_age_ms)}. "
                        f"Статус worker: {worker_status}{', heartbeat протух' if worker_stale else ''}."
                    ),
                    "next_action": f"Запустите worker: {command}",
                }
            )
            if is_stale_candidate:
                state["title"] = "Запуск завис в очереди"
                state["description"] = (
                    f"{state['description']} Runtime {state['runtime_age']} превысил stale threshold {state['stale_after']}."
                )
                state["next_action"] = "Очистите stale run или запустите execution worker, если запуск ещё должен выполняться."
            return state
        state.update(
            {
                "status": "queued",
                "severity": "info",
                "title": "Dispatch ждёт свободный worker",
                "description": f"Запуск находится в очереди {_duration_label(queued_age_ms)}; execution worker heartbeating.",
                "next_action": "Дождитесь claim события от worker.",
            }
        )
        return state

    if dispatch_status == AgentRunDispatch.STATUS_CLAIMED:
        if lease_expired:
            state.update(
                {
                    "status": "dispatch_lease_expired",
                    "severity": "warning",
                    "title": "Lease dispatch истёк",
                    "description": "Worker давно не продлевал lease; dispatch может быть перехвачен следующим worker.",
                    "next_action": f"Проверьте worker {dispatch.claimed_by or 'default'} или перезапустите execution-plane worker.",
                }
            )
            if is_stale_candidate:
                state["title"] = "Lease истёк, запуск stale"
                state["description"] = (
                    f"{state['description']} Runtime {state['runtime_age']} превысил stale threshold {state['stale_after']}."
                )
                state["next_action"] = "Очистите stale run или перезапустите execution-plane worker после проверки процесса."
            return state
        state.update(
            {
                "status": "claimed",
                "severity": "success" if worker_ready else "info",
                "title": "Worker выполняет запуск",
                "description": (
                    f"Dispatch забран worker {dispatch.claimed_by or 'default'}; "
                    f"последний heartbeat {state['heartbeat_age']} назад."
                ),
                "next_action": "Дождитесь событий выполнения агента.",
            }
        )
        return state

    if dispatch_status == AgentRunDispatch.STATUS_FAILED:
        state.update(
            {
                "status": "dispatch_failed",
                "severity": "critical",
                "title": "Dispatch завершился ошибкой",
                "description": _text(dispatch.error or "Worker сообщил ошибку выполнения.", limit=500),
                "next_action": "Проверьте событие agent_dispatch_failed и перезапустите агент после исправления причины.",
            }
        )
        return state

    if dispatch_status == AgentRunDispatch.STATUS_CANCELED:
        state.update(
            {
                "status": "dispatch_canceled",
                "severity": "warning",
                "title": "Dispatch отменён",
                "description": _text(dispatch.error or "Очередь запуска была отменена.", limit=500),
                "next_action": "При необходимости запустите агент заново.",
            }
        )
        return state

    state.update(
        {
            "status": dispatch_status or "unknown",
            "severity": "info",
            "title": "Execution state обновлён",
            "description": f"Dispatch status: {dispatch_status or 'unknown'}.",
            "next_action": "Следите за событиями запуска.",
        }
    )
    return state


def _serialize_run(run: AgentRun) -> dict[str, Any]:
    latest_dispatch = _latest_dispatch(run)
    return {
        "id": run.id,
        "agent_id": run.agent_id,
        "agent_name": _text(run.agent.name if run.agent_id and run.agent else "Agent", limit=200),
        "agent_type": run.agent.agent_type if run.agent_id and run.agent else "custom",
        "agent_mode": run.agent.mode if run.agent_id and run.agent else "mini",
        "server_name": _text(run.server.name if run.server_id and run.server else "—", limit=200),
        "server_id": run.server_id,
        "status": run.status,
        "duration_ms": int(run.duration_ms or 0),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "total_iterations": int(run.total_iterations or 0),
        "connected_servers": _json_safe(run.connected_servers or []),
        "pending_question": _text(run.pending_question),
        "dispatch": serialize_agent_dispatch(latest_dispatch),
    }


def _build_kpis(
    run: AgentRun,
    events: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    findings: list[dict[str, Any]] | None = None,
    risks: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    failed_logs = sum(1 for item in logs if int(item.get("exit_code") or 0) != 0)
    failed_steps = sum(1 for item in steps if item.get("status") in {"failed", "critical"})
    high_findings = sum(1 for item in (findings or []) if _severity_rank(item.get("severity")) >= _severity_rank("high"))
    high_risks = sum(1 for item in (risks or []) if _severity_rank(item.get("severity")) >= _severity_rank("warning"))
    problem_count = failed_logs + failed_steps + high_findings + high_risks
    servers = _server_names(run)
    return [
        {
            "id": "status",
            "label": "Статус",
            "value": _status_label(run.status),
            "hint": run.status,
            "severity": _run_severity(run),
        },
        {
            "id": "duration",
            "label": "Длительность",
            "value": _duration_label(run.duration_ms),
            "hint": "runtime",
            "severity": "info",
        },
        {
            "id": "scope",
            "label": "Серверы",
            "value": str(len(servers) or (1 if run.server_id else 0)),
            "hint": ", ".join(servers[:2]) if servers else "не указан",
            "severity": "info",
        },
        {
            "id": "signals",
            "label": "Сигналы",
            "value": str(len(events)),
            "hint": f"{problem_count} проблемных",
            "severity": "high" if problem_count else "success",
        },
    ]

__all__ = [name for name in globals() if not name.startswith("__")]
