from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from django.utils import timezone

from app.assistant_actions import AssistantActionContext, AssistantActionError, AssistantActionSpec, register_action
from studio.capability_registry import build_studio_capability_registry
from studio.models import CURRENT_PIPELINE_GRAPH_VERSION, Pipeline, PipelineDraftSession, PipelineRun, PipelineTrigger
from studio.pipeline_preflight import pipeline_integration_diagnostics
from studio.pipeline_runtime import get_executor_for_run, update_runtime_control
from studio.pipeline_runtime_context import validate_pipeline_entry_branch, validate_pipeline_runtime_context
from studio.pipeline_validation import ensure_json_object, validate_pipeline_definition
from studio.readiness_issues import runtime_limit_issue, validation_issues
from studio.skill_authoring import validate_skills
from studio.skill_registry import list_skills, normalise_skill_slugs
from studio.trigger_dispatch import get_pipeline_run_limit_error, pipeline_run_creation_error_details
from studio.views.mcp_views import _mcp_read_queryset_for_user, _mcp_to_dict
from studio.views.pipeline_assistant_preview import pipeline_assistant_risk
from studio.views.pipeline_assistant_views import _build_assistant_response_for_payload
from studio.views.pipeline_draft_helpers import (
    get_draft_for_user,
    revision_from_response,
    validate_latest_draft_revision,
)
from studio.views.pipeline_helpers import (
    _create_pipeline_run,
    _launch_pipeline_run,
    _pipeline_queryset_for_user,
    _resolve_manual_entry_trigger,
)
from studio.views.run_views import _run_queryset_for_user
from studio.views.skill_helpers import _can_read_skill, _skill_access_map, _skill_to_summary_dict


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


def list_pipelines(ctx: AssistantActionContext) -> dict[str, Any]:
    query = str(ctx.input_payload.get("q") or "").strip()
    qs = _pipeline_queryset_for_user(ctx.user)
    if query:
        qs = qs.filter(name__icontains=query)
    items = [pipeline.to_list_dict() for pipeline in qs[:25]]
    return {"pipelines": items, "count": len(items), "target_url": "/studio"}


def list_runs(ctx: AssistantActionContext) -> dict[str, Any]:
    runs = [_run.to_dict() for _run in _run_queryset_for_user(ctx.user)[:25]]
    return {"runs": runs, "count": len(runs), "target_url": "/studio/runs"}


def capability_registry(ctx: AssistantActionContext) -> dict[str, Any]:
    server_count = ctx.input_payload.get("server_count")
    try:
        parsed_server_count = int(server_count) if server_count not in (None, "") else None
    except (TypeError, ValueError) as exc:
        raise AssistantActionError("server_count must be an integer") from exc
    return {
        "capability_registry": build_studio_capability_registry(ctx.user, server_count=parsed_server_count),
        "target_url": "/studio",
    }


def list_mcp_servers(ctx: AssistantActionContext) -> dict[str, Any]:
    query = str(ctx.input_payload.get("q") or "").strip().lower()
    items = []
    for mcp in _mcp_read_queryset_for_user(ctx.user)[:50]:
        payload = _mcp_to_dict(mcp, ctx.user)
        blob = " ".join(str(payload.get(key) or "") for key in ("name", "description", "transport", "url", "command")).lower()
        if query and query not in blob:
            continue
        items.append(payload)
    return {"mcp_servers": items[:25], "count": len(items), "target_url": "/studio/mcp"}


def list_studio_skills(ctx: AssistantActionContext) -> dict[str, Any]:
    query = str(ctx.input_payload.get("q") or "").strip().lower()
    skills = list_skills()
    access_map = _skill_access_map([skill.slug for skill in skills])
    items = []
    for skill in skills:
        access = access_map.get(skill.slug.lower())
        if not _can_read_skill(ctx.user, access):
            continue
        payload = _skill_to_summary_dict(skill, ctx.user, access)
        blob = " ".join(
            str(payload.get(key) or "")
            for key in ("slug", "name", "description", "service", "category", "safety_level")
        ).lower()
        if query and query not in blob:
            continue
        items.append(payload)
    return {"skills": items[:50], "count": len(items), "target_url": "/studio/skills"}


def validate_studio_skills(ctx: AssistantActionContext) -> dict[str, Any]:
    raw_slugs = ctx.input_payload.get("slugs")
    if isinstance(raw_slugs, str):
        raw_slugs = [raw_slugs]
    slugs = normalise_skill_slugs(raw_slugs if isinstance(raw_slugs, list) else [])
    strict = bool(ctx.input_payload.get("strict"))
    if slugs:
        access_map = _skill_access_map(slugs)
        denied = [
            slug
            for slug in slugs
            if not _can_read_skill(ctx.user, access_map.get(slug.lower()))
        ]
        if denied:
            raise AssistantActionError(f"Skills not accessible: {', '.join(denied)}", status=403)
        results = validate_skills(slugs)
    else:
        skills = list_skills()
        access_map = _skill_access_map([skill.slug for skill in skills])
        visible_slugs = [
            skill.slug
            for skill in skills
            if _can_read_skill(ctx.user, access_map.get(skill.slug.lower()))
        ]
        results = validate_skills(visible_slugs) if visible_slugs else []
    error_count = sum(len(item.errors) for item in results)
    warning_count = sum(len(item.warnings) for item in results)
    return {
        "results": [item.to_dict() for item in results],
        "summary": {
            "skills": len(results),
            "errors": error_count,
            "warnings": warning_count,
            "is_valid": error_count == 0 and (warning_count == 0 if strict else True),
            "strict": strict,
        },
        "target_url": "/studio/skills",
    }


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
        raise AssistantActionError("Draft contains dangerous actions. Revise it with approval or safer commands before apply.")

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
    return {"draft": draft.to_dict(include_latest=True), "pipeline": pipeline.to_detail_dict(), "target_url": f"/studio/pipeline/{pipeline.pk}"}


def _pipeline_run_check(pipeline: Pipeline, *, context: dict[str, Any], entry_node_id: str, validate_only: bool) -> dict[str, Any]:
    validation_errors = validate_pipeline_definition(
        nodes=pipeline.nodes,
        edges=pipeline.edges,
        owner=pipeline.owner,
        graph_version=pipeline.graph_version,
        require_manual_trigger=True,
    )
    selected_trigger = None
    trigger_errors: list[str] = []
    if not validation_errors:
        selected_trigger, trigger_errors = _resolve_manual_entry_trigger(pipeline, entry_node_id)
    branch_errors = (
        validate_pipeline_entry_branch(pipeline.nodes, pipeline.edges, selected_trigger.node_id)
        if selected_trigger is not None
        else []
    )
    context_errors = (
        validate_pipeline_runtime_context(
            pipeline.nodes,
            context,
            edges=pipeline.edges,
            entry_node_id=selected_trigger.node_id,
        )
        if selected_trigger is not None and not branch_errors
        else []
    )
    integration = (
        pipeline_integration_diagnostics(pipeline, entry_node_id=selected_trigger.node_id)
        if selected_trigger is not None and not validation_errors
        else {"requirements": [], "issues": [], "errors": [], "warnings": []}
    )
    limit_error = get_pipeline_run_limit_error(pipeline.owner, cleanup_stale=not validate_only)
    limit_errors = [str(limit_error.get("error") or "Runtime limit reached.")] if limit_error else []
    limit_issues = [runtime_limit_issue(limit_error)] if limit_error else []
    all_errors = [*validation_errors, *trigger_errors, *branch_errors, *context_errors, *integration["errors"], *limit_errors]
    risk = pipeline_assistant_risk(pipeline.nodes, pipeline.edges)
    issues = [*validation_issues([*validation_errors, *trigger_errors, *branch_errors, *context_errors]), *integration["issues"], *limit_issues]
    validation = {"ok": not all_errors, "errors": all_errors, "issues": issues}
    return {
        "selected_trigger": selected_trigger,
        "validation": validation,
        "integration": integration,
        "risk": risk,
        "all_errors": all_errors,
    }


def validate_pipeline_run(ctx: AssistantActionContext) -> dict[str, Any]:
    pipeline = _pipeline_for_user(ctx.user, _int_payload(ctx, "pipeline_id"))
    raw_context, error = ensure_json_object(ctx.input_payload.get("context", {}), label="context")
    if error:
        raise AssistantActionError(error)
    entry_node_id = str(ctx.input_payload.get("entry_node_id") or "").strip()
    check = _pipeline_run_check(pipeline, context=raw_context, entry_node_id=entry_node_id, validate_only=True)
    dry_run = {
        "ok": check["validation"]["ok"] and check["risk"].get("level") != "dangerous",
        "executed": False,
        "mode": "validate_only",
        "checks": ["graph_contract", "manual_trigger", "references", "risk_review", "runtime_context", "integrations", "runtime_limits"],
        "message": "Dry-run validation completed without creating a pipeline run.",
    }
    selected_trigger = check["selected_trigger"]
    return {
        "ok": check["validation"]["ok"],
        "validation": check["validation"],
        "integration_requirements": check["integration"]["requirements"],
        "risk": check["risk"],
        "dry_run": dry_run,
        "entry_node_id": selected_trigger.node_id if selected_trigger else entry_node_id,
        "would_create_run": False,
        "target_url": f"/studio/pipeline/{pipeline.pk}",
    }


def run_pipeline(ctx: AssistantActionContext) -> dict[str, Any]:
    pipeline = _pipeline_for_user(ctx.user, _int_payload(ctx, "pipeline_id"))
    raw_context, error = ensure_json_object(ctx.input_payload.get("context", {}), label="context")
    if error:
        raise AssistantActionError(error)
    entry_node_id = str(ctx.input_payload.get("entry_node_id") or "").strip()
    check = _pipeline_run_check(pipeline, context=raw_context, entry_node_id=entry_node_id, validate_only=False)
    if check["all_errors"]:
        raise AssistantActionError("Pipeline is not runnable: " + "; ".join(check["all_errors"]), details={"validation": check["validation"]})
    selected_trigger = check["selected_trigger"]
    if selected_trigger is None:
        raise AssistantActionError("Pipeline has no runnable manual trigger")
    try:
        run = _create_pipeline_run(
            pipeline=pipeline,
            triggered_by=ctx.user,
            trigger=selected_trigger,
            context=raw_context,
            trigger_data={
                "source": "assistant_chat",
                "trigger_type": PipelineTrigger.TYPE_MANUAL,
                "entry_node_id": selected_trigger.node_id,
            },
            entry_node_id=selected_trigger.node_id,
        )
    except ValueError as exc:
        raise AssistantActionError(
            "Pipeline is not runnable: " + "; ".join(pipeline_run_creation_error_details(exc))
        ) from exc
    _launch_pipeline_run(run)
    return {"run": run.to_dict(), "target_url": f"/studio/runs?run={run.pk}"}


def stop_pipeline_run(ctx: AssistantActionContext) -> dict[str, Any]:
    run = _run_for_user(ctx.user, _int_payload(ctx, "run_id"))
    executor = get_executor_for_run(run.id)
    control, stop_delivered = update_runtime_control(run, live_executor=executor, stop_requested=True)
    if run.status in {PipelineRun.STATUS_PENDING, PipelineRun.STATUS_RUNNING}:
        run.status = PipelineRun.STATUS_STOPPED
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])
    return {"ok": True, "live_executor": stop_delivered, "runtime_control": control, "target_url": f"/studio/runs?run={run.pk}"}


def approve_pipeline_node(ctx: AssistantActionContext) -> dict[str, Any]:
    run = _run_for_user(ctx.user, _int_payload(ctx, "run_id"))
    node_id = str(ctx.input_payload.get("node_id") or "").strip()
    decision = str(ctx.input_payload.get("decision") or "approved").strip().lower()
    response_text = str(ctx.input_payload.get("response_text") or "").strip()
    if not node_id:
        raise AssistantActionError("node_id is required")
    if decision not in {"approved", "rejected"}:
        raise AssistantActionError("decision must be approved or rejected")
    state = dict((run.node_states or {}).get(node_id) or {})
    if not state:
        raise AssistantActionError(f"Node '{node_id}' not found in run #{run.pk}", status=404)
    if state.get("approval_decision"):
        return {"ok": True, "message": f"Already decided: {state['approval_decision']}", "target_url": f"/studio/runs?run={run.pk}"}
    run.node_states[node_id] = {
        **state,
        "approval_decision": decision,
        "approval_response": response_text,
        "decided_at": timezone.now().isoformat(),
    }
    PipelineRun.objects.filter(pk=run.pk).update(node_states=run.node_states)
    return {"ok": True, "decision": decision, "node_id": node_id, "target_url": f"/studio/runs?run={run.pk}"}


def register_assistant_actions() -> None:
    specs = [
        AssistantActionSpec(
            action_type="studio.pipelines.list",
            label="List Studio pipelines",
            description="List available Studio pipelines.",
            required_feature="studio_pipelines",
            risk="read",
            handler=list_pipelines,
        ),
        AssistantActionSpec(
            action_type="studio.runs.list",
            label="List Studio runs",
            description="List recent Studio pipeline runs.",
            required_feature="studio_runs",
            risk="read",
            handler=list_runs,
        ),
        AssistantActionSpec(
            action_type="studio.capabilities.registry",
            label="Show Studio capabilities",
            description="Read the Studio capability registry with matching MCP servers, skills, and task families.",
            required_feature="studio",
            risk="read",
            handler=capability_registry,
        ),
        AssistantActionSpec(
            action_type="studio.mcp.list",
            label="List Studio MCP servers",
            description="List accessible MCP servers without invoking tools.",
            required_feature="studio_mcp",
            risk="read",
            handler=list_mcp_servers,
        ),
        AssistantActionSpec(
            action_type="studio.skills.list",
            label="List Studio skills",
            description="List accessible Studio skills and their safety metadata.",
            required_feature="studio_skills",
            risk="read",
            handler=list_studio_skills,
        ),
        AssistantActionSpec(
            action_type="studio.skills.validate",
            label="Validate Studio skills",
            description="Validate accessible Studio skills without changing skill files.",
            required_feature="studio_skills",
            risk="read",
            input_schema={"optional": ["slugs", "strict"]},
            handler=validate_studio_skills,
        ),
        AssistantActionSpec(
            action_type="studio.pipeline_draft.create",
            label="Create pipeline draft",
            description="Create a Studio pipeline AI draft from a chat request.",
            required_feature="studio_pipelines",
            risk="internal_write",
            requires_confirmation=True,
            input_schema={"required": ["pipeline_name", "user_message"]},
            handler=create_pipeline_draft,
        ),
        AssistantActionSpec(
            action_type="studio.pipeline_draft.validate",
            label="Validate pipeline draft",
            description="Dry-run validate a Studio pipeline draft without runtime actions.",
            required_feature="studio_pipelines",
            risk="read",
            input_schema={"required": ["draft_id"]},
            handler=validate_pipeline_draft,
        ),
        AssistantActionSpec(
            action_type="studio.pipeline_draft.apply",
            label="Apply pipeline draft",
            description="Apply a validated Studio draft to create/update a pipeline.",
            required_feature="studio_pipelines",
            risk="internal_write",
            requires_confirmation=True,
            input_schema={"required": ["draft_id"]},
            handler=apply_pipeline_draft,
        ),
        AssistantActionSpec(
            action_type="studio.pipeline.run_validate",
            label="Validate pipeline run",
            description="Validate/dry-run a manual pipeline launch without execution.",
            required_feature="studio_pipelines",
            risk="read",
            input_schema={"required": ["pipeline_id"]},
            handler=validate_pipeline_run,
        ),
        AssistantActionSpec(
            action_type="studio.pipeline.run",
            label="Run pipeline",
            description="Launch a pipeline manual trigger after validation.",
            required_feature="studio_pipelines",
            risk="mutating",
            requires_confirmation=True,
            input_schema={"required": ["pipeline_id"]},
            handler=run_pipeline,
        ),
        AssistantActionSpec(
            action_type="studio.run.stop",
            label="Stop pipeline run",
            description="Request stop for an active Studio pipeline run.",
            required_feature="studio_runs",
            risk="mutating",
            requires_confirmation=True,
            input_schema={"required": ["run_id"]},
            handler=stop_pipeline_run,
        ),
        AssistantActionSpec(
            action_type="studio.run.approve_node",
            label="Approve pipeline node",
            description="Record an approval/rejection for a waiting pipeline approval node owned by the user.",
            required_feature="studio_runs",
            risk="mutating",
            requires_confirmation=True,
            input_schema={"required": ["run_id", "node_id", "decision"]},
            handler=approve_pipeline_node,
        ),
    ]
    for spec in specs:
        register_action(spec)
