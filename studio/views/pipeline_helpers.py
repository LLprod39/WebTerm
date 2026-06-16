"""
Shared helpers for Studio pipeline endpoints.
"""

from studio.models import Pipeline, PipelineRun, PipelineTrigger
from studio.trigger_dispatch import create_pipeline_run as _dispatch_create_pipeline_run
from studio.trigger_dispatch import launch_pipeline_run_async as _dispatch_launch_pipeline_run_async
from studio.views.common import _is_admin


def _pipeline_queryset_for_user(user):
    qs = Pipeline.objects.select_related("owner")
    if _is_admin(user):
        return qs.order_by("-updated_at")
    return qs.filter(owner=user).order_by("-updated_at")


def _initial_routing_state(entry_node_id: str) -> dict:
    entry = str(entry_node_id or "").strip()
    return {
        "entry_node_id": entry,
        "activated_nodes": [entry] if entry else [],
        "completed_nodes": [],
        "queued_nodes": [],
        "pending_merges": {},
    }


def _default_pipeline_draft_nodes() -> list[dict]:
    return [
        {
            "id": "manual_start",
            "type": "trigger/manual",
            "position": {"x": 280, "y": 80},
            "data": {
                "label": "Manual Start",
                "is_active": False,
                "description": "Connect the draft, then enable this trigger to launch the pipeline manually.",
            },
        }
    ]


def _create_pipeline_run(
    *,
    pipeline: Pipeline,
    triggered_by=None,
    trigger: PipelineTrigger | None = None,
    context: dict | None = None,
    trigger_data: dict | None = None,
    entry_node_id: str,
) -> PipelineRun:
    return _dispatch_create_pipeline_run(
        pipeline=pipeline,
        triggered_by=triggered_by,
        trigger=trigger,
        context=context,
        trigger_data=trigger_data,
        entry_node_id=entry_node_id,
    )


def _resolve_manual_entry_trigger(pipeline: Pipeline, requested_entry_node_id: str = "") -> tuple[PipelineTrigger | None, list[str]]:
    entry = str(requested_entry_node_id or "").strip()
    manual_triggers = list(
        pipeline.triggers.filter(
            trigger_type=PipelineTrigger.TYPE_MANUAL,
            is_active=True,
        ).order_by("created_at", "id")
    )
    if not manual_triggers:
        return None, ["Pipeline has no active manual trigger nodes."]

    if entry:
        selected = next((item for item in manual_triggers if item.node_id == entry), None)
        if selected is None:
            options = ", ".join(item.node_id for item in manual_triggers[:6])
            return None, [f"Manual trigger '{entry}' was not found. Available manual triggers: {options}."]
        return selected, []

    if len(manual_triggers) == 1:
        return manual_triggers[0], []

    options = ", ".join(item.node_id for item in manual_triggers[:6])
    return None, [f"Pipeline has multiple manual triggers. Provide entry_node_id. Available manual triggers: {options}."]


def _get_pipeline(request, pipeline_id: int) -> Pipeline | None:
    return _pipeline_queryset_for_user(request.user).filter(pk=pipeline_id).first()


def _launch_pipeline_run(run: PipelineRun):
    from studio import views as studio_views

    launcher = getattr(studio_views, "_launch_pipeline_run_async", _launch_pipeline_run_async)
    launcher(run)


def _launch_pipeline_run_async(run: PipelineRun):
    _dispatch_launch_pipeline_run_async(run)
