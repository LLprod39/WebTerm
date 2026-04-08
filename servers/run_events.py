from __future__ import annotations

from asgiref.sync import sync_to_async
from django.db import IntegrityError

from app.agent_kernel.memory.redaction import sanitize_observation_text
from servers.models import AgentRunEvent

MAX_STRING_LENGTH = 1200
MAX_LIST_ITEMS = 20


def _compact_value(value):
    if isinstance(value, str):
        text = sanitize_observation_text(value).text.strip()
        return text[:MAX_STRING_LENGTH]
    if isinstance(value, list):
        return [_compact_value(item) for item in value[:MAX_LIST_ITEMS]]
    if isinstance(value, dict):
        return {str(key): _compact_value(item) for key, item in list(value.items())[:40]}
    return value


def _derive_message(event_type: str, payload: dict) -> str:
    if event_type == "agent_status":
        status = str(payload.get("status") or "").strip()
        return f"Status: {status}" if status else "Status updated"
    if event_type == "agent_pipeline_phase":
        return str(payload.get("message") or payload.get("phase") or "Pipeline phase updated")[:MAX_STRING_LENGTH]
    if event_type in {"agent_task_start", "agent_task_done", "agent_task_failed"}:
        name = str(payload.get("name") or payload.get("task_name") or "").strip()
        error = str(payload.get("error") or "").strip()
        result = str(payload.get("result") or "").strip()
        if event_type == "agent_task_failed" and error:
            return f"{name or 'Task'} failed: {error}"[:MAX_STRING_LENGTH]
        if event_type == "agent_task_done" and result:
            return f"{name or 'Task'} done: {result}"[:MAX_STRING_LENGTH]
        if name:
            return name[:MAX_STRING_LENGTH]
    if event_type in {"agent_subagent_start", "agent_subagent_done"}:
        title = str(payload.get("title") or payload.get("role") or "Subagent").strip()
        summary = str(payload.get("verification_summary") or "").strip()
        if summary:
            return f"{title}: {summary}"[:MAX_STRING_LENGTH]
        return title[:MAX_STRING_LENGTH]
    for key in ("question", "message", "text", "error", "output", "observation", "thought"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value[:MAX_STRING_LENGTH]
    return event_type.replace("_", " ").strip()


def record_run_event(run_id: int, event_type: str, payload: dict | None = None) -> AgentRunEvent | None:
    data = _compact_value(payload or {}) or {}
    task_id = data.get("task_id")
    try:
        task_id = int(task_id) if task_id is not None else None
    except (TypeError, ValueError):
        task_id = None
    message = sanitize_observation_text(_derive_message(str(event_type or ""), data)).text[:MAX_STRING_LENGTH]
    try:
        return AgentRunEvent.objects.create(
            run_id=run_id,
            event_type=str(event_type or "")[:80],
            task_id=task_id,
            message=message,
            payload=data,
        )
    except IntegrityError:
        return None


async def record_run_event_async(run_id: int, event_type: str, payload: dict | None = None) -> AgentRunEvent | None:
    return await sync_to_async(record_run_event, thread_sensitive=True)(run_id, event_type, payload)


def serialize_run_event(event: AgentRunEvent) -> dict:
    return {
        "id": event.id,
        "run_id": event.run_id,
        "event_type": event.event_type,
        "task_id": event.task_id,
        "message": event.message,
        "payload": event.payload or {},
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }
