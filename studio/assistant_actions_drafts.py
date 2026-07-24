"""Pipeline draft create / validate / apply / revise assistant actions."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from app.assistant_actions import AssistantActionContext, AssistantActionError
from studio.assistant_actions_common import _draft_for_user, _int_payload, _request_like
from studio.models import CURRENT_PIPELINE_GRAPH_VERSION, Pipeline, PipelineDraftSession
from studio.pipeline_validation import validate_pipeline_definition
from studio.services.pipeline_assistant_interview import (
    build_revision_interview_message,
    merge_revision_goal,
)
from studio.views.pipeline_assistant_views import _build_assistant_response_for_payload
from studio.views.pipeline_draft_helpers import (
    CLOSED_DRAFT_STATUSES,
    latest_revision_graph,
    revision_from_response,
    validate_latest_draft_revision,
)
from studio.views.pipeline_helpers import _pipeline_queryset_for_user


def create_pipeline_draft(ctx: AssistantActionContext) -> dict[str, Any]:
    title = str(ctx.input_payload.get("pipeline_name") or "").strip() or "AI Chat Pipeline"
    user_message = str(ctx.input_payload.get("user_message") or "").strip()
    if not user_message:
        raise AssistantActionError("user_message is required")

    data = {
        "pipeline_name": title,
        "nodes": ctx.input_payload.get("nodes") if isinstance(ctx.input_payload.get("nodes"), list) else [],
        "edges": ctx.input_payload.get("edges") if isinstance(ctx.input_payload.get("edges"), list) else [],
        "user_message": user_message,
        "intent": str(ctx.input_payload.get("intent") or "create"),
        "draft_mode": True,
    }
    compiler_mode = str(ctx.input_payload.get("compiler_mode") or "").strip()
    if compiler_mode:
        data["compiler_mode"] = compiler_mode

    response, meta, error = _build_assistant_response_for_payload(_request_like(ctx.user), data)
    if error is not None:
        try:
            message = error.content.decode("utf-8")
        except Exception:
            message = "Pipeline assistant failed"
        raise AssistantActionError(message, status=getattr(error, "status_code", 400))

    source_pipeline = meta["pipeline"]
    session = PipelineDraftSession.objects.create(
        owner=ctx.user,
        source_pipeline=source_pipeline,
        status=PipelineDraftSession.STATUS_DRAFTING,
        intent=meta["intent"],
        title=meta["pipeline_name"],
        user_goal=meta["user_message"],
        current_graph_snapshot={
            "pipeline_id": source_pipeline.id if source_pipeline else None,
            "pipeline_name": meta["pipeline_name"],
            "nodes": meta["nodes"],
            "edges": meta["edges"],
            "selected_node": meta["selected_node"],
        },
        selected_node_id=meta["selected_node_id"],
    )
    revision_from_response(
        session=session,
        user_message=meta["user_message"],
        response=response,
        preview_nodes=meta["preview_nodes"],
        preview_edges=meta["preview_edges"],
    )
    return {"draft": session.to_dict(include_latest=True), "target_url": f"/studio/drafts?draft={session.pk}"}


def validate_pipeline_draft(ctx: AssistantActionContext) -> dict[str, Any]:
    draft = _draft_for_user(ctx.user, _int_payload(ctx, "draft_id"))
    latest = draft.latest_revision()
    if latest is None:
        raise AssistantActionError("Draft has no revisions")
    result = validate_latest_draft_revision(draft, latest)
    return {"draft": draft.to_dict(include_latest=True), **result, "target_url": f"/studio/drafts?draft={draft.pk}"}


def apply_pipeline_draft(ctx: AssistantActionContext) -> dict[str, Any]:
    draft = _draft_for_user(ctx.user, _int_payload(ctx, "draft_id"))
    if draft.status == PipelineDraftSession.STATUS_DISCARDED:
        raise AssistantActionError("Draft is discarded")
    if draft.status == PipelineDraftSession.STATUS_APPLIED:
        raise AssistantActionError("Draft is already applied")
    latest = draft.latest_revision()
    if latest is None:
        raise AssistantActionError("Draft has no revisions")
    if latest.validation.get("ok") is False:
        raise AssistantActionError("Draft validation must pass before apply")
    if latest.risk.get("level") == "dangerous":
        raise AssistantActionError(
            "Draft contains dangerous actions. Revise it with approval or safer commands before apply."
        )

    create_new = ctx.input_payload.get("create_new") is not False or draft.source_pipeline_id is None
    title = str(ctx.input_payload.get("name") or draft.title or "AI Chat Pipeline").strip()
    description = str(ctx.input_payload.get("description") or draft.user_goal or latest.assistant_reply or "").strip()
    tags = ctx.input_payload.get("tags") if isinstance(ctx.input_payload.get("tags"), list) else ["ai-chat"]
    nodes = latest.preview_nodes or []
    edges = latest.preview_edges or []
    owner = draft.source_pipeline.owner if draft.source_pipeline_id and draft.source_pipeline else draft.owner
    errors = validate_pipeline_definition(
        nodes=nodes,
        edges=edges,
        owner=owner,
        graph_version=CURRENT_PIPELINE_GRAPH_VERSION,
    )
    if errors:
        raise AssistantActionError("Pipeline validation failed: " + "; ".join(errors), details={"errors": errors})

    if create_new:
        pipeline = Pipeline.objects.create(
            name=title,
            description=description,
            icon=str(ctx.input_payload.get("icon") or "W")[:8] or "W",
            tags=tags,
            nodes=nodes,
            edges=edges,
            graph_version=CURRENT_PIPELINE_GRAPH_VERSION,
            owner=draft.owner,
        )
    else:
        pipeline = _pipeline_queryset_for_user(ctx.user).filter(pk=draft.source_pipeline_id).first()
        if pipeline is None:
            raise AssistantActionError("Source pipeline not found", status=404)
        pipeline.name = title or pipeline.name
        pipeline.description = description
        pipeline.nodes = nodes
        pipeline.edges = edges
        pipeline.graph_version = CURRENT_PIPELINE_GRAPH_VERSION
        pipeline.save()

    pipeline.sync_triggers_from_nodes()
    draft.status = PipelineDraftSession.STATUS_APPLIED
    draft.applied_pipeline = pipeline
    draft.applied_at = timezone.now()
    draft.save(update_fields=["status", "applied_pipeline", "applied_at", "updated_at"])
    return {
        "draft": draft.to_dict(include_latest=True),
        "pipeline": pipeline.to_detail_dict(),
        "target_url": f"/studio/pipeline/{pipeline.pk}",
    }


def revise_pipeline_draft(ctx: AssistantActionContext) -> dict[str, Any]:
    """Continue configuring a draft with a natural-language instruction.

    Self-bootstrapping: when no draft_id is supplied the first revise call creates
    the draft from the instruction, so the model can start the pipeline flow with a
    single tool even if it skipped pipeline_draft.create.
    """
    raw_draft_id = ctx.input_payload.get("draft_id")
    if raw_draft_id in (None, "", 0, "0"):
        user_message = str(ctx.input_payload.get("user_message") or "").strip()
        if not user_message:
            raise AssistantActionError("user_message is required")
        return create_pipeline_draft(
            AssistantActionContext(
                user=ctx.user,
                input_payload={
                    "user_message": user_message,
                    "pipeline_name": ctx.input_payload.get("pipeline_name"),
                    "intent": "create",
                },
                request=ctx.request,
            )
        )
    draft = _draft_for_user(ctx.user, _int_payload(ctx, "draft_id"))
    if draft.status in CLOSED_DRAFT_STATUSES:
        raise AssistantActionError("Draft is already closed")
    raw_user_message = str(ctx.input_payload.get("user_message") or "").strip()
    if not raw_user_message:
        raise AssistantActionError("user_message is required")

    base_nodes, base_edges = latest_revision_graph(draft)
    latest = draft.latest_revision()
    previous_questions = latest.questions if latest and isinstance(latest.questions, list) else []
    assistant_user_message = build_revision_interview_message(
        original_goal=draft.user_goal,
        user_message=raw_user_message,
        previous_questions=previous_questions,
    )
    payload = {
        "pipeline_id": draft.source_pipeline_id,
        "pipeline_name": str(ctx.input_payload.get("pipeline_name") or draft.title or "Untitled pipeline"),
        "nodes": base_nodes,
        "edges": base_edges,
        "user_message": assistant_user_message,
        "intent": str(ctx.input_payload.get("intent") or draft.intent or "update"),
        "draft_mode": True,
        "history": [],
        "last_validation_errors": [],
        "last_run_summary": {},
    }
    if draft.selected_node_id:
        payload["selected_node"] = next(
            (
                node
                for node in payload["nodes"]
                if isinstance(node, dict) and str(node.get("id") or "") == draft.selected_node_id
            ),
            None,
        )

    response, meta, error = _build_assistant_response_for_payload(_request_like(ctx.user), payload)
    if error is not None:
        try:
            message = error.content.decode("utf-8")
        except Exception:
            message = "Pipeline draft revise failed"
        raise AssistantActionError(message, status=getattr(error, "status_code", 400))

    draft.title = meta["pipeline_name"]
    draft.user_goal = merge_revision_goal(
        original_goal=draft.user_goal,
        user_message=raw_user_message or meta["user_message"],
        previous_questions=previous_questions,
    )
    draft.intent = meta["intent"]
    draft.current_graph_snapshot = {
        "pipeline_id": draft.source_pipeline_id,
        "pipeline_name": meta["pipeline_name"],
        "nodes": meta["nodes"],
        "edges": meta["edges"],
        "selected_node": meta["selected_node"],
    }
    draft.selected_node_id = meta["selected_node_id"]
    draft.save(
        update_fields=["title", "user_goal", "intent", "current_graph_snapshot", "selected_node_id", "updated_at"]
    )
    revision_from_response(
        session=draft,
        user_message=raw_user_message or meta["user_message"],
        response=response,
        preview_nodes=meta["preview_nodes"],
        preview_edges=meta["preview_edges"],
    )
    return {
        "draft": draft.to_dict(include_latest=True),
        "assistant_reply": str(response.get("reply") or "")[:2000],
        "patch_summary": str(response.get("patch_summary") or "")[:1000],
        "target_url": f"/studio/drafts?draft={draft.pk}",
    }
