from __future__ import annotations

from copy import deepcopy

import pytest

from servers.agents.multi_agent_plan_executor import PlanExecutionCallbacks, execute_plan_tasks


class FakePlanCallbacks:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []
        self.persisted_tasks: list[list[dict]] = []
        self.persisted_state: list[tuple[list[dict], list[dict]]] = []
        self.run_calls: list[tuple[int, str, float]] = []
        self.waiting_questions: list[str] = []
        self.clear_waiting_calls = 0
        self.stop_requested_value = False
        self.failure_decisions: list[dict] = []
        self.replan_tasks: list[dict] = []
        self.user_answer = "continue"
        self.unattended = False
        self.wait_for_user_reply_calls = 0

    def callbacks(self) -> PlanExecutionCallbacks:
        return PlanExecutionCallbacks(
            stop_requested=lambda: self.stop_requested_value,
            wait_for_resume=self.wait_for_resume,
            emit=self.emit,
            persist_plan_tasks=self.persist_plan_tasks,
            persist_plan_state=self.persist_plan_state,
            set_waiting=self.set_waiting,
            clear_waiting=self.clear_waiting,
            run_task=self.run_task,
            handle_failure=self.handle_failure,
            replan=self.replan,
            wait_for_user_reply=self.wait_for_user_reply,
            unattended=self.unattended,
        )

    async def wait_for_resume(self):
        return None

    async def emit(self, event: str, payload: dict):
        self.events.append((event, dict(payload)))

    async def persist_plan_tasks(self, plan_tasks: list[dict]):
        self.persisted_tasks.append(deepcopy(plan_tasks))

    async def persist_plan_state(self, plan_tasks: list[dict], orchestrator_log: list[dict]):
        self.persisted_state.append((deepcopy(plan_tasks), deepcopy(orchestrator_log)))

    async def set_waiting(self, question: str, _plan_tasks: list[dict]):
        self.waiting_questions.append(question)

    async def clear_waiting(self):
        self.clear_waiting_calls += 1

    async def run_task(self, task: dict, context_summary: str, deadline: float):
        self.run_calls.append((task["id"], context_summary, deadline))
        if task.get("raise"):
            raise RuntimeError(task["raise"])
        return f"result-{task['id']}", [{"iteration": 1}]

    async def handle_failure(self, _task: dict, _error: str, _plan_tasks: list[dict], _orchestrator_log: list[dict]):
        return self.failure_decisions.pop(0)

    async def replan(self, _goal: str, _plan_tasks: list[dict], _orchestrator_log: list[dict]):
        return deepcopy(self.replan_tasks)

    async def wait_for_user_reply(self):
        self.wait_for_user_reply_calls += 1
        return self.user_answer


@pytest.mark.asyncio
async def test_execute_plan_tasks_runs_pending_tasks_and_carries_context():
    fake = FakePlanCallbacks()
    plan_tasks = [
        {"id": 1, "name": "first", "description": "first", "status": "pending"},
        {"id": 2, "name": "second", "description": "second", "status": "pending"},
    ]

    await execute_plan_tasks(
        goal="goal",
        plan_tasks=plan_tasks,
        orchestrator_log=[],
        deadline=999999,
        callbacks=fake.callbacks(),
        skip_completed=True,
    )

    assert [task["status"] for task in plan_tasks] == ["done", "done"]
    assert fake.run_calls[0][1] == ""
    assert "### Задача 1: first" in fake.run_calls[1][1]
    assert ("agent_task_start", {"task_id": 1, "name": "first", "description": "first"}) in fake.events
    assert ("agent_task_done", {"task_id": 2, "result": "result-2"}) in fake.events
    assert len(fake.persisted_state) == 2


@pytest.mark.asyncio
async def test_execute_plan_tasks_skips_done_and_skipped_tasks():
    fake = FakePlanCallbacks()
    plan_tasks = [
        {"id": 1, "name": "done", "description": "done", "status": "done"},
        {"id": 2, "name": "skipped", "description": "skipped", "status": "skipped"},
        {"id": 3, "name": "pending", "description": "pending", "status": "pending"},
    ]

    await execute_plan_tasks(
        goal="goal",
        plan_tasks=plan_tasks,
        orchestrator_log=[],
        deadline=999999,
        callbacks=fake.callbacks(),
        skip_completed=True,
    )

    assert [call[0] for call in fake.run_calls] == [3]
    assert plan_tasks[0]["status"] == "done"
    assert plan_tasks[1]["status"] == "skipped"
    assert plan_tasks[2]["status"] == "done"


@pytest.mark.asyncio
async def test_execute_plan_tasks_replan_does_not_rerun_done_tasks():
    fake = FakePlanCallbacks()
    fake.failure_decisions = [{"action": "replan"}]
    fake.replan_tasks = [{"name": "new", "description": "new", "status": "pending"}]
    plan_tasks = [
        {"id": 1, "name": "already done", "description": "done", "status": "done"},
        {"id": 2, "name": "fails", "description": "fails", "status": "pending", "raise": "boom"},
    ]

    await execute_plan_tasks(
        goal="goal",
        plan_tasks=plan_tasks,
        orchestrator_log=[],
        deadline=999999,
        callbacks=fake.callbacks(),
        skip_completed=True,
    )

    assert [call[0] for call in fake.run_calls] == [2, 2]
    assert [task["name"] for task in plan_tasks] == ["already done", "new"]
    assert [task["status"] for task in plan_tasks] == ["done", "done"]
    assert any(event == "agent_plan" for event, _payload in fake.events)


@pytest.mark.asyncio
async def test_execute_plan_tasks_ask_user_updates_waiting_state_and_context():
    fake = FakePlanCallbacks()
    fake.failure_decisions = [{"action": "ask_user", "message": "Continue?"}]
    fake.user_answer = "yes"
    plan_tasks = [
        {"id": 1, "name": "needs input", "description": "needs input", "status": "pending", "raise": "need input"},
        {"id": 2, "name": "after input", "description": "after input", "status": "pending"},
    ]

    await execute_plan_tasks(
        goal="goal",
        plan_tasks=plan_tasks,
        orchestrator_log=[],
        deadline=999999,
        callbacks=fake.callbacks(),
        skip_completed=True,
    )

    assert fake.waiting_questions == ["Continue?"]
    assert fake.clear_waiting_calls == 1
    assert fake.wait_for_user_reply_calls == 1
    assert "### Ответ пользователя по задаче 1\nyes" in fake.run_calls[-1][1]
    assert plan_tasks[0]["status"] == "failed"
    assert plan_tasks[0]["result"] == "Пользователь ответил: yes"


@pytest.mark.asyncio
async def test_execute_plan_tasks_unattended_ask_user_does_not_block():
    """Production path: orchestrator recovery ask_user must not await human reply when unattended."""
    from servers.agents.multi_agent_plan_executor import UNATTENDED_ASK_USER_DENY

    fake = FakePlanCallbacks()
    fake.unattended = True
    fake.failure_decisions = [{"action": "ask_user", "message": "Need human?"}]
    plan_tasks = [
        {"id": 1, "name": "fails", "description": "fails", "status": "pending", "raise": "boom"},
        {"id": 2, "name": "next", "description": "next", "status": "pending"},
    ]

    await execute_plan_tasks(
        goal="goal",
        plan_tasks=plan_tasks,
        orchestrator_log=[],
        deadline=999999,
        callbacks=fake.callbacks(),
        skip_completed=True,
    )

    assert fake.wait_for_user_reply_calls == 0
    assert fake.waiting_questions == []
    assert fake.clear_waiting_calls == 0
    # Second task still ran with deny message in context (fail-fast, no hang).
    assert [call[0] for call in fake.run_calls] == [1, 2]
    assert UNATTENDED_ASK_USER_DENY in fake.run_calls[-1][1]
    assert any(
        event == "agent_status" and payload.get("outcome_note") == "ask_user_denied_unattended"
        for event, payload in fake.events
    )
