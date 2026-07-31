from __future__ import annotations

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from studio.pipeline.pipeline_dead_letter import resolve_node_dead_letter
from studio.pipeline.pipeline_executor import PipelineExecutor
from studio.pipeline.pipeline_retry import node_retry_policy
from studio.retry_models import PipelineNodeDeadLetter
from tests.studio_pipeline_v2_harness import Pipeline, PipelineRun, build_run

pytestmark = pytest.mark.django_db(transaction=True)


def _pipeline(owner: User, *, node_type: str = "output/report", data: dict | None = None) -> Pipeline:
    return Pipeline.objects.create(
        owner=owner,
        name="Per-node retry",
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {}},
            {
                "id": "work",
                "type": node_type,
                "position": {"x": 200, "y": 0},
                "data": {"label": "Retry work", "template": "ok", **(data or {})},
            },
        ],
        edges=[{"id": "e1", "source": "manual", "target": "work", "sourceHandle": "out"}],
    )


def test_idempotent_node_retries_with_bounded_exponential_backoff(monkeypatch) -> None:
    owner = User.objects.create_user(username="retry-success", password="x")
    pipeline = _pipeline(
        owner,
        data={
            "retry_max_attempts": 3,
            "retry_initial_delay_seconds": 2,
            "retry_backoff_multiplier": 3,
            "retry_max_delay_seconds": 5,
            "on_failure": "abort",
        },
    )
    run = build_run(pipeline, entry_node_id="manual")
    attempts = 0
    delays: list[int] = []

    async def fake_execute_node(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return {"status": "failed", "error": f"transient-{attempts}"}
        return {"status": "completed", "output": "recovered"}

    async def fake_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(PipelineExecutor, "_execute_node", fake_execute_node)
    monkeypatch.setattr("studio.pipeline.pipeline_run_loop.asyncio.sleep", fake_sleep)
    result = async_to_sync(PipelineExecutor(run).execute)(context={})

    assert result.status == PipelineRun.STATUS_COMPLETED
    assert attempts == 3
    assert delays == [2, 5]
    assert result.node_states["work"]["attempt_count"] == 3
    assert len(result.node_states["work"]["retry_history"]) == 2
    assert not PipelineNodeDeadLetter.objects.filter(run=run).exists()


def test_exhausted_node_is_written_to_durable_dead_letter_queue(monkeypatch) -> None:
    owner = User.objects.create_user(username="retry-exhausted", password="x")
    pipeline = _pipeline(
        owner,
        data={
            "retry_max_attempts": 2,
            "retry_initial_delay_seconds": 0,
            "on_failure": "abort",
        },
    )
    run = build_run(pipeline, entry_node_id="manual")

    async def always_fail(*_args, **_kwargs):
        return {"status": "failed", "error": "upstream unavailable"}

    monkeypatch.setattr(PipelineExecutor, "_execute_node", always_fail)
    result = async_to_sync(PipelineExecutor(run).execute)(context={})

    assert result.status == PipelineRun.STATUS_FAILED
    item = PipelineNodeDeadLetter.objects.get(run=run, node_id="work")
    assert item.status == PipelineNodeDeadLetter.STATUS_OPEN
    assert item.attempt_count == 2
    assert item.max_attempts == 2
    assert item.last_error == "upstream unavailable"
    assert result.node_states["work"]["dead_letter_id"] == item.pk

    resolved = resolve_node_dead_letter(item.pk, actor=owner, note="Reviewed upstream outage")
    assert resolved.status == PipelineNodeDeadLetter.STATUS_RESOLVED
    assert resolved.resolved_by == owner


def test_non_idempotent_retry_is_fail_closed_without_explicit_policy(monkeypatch) -> None:
    owner = User.objects.create_user(username="retry-side-effect", password="x")
    pipeline = _pipeline(
        owner,
        node_type="output/webhook",
        data={"retry_max_attempts": 3, "retry_initial_delay_seconds": 0, "on_failure": "abort"},
    )
    run = build_run(pipeline, entry_node_id="manual")
    attempts = 0

    async def always_fail(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        return {"status": "failed", "error": "ambiguous delivery"}

    monkeypatch.setattr(PipelineExecutor, "_execute_node", always_fail)
    result = async_to_sync(PipelineExecutor(run).execute)(context={})

    assert attempts == 1
    assert result.node_states["work"]["max_attempts"] == 1
    assert "retry_non_idempotent=true" in result.node_states["work"]["retry_suppressed_reason"]
    assert PipelineNodeDeadLetter.objects.get(run=run, node_id="work").attempt_count == 1


def test_explicit_non_idempotent_retry_policy_is_honored() -> None:
    policy = node_retry_policy(
        {
            "id": "notify",
            "type": "output/webhook",
            "data": {"retry_max_attempts": 3, "retry_non_idempotent": True},
        }
    )
    assert policy.max_attempts == 3
    assert policy.non_idempotent_retry_enabled is True
