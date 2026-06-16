from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from studio.models import Pipeline, PipelineRun
from studio.trigger_dispatch import create_pipeline_run


def _manual_node() -> dict:
    return {
        "id": "manual",
        "type": "trigger/manual",
        "position": {"x": 0, "y": 0},
        "data": {"label": "Manual"},
    }


def _report_node(*, template: str = "ok") -> dict:
    return {
        "id": "report",
        "type": "output/report",
        "position": {"x": 200, "y": 0},
        "data": {"template": template},
    }


def _pipeline(owner: User, *, nodes: list[dict], edges: list[dict], graph_version: int = 2) -> Pipeline:
    pipeline = Pipeline.objects.create(
        name="Run creation preflight",
        owner=owner,
        graph_version=graph_version,
        nodes=nodes,
        edges=edges,
    )
    pipeline.sync_triggers_from_nodes()
    return pipeline


@pytest.mark.django_db
def test_create_pipeline_run_rejects_invalid_graph_before_db_write():
    owner = User.objects.create_user(username="run-create-invalid-graph", password="x")
    pipeline = _pipeline(
        owner,
        graph_version=1,
        nodes=[_manual_node(), _report_node()],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )

    with pytest.raises(ValueError, match="graph_version=1"):
        create_pipeline_run(pipeline=pipeline, entry_node_id="manual")

    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 0


@pytest.mark.django_db
def test_create_pipeline_run_rejects_trigger_without_downstream_node_before_db_write():
    owner = User.objects.create_user(username="run-create-empty-branch", password="x")
    pipeline = _pipeline(owner, nodes=[_manual_node()], edges=[])

    with pytest.raises(ValueError, match="no downstream executable nodes"):
        create_pipeline_run(pipeline=pipeline, entry_node_id="manual")

    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 0


@pytest.mark.django_db
def test_create_pipeline_run_rejects_missing_runtime_context_before_db_write():
    owner = User.objects.create_user(username="run-create-missing-context", password="x")
    pipeline = _pipeline(
        owner,
        nodes=[_manual_node(), _report_node(template="Ticket {ticket_id}")],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )

    with pytest.raises(ValueError, match="ticket_id"):
        create_pipeline_run(pipeline=pipeline, entry_node_id="manual", context={})

    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 0


@pytest.mark.django_db
def test_create_pipeline_run_rejects_missing_integrations_before_db_write(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    owner = User.objects.create_user(username="run-create-missing-integration", password="x")
    pipeline = _pipeline(
        owner,
        nodes=[
            _manual_node(),
            {
                "id": "llm",
                "type": "agent/llm_query",
                "position": {"x": 200, "y": 0},
                "data": {"provider": "gemini", "prompt": "Summarize"},
            },
        ],
        edges=[{"id": "e1", "source": "manual", "target": "llm", "sourceHandle": "out"}],
    )

    with pytest.raises(ValueError, match="LLM provider gemini"):
        create_pipeline_run(pipeline=pipeline, entry_node_id="manual", context={})

    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 0


@pytest.mark.django_db
def test_create_pipeline_run_checks_integrations_only_for_selected_branch(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    owner = User.objects.create_user(username="run-create-branch-integration", password="x")
    pipeline = _pipeline(
        owner,
        nodes=[
            _manual_node(),
            {"id": "webhook", "type": "trigger/webhook", "position": {"x": 0, "y": 120}, "data": {}},
            _report_node(),
            {
                "id": "webhook_llm",
                "type": "agent/llm_query",
                "position": {"x": 200, "y": 120},
                "data": {"provider": "gemini", "prompt": "Summarize"},
            },
        ],
        edges=[
            {"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"},
            {"id": "e2", "source": "webhook", "target": "webhook_llm", "sourceHandle": "out"},
        ],
    )

    run = create_pipeline_run(pipeline=pipeline, entry_node_id="manual", context={})

    assert run.entry_node_id == "manual"
    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 1

    with pytest.raises(ValueError, match="LLM provider gemini"):
        create_pipeline_run(pipeline=pipeline, entry_node_id="webhook", context={})

    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 1


@pytest.mark.django_db
def test_create_pipeline_run_accepts_valid_pipeline():
    owner = User.objects.create_user(username="run-create-valid", password="x")
    pipeline = _pipeline(
        owner,
        nodes=[_manual_node(), _report_node(template="Ticket {ticket_id}")],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )

    run = create_pipeline_run(
        pipeline=pipeline,
        entry_node_id="manual",
        context={"ticket_id": "INC-501"},
        trigger_data={"source": "unit"},
    )

    assert run.status == PipelineRun.STATUS_PENDING
    assert run.entry_node_id == "manual"
    assert run.context == {"ticket_id": "INC-501"}
    assert run.trigger_data == {"source": "unit"}
