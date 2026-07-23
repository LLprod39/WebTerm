"""Unit tests for read-only multi-agent parallel scheduling helpers."""

from __future__ import annotations

import asyncio

import pytest

from servers.multi_agent_parallel import (
    can_run_parallel,
    select_next_execution_batch,
    task_is_read_only,
)
from servers.multi_agent_plan_executor import PlanExecutionCallbacks, execute_plan_tasks


def test_task_is_read_only_roles():
    assert task_is_read_only({"role": "infra_scout", "name": "Inventory", "description": "list services"})
    assert task_is_read_only({"role": "log_investigator", "name": "Logs", "description": "read journal"})
    assert not task_is_read_only({"role": "deploy_operator", "name": "Deploy", "description": "restart nginx"})
    assert not task_is_read_only({"role": "incident_commander", "name": "Fix", "description": "recover"})
    # No role → sequential by default
    assert not task_is_read_only({"name": "first", "description": "first", "status": "pending"})
    assert not task_is_read_only({"role": "custom", "description": "restart service"})


def test_select_parallel_batch_two_read_only_independent():
    plan = [
        {"id": 1, "name": "Scout A", "description": "inventory packages", "role": "infra_scout", "status": "pending"},
        {"id": 2, "name": "Logs B", "description": "read error logs", "role": "log_investigator", "status": "pending"},
        {"id": 3, "name": "Deploy", "description": "restart nginx", "role": "deploy_operator", "status": "pending"},
    ]
    batch = select_next_execution_batch(plan)
    assert len(batch) >= 2
    assert [t["id"] for t in batch] == [1, 2]
    assert can_run_parallel(batch)
    assert all(task_is_read_only(t) for t in batch)


def test_select_mutate_task_is_sequential_only():
    plan = [
        {"id": 1, "name": "Deploy", "description": "restart nginx", "role": "deploy_operator", "status": "pending"},
        {"id": 2, "name": "Scout", "description": "inventory", "role": "infra_scout", "status": "pending"},
    ]
    batch = select_next_execution_batch(plan)
    assert len(batch) == 1
    assert batch[0]["id"] == 1
    assert not can_run_parallel(batch)


def test_select_skips_done_and_stops_before_mutate():
    plan = [
        {"id": 1, "name": "Done scout", "role": "infra_scout", "status": "done", "description": "x"},
        {"id": 2, "name": "Logs", "role": "log_investigator", "status": "pending", "description": "logs"},
        {"id": 3, "name": "Security", "role": "security_patrol", "status": "pending", "description": "ports"},
        {"id": 4, "name": "Fix", "role": "deploy_operator", "status": "pending", "description": "restart"},
    ]
    batch = select_next_execution_batch(plan, skip_completed=True)
    assert [t["id"] for t in batch] == [2, 3]
    assert can_run_parallel(batch)


class _ParallelFake:
    def __init__(self):
        self.run_order: list[int] = []
        self.concurrent = 0
        self.max_concurrent = 0
        self.events: list[tuple[str, dict]] = []
        self.lock = asyncio.Lock()

    def callbacks(self) -> PlanExecutionCallbacks:
        return PlanExecutionCallbacks(
            stop_requested=lambda: False,
            wait_for_resume=self._noop,
            emit=self.emit,
            persist_plan_tasks=self._persist,
            persist_plan_state=self._persist_state,
            set_waiting=self._set_waiting,
            clear_waiting=self._noop,
            run_task=self.run_task,
            handle_failure=self._fail,
            replan=self._replan,
            wait_for_user_reply=self._reply,
            unattended=True,
        )

    async def _noop(self, *args, **kwargs):
        return None

    async def emit(self, event, payload):
        self.events.append((event, dict(payload)))

    async def _persist(self, plan_tasks):
        return None

    async def _persist_state(self, plan_tasks, log):
        return None

    async def _set_waiting(self, q, tasks):
        return None

    async def run_task(self, task, context_summary, deadline):
        async with self.lock:
            self.concurrent += 1
            self.max_concurrent = max(self.max_concurrent, self.concurrent)
            self.run_order.append(task["id"])
        await asyncio.sleep(0.05)
        async with self.lock:
            self.concurrent -= 1
        return f"ok-{task['id']}", [{"iteration": 1}]

    async def _fail(self, *a, **k):
        return {"action": "skip"}

    async def _replan(self, *a, **k):
        return []

    async def _reply(self):
        return "ok"


@pytest.mark.asyncio
async def test_execute_plan_runs_read_only_batch_concurrently():
    fake = _ParallelFake()
    plan_tasks = [
        {"id": 1, "name": "Scout", "description": "inventory", "role": "infra_scout", "status": "pending"},
        {"id": 2, "name": "Logs", "description": "logs", "role": "log_investigator", "status": "pending"},
        {"id": 3, "name": "Deploy", "description": "restart nginx", "role": "deploy_operator", "status": "pending"},
    ]
    await execute_plan_tasks(
        goal="goal",
        plan_tasks=plan_tasks,
        orchestrator_log=[],
        deadline=999999,
        callbacks=fake.callbacks(),
        skip_completed=True,
    )
    assert [t["status"] for t in plan_tasks] == ["done", "done", "done"]
    # First two read-only tasks overlapped.
    assert fake.max_concurrent >= 2
    assert set(fake.run_order[:2]) == {1, 2}
    assert 3 in fake.run_order
    assert any(event == "agent_pipeline_phase" and payload.get("parallel") is True for event, payload in fake.events)
