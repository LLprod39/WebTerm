from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from django.conf import settings
from django.utils import timezone

from app.agent_kernel.memory.redaction import sanitize_observation_text
from servers.agent_dispatch import serialize_agent_dispatch
from servers.agent_execution_state import AGENT_EXECUTION_COMMAND, AGENT_OPS_SUPERVISOR_COMMAND
from servers.agent_inputs import normalize_report_delivery
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


__all__ = [name for name in globals() if not name.startswith("__")]
