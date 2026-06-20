from __future__ import annotations

import time
from typing import Any

from django.utils import timezone

STOPPED_REASON = "Stopped by user"
TIMEOUT_REASON = "Session timeout"
SESSION_TIMEOUT_RETRY_SECONDS = 300


def mark_task_skipped(task: dict[str, Any], reason: str) -> None:
    task["status"] = "skipped"
    task["error"] = reason


def mark_task_running(task: dict[str, Any]) -> dict[str, Any]:
    task["status"] = "running"
    task["started_at"] = timezone.now().isoformat()
    return {
        "task_id": task["id"],
        "name": task["name"],
        "description": task["description"],
    }


def mark_task_done(task: dict[str, Any], result: str, iterations: list[dict[str, Any]]) -> dict[str, Any]:
    task["status"] = "done"
    task["result"] = result
    task["iterations"] = iterations
    task["completed_at"] = timezone.now().isoformat()
    return {"task_id": task["id"], "result": result[:500]}


def mark_task_failed(task: dict[str, Any], error: str) -> dict[str, Any]:
    task["status"] = "failed"
    task["error"] = error
    task["completed_at"] = timezone.now().isoformat()
    return {"task_id": task["id"], "error": error}


def mark_task_stopped(task: dict[str, Any]) -> None:
    mark_task_skipped(task, STOPPED_REASON)
    task["completed_at"] = timezone.now().isoformat()


def append_task_result_context(
    context_summary: str,
    task: dict[str, Any],
    result: str,
    *,
    retry: bool = False,
) -> str:
    retry_label = " (повтор)" if retry else ""
    return context_summary + f"\n\n### Задача {task['id']}: {task['name']}{retry_label}\nРезультат: {result[:1000]}"


def append_user_answer_context(context_summary: str, task: dict[str, Any], answer: str) -> str:
    task["result"] = f"Пользователь ответил: {answer}"
    return context_summary + f"\n\n### Ответ пользователя по задаче {task['id']}\n{answer}"


def build_replanned_tasks(plan_tasks: list[dict[str, Any]], new_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    done_tasks = [task for task in plan_tasks if task.get("status") == "done"]
    for index, task in enumerate(new_tasks, start=1):
        task["id"] = len(done_tasks) + index
    return done_tasks + new_tasks


def retry_deadline_for_error(error: Exception | str, current_deadline: float) -> float:
    error_text = str(error)
    if "Session timeout" in error_text or "session timeout" in error_text.lower():
        return time.monotonic() + SESSION_TIMEOUT_RETRY_SECONDS
    return current_deadline
