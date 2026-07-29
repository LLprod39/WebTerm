"""Studio assistant actions: pipeline drafts, runs, skills and inspect APIs.

F-08a: handlers live in cohesive submodules
(``assistant_actions_common`` / ``_inspect`` / ``_drafts`` / ``_runs`` /
``_skills``). This module re-exports the public API used by
``assistant_action_registry`` and keeps ``build_assistant_runtime_context``.
"""

from __future__ import annotations

from typing import Any

from core_ui.access import feature_allowed_for_user
from studio.assistant_actions_drafts import (
    apply_pipeline_draft,
    create_pipeline_draft,
    revise_pipeline_draft,
    validate_pipeline_draft,
)
from studio.assistant_actions_inspect import (
    capability_registry,
    get_pipeline,
    get_studio_skill,
    list_mcp_servers,
    list_pipeline_drafts,
    list_pipelines,
    list_runs,
    list_studio_skills,
    validate_studio_skills,
)
from studio.assistant_actions_runs import run_pipeline, stop_pipeline_run, validate_pipeline_run
from studio.assistant_actions_skills import create_studio_skill, update_studio_skill
from studio.views.pipeline_helpers import _pipeline_queryset_for_user

__all__ = [
    "apply_pipeline_draft",
    "build_assistant_runtime_context",
    "capability_registry",
    "create_pipeline_draft",
    "create_studio_skill",
    "get_pipeline",
    "get_studio_skill",
    "list_mcp_servers",
    "list_pipeline_drafts",
    "list_pipelines",
    "list_runs",
    "list_studio_skills",
    "revise_pipeline_draft",
    "run_pipeline",
    "stop_pipeline_run",
    "update_studio_skill",
    "validate_pipeline_draft",
    "validate_pipeline_run",
    "validate_studio_skills",
]


def build_assistant_runtime_context(user) -> dict[str, Any]:
    context: dict[str, Any] = {"pipelines": []}
    if not feature_allowed_for_user(user, "studio_pipelines"):
        return context
    pipelines = list(_pipeline_queryset_for_user(user).order_by("-updated_at", "-id")[:25])
    context["pipelines"] = [
        {
            "id": pipeline.id,
            "name": pipeline.name,
            "description": (pipeline.description or "")[:400],
            "node_count": len(pipeline.nodes or []),
            "tag_count": len(pipeline.tags or []),
            "is_template": bool(pipeline.is_template),
        }
        for pipeline in pipelines
    ]
    return context
