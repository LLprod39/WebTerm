from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from servers.multi_agent_run_state import (
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


UNATTENDED_ASK_USER_DENY = (
    "Human input unavailable in unattended pipeline/agent run. "
    "Use logic/human_approval or logic/telegram_input nodes, "
    "or set interaction_mode=interactive on the agent node."
)


@dataclass(frozen=True)
class PlanExecutionCallbacks:
    stop_requested: Callable[[], bool]
    wait_for_resume: Callable[[], Awaitable[None]]
    emit: Callable[[str, dict[str, Any]], Awaitable[None]]
    persist_plan_tasks: Callable[[list[dict[str, Any]]], Awaitable[None]]
    persist_plan_state: Callable[[list[dict[str, Any]], list[dict[str, Any]]], Awaitable[None]]
    set_waiting: Callable[[str, list[dict[str, Any]]], Awaitable[None]]
    clear_waiting: Callable[[], Awaitable[None]]
    run_task: Callable[[dict[str, Any], str, float], Awaitable[tuple[str, list[dict[str, Any]]]]]
    handle_failure: Callable[[dict[str, Any], str, list[dict[str, Any]], list[dict[str, Any]]], Awaitable[dict[str, Any]]]
    replan: Callable[[str, list[dict[str, Any]], list[dict[str, Any]]], Awaitable[list[dict[str, Any]]]]
    wait_for_user_reply: Callable[[], Awaitable[str]]
    # When True, orchestrator recovery action "ask_user" must not block on wait_for_user_reply.
    unattended: bool = False


async def execute_plan_tasks(
    *,
    goal: str,
    plan_tasks: list[dict[str, Any]],
    orchestrator_log: list[dict[str, Any]],
    deadline: float,
    callbacks: PlanExecutionCallbacks,
    skip_completed: bool,
) -> None:
    context_summary = ""

    while True:
        loop_break = False
        restart_with_new_plan = False
        for task in plan_tasks:
            if skip_completed and task.get("status") in ("done", "skipped"):
                continue
            if callbacks.stop_requested():
                mark_task_skipped(task, STOPPED_REASON)
                continue

            await callbacks.wait_for_resume()

            if time.monotonic() > deadline:
                mark_task_skipped(task, TIMEOUT_REASON)
                continue

            task_start_event = mark_task_running(task)
            await callbacks.persist_plan_tasks(plan_tasks)
            await callbacks.emit("agent_task_start", task_start_event)

            persist_after_iteration = True
            try:
                result, iterations = await callbacks.run_task(task, context_summary, deadline)
                task_done_event = mark_task_done(task, result, iterations)
                context_summary = append_task_result_context(context_summary, task, result)
                await callbacks.emit("agent_task_done", task_done_event)
            except Exception as exc:
                if callbacks.stop_requested():
                    mark_task_stopped(task)
                    await callbacks.persist_plan_state(plan_tasks, orchestrator_log)
                    loop_break = True
                    persist_after_iteration = False
                    break

                await callbacks.emit("agent_task_failed", mark_task_failed(task, str(exc)))

                decision = await callbacks.handle_failure(task, str(exc), plan_tasks, orchestrator_log)
                task["orchestrator_decision"] = decision

                if decision["action"] == "abort":
                    await callbacks.emit("agent_pipeline_phase", {"phase": "aborted", "message": decision.get("reason", "")})
                    loop_break = True
                    persist_after_iteration = False
                    break
                if decision["action"] == "replan":
                    new_tasks = await callbacks.replan(goal, plan_tasks, orchestrator_log)
                    plan_tasks[:] = build_replanned_tasks(plan_tasks, new_tasks)
                    await callbacks.persist_plan_state(plan_tasks, orchestrator_log)
                    await callbacks.emit("agent_plan", {"tasks": plan_tasks})
                    await callbacks.emit(
                        "agent_pipeline_phase",
                        {"phase": "executing", "message": "План пересобран. Продолжаю выполнение…"},
                    )
                    restart_with_new_plan = True
                    persist_after_iteration = False
                    break
                if decision["action"] == "ask_user":
                    if callbacks.unattended:
                        # Fail-fast: never block scheduled/webhook multi runs on human reply.
                        answer = UNATTENDED_ASK_USER_DENY
                        await callbacks.emit(
                            "agent_status",
                            {
                                "status": "running",
                                "outcome_note": "ask_user_denied_unattended",
                                "message": answer,
                            },
                        )
                        context_summary = append_user_answer_context(context_summary, task, answer)
                    else:
                        question = decision.get("message", "Что делать с ошибкой задачи?")
                        await callbacks.set_waiting(question, plan_tasks)
                        await callbacks.emit("agent_status", {"status": "waiting"})
                        answer = await callbacks.wait_for_user_reply()
                        await callbacks.clear_waiting()
                        context_summary = append_user_answer_context(context_summary, task, answer)
                elif decision["action"] == "retry":
                    retry_deadline = retry_deadline_for_error(exc, deadline)
                    try:
                        task["status"] = "running"
                        result, iterations = await callbacks.run_task(task, context_summary, retry_deadline)
                        task_done_event = mark_task_done(task, result, iterations)
                        context_summary = append_task_result_context(context_summary, task, result, retry=True)
                        await callbacks.emit("agent_task_done", task_done_event)
                    except Exception as exc2:
                        task["status"] = "failed"
                        task["error"] = f"Retry failed: {exc2}"

            if persist_after_iteration:
                await callbacks.persist_plan_state(plan_tasks, orchestrator_log)

        if loop_break:
            break
        if restart_with_new_plan:
            continue
        if not any(task.get("status") == "pending" for task in plan_tasks):
            break
