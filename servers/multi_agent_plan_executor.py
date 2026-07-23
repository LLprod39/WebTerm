from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from servers.multi_agent_parallel import can_run_parallel, select_next_execution_batch
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
    handle_failure: Callable[
        [dict[str, Any], str, list[dict[str, Any]], list[dict[str, Any]]], Awaitable[dict[str, Any]]
    ]
    replan: Callable[[str, list[dict[str, Any]], list[dict[str, Any]]], Awaitable[list[dict[str, Any]]]]
    wait_for_user_reply: Callable[[], Awaitable[str]]
    # When True, orchestrator recovery action "ask_user" must not block on wait_for_user_reply.
    unattended: bool = False


async def _handle_task_failure(
    *,
    task: dict[str, Any],
    exc: Exception,
    goal: str,
    plan_tasks: list[dict[str, Any]],
    orchestrator_log: list[dict[str, Any]],
    deadline: float,
    context_summary: str,
    callbacks: PlanExecutionCallbacks,
) -> tuple[str, bool, bool, str]:
    """Handle a failed task. Returns (context_summary, loop_break, restart_plan, context_summary).

    Returns: (updated_context, loop_break, restart_with_new_plan)
    """
    if callbacks.stop_requested():
        mark_task_stopped(task)
        await callbacks.persist_plan_state(plan_tasks, orchestrator_log)
        return context_summary, True, False

    await callbacks.emit("agent_task_failed", mark_task_failed(task, str(exc)))

    decision = await callbacks.handle_failure(task, str(exc), plan_tasks, orchestrator_log)
    task["orchestrator_decision"] = decision

    if decision["action"] == "abort":
        await callbacks.emit("agent_pipeline_phase", {"phase": "aborted", "message": decision.get("reason", "")})
        return context_summary, True, False
    if decision["action"] == "replan":
        new_tasks = await callbacks.replan(goal, plan_tasks, orchestrator_log)
        plan_tasks[:] = build_replanned_tasks(plan_tasks, new_tasks)
        await callbacks.persist_plan_state(plan_tasks, orchestrator_log)
        await callbacks.emit("agent_plan", {"tasks": plan_tasks})
        await callbacks.emit(
            "agent_pipeline_phase",
            {"phase": "executing", "message": "План пересобран. Продолжаю выполнение…"},
        )
        return context_summary, False, True
    if decision["action"] == "ask_user":
        if callbacks.unattended:
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

    return context_summary, False, False


async def _execute_single_task(
    *,
    task: dict[str, Any],
    goal: str,
    plan_tasks: list[dict[str, Any]],
    orchestrator_log: list[dict[str, Any]],
    deadline: float,
    context_summary: str,
    callbacks: PlanExecutionCallbacks,
) -> tuple[str, bool, bool]:
    """Run one task sequentially. Returns (context, loop_break, restart_plan)."""
    if callbacks.stop_requested():
        mark_task_skipped(task, STOPPED_REASON)
        return context_summary, False, False

    await callbacks.wait_for_resume()

    if time.monotonic() > deadline:
        mark_task_skipped(task, TIMEOUT_REASON)
        return context_summary, False, False

    task_start_event = mark_task_running(task)
    await callbacks.persist_plan_tasks(plan_tasks)
    await callbacks.emit("agent_task_start", task_start_event)

    try:
        result, iterations = await callbacks.run_task(task, context_summary, deadline)
        task_done_event = mark_task_done(task, result, iterations)
        context_summary = append_task_result_context(context_summary, task, result)
        await callbacks.emit("agent_task_done", task_done_event)
        await callbacks.persist_plan_state(plan_tasks, orchestrator_log)
        return context_summary, False, False
    except Exception as exc:
        context_summary, loop_break, restart = await _handle_task_failure(
            task=task,
            exc=exc,
            goal=goal,
            plan_tasks=plan_tasks,
            orchestrator_log=orchestrator_log,
            deadline=deadline,
            context_summary=context_summary,
            callbacks=callbacks,
        )
        if not loop_break and not restart:
            await callbacks.persist_plan_state(plan_tasks, orchestrator_log)
        return context_summary, loop_break, restart


async def _execute_parallel_batch(
    *,
    batch: list[dict[str, Any]],
    goal: str,
    plan_tasks: list[dict[str, Any]],
    orchestrator_log: list[dict[str, Any]],
    deadline: float,
    context_summary: str,
    callbacks: PlanExecutionCallbacks,
) -> tuple[str, bool, bool]:
    """Run a read-only batch concurrently; merge handoffs in plan order."""
    if callbacks.stop_requested():
        for task in batch:
            mark_task_skipped(task, STOPPED_REASON)
        return context_summary, False, False

    await callbacks.wait_for_resume()

    if time.monotonic() > deadline:
        for task in batch:
            mark_task_skipped(task, TIMEOUT_REASON)
        return context_summary, False, False

    # Snapshot context before batch so each task sees the same prior handoffs.
    shared_context = context_summary
    for task in batch:
        start_event = mark_task_running(task)
        await callbacks.emit("agent_task_start", start_event)
    await callbacks.persist_plan_tasks(plan_tasks)
    await callbacks.emit(
        "agent_pipeline_phase",
        {
            "phase": "executing",
            "message": f"Параллельно (read-only): {len(batch)} задач",
            "parallel": True,
            "task_ids": [t.get("id") for t in batch],
        },
    )

    async def _run_one(task: dict[str, Any]) -> tuple[dict[str, Any], str, Any, Any]:
        try:
            result, iterations = await callbacks.run_task(task, shared_context, deadline)
            return task, "ok", result, iterations
        except Exception as exc:  # noqa: BLE001
            return task, "err", exc, None

    outcomes = await asyncio.gather(*[_run_one(task) for task in batch])

    # Merge results in original plan order for stable handoff context.
    order = {id(t): i for i, t in enumerate(batch)}
    outcomes_sorted = sorted(outcomes, key=lambda item: order.get(id(item[0]), 0))

    for task, kind, payload, iterations in outcomes_sorted:
        if kind == "ok":
            result = str(payload or "")
            task_done_event = mark_task_done(task, result, iterations or [])
            context_summary = append_task_result_context(context_summary, task, result)
            await callbacks.emit("agent_task_done", task_done_event)
            continue

        # Failure path — sequential recovery (may replan/abort).
        exc = payload if isinstance(payload, Exception) else RuntimeError(str(payload))
        context_summary, loop_break, restart = await _handle_task_failure(
            task=task,
            exc=exc,
            goal=goal,
            plan_tasks=plan_tasks,
            orchestrator_log=orchestrator_log,
            deadline=deadline,
            context_summary=context_summary,
            callbacks=callbacks,
        )
        if loop_break or restart:
            if not loop_break:
                await callbacks.persist_plan_state(plan_tasks, orchestrator_log)
            return context_summary, loop_break, restart

    await callbacks.persist_plan_state(plan_tasks, orchestrator_log)
    return context_summary, False, False


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

        # Batch-oriented loop: pick next frontier of pending work.
        # Read-only independent tasks may run concurrently; mutates stay sequential.
        progressed = False
        while True:
            batch = select_next_execution_batch(plan_tasks, skip_completed=skip_completed)
            if not batch:
                break

            progressed = True
            if can_run_parallel(batch):
                context_summary, loop_break, restart_with_new_plan = await _execute_parallel_batch(
                    batch=batch,
                    goal=goal,
                    plan_tasks=plan_tasks,
                    orchestrator_log=orchestrator_log,
                    deadline=deadline,
                    context_summary=context_summary,
                    callbacks=callbacks,
                )
            else:
                context_summary, loop_break, restart_with_new_plan = await _execute_single_task(
                    task=batch[0],
                    goal=goal,
                    plan_tasks=plan_tasks,
                    orchestrator_log=orchestrator_log,
                    deadline=deadline,
                    context_summary=context_summary,
                    callbacks=callbacks,
                )

            if loop_break or restart_with_new_plan:
                break

        if loop_break:
            break
        if restart_with_new_plan:
            continue
        if not progressed:
            break
        if not any(str(task.get("status") or "pending") == "pending" for task in plan_tasks):
            break
