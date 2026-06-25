from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from django.conf import settings
from django.utils import timezone

from app.agent_kernel.memory.redaction import sanitize_observation_text
from servers.agent_execution_state import AGENT_EXECUTION_COMMAND, AGENT_OPS_SUPERVISOR_COMMAND
from servers.agent_inputs import normalize_report_delivery
from servers.agent_dispatch import serialize_agent_dispatch
from servers.models import AgentRun, AgentRunArtifact, AgentRunDispatch, AgentRunEvent, BackgroundWorkerState
from servers.run_events import record_run_event, serialize_run_event

REPORT_SCHEMA_VERSION = 1
TEXT_PREVIEW_LIMIT = 4000
ARTIFACT_CONTENT_LIMIT = 120_000
MAX_EVENTS = 500
ARTIFACT_MANIFEST_KEY = "artifact-manifest"

SEVERITIES = {"success", "info", "warning", "high", "critical", "fatal"}
ACTIVE_STATUSES = {
    AgentRun.STATUS_PENDING,
    AgentRun.STATUS_RUNNING,
    AgentRun.STATUS_PAUSED,
    AgentRun.STATUS_WAITING,
    AgentRun.STATUS_PLAN_REVIEW,
}
TERMINAL_STATUSES = {
    AgentRun.STATUS_COMPLETED,
    AgentRun.STATUS_FAILED,
    AgentRun.STATUS_STOPPED,
}
DELIVERY_EVENT_TYPES = {
    "agent_report_delivered",
    "agent_report_delivery_sent",
    "agent_report_delivery_skipped",
    "agent_report_delivery_failed",
}


def _text(value: Any, *, limit: int = TEXT_PREVIEW_LIMIT) -> str:
    text = sanitize_observation_text(str(value or "")).text.strip()
    if len(text) > limit:
        return text[: max(0, limit - 1)].rstrip() + "…"
    return text


def _mask_identifier(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 4:
        return "***"
    return f"***{text[-4:]}"


def _json_safe(value: Any) -> Any:
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, list):
        return [_json_safe(item) for item in value[:100]]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in list(value.items())[:80]:
            safe_key = str(key)
            if safe_key.lower() in {"chat_id", "telegram_chat_id"}:
                result[safe_key] = _mask_identifier(item)
            else:
                result[safe_key] = _json_safe(item)
        return result
    return value


def _duration_label(ms: int | None) -> str:
    value = int(ms or 0)
    if value <= 0:
        return "—"
    if value < 1000:
        return f"{value}ms"
    seconds = value // 1000
    if seconds < 60:
        return f"{seconds}s"
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {rest}s"
    hours, rest_minutes = divmod(minutes, 60)
    return f"{hours}h {rest_minutes}m"


def _bytes_label(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _age_ms(value: datetime | None, *, now: datetime | None = None) -> int | None:
    if value is None:
        return None
    current = now or timezone.now()
    return max(0, int((current - value).total_seconds() * 1000))


def _age_label(value: datetime | None, *, now: datetime | None = None) -> str:
    ms = _age_ms(value, now=now)
    return _duration_label(ms) if ms is not None else "—"


def _serialize_worker_row(worker: BackgroundWorkerState | None, *, now: datetime | None = None) -> dict[str, Any]:
    if worker is None:
        return {
            "worker_kind": BackgroundWorkerState.KIND_AGENT_EXECUTION,
            "worker_key": "",
            "status": "missing",
            "is_stale": True,
            "hostname": "",
            "pid": None,
            "command": "",
            "heartbeat_at": None,
            "lease_expires_at": None,
            "last_started_at": None,
            "last_stopped_at": None,
            "last_cycle_started_at": None,
            "last_cycle_finished_at": None,
            "last_summary": {},
            "last_error": "",
        }
    current = now or timezone.now()
    lease_expires_at = worker.lease_expires_at
    is_stale = bool(
        worker.status == BackgroundWorkerState.STATUS_RUNNING
        and (lease_expires_at is None or lease_expires_at <= current)
    )
    return {
        "worker_kind": worker.worker_kind,
        "worker_key": worker.worker_key,
        "status": worker.status,
        "is_stale": is_stale,
        "hostname": _text(worker.hostname, limit=255),
        "pid": worker.pid,
        "command": _text(worker.command, limit=255),
        "heartbeat_at": worker.heartbeat_at.isoformat() if worker.heartbeat_at else None,
        "heartbeat_age_ms": _age_ms(worker.heartbeat_at, now=current),
        "lease_expires_at": lease_expires_at.isoformat() if lease_expires_at else None,
        "last_started_at": worker.last_started_at.isoformat() if worker.last_started_at else None,
        "last_stopped_at": worker.last_stopped_at.isoformat() if worker.last_stopped_at else None,
        "last_cycle_started_at": worker.last_cycle_started_at.isoformat() if worker.last_cycle_started_at else None,
        "last_cycle_finished_at": worker.last_cycle_finished_at.isoformat() if worker.last_cycle_finished_at else None,
        "last_summary": _json_safe(worker.last_summary or {}),
        "last_error": _text(worker.last_error, limit=1000),
    }


def _select_agent_execution_worker(dispatch: AgentRunDispatch | None, *, now: datetime | None = None) -> BackgroundWorkerState | None:
    current = now or timezone.now()
    workers = list(BackgroundWorkerState.objects.filter(worker_kind=BackgroundWorkerState.KIND_AGENT_EXECUTION))
    if not workers:
        return None
    claimed_by = str(getattr(dispatch, "claimed_by", "") or "").strip()
    if claimed_by:
        for worker in workers:
            if worker.worker_key == claimed_by:
                return worker

    def score(worker: BackgroundWorkerState) -> tuple[int, float]:
        stale = bool(
            worker.status == BackgroundWorkerState.STATUS_RUNNING
            and (worker.lease_expires_at is None or worker.lease_expires_at <= current)
        )
        ready = worker.status == BackgroundWorkerState.STATUS_RUNNING and not stale
        heartbeat = worker.heartbeat_at or worker.updated_at or worker.created_at
        return (1 if ready else 0, heartbeat.timestamp() if heartbeat else 0)

    return sorted(workers, key=score, reverse=True)[0]


def _severity(value: Any) -> str:
    normalized = str(value or "info").lower().strip()
    if normalized in SEVERITIES:
        return normalized
    if normalized in {"failed", "error", "danger"}:
        return "critical"
    if normalized in {"done", "completed", "ok"}:
        return "success"
    if normalized in {"running", "pending", "waiting"}:
        return "info"
    return "info"


def _severity_rank(value: Any) -> int:
    return {
        "success": 0,
        "info": 1,
        "warning": 2,
        "high": 3,
        "critical": 4,
        "fatal": 5,
    }.get(_severity(value), 1)


def _clean_inline_markdown(value: Any) -> str:
    text = _text(value, limit=1000)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def _run_severity(run: AgentRun) -> str:
    if run.status == AgentRun.STATUS_FAILED:
        return "critical"
    if run.status == AgentRun.STATUS_STOPPED:
        return "warning"
    if run.status == AgentRun.STATUS_COMPLETED:
        if any(int(cmd.get("exit_code") or 0) != 0 for cmd in (run.commands_output or [])):
            return "high"
        if any(str(task.get("status")) == "failed" for task in (run.plan_tasks or [])):
            return "high"
        return "success"
    return "info"


def _overall_severity(
    run: AgentRun,
    findings: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    steps: list[dict[str, Any]],
) -> str:
    severities = [_run_severity(run)]
    severities.extend(str(item.get("severity") or "info") for item in findings)
    severities.extend(str(item.get("severity") or "info") for item in risks)
    severities.extend(str(item.get("severity") or "info") for item in logs)
    severities.extend(str(item.get("severity") or "info") for item in steps)
    return max(severities, key=_severity_rank)


def _line_items_from_section(markdown: str, headings: tuple[str, ...], *, limit: int = 6) -> list[str]:
    if not markdown:
        return []
    heading_re = "|".join(re.escape(item) for item in headings)
    pattern = re.compile(rf"^##\s+(?:{heading_re})\s*$([\s\S]*?)(?=^##\s+|\Z)", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(markdown)
    if not match:
        return []
    items: list[str] = []
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if line.startswith(("-", "*")):
            line = line[1:].strip()
        elif re.match(r"^\d+\.\s+", line):
            line = re.sub(r"^\d+\.\s+", "", line).strip()
        else:
            continue
        if line:
            items.append(_clean_inline_markdown(line))
        if len(items) >= limit:
            break
    return items


def _summary_from_markdown(markdown: str, fallback: str) -> str:
    if not markdown:
        return fallback
    quote = next((line.strip()[1:].strip() for line in markdown.splitlines() if line.strip().startswith(">")), "")
    if quote:
        return _text(quote, limit=700)
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and not line.startswith("---"):
            return _text(line, limit=700)
    return fallback


def _server_names(run: AgentRun) -> list[str]:
    connected = run.connected_servers or []
    names = [_text(item.get("server_name"), limit=120) for item in connected if isinstance(item, dict) and item.get("server_name")]
    if names:
        return names
    if run.server_id and run.server:
        return [_text(run.server.name, limit=120)]
    return []


def _latest_dispatch(run: AgentRun) -> AgentRunDispatch | None:
    return run.dispatches.order_by("-queued_at", "-id").first()


def _agent_run_stale_seconds_setting() -> int:
    return max(int(getattr(settings, "AGENT_RUN_STALE_SECONDS", 0) or 0), 0)


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


def _status_label(status: str) -> str:
    return {
        "pending": "Ожидает",
        "running": "Выполняется",
        "paused": "Пауза",
        "waiting": "Ждет ответа",
        "plan_review": "Проверка плана",
        "completed": "Завершен",
        "failed": "Ошибка",
        "stopped": "Остановлен",
    }.get(str(status or ""), str(status or "unknown"))


def _event_severity(event_type: str, payload: dict[str, Any]) -> str:
    lowered = event_type.lower()
    if "failed" in lowered or "error" in lowered:
        return "critical"
    if "stopped" in lowered or "canceled" in lowered or "skipped" in lowered:
        return "warning"
    if "done" in lowered or "completed" in lowered or "sent" in lowered:
        return "success"
    return _severity(payload.get("severity") or payload.get("status"))


def _event_phase(event_type: str, payload: dict[str, Any]) -> str:
    phase = str(payload.get("phase") or "").strip()
    if phase:
        return phase[:40]
    if event_type in {"agent_run_created", "agent_dispatch_enqueued", "agent_manual_dispatch"}:
        return "queued"
    if event_type in {"agent_worker_claimed", "agent_background_started", "agent_plan_execution_started"}:
        return "starting"
    if event_type in {"agent_plan", "agent_plan_approved"}:
        return "planning"
    if event_type.startswith("agent_task_") or event_type in {"agent_action", "agent_observation", "agent_thought"}:
        return "executing"
    if event_type in {"agent_report", "agent_completed"}:
        return "synthesizing" if payload.get("interim") else "ready"
    if event_type in DELIVERY_EVENT_TYPES:
        return "delivery"
    if "failed" in event_type or "error" in event_type:
        return "failed"
    return "activity"


def _event_category(event_type: str) -> str:
    if "dispatch" in event_type or "worker" in event_type or "background" in event_type:
        return "system"
    if event_type.startswith("agent_task_"):
        return "task"
    if event_type in {"agent_action", "agent_observation", "agent_thought"}:
        return "agent"
    if event_type == "agent_report" or event_type in DELIVERY_EVENT_TYPES:
        return "report"
    if event_type.startswith("agent_control") or event_type in {"agent_user_reply", "agent_plan_approved"}:
        return "operator"
    return "agent"


def _event_title(event_type: str, payload: dict[str, Any], message: str) -> str:
    titles = {
        "agent_run_created": "Запуск создан",
        "agent_dispatch_enqueued": "Поставлен в очередь",
        "agent_manual_dispatch": "Запущен вручную",
        "agent_worker_claimed": "Worker забрал запуск",
        "agent_background_started": "Фоновый запуск начат",
        "agent_plan_execution_started": "Запуск плана начат",
        "agent_plan": "План подготовлен",
        "agent_plan_approved": "План подтверждён",
        "agent_task_start": "Задача началась",
        "agent_task_done": "Задача выполнена",
        "agent_task_failed": "Задача завершилась ошибкой",
        "agent_action": "Действие агента",
        "agent_observation": "Наблюдение агента",
        "agent_thought": "Рассуждение агента",
        "agent_pipeline_phase": "Этап пайплайна",
        "agent_report": "Формирование отчёта",
        "agent_completed": "Агент завершил запуск",
        "agent_control_stop_requested": "Остановка запрошена",
        "agent_report_delivered": "Отчёт доставлен",
        "agent_report_delivery_sent": "Отчёт доставлен",
        "agent_report_delivery_skipped": "Доставка отчёта пропущена",
        "agent_report_delivery_failed": "Доставка отчёта не удалась",
        "agent_background_failed": "Фоновый запуск упал",
    }
    if event_type == "agent_status":
        status = str(payload.get("status") or "").strip()
        return f"Статус: {_status_label(status)}" if status else "Статус обновлён"
    if event_type in {"agent_task_start", "agent_task_done", "agent_task_failed"}:
        name = str(payload.get("name") or payload.get("task_name") or "").strip()
        if name:
            return _text(name, limit=180)
    return titles.get(event_type, _clean_inline_markdown(message or event_type.replace("_", " "))) or event_type


def _event_summary(event_type: str, payload: dict[str, Any], message: str) -> str:
    if event_type == "agent_status":
        status = str(payload.get("status") or "").strip()
        iteration = payload.get("iteration")
        if iteration is not None:
            return f"{_status_label(status)} · итерация {iteration}"
        return _status_label(status) if status else message
    if event_type == "agent_pipeline_phase":
        return _text(payload.get("message") or payload.get("phase") or message, limit=500)
    if event_type == "agent_report":
        return "Генерируется черновик отчёта." if payload.get("interim") else "Финальный отчёт сформирован."
    if event_type in DELIVERY_EVENT_TYPES:
        channel = str(payload.get("channel") or "external").strip()
        channel_label = "Telegram" if channel == "telegram" else channel
        if event_type in {"agent_report_delivered", "agent_report_delivery_sent"}:
            return f"Отчёт отправлен в {channel_label}."
        if event_type == "agent_report_delivery_skipped":
            reason = str(payload.get("reason") or "").strip()
            if reason == "telegram_not_configured":
                return "Доставка в Telegram пропущена: не настроены bot token или chat id."
            return _text(payload.get("message") or f"Доставка в {channel_label} пропущена.", limit=500)
        status_code = payload.get("status_code")
        if status_code:
            return f"Доставка в {channel_label} завершилась ошибкой HTTP {status_code}."
        return _text(payload.get("error") or payload.get("message") or f"Доставка в {channel_label} завершилась ошибкой.", limit=500)
    if event_type in {"agent_action", "agent_observation", "agent_thought"}:
        return _text(message, limit=500)
    if event_type.startswith("agent_task_"):
        result = payload.get("result") or payload.get("error") or payload.get("description") or message
        return _text(result, limit=500)
    return _text(payload.get("message") or message, limit=500)


def _event_important(event_type: str, severity: str, payload: dict[str, Any]) -> bool:
    if _severity_rank(severity) >= _severity_rank("warning"):
        return True
    if event_type in {
        "agent_run_created",
        "agent_dispatch_enqueued",
        "agent_worker_claimed",
        "agent_background_started",
        "agent_manual_dispatch",
        "agent_pipeline_phase",
        "agent_plan",
        "agent_plan_approved",
        "agent_task_start",
        "agent_task_done",
        "agent_task_failed",
        "agent_report",
        "agent_completed",
        "agent_report_delivered",
        "agent_report_delivery_sent",
        "agent_report_delivery_skipped",
        "agent_report_delivery_failed",
        "agent_control_stop_requested",
        "agent_background_failed",
    }:
        return True
    if event_type == "agent_status":
        return str(payload.get("status") or "") in {"connecting", "planning", "running", "waiting", "failed", "completed"}
    return False


EVENT_PHASE_LABELS = {
    "queued": "Очередь",
    "starting": "Старт",
    "planning": "Планирование",
    "plan_review": "Подтверждение",
    "executing": "Выполнение",
    "waiting": "Ожидание",
    "synthesizing": "Отчёт",
    "delivery": "Доставка",
    "ready": "Готово",
    "failed": "Ошибка",
    "stopped": "Остановлен",
    "activity": "Активность",
}


def _event_bucket(events: list[dict[str, Any]], predicate) -> list[dict[str, Any]]:
    return [event for event in events if predicate(event)]


def _build_event_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    important = _event_bucket(events, lambda event: bool(event.get("important")))
    problems = _event_bucket(events, lambda event: _severity_rank(event.get("severity")) >= _severity_rank("warning"))
    debug = _event_bucket(events, lambda event: bool(event.get("payload")))
    categories: dict[str, int] = {}
    severities: dict[str, int] = {}
    for event in events:
        category = str(event.get("category") or "agent")
        severity = _severity(event.get("severity"))
        categories[category] = categories.get(category, 0) + 1
        severities[severity] = severities.get(severity, 0) + 1

    latest = events[-1] if events else None
    latest_important = important[-1] if important else latest
    return {
        "total": len(events),
        "important": len(important),
        "problems": len(problems),
        "debug": len(debug),
        "categories": categories,
        "severities": severities,
        "latest": latest,
        "latest_important": latest_important,
    }


def _build_event_groups(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for event in events:
        phase = str(event.get("phase") or "activity")
        current = groups[-1] if groups else None
        if not current or current.get("phase") != phase:
            current = {
                "phase": phase,
                "label": EVENT_PHASE_LABELS.get(phase, phase),
                "count": 0,
                "important": 0,
                "problems": 0,
                "first_at": event.get("created_at"),
                "last_at": event.get("created_at"),
                "events": [],
            }
            groups.append(current)
        current["count"] += 1
        current["last_at"] = event.get("created_at")
        if event.get("important"):
            current["important"] += 1
        if _severity_rank(event.get("severity")) >= _severity_rank("warning"):
            current["problems"] += 1
        current["events"].append(event)
    return groups


def _build_delivery_state(run: AgentRun, events: list[dict[str, Any]], report_state: dict[str, Any]) -> dict[str, Any]:
    delivery = normalize_report_delivery(run.agent.report_delivery if run.agent_id and run.agent else {})
    telegram = delivery.get("telegram") or {}
    enabled_channels = []
    if telegram.get("enabled"):
        enabled_channels.append("telegram")
    delivery_events = [event for event in events if event.get("event_type") in DELIVERY_EVENT_TYPES]
    latest = delivery_events[-1] if delivery_events else None
    target = _mask_identifier(telegram.get("chat_id"))
    base = {
        "enabled": bool(enabled_channels),
        "channels": enabled_channels,
        "channel": str((latest or {}).get("payload", {}).get("channel") or (enabled_channels[0] if enabled_channels else "")),
        "target": target,
        "status": "disabled",
        "severity": "info",
        "label": "Выключена",
        "title": "Внешняя доставка выключена",
        "description": "Отчёт доступен в UI и в downloadable artifacts.",
        "next_action": "",
        "updated_at": None,
        "event": latest,
    }

    if latest:
        event_type = str(latest.get("event_type") or "")
        payload = latest.get("payload") if isinstance(latest.get("payload"), dict) else {}
        base.update(
            {
                "channel": str(payload.get("channel") or base["channel"] or "external"),
                "target": _text(payload.get("chat_id") or payload.get("target") or base["target"], limit=120),
                "updated_at": latest.get("created_at"),
                "event": latest,
            }
        )
        if event_type in {"agent_report_delivered", "agent_report_delivery_sent"}:
            base.update(
                {
                    "enabled": True,
                    "status": "sent",
                    "severity": "success",
                    "label": "Доставлено",
                    "title": "Отчёт доставлен",
                    "description": latest.get("summary") or "Отчёт успешно отправлен во внешний канал.",
                    "next_action": "",
                }
            )
            return base
        if event_type == "agent_report_delivery_skipped":
            reason = str(payload.get("reason") or "")
            next_action = "Настройте Telegram bot token и chat id или выключите доставку для агента."
            if reason and reason != "telegram_not_configured":
                next_action = "Проверьте настройки доставки отчёта."
            base.update(
                {
                    "enabled": True,
                    "status": "skipped",
                    "severity": "warning",
                    "label": "Пропущено",
                    "title": "Доставка отчёта пропущена",
                    "description": latest.get("summary") or latest.get("message") or "Доставка отчёта была пропущена.",
                    "next_action": next_action,
                }
            )
            return base
        if event_type == "agent_report_delivery_failed":
            base.update(
                {
                    "enabled": True,
                    "status": "failed",
                    "severity": "critical",
                    "label": "Ошибка",
                    "title": "Доставка отчёта не удалась",
                    "description": latest.get("summary") or latest.get("message") or "Внешний канал вернул ошибку доставки.",
                    "next_action": "Проверьте настройки канала и повторите отправку отчёта после исправления причины.",
                }
            )
            return base

    if not enabled_channels:
        return base
    if not report_state.get("report_ready"):
        base.update(
            {
                "status": "waiting_report",
                "severity": "info",
                "label": "Ждёт отчёт",
                "title": "Доставка ждёт финальный отчёт",
                "description": "Внешняя доставка включена, но финальный отчёт ещё не сформирован.",
                "next_action": "Дождитесь завершения агента.",
            }
        )
        return base
    base.update(
        {
            "status": "pending",
            "severity": "warning",
            "label": "Ожидает",
            "title": "Доставка ещё не подтверждена",
            "description": "Финальный отчёт готов, но событие успешной доставки ещё не записано.",
            "next_action": "Проверьте worker и настройки доставки отчёта.",
        }
    )
    return base


def _build_events(run: AgentRun, event_rows: list[AgentRunEvent] | None = None) -> list[dict[str, Any]]:
    rows = event_rows
    if rows is None:
        rows = list(AgentRunEvent.objects.filter(run=run).order_by("created_at", "id")[:MAX_EVENTS])
    events = []
    for event in rows:
        payload = _json_safe(event.payload or {})
        message = _text(event.message or event.event_type, limit=1200)
        severity = _event_severity(event.event_type, payload if isinstance(payload, dict) else {})
        events.append(
            {
                **serialize_run_event(event),
                "message": message,
                "payload": payload,
                "severity": severity,
                "source": _text(str((payload or {}).get("source") or event.event_type).replace("_", " "), limit=80)
                if isinstance(payload, dict)
                else event.event_type,
                "title": _event_title(event.event_type, payload if isinstance(payload, dict) else {}, message),
                "summary": _event_summary(event.event_type, payload if isinstance(payload, dict) else {}, message),
                "phase": _event_phase(event.event_type, payload if isinstance(payload, dict) else {}),
                "category": _event_category(event.event_type),
                "important": _event_important(event.event_type, severity, payload if isinstance(payload, dict) else {}),
            }
        )
    if not events and run.started_at:
        message = "Agent run created."
        severity = "info"
        payload: dict[str, Any] = {}
        events.append(
            {
                "id": 0,
                "run_id": run.id,
                "event_type": "agent_run_created",
                "task_id": None,
                "message": message,
                "payload": payload,
                "created_at": run.started_at.isoformat(),
                "severity": severity,
                "source": "agent",
                "title": _event_title("agent_run_created", payload, message),
                "summary": _event_summary("agent_run_created", payload, message),
                "phase": _event_phase("agent_run_created", payload),
                "category": _event_category("agent_run_created"),
                "important": _event_important("agent_run_created", severity, payload),
            }
        )
    return events


def _build_logs(run: AgentRun) -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    for index, item in enumerate(run.commands_output or [], start=1):
        exit_code = int(item.get("exit_code") or 0)
        logs.append(
            {
                "id": f"cmd-{index}",
                "index": index,
                "kind": "command",
                "title": _text(item.get("cmd") or f"Command {index}", limit=500),
                "command": _text(item.get("cmd"), limit=2000),
                "stdout": _text(item.get("stdout")),
                "stderr": _text(item.get("stderr")),
                "exit_code": exit_code,
                "duration_ms": int(item.get("duration_ms") or 0),
                "status": "completed" if exit_code == 0 else "failed",
                "severity": "success" if exit_code == 0 else "critical",
                "timestamp": item.get("timestamp") or None,
            }
        )
    return logs


def _build_agent_steps(run: AgentRun) -> list[dict[str, Any]]:
    if run.plan_tasks:
        steps = []
        for index, task in enumerate(run.plan_tasks or [], start=1):
            status = str(task.get("status") or "pending")
            steps.append(
                {
                    "id": str(task.get("id") or f"task-{index}"),
                    "index": index,
                    "title": _text(task.get("name") or f"Task {index}", limit=200),
                    "description": _text(task.get("description"), limit=1200),
                    "command": _text(task.get("action") or ""),
                    "status": status,
                    "severity": "critical" if status == "failed" else "success" if status == "done" else "info",
                    "status_label": _status_label(status),
                    "duration_ms": _task_duration_ms(task),
                    "details": _text(task.get("result") or task.get("error") or task.get("thought"), limit=2000),
                    "error": _text(task.get("error"), limit=1200),
                    "started_at": task.get("started_at"),
                    "completed_at": task.get("completed_at"),
                }
            )
        return steps

    if run.iterations_log:
        steps = []
        for index, item in enumerate(run.iterations_log or [], start=1):
            action = item.get("action") or item.get("tool") or ""
            observation = item.get("observation") or ""
            steps.append(
                {
                    "id": f"iteration-{item.get('iteration') or index}",
                    "index": index,
                    "title": _text(action or f"Iteration {index}", limit=200),
                    "description": _text(item.get("thought"), limit=1200),
                    "command": _text(action, limit=1000),
                    "status": "completed",
                    "severity": "success",
                    "status_label": "Завершено",
                    "duration_ms": int(item.get("duration_ms") or 0),
                    "details": _text(observation, limit=2000),
                    "error": "",
                    "started_at": item.get("timestamp"),
                    "completed_at": item.get("timestamp"),
                }
            )
        return steps

    return [
        {
            "id": item["id"],
            "index": item["index"],
            "title": item["title"],
            "description": "",
            "command": item["command"],
            "status": item["status"],
            "severity": item["severity"],
            "status_label": "Завершено" if item["exit_code"] == 0 else f"Код {item['exit_code']}",
            "duration_ms": item["duration_ms"],
            "details": item["stderr"] or item["stdout"],
            "error": item["stderr"],
            "started_at": item["timestamp"],
            "completed_at": item["timestamp"],
        }
        for item in _build_logs(run)
    ]


def _task_duration_ms(task: dict[str, Any]) -> int:
    started = task.get("started_at")
    completed = task.get("completed_at")
    if not started or not completed:
        return 0
    try:
        start_dt = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(str(completed).replace("Z", "+00:00"))
        return max(0, int((end_dt - start_dt).total_seconds() * 1000))
    except ValueError:
        return 0


def _build_findings(run: AgentRun, markdown: str, logs: list[dict[str, Any]], steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for index, item in enumerate(_line_items_from_section(markdown, ("Ключевые находки", "Обнаружения", "Findings")), start=1):
        findings.append({"id": f"md-finding-{index}", "title": item, "description": "", "severity": "info", "source": "report"})
    for item in logs:
        if int(item.get("exit_code") or 0) != 0:
            findings.append(
                {
                    "id": f"log-{item['id']}",
                    "title": f"Команда завершилась с кодом {item['exit_code']}",
                    "description": item["title"],
                    "severity": "critical",
                    "source": "command",
                }
            )
    for step in steps:
        if step.get("status") == "failed":
            findings.append(
                {
                    "id": f"step-{step['id']}",
                    "title": f"Шаг не выполнен: {step['title']}",
                    "description": step.get("error") or step.get("details") or "",
                    "severity": "critical",
                    "source": "agent_step",
                }
            )
    return findings[:12]


def _build_risks(run: AgentRun, markdown: str, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    risks = [
        {"id": f"md-risk-{index}", "title": item, "description": "", "severity": "high"}
        for index, item in enumerate(_line_items_from_section(markdown, ("Проблемы и риски", "Риски", "Risks")), start=1)
    ]
    for finding in findings:
        if finding.get("severity") in {"critical", "fatal"}:
            risks.append(
                {
                    "id": f"risk-{finding['id']}",
                    "title": finding["title"],
                    "description": finding.get("description") or "Требуется проверка оператора.",
                    "severity": finding.get("severity") or "high",
                }
            )
    if run.status == AgentRun.STATUS_FAILED and not risks:
        risks.append(
            {
                "id": "run-failed",
                "title": "Запуск агента завершился ошибкой",
                "description": _text(run.ai_analysis or run.final_report, limit=1000),
                "severity": "critical",
            }
        )
    return risks[:10]


def _build_recommendations(run: AgentRun, markdown: str, risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = [
        {
            "id": f"md-action-{index}",
            "priority": "P1" if index == 1 else "P2",
            "title": item,
            "description": "",
            "owner": "Оператор",
            "done": False,
        }
        for index, item in enumerate(_line_items_from_section(markdown, ("Рекомендации", "Следующие шаги", "Recommendations")), start=1)
    ]
    if risks and not items:
        items.append(
            {
                "id": "review-risk",
                "priority": "P1",
                "title": "Проверить проблемные шаги и повторить сбор данных",
                "description": "Сформировано автоматически по failed-командам или failed-задачам.",
                "owner": "Оператор",
                "done": False,
            }
        )
    return items[:8]


def _report_markdown_ready(run: AgentRun, markdown: str) -> bool:
    if run.status not in TERMINAL_STATUSES or not str(markdown or "").strip():
        return False
    if str(run.final_report or "").strip():
        return True
    return run.status == AgentRun.STATUS_COMPLETED and bool(str(run.ai_analysis or "").strip())


def _latest_important_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.get("important"):
            return event
    return events[-1] if events else None


def _phase_from_run(run: AgentRun, events: list[dict[str, Any]], report_ready: bool) -> str:
    if report_ready:
        return "ready"
    if run.status == AgentRun.STATUS_FAILED:
        return "failed"
    if run.status == AgentRun.STATUS_STOPPED:
        return "stopped"
    if run.status == AgentRun.STATUS_WAITING:
        return "waiting"
    if run.status == AgentRun.STATUS_PLAN_REVIEW:
        return "plan_review"
    if run.status == AgentRun.STATUS_PENDING:
        return "queued"
    latest = _latest_important_event(events)
    phase = str((latest or {}).get("phase") or "").strip()
    if phase and phase != "activity":
        return phase
    if run.status == AgentRun.STATUS_RUNNING:
        return "executing"
    if run.status == AgentRun.STATUS_COMPLETED:
        return "synthesizing"
    return "activity"


def _phase_progress(phase: str) -> int:
    return {
        "queued": 8,
        "starting": 18,
        "planning": 35,
        "plan_review": 42,
        "executing": 62,
        "waiting": 55,
        "synthesizing": 86,
        "delivery": 94,
        "ready": 100,
        "failed": 100,
        "stopped": 100,
        "activity": 28,
    }.get(phase, 28)


def _problem_signal_count(
    events: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    steps: list[dict[str, Any]],
) -> int:
    event_count = sum(1 for event in events if _severity_rank(event.get("severity")) >= _severity_rank("warning"))
    log_count = sum(1 for item in logs if int(item.get("exit_code") or 0) != 0)
    step_count = sum(1 for item in steps if item.get("status") in {"failed", "critical"})
    return event_count + log_count + step_count


def _build_report_state(
    run: AgentRun,
    *,
    markdown: str,
    events: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    report_ready = _report_markdown_ready(run, markdown)
    phase = _phase_from_run(run, events, report_ready)
    latest = _latest_important_event(events)
    current_step = _text((latest or {}).get("title") or (latest or {}).get("message") or "", limit=240)
    problem_count = _problem_signal_count(events, logs, steps)
    execution_state = _build_execution_state(run)

    text_by_phase = {
        "queued": (
            "Запуск ожидает worker",
            "Backend создал run и поставил его в очередь. Финальный отчёт и артефакты появятся после выполнения агента.",
            "Worker заберёт запуск и начнёт сбор данных.",
        ),
        "starting": (
            "Worker поднимает выполнение",
            "Запуск уже принят в работу, идёт подготовка окружения и подключений.",
            "Агент перейдёт к планированию или сбору данных.",
        ),
        "planning": (
            "Агент готовит план",
            "Идёт построение плана проверки. Финальный отчёт ещё не сформирован.",
            "После плана начнётся выполнение задач.",
        ),
        "plan_review": (
            "План ждёт подтверждения",
            "Агент подготовил план и остановился до подтверждения оператора.",
            "Подтвердите план или остановите запуск.",
        ),
        "executing": (
            "Агент выполняет проверки",
            "Идёт сбор данных, выполнение команд и накопление доказательств для финального отчёта.",
            "После выполнения агент соберёт итоговый markdown-отчёт.",
        ),
        "waiting": (
            "Агент ждёт ответ",
            "Выполнение приостановлено, потому что агент запросил ввод оператора.",
            "Ответьте на вопрос агента, чтобы продолжить запуск.",
        ),
        "synthesizing": (
            "Агент собирает финальный отчёт",
            "Запуск дошёл до стадии подготовки результата. Артефакты появятся после сохранения markdown-отчёта.",
            "Дождитесь сохранения финального отчёта.",
        ),
        "delivery": (
            "Отчёт доставляется",
            "Финальный отчёт сформирован, выполняется доставка во внешние каналы.",
            "После доставки артефакты будут доступны в этом экране.",
        ),
        "ready": (
            "Финальный отчёт готов",
            "Структурированный отчёт сохранён. Можно смотреть вывод, события, логи и скачивать артефакты.",
            "Дополнительных действий не требуется.",
        ),
        "failed": (
            "Запуск завершился ошибкой",
            "Агент не дошёл до корректного финального отчёта. Доступны события, логи и сохранённые шаги для диагностики.",
            "Проверьте последние ошибки и перезапустите агент после исправления причины.",
        ),
        "stopped": (
            "Запуск остановлен",
            "Оператор остановил выполнение до формирования финального отчёта.",
            "При необходимости запустите агент повторно.",
        ),
    }
    headline, description, next_expected = text_by_phase.get(
        phase,
        (
            "Запуск активен",
            "Backend получает события агента. Финальный отчёт ещё не сформирован.",
            "Дождитесь следующего события агента.",
        ),
    )
    if not report_ready and problem_count:
        description = f"{description} Уже есть проблемные сигналы: {problem_count}."
    if not report_ready and _severity_rank(execution_state.get("severity")) >= _severity_rank("warning"):
        current_step = _text(execution_state.get("title") or current_step, limit=240)
        description = f"{description} {execution_state.get('description')}"
        next_expected = _text(execution_state.get("next_action") or next_expected, limit=500)
    return {
        "phase": phase,
        "report_ready": report_ready,
        "artifacts_ready": report_ready,
        "is_terminal": run.status in TERMINAL_STATUSES,
        "headline": headline,
        "description": description,
        "current_step": current_step,
        "next_expected": next_expected,
        "progress": _phase_progress(phase),
        "execution_state": execution_state,
    }


def _build_artifact_state(report_state: dict[str, Any]) -> dict[str, Any]:
    if report_state.get("artifacts_ready"):
        return {
            "ready": True,
            "title": "Артефакты отчёта готовы",
            "description": "Файлы собраны из финального отчёта и сохранённых данных запуска.",
            "empty_title": "",
            "empty_description": "",
        }
    return {
        "ready": False,
        "title": "Артефакты ещё не готовы",
        "description": "Артефакты появятся только после того, как агент сохранит финальный markdown-отчёт.",
        "empty_title": "Артефакты появятся после финального отчёта",
        "empty_description": report_state.get("next_expected") or "Дождитесь завершения агента.",
    }


def _build_artifact_state_for_artifacts(
    run: AgentRun,
    report_state: dict[str, Any],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    artifact_state = _build_artifact_state(report_state)
    total_size = sum(int(item.get("size_bytes") or 0) for item in artifacts)
    server_artifact_count = sum(1 for item in artifacts if item.get("download_kind") == "server")
    artifact_state.update(
        {
            "bundle_ready": bool(server_artifact_count),
            "bundle_download_url": _artifact_bundle_download_url(run.id) if server_artifact_count else "",
            "artifact_count": server_artifact_count or len(artifacts),
            "total_size_bytes": total_size,
            "total_size_label": _bytes_label(total_size),
            "manifest_ready": any(item.get("id") == ARTIFACT_MANIFEST_KEY for item in artifacts),
            "manifest_name": "artifact-manifest.json" if any(item.get("id") == ARTIFACT_MANIFEST_KEY for item in artifacts) else "",
        }
    )
    return artifact_state


def _artifact(id_: str, name: str, type_: str, description: str, content: str, created_at: str | None) -> dict[str, Any]:
    original_size = len(content.encode("utf-8", errors="replace"))
    safe_content = content
    truncated = False
    if len(safe_content) > ARTIFACT_CONTENT_LIMIT:
        safe_content = safe_content[: ARTIFACT_CONTENT_LIMIT - 1].rstrip() + "…"
        truncated = True
    encoded_size = len(safe_content.encode("utf-8", errors="replace"))
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "description": description,
        "size_bytes": encoded_size,
        "original_size_bytes": original_size,
        "size_label": _bytes_label(encoded_size),
        "created_at": created_at,
        "artifact_id": None,
        "download_kind": "inline",
        "download_url": "",
        "content_type": "application/json" if name.endswith(".json") else "text/markdown",
        "content": safe_content,
        "truncated": truncated,
        "checksum_sha256": _sha256_text(safe_content),
    }


def _build_artifact_manifest(run: AgentRun, artifacts: list[dict[str, Any]], created_at: str | None) -> dict[str, Any]:
    manifest_items = []
    total_size = 0
    for item in artifacts:
        if item.get("id") == ARTIFACT_MANIFEST_KEY:
            continue
        size_bytes = int(item.get("size_bytes") or 0)
        total_size += size_bytes
        manifest_items.append(
            {
                "key": str(item.get("id") or ""),
                "name": str(item.get("name") or ""),
                "type": str(item.get("type") or ""),
                "content_type": str(item.get("content_type") or ""),
                "size_bytes": size_bytes,
                "checksum_sha256": str(item.get("checksum_sha256") or _sha256_text(str(item.get("content") or ""))),
                "truncated": bool(item.get("truncated")),
            }
        )
    content = json.dumps(
        _json_safe(
            {
                "schema_version": REPORT_SCHEMA_VERSION,
                "kind": "agent_run_artifact_manifest",
                "run_id": run.id,
                "agent_id": run.agent_id,
                "agent_name": run.agent.name if run.agent_id and run.agent else "Agent",
                "status": run.status,
                "generated_at": timezone.now().isoformat(),
                "artifact_count": len(manifest_items),
                "total_size_bytes": total_size,
                "artifacts": manifest_items,
            }
        ),
        ensure_ascii=False,
        indent=2,
    )
    return _artifact(
        ARTIFACT_MANIFEST_KEY,
        "artifact-manifest.json",
        "JSON",
        "Integrity manifest with artifact sizes and SHA-256 checksums.",
        content,
        created_at,
    )


def _build_artifacts(
    run: AgentRun,
    *,
    markdown: str,
    events: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    created_at = run.completed_at.isoformat() if run.completed_at else run.started_at.isoformat() if run.started_at else None
    context = {
        "run": _serialize_run(run),
        "report": {key: value for key, value in report.items() if key not in {"markdown"}},
        "agent_steps": steps,
    }
    artifacts = [
        _artifact(
            "run-context",
            "run-context.json",
            "JSON",
            "Normalized run metadata and structured report context.",
            json.dumps(_json_safe(context), ensure_ascii=False, indent=2),
            created_at,
        ),
        _artifact(
            "commands-output",
            "commands-output.json",
            "JSON",
            "Command output captured during the run.",
            json.dumps(_json_safe(logs), ensure_ascii=False, indent=2),
            created_at,
        ),
        _artifact(
            "events",
            "events.json",
            "JSON",
            "Persistent agent events for this run.",
            json.dumps(_json_safe(events), ensure_ascii=False, indent=2),
            created_at,
        ),
    ]
    if markdown.strip():
        artifacts.insert(
            0,
            _artifact("final-report", "final-report.md", "Markdown", "Readable final report.", markdown, created_at),
        )
    artifacts.append(_build_artifact_manifest(run, artifacts, created_at))
    return artifacts


def _artifact_download_url(run_id: int, artifact_id: int) -> str:
    return f"/servers/api/agents/runs/{run_id}/artifacts/{artifact_id}/download/"


def _artifact_bundle_download_url(run_id: int) -> str:
    return f"/servers/api/agents/runs/{run_id}/artifacts/download-all/"


def _build_persisted_artifacts(run: AgentRun) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []

    def sort_key(artifact: AgentRunArtifact) -> tuple[int, str, int]:
        metadata = artifact.metadata if isinstance(artifact.metadata, dict) else {}
        try:
            position = int(metadata.get("position", 99))
        except (TypeError, ValueError):
            position = 99
        return position, artifact.name, artifact.id

    for artifact in sorted(AgentRunArtifact.objects.filter(run=run), key=sort_key):
        metadata = artifact.metadata if isinstance(artifact.metadata, dict) else {}
        artifacts.append(
            {
                "id": artifact.artifact_key,
                "name": artifact.name,
                "type": artifact.artifact_type,
                "description": artifact.description,
                "size_bytes": int(artifact.size_bytes or 0),
                "original_size_bytes": int(metadata.get("original_size_bytes") or artifact.size_bytes or 0),
                "size_label": _bytes_label(int(artifact.size_bytes or 0)),
                "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
                "artifact_id": artifact.id,
                "download_kind": "server",
                "download_url": _artifact_download_url(run.id, artifact.id),
                "content_type": artifact.content_type,
                "content": "",
                "truncated": bool(artifact.truncated),
                "checksum_sha256": _text(metadata.get("checksum_sha256") or "", limit=80),
                "metadata": _json_safe(metadata),
            }
        )
    return artifacts


def _artifact_owner_id(run: AgentRun) -> int | None:
    if run.user_id:
        return run.user_id
    if run.agent_id and run.agent:
        return run.agent.user_id
    return None


def _sync_agent_run_artifacts(run: AgentRun, artifacts: list[dict[str, Any]]) -> None:
    if not run.pk:
        return
    owner_id = _artifact_owner_id(run)
    synced_keys: set[str] = set()
    for position, item in enumerate(artifacts):
        artifact_key = _text(item.get("id") or item.get("name") or "artifact", limit=80) or "artifact"
        content = str(item.get("content") or "")
        size_bytes = len(content.encode("utf-8", errors="replace"))
        checksum_sha256 = str(item.get("checksum_sha256") or _sha256_text(content))
        synced_keys.add(artifact_key)
        AgentRunArtifact.objects.update_or_create(
            run=run,
            artifact_key=artifact_key,
            defaults={
                "user_id": owner_id,
                "name": _text(item.get("name") or f"{artifact_key}.txt", limit=255),
                "artifact_type": _text(item.get("type") or "Text", limit=40),
                "description": _text(item.get("description") or "", limit=1000),
                "content_type": _text(item.get("content_type") or "text/plain;charset=utf-8", limit=120),
                "content": content,
                "size_bytes": size_bytes,
                "truncated": bool(item.get("truncated")),
                "metadata": {
                    "schema_version": REPORT_SCHEMA_VERSION,
                    "source": "agent_run_report",
                    "position": position,
                    "checksum_sha256": checksum_sha256,
                    "original_size_bytes": int(item.get("original_size_bytes") or size_bytes),
                    "manifest": artifact_key == ARTIFACT_MANIFEST_KEY,
                },
            },
        )
    AgentRunArtifact.objects.filter(run=run).exclude(artifact_key__in=synced_keys).delete()


def build_agent_run_report_payload(
    run: AgentRun,
    *,
    event_rows: list[AgentRunEvent] | None = None,
    prefer_persisted_artifacts: bool = True,
) -> dict[str, Any]:
    markdown = _text(run.final_report or run.ai_analysis, limit=80_000)
    events = _build_events(run, event_rows)
    logs = _build_logs(run)
    steps = _build_agent_steps(run)
    findings = _build_findings(run, markdown, logs, steps)
    risks = _build_risks(run, markdown, findings)
    recommendations = _build_recommendations(run, markdown, risks)
    report_state = _build_report_state(run, markdown=markdown, events=events, logs=logs, steps=steps)
    fallback_summary = report_state["description"]
    summary = _summary_from_markdown(markdown, fallback_summary) if report_state["report_ready"] else fallback_summary
    servers = _server_names(run)
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "title": _text(run.agent.name if run.agent_id and run.agent else "Agent run", limit=200),
        "subtitle": summary,
        "status": run.status,
        "status_label": _status_label(run.status),
        "severity": _overall_severity(run, findings, risks, logs, steps),
        "summary": summary,
        "root_cause": None,
        "markdown": markdown if report_state["report_ready"] else "",
        "meta": {
            "server": ", ".join(servers) if servers else "—",
            "window": _time_window(run),
            "analysis_duration": _duration_label(run.duration_ms),
            "finished_at": run.completed_at.isoformat() if run.completed_at else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
        },
        "kpis": [],
        "findings": findings,
        "risks": risks,
        "recommendations": recommendations,
    }
    report["kpis"] = _build_kpis(run, events, logs, steps, findings, risks)
    artifacts: list[dict[str, Any]] = []
    if report_state["artifacts_ready"]:
        persisted_artifacts = _build_persisted_artifacts(run) if prefer_persisted_artifacts else []
        artifacts = persisted_artifacts or _build_artifacts(
            run,
            markdown=markdown,
            events=events,
            logs=logs,
            steps=steps,
            report=report,
        )
    artifact_state = _build_artifact_state_for_artifacts(run, report_state, artifacts)
    delivery_state = _build_delivery_state(run, events, report_state)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run": _serialize_run(run),
        "report": report,
        "report_state": report_state,
        "artifact_state": artifact_state,
        "delivery_state": delivery_state,
        "event_summary": _build_event_summary(events),
        "event_groups": _build_event_groups(events),
        "events": events,
        "logs": logs,
        "agent_steps": steps,
        "artifacts": artifacts,
        "generated_at": timezone.now().isoformat(),
    }


def _time_window(run: AgentRun) -> str:
    if run.started_at and run.completed_at:
        return f"{run.started_at.isoformat()} - {run.completed_at.isoformat()}"
    if run.started_at:
        return run.started_at.isoformat()
    return "—"


def _normalize_report_items(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items[:40], start=1):
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                **item,
                "id": str(item.get("id") or f"item-{index}"),
                "title": _clean_inline_markdown(item.get("title") or ""),
                "description": _clean_inline_markdown(item.get("description") or ""),
                "severity": _severity(item.get("severity")),
            }
        )
    return normalized


def _normalize_recommendations(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items[:20], start=1):
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                **item,
                "id": str(item.get("id") or f"recommendation-{index}"),
                "priority": str(item.get("priority") or ("P1" if index == 1 else "P2")),
                "title": _clean_inline_markdown(item.get("title") or ""),
                "description": _clean_inline_markdown(item.get("description") or ""),
                "owner": _text(item.get("owner") or "Оператор", limit=120),
                "done": bool(item.get("done") or False),
            }
        )
    return normalized


def normalize_agent_run_report_payload(run: AgentRun, payload: Any | None = None) -> dict[str, Any]:
    base = build_agent_run_report_payload(run)
    saved = payload if isinstance(payload, dict) else run.report_payload if isinstance(run.report_payload, dict) else {}
    if not saved:
        return base

    report = saved.get("report") if isinstance(saved.get("report"), dict) else {}
    merged_report = {**base["report"], **_json_safe(report)}
    merged = {
        **base,
        "run": base["run"],
        "report": merged_report,
        "events": base["events"],
        "logs": base["logs"],
        "agent_steps": base["agent_steps"],
        "event_summary": base["event_summary"],
        "event_groups": base["event_groups"],
        "delivery_state": base["delivery_state"],
    }
    merged["report"]["findings"] = _normalize_report_items(merged["report"].get("findings"))
    merged["report"]["risks"] = _normalize_report_items(merged["report"].get("risks"))
    merged["report"]["recommendations"] = _normalize_recommendations(merged["report"].get("recommendations"))
    merged["report"]["severity"] = _overall_severity(
        run,
        merged["report"]["findings"],
        merged["report"]["risks"],
        merged["logs"],
        merged["agent_steps"],
    )
    merged["report"]["kpis"] = _build_kpis(
        run,
        merged["events"],
        merged["logs"],
        merged["agent_steps"],
        merged["report"]["findings"],
        merged["report"]["risks"],
    )
    markdown = _text(merged["report"].get("markdown") or run.final_report or run.ai_analysis, limit=80_000)
    report_state = _build_report_state(
        run,
        markdown=markdown,
        events=merged["events"],
        logs=merged["logs"],
        steps=merged["agent_steps"],
    )
    if report_state["report_ready"]:
        merged["report"]["markdown"] = markdown
        if not merged["report"].get("summary"):
            merged["report"]["summary"] = _summary_from_markdown(markdown, report_state["description"])
        if not merged["report"].get("subtitle"):
            merged["report"]["subtitle"] = merged["report"]["summary"]
        merged["artifacts"] = _build_persisted_artifacts(run) or _build_artifacts(
            run,
            markdown=markdown,
            events=merged["events"],
            logs=merged["logs"],
            steps=merged["agent_steps"],
            report=merged["report"],
        )
    else:
        merged["report"]["markdown"] = ""
        merged["report"]["summary"] = report_state["description"]
        merged["report"]["subtitle"] = report_state["description"]
        merged["artifacts"] = []
    merged["report_state"] = report_state
    merged["artifact_state"] = _build_artifact_state_for_artifacts(run, report_state, merged["artifacts"])
    merged["delivery_state"] = _build_delivery_state(run, merged["events"], report_state)
    merged["event_summary"] = _build_event_summary(merged["events"])
    merged["event_groups"] = _build_event_groups(merged["events"])
    return merged


def build_agent_run_events_payload(run: AgentRun, *, event_rows: list[AgentRunEvent] | None = None) -> list[dict[str, Any]]:
    return _build_events(run, event_rows)


def refresh_agent_run_report_payload(run: AgentRun) -> dict[str, Any]:
    payload = build_agent_run_report_payload(run, prefer_persisted_artifacts=False)
    if payload.get("report_state", {}).get("artifacts_ready"):
        _sync_agent_run_artifacts(run, payload.get("artifacts") or [])
        payload["artifacts"] = _build_persisted_artifacts(run)
    else:
        AgentRunArtifact.objects.filter(run=run).delete()
        payload["artifacts"] = []
    payload["artifact_state"] = _build_artifact_state_for_artifacts(
        run,
        payload.get("report_state", {}),
        payload.get("artifacts") or [],
    )
    run.report_payload = payload
    run.save(update_fields=["report_payload"])
    return run.report_payload


def record_run_event_and_refresh_report(run: AgentRun, event_type: str, payload: dict[str, Any] | None = None) -> AgentRunEvent | None:
    event = record_run_event(run.id, event_type, payload or {})
    refresh_agent_run_report_payload(run)
    return event


def build_agent_run_report_response(run: AgentRun) -> dict[str, Any]:
    payload = normalize_agent_run_report_payload(run)
    return {"success": True, **payload}
