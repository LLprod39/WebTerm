from __future__ import annotations

from servers.multi_agent_task_iterations import (
    ITERATION_EVENT_OBSERVATION_LIMIT,
    ITERATION_OBSERVATION_LIMIT,
    append_observation_history,
    append_verification_blocked_history,
    build_iteration_thought_event,
    build_task_iteration_entry,
    merge_task_update_into_plan_tasks,
    record_final_answer_iteration,
    record_observed_iteration,
    record_verification_blocked_iteration,
)


class FakeHookManager:
    def __init__(self):
        self.calls: list[tuple[str, int]] = []

    def build_observation_message(self, observation: str, *, limit: int) -> str:
        self.calls.append((observation, limit))
        return f"wrapped:{observation[:limit]}"


def test_build_task_iteration_entry_and_thought_event():
    entry = build_task_iteration_entry(
        iteration=3,
        thought="Проверяю статус",
        action_name="ssh_execute",
        action_args={"server": "prod", "command": "systemctl status nginx"},
    )

    assert entry["iteration"] == 3
    assert entry["thought"] == "Проверяю статус"
    assert entry["action"] == "ssh_execute"
    assert entry["args"]["server"] == "prod"
    assert entry["observation"] == ""
    assert "T" in entry["timestamp"]
    assert build_iteration_thought_event(7, entry) == {
        "task_id": 7,
        "iteration": 3,
        "thought": "Проверяю статус",
        "action": "ssh_execute",
        "args": {"server": "prod", "command": "systemctl status nginx"},
    }


def test_record_observed_iteration_updates_task_and_truncates_event():
    task = {"id": 11}
    iterations = []
    entry = build_task_iteration_entry(iteration=1, thought="t", action_name="tool", action_args={})
    observation = "x" * (ITERATION_OBSERVATION_LIMIT + 100)

    event = record_observed_iteration(task=task, iterations=iterations, entry=entry, observation=observation)

    assert iterations == [entry]
    assert task["iterations"] == iterations
    assert entry["observation"] == observation[:ITERATION_OBSERVATION_LIMIT]
    assert event == {
        "task_id": 11,
        "iteration": 1,
        "observation": observation[:ITERATION_EVENT_OBSERVATION_LIMIT],
    }


def test_record_final_and_verification_blocked_iterations_update_verification_state():
    task = {"id": 9}
    iterations = []
    final_entry = build_task_iteration_entry(iteration=1, thought="done", action_name=None, action_args={})
    record_final_answer_iteration(
        task=task,
        iterations=iterations,
        entry=final_entry,
        verification_summary="verified",
    )

    assert iterations == [final_entry]
    assert final_entry["observation"] == "(final answer)"
    assert task["verification_summary"] == "verified"

    blocked_entry = build_task_iteration_entry(iteration=2, thought="done", action_name=None, action_args={})
    event = record_verification_blocked_iteration(
        task=task,
        iterations=iterations,
        entry=blocked_entry,
        verification_summary="needs verification",
    )

    assert iterations == [final_entry, blocked_entry]
    assert blocked_entry["observation"] == "needs verification"
    assert task["verification_summary"] == "needs verification"
    assert event["observation"] == "needs verification"


def test_append_observation_history_uses_hook_manager_limit():
    history = [{"role": "system", "content": "s"}]
    hook_manager = FakeHookManager()

    append_observation_history(
        history=history,
        llm_response="assistant response",
        observation="tool output",
        hook_manager=hook_manager,
    )

    assert history[-2:] == [
        {"role": "assistant", "content": "assistant response"},
        {"role": "user", "content": "wrapped:tool output"},
    ]
    assert hook_manager.calls == [("tool output", 4000)]


def test_append_verification_blocked_history_adds_required_instruction():
    history = []
    hook_manager = FakeHookManager()

    append_verification_blocked_history(
        history=history,
        llm_response="final without verification",
        verification_summary="Остались непроверенные изменения",
        hook_manager=hook_manager,
    )

    observation, limit = hook_manager.calls[0]
    assert limit == 4000
    assert "Остались непроверенные изменения" in observation
    assert "post-change verification" in observation
    assert history[0] == {"role": "assistant", "content": "final without verification"}


def test_merge_task_update_into_plan_tasks_updates_match_without_mutating_input():
    original = [
        {"id": 1, "name": "first", "status": "pending"},
        {"id": 2, "name": "second", "status": "pending"},
    ]
    task = {"id": 2, "status": "done", "iterations": [{"iteration": 1}]}

    merged = merge_task_update_into_plan_tasks(original, task)

    assert merged == [
        {"id": 1, "name": "first", "status": "pending"},
        {"id": 2, "name": "second", "status": "done", "iterations": [{"iteration": 1}]},
    ]
    assert original == [
        {"id": 1, "name": "first", "status": "pending"},
        {"id": 2, "name": "second", "status": "pending"},
    ]
