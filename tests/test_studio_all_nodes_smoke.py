from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from servers.models import Server
from studio.all_nodes_smoke import build_all_nodes_smoke_edges, ensure_all_nodes_smoke_pipeline
from studio.pipeline_validation import KNOWN_NODE_TYPES, validate_pipeline_definition

pytestmark = pytest.mark.django_db


def test_all_nodes_smoke_pipeline_contains_every_known_node_type_and_validates():
    owner = User.objects.create_user(
        username="all-nodes-smoke-owner",
        password="x",
        is_staff=True,
        is_superuser=True,
    )
    Server.objects.create(user=owner, name="smoke-a", host="10.0.0.10", username="root")
    Server.objects.create(user=owner, name="smoke-b", host="10.0.0.11", username="root")

    pipeline = ensure_all_nodes_smoke_pipeline(owner)

    node_types = {str(node.get("type") or "") for node in pipeline.nodes}
    assert node_types == KNOWN_NODE_TYPES

    errors = validate_pipeline_definition(
        nodes=pipeline.nodes,
        edges=build_all_nodes_smoke_edges(),
        owner=owner,
        graph_version=pipeline.graph_version,
    )
    assert errors == []

    trigger_types = set(pipeline.triggers.values_list("trigger_type", flat=True))
    assert trigger_types == {"manual", "webhook", "schedule"}
