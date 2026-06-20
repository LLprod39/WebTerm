from __future__ import annotations

from typing import Any

from django.utils import timezone

OBSERVATION_HISTORY_LIMIT = 4000
ITERATION_OBSERVATION_LIMIT = 3000
ITERATION_EVENT_OBSERVATION_LIMIT = 500
VERIFICATION_BLOCKED_INSTRUCTION = (
    " Ты не можешь завершить задачу, пока не выполнишь обязательную post-change verification."
)


def build_task_iteration_entry(
    *,
    iteration: int,
    thought: str,
    action_name: str | None,
    action_args: dict[str, Any],
) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "thought": thought,
        "action": action_name,
        "args": action_args,
        "observation": "",
        "timestamp": timezone.now().isoformat(),
    }


def build_iteration_thought_event(task_id: int, entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "iteration": entry["iteration"],
        "thought": entry.get("thought"),
        "action": entry.get("action"),
        "args": entry.get("args"),
    }


def build_iteration_observation_event(task_id: int, entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "iteration": entry["iteration"],
        "observation": str(entry.get("observation") or "")[:ITERATION_EVENT_OBSERVATION_LIMIT],
    }


def record_observed_iteration(
    *,
    task: dict[str, Any],
    iterations: list[dict[str, Any]],
    entry: dict[str, Any],
    observation: str,
) -> dict[str, Any]:
    entry["observation"] = observation[:ITERATION_OBSERVATION_LIMIT]
    iterations.append(entry)
    task["iterations"] = iterations
    return build_iteration_observation_event(task["id"], entry)


def record_final_answer_iteration(
    *,
    task: dict[str, Any],
    iterations: list[dict[str, Any]],
    entry: dict[str, Any],
    verification_summary: str,
) -> None:
    entry["observation"] = "(final answer)"
    iterations.append(entry)
    task["verification_summary"] = verification_summary


def record_verification_blocked_iteration(
    *,
    task: dict[str, Any],
    iterations: list[dict[str, Any]],
    entry: dict[str, Any],
    verification_summary: str,
) -> dict[str, Any]:
    entry["observation"] = verification_summary
    iterations.append(entry)
    task["verification_summary"] = verification_summary
    return build_iteration_observation_event(task["id"], entry)


def append_observation_history(
    *,
    history: list[dict[str, str]],
    llm_response: str,
    observation: str,
    hook_manager: Any,
) -> None:
    history.append({"role": "assistant", "content": llm_response})
    history.append(
        {
            "role": "user",
            "content": hook_manager.build_observation_message(
                observation,
                limit=OBSERVATION_HISTORY_LIMIT,
            ),
        }
    )


def append_verification_blocked_history(
    *,
    history: list[dict[str, str]],
    llm_response: str,
    verification_summary: str,
    hook_manager: Any,
) -> None:
    append_observation_history(
        history=history,
        llm_response=llm_response,
        observation=verification_summary + VERIFICATION_BLOCKED_INSTRUCTION,
        hook_manager=hook_manager,
    )


def merge_task_update_into_plan_tasks(
    plan_tasks: list[dict[str, Any]],
    task: dict[str, Any],
) -> list[dict[str, Any]]:
    merged_tasks: list[dict[str, Any]] = []
    for item in plan_tasks:
        updated = dict(item)
        if updated.get("id") == task.get("id"):
            updated.update(task)
        merged_tasks.append(updated)
    return merged_tasks
