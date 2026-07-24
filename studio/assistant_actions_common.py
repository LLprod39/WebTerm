"""Shared helpers for Studio assistant actions."""

from __future__ import annotations

from types import SimpleNamespace

from app.assistant_actions import AssistantActionContext, AssistantActionError
from studio.models import Pipeline, PipelineDraftSession, PipelineRun
from studio.views.pipeline_draft_helpers import get_draft_for_user
from studio.views.pipeline_helpers import _pipeline_queryset_for_user
from studio.views.run_views import _run_queryset_for_user


def _request_like(user):
    return SimpleNamespace(user=user)


def _int_payload(ctx: AssistantActionContext, key: str) -> int:
    value = ctx.input_payload.get(key)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AssistantActionError(f"{key} must be an integer") from exc
    if parsed <= 0:
        raise AssistantActionError(f"{key} must be positive")
    return parsed


def _pipeline_for_user(user, pipeline_id: int) -> Pipeline:
    pipeline = _pipeline_queryset_for_user(user).filter(pk=pipeline_id).first()
    if pipeline is None:
        raise AssistantActionError("Pipeline not found", status=404)
    return pipeline


def _draft_for_user(user, draft_id: int) -> PipelineDraftSession:
    draft = get_draft_for_user(user, draft_id)
    if draft is None:
        raise AssistantActionError("Draft not found", status=404)
    return draft


def _run_for_user(user, run_id: int) -> PipelineRun:
    run = _run_queryset_for_user(user).filter(pk=run_id).first()
    if run is None:
        raise AssistantActionError("Run not found", status=404)
    return run


def _target_url(path: str) -> str:
    return {"target_url": path}
