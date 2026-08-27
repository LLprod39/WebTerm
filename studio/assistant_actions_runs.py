"""Pipeline run validate / start / stop assistant actions."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from app.assistant_actions import AssistantActionContext, AssistantActionError
from studio.assistant_actions_common import _int_payload, _pipeline_for_user, _run_for_user
from studio.models import Pipeline, PipelineRun, PipelineTrigger
from studio.pipeline.pipeline_preflight import pipeline_integration_diagnostics
from studio.pipeline.pipeline_runtime import update_runtime_control
from studio.pipeline.pipeline_runtime_context import validate_pipeline_entry_branch, validate_pipeline_runtime_context
from studio.pipeline.pipeline_validation import ensure_json_object, validate_pipeline_definition
from studio.readiness_issues import runtime_limit_issue, validation_issues
from studio.trigger_dispatch import get_pipeline_run_limit_error, pipeline_run_creation_error_details
from studio.views.pipeline_assistant_preview import pipeline_assistant_risk
from studio.views.pipeline_helpers import (
    _create_pipeline_run,
    _launch_pipeline_run,
    _resolve_manual_entry_trigger,
)


def _pipeline_run_check(
    pipeline: Pipeline,
    *,
    actor,
    context: dict[str, Any],
    entry_node_id: str,
    validate_only: bool,
) -> dict[str, Any]:
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
        pipeline_integration_diagnostics(
            pipeline,
            entry_node_id=selected_trigger.node_id,
            actor=actor,
            unattended=False,
        )
        if selected_trigger is not None and not validation_errors
        else {"requirements": [], "issues": [], "errors": [], "warnings": []}
    )
    limit_error = get_pipeline_run_limit_error(pipeline.owner, cleanup_stale=not validate_only)
    limit_errors = [str(limit_error.get("error") or "Runtime limit reached.")] if limit_error else []
    limit_issues = [runtime_limit_issue(limit_error)] if limit_error else []
    all_errors = [
        *validation_errors,
        *trigger_errors,
        *branch_errors,
        *context_errors,
        *integration["errors"],
        *limit_errors,
    ]
    risk = pipeline_assistant_risk(pipeline.nodes, pipeline.edges)
    issues = [
        *validation_issues([*validation_errors, *trigger_errors, *branch_errors, *context_errors]),
        *integration["issues"],
        *limit_issues,
    ]
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
    check = _pipeline_run_check(
        pipeline,
        actor=ctx.user,
        context=raw_context,
        entry_node_id=entry_node_id,
        validate_only=True,
    )
    dry_run = {
        "ok": check["validation"]["ok"] and check["risk"].get("level") != "dangerous",
        "executed": False,
        "mode": "validate_only",
        "checks": [
            "graph_contract",
            "manual_trigger",
            "references",
            "risk_review",
            "runtime_context",
            "integrations",
            "runtime_limits",
        ],
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
    check = _pipeline_run_check(
        pipeline,
        actor=ctx.user,
        context=raw_context,
        entry_node_id=entry_node_id,
        validate_only=False,
    )
    if check["all_errors"]:
        raise AssistantActionError(
            "Pipeline is not runnable: " + "; ".join(check["all_errors"]), details={"validation": check["validation"]}
        )
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
    control = update_runtime_control(run, stop_requested=True)
    from studio.dispatch import cancel_pipeline_dispatch_for_run

    cancel_pipeline_dispatch_for_run(run.pk)
    if run.status in {PipelineRun.STATUS_PENDING, PipelineRun.STATUS_RUNNING, PipelineRun.STATUS_HIBERNATING}:
        run.status = PipelineRun.STATUS_STOPPED
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])
    return {
        "ok": True,
        "live_executor": False,
        "runtime_control": control,
        "target_url": f"/studio/runs?run={run.pk}",
    }
