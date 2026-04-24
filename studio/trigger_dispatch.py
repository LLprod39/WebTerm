from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from django.utils import timezone

from app.runtime_limits import get_pipeline_run_limit_error
from servers.services.alert_query import ServerAlertSnapshot, get_open_alert_snapshot

from .models import PipelineRun, PipelineTrigger
from .pipeline_validation import validate_pipeline_definition


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


def create_pipeline_run(
    *,
    pipeline,
    triggered_by=None,
    trigger: PipelineTrigger | None = None,
    context: dict[str, Any] | None = None,
    trigger_data: dict[str, Any] | None = None,
    entry_node_id: str,
) -> PipelineRun:
    entry = str(entry_node_id or "").strip()
    if not entry:
        raise ValueError("entry_node_id is required")
    return PipelineRun.objects.create(
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
    )


def launch_pipeline_run_async(run: PipelineRun) -> None:
    """Launch pipeline execution in a background thread."""

    run_pk = run.pk

    def _run_in_thread():
        try:
            async def _main():
                from asgiref.sync import sync_to_async

                from studio.pipeline_executor import PipelineExecutor

                run_obj = await sync_to_async(
                    lambda: PipelineRun.objects.select_related(
                        "pipeline",
                        "pipeline__owner",
                        "triggered_by",
                        "trigger",
                    ).get(pk=run_pk)
                )()
                executor = PipelineExecutor(run_obj)
                await executor.execute(context=run_obj.context)

            asyncio.run(_main())
        except Exception as exc:
            PipelineRun.objects.filter(pk=run_pk).update(
                status=PipelineRun.STATUS_FAILED,
                error=str(exc),
                finished_at=timezone.now(),
            )

    threading.Thread(target=_run_in_thread, daemon=True).start()


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


def launch_monitoring_triggers_for_alert(alert: ServerAlertSnapshot) -> list[PipelineRun]:
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
        if get_pipeline_run_limit_error(trigger.pipeline.owner):
            continue

        context = build_monitoring_alert_context(alert)
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
