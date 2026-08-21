from __future__ import annotations

import json
from typing import Any

from django.db import transaction
from django.utils import timezone

from app.ai_runtime import ExecutionMode
from app.runtime_limits import get_pipeline_run_limit_error
from app.server_alert_provider import ServerAlertSnapshot, get_alert_snapshot, get_open_alert_snapshot
from core_ui.ai_model_policy import operational_provider_binding, stored_operational_provider_binding
from core_ui.services.ai_execution_context import build_execution_context

from .models import PipelineRun, PipelineTrigger
from .pipeline.pipeline_preflight import pipeline_integration_diagnostics
from .pipeline.pipeline_runtime_context import validate_pipeline_entry_branch, validate_pipeline_runtime_context
from .pipeline.pipeline_validation import validate_pipeline_definition


def _clone_json_snapshot(value: Any):
    return json.loads(json.dumps(value))


def _initial_routing_state(entry_node_id: str) -> dict[str, Any]:
    entry = str(entry_node_id or "").strip()
    return {
        "entry_node_id": entry,
        "activated_nodes": [entry] if entry else [],
        "completed_nodes": [],
        "queued_nodes": [],
        "pending_merges": {},
    }


def pipeline_run_creation_error_details(exc: ValueError) -> list[str]:
    message = str(exc).strip() or "Pipeline is not runnable."
    prefix = "Pipeline is not runnable: "
    if message.startswith(prefix):
        message = message[len(prefix) :]
    details = [item.strip() for item in message.split(";") if item.strip()]
    return details or [message]


def validate_pipeline_run_creation(
    *,
    pipeline,
    context: dict[str, Any] | None,
    entry_node_id: str,
) -> list[str]:
    entry = str(entry_node_id or "").strip()
    if not entry:
        return ["entry_node_id is required"]
    if context is not None and not isinstance(context, dict):
        return ["Pipeline run context must be a JSON object."]

    validation_errors = validate_pipeline_definition(
        nodes=pipeline.nodes,
        edges=pipeline.edges,
        owner=pipeline.owner,
        graph_version=pipeline.graph_version,
    )
    if validation_errors:
        return validation_errors

    branch_errors = validate_pipeline_entry_branch(pipeline.nodes, pipeline.edges, entry)
    if branch_errors:
        return branch_errors

    context_errors = validate_pipeline_runtime_context(
        pipeline.nodes,
        context or {},
        edges=pipeline.edges,
        entry_node_id=entry,
    )
    integration = pipeline_integration_diagnostics(pipeline, entry_node_id=entry)
    return [*context_errors, *integration["errors"]]


def create_pipeline_run(
    *,
    pipeline,
    triggered_by=None,
    trigger: PipelineTrigger | None = None,
    context: dict[str, Any] | None = None,
    trigger_data: dict[str, Any] | None = None,
    entry_node_id: str,
    explicit_provider_binding: dict[str, Any] | None = None,
) -> PipelineRun:
    entry = str(entry_node_id or "").strip()
    preflight_errors = validate_pipeline_run_creation(
        pipeline=pipeline,
        context=context,
        entry_node_id=entry,
    )
    if preflight_errors:
        raise ValueError(f"Pipeline is not runnable: {'; '.join(preflight_errors)}")

    from studio.dispatch import enqueue_pipeline_run_dispatch

    actor = triggered_by or pipeline.owner
    unattended = triggered_by is None or (trigger is not None and trigger.trigger_type != PipelineTrigger.TYPE_MANUAL)
    execution_mode = ExecutionMode.UNATTENDED if unattended else ExecutionMode.INTERACTIVE
    execution_context = build_execution_context(
        actor_user_id=actor.pk,
        project_id=pipeline.project_id,
        purpose="ops",
        source_kind="pipeline",
        source_id=pipeline.pk,
        mode=execution_mode,
        explicit_binding=operational_provider_binding(actor, explicit_provider_binding),
        stored_binding=stored_operational_provider_binding(actor, pipeline.provider_binding),
        requested_provider="auto",
    )

    with transaction.atomic():
        run = PipelineRun.objects.create(
            pipeline=pipeline,
            triggered_by=triggered_by,
            trigger=trigger,
            status=PipelineRun.STATUS_PENDING,
            nodes_snapshot=_clone_json_snapshot(pipeline.nodes or []),
            edges_snapshot=_clone_json_snapshot(pipeline.edges or []),
            context=dict(context or {}),
            trigger_data=dict(trigger_data or {}),
            entry_node_id=entry,
            routing_state=_initial_routing_state(entry),
            provider_binding_snapshot=execution_context.binding.to_dict(),
            provider_execution_mode=execution_mode.value,
        )
        enqueue_pipeline_run_dispatch(run)
    return run


def launch_pipeline_run_async(run: PipelineRun) -> None:
    """Compatibility facade: ensure the run is present in the durable queue."""

    from studio.dispatch import enqueue_pipeline_run_dispatch

    enqueue_pipeline_run_dispatch(run)


def build_monitoring_alert_context(alert: ServerAlertSnapshot) -> dict[str, Any]:
    metadata = dict(alert.metadata or {})
    containers = metadata.get("containers") if isinstance(metadata.get("containers"), list) else []
    container_names = [
        str(item.get("name") or "").strip()
        for item in containers
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    if not container_names:
        single = str(metadata.get("container_name") or "").strip()
        if single:
            container_names = [single]

    return {
        "alert_id": alert.alert_id,
        "alert_type": alert.alert_type,
        "alert_severity": alert.severity,
        "alert_title": alert.title,
        "alert_message": alert.message,
        "alert_metadata": metadata,
        "server_id": alert.server_id,
        "server_name": alert.server_name,
        "server_host": alert.server_host,
        "server_username": alert.server_username,
        "container_name": container_names[0] if container_names else "",
        "container_names": container_names,
        "container_names_csv": ", ".join(container_names),
        "trigger_source": "monitoring",
    }


def _normalize_str_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    values: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text:
            values.append(text)
    return values


def _text_contains_any(text: str, needles: list[str]) -> bool:
    lowered = text.lower()
    return any(needle.lower() in lowered for needle in needles if needle)


def monitoring_trigger_matches_alert(trigger: PipelineTrigger, alert: ServerAlertSnapshot) -> bool:
    filters = trigger.monitoring_filters if isinstance(trigger.monitoring_filters, dict) else {}

    server_ids = {int(item) for item in filters.get("server_ids", []) if str(item).strip().isdigit()}
    if server_ids and alert.server_id not in server_ids:
        return False

    severities = {value.lower() for value in _normalize_str_list(filters.get("severities"))}
    if severities and str(alert.severity or "").lower() not in severities:
        return False

    alert_types = {value.lower() for value in _normalize_str_list(filters.get("alert_types"))}
    if alert_types and str(alert.alert_type or "").lower() not in alert_types:
        return False

    container_filters = [value.lower() for value in _normalize_str_list(filters.get("container_names"))]
    if container_filters:
        metadata = alert.metadata if isinstance(alert.metadata, dict) else {}
        containers = metadata.get("containers") if isinstance(metadata.get("containers"), list) else []
        detected_names = {
            str(item.get("name") or "").strip().lower()
            for item in containers
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        }
        single_name = str(metadata.get("container_name") or "").strip().lower()
        if single_name:
            detected_names.add(single_name)
        if not detected_names.intersection(container_filters):
            return False

    match_text = str(filters.get("match_text") or "").strip()
    if match_text:
        haystack = "\n".join(
            [
                str(alert.title or ""),
                str(alert.message or ""),
                json.dumps(alert.metadata or {}, ensure_ascii=False),
            ]
        )
        if match_text.lower() not in haystack.lower():
            return False

    return not alert.is_resolved


def _iter_matching_monitoring_triggers(alert: ServerAlertSnapshot) -> list[PipelineTrigger]:
    triggers = (
        PipelineTrigger.objects.select_related("pipeline", "pipeline__owner")
        .filter(
            trigger_type=PipelineTrigger.TYPE_MONITORING,
            is_active=True,
            pipeline__owner_id=alert.server_owner_id,
        )
        .order_by("pipeline_id", "id")
    )
    return [trigger for trigger in triggers if monitoring_trigger_matches_alert(trigger, alert)]


def _coerce_alert_snapshot(alert: Any) -> ServerAlertSnapshot | None:
    if isinstance(alert, ServerAlertSnapshot):
        return alert
    alert_id = getattr(alert, "alert_id", None) or getattr(alert, "pk", None)
    if alert_id is None:
        return None
    return get_alert_snapshot(int(alert_id))


def launch_monitoring_triggers_for_alert(alert: ServerAlertSnapshot) -> list[PipelineRun]:
    alert = _coerce_alert_snapshot(alert)
    if alert is None:
        return []
    if alert.is_resolved:
        return []

    matched = _iter_matching_monitoring_triggers(alert)
    runs: list[PipelineRun] = []
    for trigger in matched:
        validation_errors = validate_pipeline_definition(
            nodes=trigger.pipeline.nodes,
            edges=trigger.pipeline.edges,
            owner=trigger.pipeline.owner,
            graph_version=trigger.pipeline.graph_version,
        )
        if validation_errors:
            continue
        if validate_pipeline_entry_branch(trigger.pipeline.nodes, trigger.pipeline.edges, trigger.node_id):
            continue
        if get_pipeline_run_limit_error(trigger.pipeline.owner):
            continue

        context = build_monitoring_alert_context(alert)
        if validate_pipeline_runtime_context(
            trigger.pipeline.nodes,
            context,
            edges=trigger.pipeline.edges,
            entry_node_id=trigger.node_id,
        ):
            continue
        try:
            run = create_pipeline_run(
                pipeline=trigger.pipeline,
                trigger=trigger,
                context=context,
                trigger_data={
                    "source": "monitoring",
                    "alert_id": alert.alert_id,
                    "alert_type": alert.alert_type,
                    "severity": alert.severity,
                    "server_id": alert.server_id,
                },
                entry_node_id=trigger.node_id,
            )
        except ValueError:
            continue
        trigger.last_triggered_at = timezone.now()
        trigger.save(update_fields=["last_triggered_at"])
        launch_pipeline_run_async(run)
        runs.append(run)
    return runs


def launch_monitoring_triggers_for_alert_id(alert_id: int) -> list[PipelineRun]:
    alert = get_open_alert_snapshot(alert_id)
    if alert is None:
        return []
    return launch_monitoring_triggers_for_alert(alert)
