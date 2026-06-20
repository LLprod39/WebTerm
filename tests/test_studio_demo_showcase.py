from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from studio.demo_showcase import (
    CONTENT_PIPELINE_NAME,
    DETECTIVE_PIPELINE_NAME,
    INCIDENT_PIPELINE_NAME,
    build_content_edges,
    build_content_nodes,
    build_detective_edges,
    build_detective_nodes,
    build_incident_edges,
    build_incident_nodes,
    ensure_all_demo_showcase_pipelines,
)
from studio.models import CURRENT_PIPELINE_GRAPH_VERSION
from studio.pipeline_validation import validate_pipeline_definition

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("name", "build_nodes", "build_edges"),
    [
        (INCIDENT_PIPELINE_NAME, build_incident_nodes, build_incident_edges),
        (CONTENT_PIPELINE_NAME, build_content_nodes, build_content_edges),
        (DETECTIVE_PIPELINE_NAME, build_detective_nodes, build_detective_edges),
    ],
)
def test_demo_showcase_graphs_validate(name, build_nodes, build_edges):
    owner = User.objects.create_user(username=f"{name}-owner", password="x")

    errors = validate_pipeline_definition(
        nodes=build_nodes(),
        edges=build_edges(),
        owner=owner,
        graph_version=CURRENT_PIPELINE_GRAPH_VERSION,
    )

    assert errors == []


def test_ensure_all_demo_showcase_pipelines_creates_expected_pipelines():
    owner = User.objects.create_user(username="demo-showcase-owner", password="x")

    pipelines = ensure_all_demo_showcase_pipelines(owner)

    assert [pipeline.name for pipeline in pipelines] == [
        INCIDENT_PIPELINE_NAME,
        CONTENT_PIPELINE_NAME,
        DETECTIVE_PIPELINE_NAME,
    ]
    assert all(pipeline.graph_version == CURRENT_PIPELINE_GRAPH_VERSION for pipeline in pipelines)
    assert all(pipeline.triggers.exists() for pipeline in pipelines)
