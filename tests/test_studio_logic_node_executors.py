from __future__ import annotations

import pytest
from asgiref.sync import async_to_sync

from studio.pipeline.pipeline_executor import PipelineExecutor
from tests.studio_node_executor_harness import disable_activity_logging, make_run

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _disable_activity_logging(monkeypatch):
    disable_activity_logging(monkeypatch)


def test_parallel_node_dispatch_returns_gateway():
    run = make_run("parallel-node-user")
    executor = PipelineExecutor(run)

    result = async_to_sync(executor._execute_node)(
        {"id": "parallel", "type": "logic/parallel", "data": {}},
        {},
        {},
    )

    assert result == {"status": "completed", "output": "параллельное разветвление"}


def test_condition_node_evaluates_status_failed():
    run = make_run("condition-node-user")
    executor = PipelineExecutor(run)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "condition",
            "type": "logic/condition",
            "data": {"source_node_id": "prep", "check_type": "status_failed"},
        },
        {},
        {"prep": {"status": "failed", "output": "boom"}},
    )

    assert result["status"] == "completed"
    assert result["passed"] is True
    assert result["output"] == "True"


def test_condition_node_evaluates_contains_case_insensitive():
    run = make_run("condition-contains-user")
    executor = PipelineExecutor(run)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "condition",
            "type": "logic/condition",
            "data": {"source_node_id": "prep", "check_type": "contains", "check_value": "HEALTHY"},
        },
        {},
        {"prep": {"status": "completed", "output": "service is healthy"}},
    )

    assert result["status"] == "completed"
    assert result["passed"] is True
    assert result["output"] == "True"


def test_merge_node_returns_selected_mode():
    run = make_run("merge-node-user")
    executor = PipelineExecutor(run)

    result = async_to_sync(executor._execute_node)(
        {"id": "merge", "type": "logic/merge", "data": {"mode": "any"}},
        {},
        {},
    )

    assert result == {"status": "completed", "output": "объединение: любая ветка"}


def test_merge_node_coerces_invalid_mode_to_all():
    run = make_run("merge-invalid-mode-user")
    executor = PipelineExecutor(run)

    result = async_to_sync(executor._execute_node)(
        {"id": "merge", "type": "logic/merge", "data": {"mode": "invalid"}},
        {},
        {},
    )

    assert result == {"status": "completed", "output": "объединение: все ветки"}


def test_wait_node_completes_after_sleep_loop(monkeypatch):
    run = make_run("wait-node-user")
    executor = PipelineExecutor(run)
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr("studio.pipeline.pipeline_logic.asyncio.sleep", fake_sleep)

    result = async_to_sync(executor._execute_node)(
        {"id": "wait", "type": "logic/wait", "data": {"wait_minutes": 0.1}},
        {},
        {},
    )

    assert result["status"] == "completed"
    assert result["output"] == "⏱️ Ожидание завершено: 0.1 мин."
    assert len(sleep_calls) == 6


def test_wait_node_respects_executor_stop_event(monkeypatch):
    run = make_run("wait-stop-user")
    executor = PipelineExecutor(run)
    executor.request_stop()

    async def fake_sleep(seconds: float) -> None:
        raise AssertionError("wait should stop before sleeping")

    monkeypatch.setattr("studio.pipeline.pipeline_logic.asyncio.sleep", fake_sleep)

    result = async_to_sync(executor._execute_node)(
        {"id": "wait", "type": "logic/wait", "data": {"wait_minutes": 0.1}},
        {},
        {},
    )

    assert result == {"status": "stopped", "output": "Wait cancelled by stop request", "stopped": True}
