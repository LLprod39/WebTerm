from __future__ import annotations

import servers.agents.multi_agent_run_state as run_state
from servers.agents.multi_agent_run_state import (
    SESSION_TIMEOUT_RETRY_SECONDS,
    STOPPED_REASON,
    TIMEOUT_REASON,
    append_task_result_context,
    append_user_answer_context,
    build_replanned_tasks,
    mark_task_done,
    mark_task_failed,
    mark_task_running,
    mark_task_skipped,
    mark_task_stopped,
    retry_deadline_for_error,
)


def test_task_lifecycle_markers_set_status_and_events():
    task = {"id": 5, "name": "Проверить nginx", "description": "status"}

    start_event = mark_task_running(task)
    assert task["status"] == "running"
    assert "T" in task["started_at"]
    assert start_event == {"task_id": 5, "name": "Проверить nginx", "description": "status"}

    done_event = mark_task_done(task, "x" * 600, [{"iteration": 1}])
    assert task["status"] == "done"
    assert task["result"] == "x" * 600
    assert task["iterations"] == [{"iteration": 1}]
    assert "T" in task["completed_at"]
    assert done_event == {"task_id": 5, "result": "x" * 500}


def test_task_error_and_skip_markers_preserve_legacy_reasons():
    task = {"id": 2}

    mark_task_skipped(task, TIMEOUT_REASON)
    assert task == {"id": 2, "status": "skipped", "error": "Session timeout"}

    failed_event = mark_task_failed(task, "boom")
    assert task["status"] == "failed"
    assert task["error"] == "boom"
    assert "T" in task["completed_at"]
    assert failed_event == {"task_id": 2, "error": "boom"}

    mark_task_stopped(task)
    assert task["status"] == "skipped"
    assert task["error"] == STOPPED_REASON
    assert "T" in task["completed_at"]


def test_context_summary_helpers_match_orchestrator_format():
    task = {"id": 3, "name": "Deploy", "role": "custom", "status": "done"}

    context = append_task_result_context("", task, "ok" * 600)
    context = append_task_result_context(context, task, "retry ok", retry=True)
    context = append_user_answer_context(context, task, "continue")

    # Structured handoff includes role/status and result excerpt (not only free text).
    assert "### Задача 3: Deploy" in context
    assert "status=done" in context
    assert "Результат:" in context
    assert "retry" in context
    assert "### Ответ пользователя по задаче 3\ncontinue" in context
    assert task["result"] == "Пользователь ответил: continue"
    assert isinstance(task.get("handoff"), dict)


def test_build_replanned_tasks_keeps_done_tasks_and_reassigns_ids():
    original = [
        {"id": 1, "status": "done", "name": "first"},
        {"id": 2, "status": "failed", "name": "failed"},
        {"id": 3, "status": "pending", "name": "old pending"},
    ]
    new_tasks = [{"name": "new a"}, {"id": 99, "name": "new b"}]

    replanned = build_replanned_tasks(original, new_tasks)

    assert replanned == [
        {"id": 1, "status": "done", "name": "first"},
        {"id": 2, "name": "new a"},
        {"id": 3, "name": "new b"},
    ]


def test_retry_deadline_extends_only_session_timeout(monkeypatch):
    monkeypatch.setattr(run_state.time, "monotonic", lambda: 100.0)

    assert retry_deadline_for_error("other", 20.0) == 20.0
    assert retry_deadline_for_error("Session timeout", 20.0) == 100.0 + SESSION_TIMEOUT_RETRY_SECONDS
    assert retry_deadline_for_error("session timeout happened", 20.0) == 100.0 + SESSION_TIMEOUT_RETRY_SECONDS
