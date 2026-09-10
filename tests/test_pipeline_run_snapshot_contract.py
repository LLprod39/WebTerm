"""Run visualization uses the immutable graph, including after pipeline edits."""

from copy import deepcopy

import pytest
from django.contrib.auth.models import User
from django.test import Client

from studio.models import Pipeline, PipelineRun
from tests.servers_api_smoke_harness import grant_feature


@pytest.mark.django_db
@pytest.mark.parametrize("with_edge", [True, False])
def test_run_detail_returns_persisted_graph_snapshot_after_pipeline_changes(with_edge):
    owner = User.objects.create_user(username="run-snapshot-owner", password="x")
    grant_feature(owner, "studio_runs")
    nodes = [
        {"id": "start", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Original"}},
        {
            "id": "check",
            "type": "logic/condition",
            "position": {"x": 0, "y": 200},
            "data": {"check_type": "always_true"},
        },
    ]
    original_edges = (
        [{"id": "original-edge", "source": "start", "target": "check", "sourceHandle": "out"}] if with_edge else []
    )
    pipeline = Pipeline.objects.create(owner=owner, name="Snapshot contract", nodes=nodes, edges=original_edges)
    run = PipelineRun.objects.create(
        pipeline=pipeline,
        triggered_by=owner,
        status=PipelineRun.STATUS_COMPLETED,
        entry_node_id="start",
        nodes_snapshot=deepcopy(nodes),
        edges_snapshot=deepcopy(original_edges),
        node_states={"check": {"status": "completed", "output": "Condition true"}},
    )
    pipeline.nodes = [
        {"id": "replacement", "type": "trigger/manual", "position": {"x": 900, "y": 900}, "data": {"label": "Changed"}}
    ]
    pipeline.edges = [{"id": "different-edge", "source": "replacement", "target": "elsewhere", "sourceHandle": "true"}]
    pipeline.save(update_fields=["nodes", "edges"])

    client = Client()
    client.force_login(owner)
    response = client.get(f"/api/studio/runs/{run.pk}/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["nodes_snapshot"] == nodes
    assert payload["edges_snapshot"] == original_edges
    assert payload["node_states"] == {"check": {"status": "completed", "output": "Condition true"}}
    # No synthetic state is added for an entry node without persisted output.
    assert "start" not in payload["node_states"]
    run.refresh_from_db()
    assert run.edges_snapshot == original_edges
