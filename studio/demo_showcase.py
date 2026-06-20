"""
Demo showcase pipelines for Agent Studio — safe, visually impressive, easy to run.

The individual showcase graph definitions live in focused modules:
- ``demo_showcase_incident`` for incident triage.
- ``demo_showcase_content`` for content generation.
- ``demo_showcase_detective`` for multi-angle product analysis.
"""

from __future__ import annotations

from .demo_showcase_content import (
    CONTENT_DEFAULT_TOPIC,
    CONTENT_PIPELINE_DESCRIPTION,
    CONTENT_PIPELINE_NAME,
    build_content_edges,
    build_content_nodes,
)
from .demo_showcase_detective import (
    DETECTIVE_DEFAULT_BRIEF,
    DETECTIVE_PIPELINE_DESCRIPTION,
    DETECTIVE_PIPELINE_NAME,
    build_detective_edges,
    build_detective_nodes,
)
from .demo_showcase_incident import (
    INCIDENT_DEMO_PAYLOAD,
    INCIDENT_PIPELINE_DESCRIPTION,
    INCIDENT_PIPELINE_NAME,
    build_incident_edges,
    build_incident_nodes,
)
from .models import CURRENT_PIPELINE_GRAPH_VERSION, Pipeline

LOCAL_WEBHOOK_TARGET = "http://127.0.0.1:9000/api/health/"
DEMO_SHOWCASE_TAGS = ["demo", "showcase", "safe", "llm", "studio"]

__all__ = [
    "CONTENT_DEFAULT_TOPIC",
    "CONTENT_PIPELINE_DESCRIPTION",
    "CONTENT_PIPELINE_NAME",
    "DEMO_SHOWCASE_TAGS",
    "DETECTIVE_DEFAULT_BRIEF",
    "DETECTIVE_PIPELINE_DESCRIPTION",
    "DETECTIVE_PIPELINE_NAME",
    "INCIDENT_DEMO_PAYLOAD",
    "INCIDENT_PIPELINE_DESCRIPTION",
    "INCIDENT_PIPELINE_NAME",
    "LOCAL_WEBHOOK_TARGET",
    "build_content_edges",
    "build_content_nodes",
    "build_detective_edges",
    "build_detective_nodes",
    "build_incident_edges",
    "build_incident_nodes",
    "ensure_all_demo_showcase_pipelines",
    "ensure_content_pipeline",
    "ensure_detective_pipeline",
    "ensure_incident_pipeline",
]


def _ensure_pipeline(
    user,
    *,
    name: str,
    description: str,
    icon: str,
    extra_tags: list[str],
    nodes: list[dict],
    edges: list[dict],
) -> Pipeline:
    pipeline, _ = Pipeline.objects.update_or_create(
        owner=user,
        name=name,
        defaults={
            "description": description,
            "icon": icon,
            "tags": list({*DEMO_SHOWCASE_TAGS, *extra_tags}),
            "nodes": nodes,
            "edges": edges,
            "graph_version": CURRENT_PIPELINE_GRAPH_VERSION,
            "is_shared": False,
        },
    )
    pipeline.sync_triggers_from_nodes()
    return pipeline


def ensure_incident_pipeline(user) -> Pipeline:
    return _ensure_pipeline(
        user,
        name=INCIDENT_PIPELINE_NAME,
        description=INCIDENT_PIPELINE_DESCRIPTION,
        icon="🚨",
        extra_tags=["incident", "triage", "ai"],
        nodes=build_incident_nodes(),
        edges=build_incident_edges(),
    )


def ensure_content_pipeline(user) -> Pipeline:
    return _ensure_pipeline(
        user,
        name=CONTENT_PIPELINE_NAME,
        description=CONTENT_PIPELINE_DESCRIPTION,
        icon="✍️",
        extra_tags=["content", "marketing", "ai"],
        nodes=build_content_nodes(),
        edges=build_content_edges(),
    )


def ensure_detective_pipeline(user) -> Pipeline:
    return _ensure_pipeline(
        user,
        name=DETECTIVE_PIPELINE_NAME,
        description=DETECTIVE_PIPELINE_DESCRIPTION,
        icon="🕵️",
        extra_tags=["analysis", "product", "ai"],
        nodes=build_detective_nodes(),
        edges=build_detective_edges(),
    )


def ensure_all_demo_showcase_pipelines(user) -> list[Pipeline]:
    return [
        ensure_incident_pipeline(user),
        ensure_content_pipeline(user),
        ensure_detective_pipeline(user),
    ]
