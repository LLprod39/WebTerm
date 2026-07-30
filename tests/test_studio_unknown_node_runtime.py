from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from studio.models import Pipeline, PipelineRun
from studio.pipeline.pipeline_executor import PipelineExecutor


def test_unknown_pipeline_node_type_fails_instead_of_skipping(db):
    owner = User.objects.create_user(username="unknown-node-owner", password="x")
    pipeline = Pipeline.objects.create(
        name="Unknown node flow",
        owner=owner,
        nodes=[{"id": "legacy", "type": "agent/does_not_exist", "position": {"x": 0, "y": 0}, "data": {}}],
        edges=[],
    )
    run = PipelineRun.objects.create(
        pipeline=pipeline,
        triggered_by=owner,
        status=PipelineRun.STATUS_PENDING,
        nodes_snapshot=list(pipeline.nodes),
        edges_snapshot=list(pipeline.edges),
        context={},
    )

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        pipeline.nodes[0],
        {},
        {},
    )

    assert result == {
        "status": "failed",
        "error": "Node type is not registered: agent/does_not_exist",
    }
