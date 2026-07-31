from __future__ import annotations

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from studio.dispatch_models import PipelineRunDispatch
from studio.node_manifest import NODE_MANIFESTS
from studio.pipeline.pipeline_executor import PipelineExecutor
from studio.pipeline.pipeline_resume import (
    PipelineResumeConfirmationRequired,
    build_resume_checkpoint,
    request_pipeline_run_resume,
)
from tests.studio_pipeline_v2_harness import Pipeline, PipelineRun, build_run, report_node

pytestmark = pytest.mark.django_db(transaction=True)


def _pipeline(owner: User, *, final_type: str = "output/report") -> Pipeline:
    nodes = [
        {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {}},
        report_node("first", extra={"template": "first"}),
        {
            "id": "retry",
            "type": final_type,
            "position": {"x": 400, "y": 0},
            "data": {
                "label": "Retry target",
                "template": "retry",
                "url": "https://example.invalid/hook",
                "on_failure": "abort",
            },
        },
    ]
    return Pipeline.objects.create(
        owner=owner,
        name="Checkpoint resume",
        nodes=nodes,
        edges=[
            {"id": "e1", "source": "manual", "target": "first", "sourceHandle": "out"},
            {"id": "e2", "source": "first", "target": "retry", "sourceHandle": "success"},
        ],
    )


def _failed_run(pipeline: Pipeline, *, retry_status: str = "failed") -> PipelineRun:
    run = build_run(pipeline, entry_node_id="manual")
    run.status = PipelineRun.STATUS_FAILED
    run.error = "worker interrupted"
    run.node_states = {
        "first": {
            "status": "completed",
            "output": "durable first result",
            "routing_ports": ["success", "out"],
        },
        "retry": {"status": retry_status, "error": "connection lost"},
    }
    run.routing_state = {
        "entry_node_id": "manual",
        "activated_nodes": ["manual", "first", "retry"],
        "completed_nodes": ["manual", "first", "retry"],
        "queued_nodes": [],
        "pending_merges": {},
    }
    run.save(update_fields=["status", "error", "node_states", "routing_state"])
    return run


def test_resume_uses_completed_nodes_and_retries_only_failed_idempotent_node(monkeypatch) -> None:
    owner = User.objects.create_user(username="resume-idempotent", password="x")
    run = _failed_run(_pipeline(owner))
    checkpoint = build_resume_checkpoint(run)
    assert checkpoint.retry_node_ids == ["retry"]
    assert checkpoint.confirmation_nodes == []

    resumed = request_pipeline_run_resume(run.pk, actor=owner)
    dispatch = PipelineRunDispatch.objects.get(run=resumed)
    assert dispatch.status == PipelineRunDispatch.STATUS_QUEUED
    assert dispatch.metadata["resume"] is True

    executed: list[tuple[str, dict]] = []

    async def fake_execute_node(self, node, context, node_outputs):
        executed.append((str(node["id"]), dict(node_outputs)))
        return {"status": "completed", "output": "retried"}

    monkeypatch.setattr(PipelineExecutor, "_execute_node", fake_execute_node)
    result = async_to_sync(PipelineExecutor(resumed).execute)(context=resumed.context, resume=True)

    assert result.status == PipelineRun.STATUS_COMPLETED
    assert [node_id for node_id, _outputs in executed] == ["retry"]
    assert executed[0][1]["first"]["output"] == "durable first result"
    assert set(result.routing_state["completed_nodes"]) == {"manual", "first", "retry"}


def test_non_idempotent_retry_requires_explicit_operator_confirmation() -> None:
    owner = User.objects.create_user(username="resume-side-effect", password="x")
    run = _failed_run(_pipeline(owner, final_type="output/webhook"), retry_status="running")

    checkpoint = build_resume_checkpoint(run)
    assert checkpoint.confirmation_nodes == [
        {
            "id": "retry",
            "type": "output/webhook",
            "label": "Retry target",
            "idempotency": "non_idempotent",
        }
    ]
    with pytest.raises(PipelineResumeConfirmationRequired):
        request_pipeline_run_resume(run.pk, actor=owner)

    run.refresh_from_db()
    assert run.status == PipelineRun.STATUS_FAILED
    resumed = request_pipeline_run_resume(run.pk, actor=owner, confirm_non_idempotent=True)
    dispatch = PipelineRunDispatch.objects.get(run=resumed)
    assert dispatch.metadata["non_idempotent_confirmed"] is True
    assert dispatch.metadata["confirmed_node_ids"] == ["retry"]


def test_automatic_resume_pauses_before_ambiguous_non_idempotent_node(monkeypatch) -> None:
    owner = User.objects.create_user(username="resume-auto-gate", password="x")
    run = _failed_run(_pipeline(owner, final_type="output/webhook"), retry_status="running")

    async def must_not_execute(*_args, **_kwargs):
        raise AssertionError("non-idempotent node executed without confirmation")

    monkeypatch.setattr(PipelineExecutor, "_execute_node", must_not_execute)
    result = async_to_sync(PipelineExecutor(run).execute)(context=run.context, resume=True)

    assert result.status == PipelineRun.STATUS_FAILED
    assert result.trigger_data["resume_confirmation_required"][0]["id"] == "retry"


def test_all_builtin_node_manifests_publish_idempotency() -> None:
    assert {manifest.idempotency for manifest in NODE_MANIFESTS.values()} <= {
        "idempotent",
        "non_idempotent",
    }
    assert NODE_MANIFESTS["output/report"].idempotency == "idempotent"
    assert NODE_MANIFESTS["output/webhook"].idempotency == "non_idempotent"
    assert NODE_MANIFESTS["ops/service_action"].idempotency == "non_idempotent"
