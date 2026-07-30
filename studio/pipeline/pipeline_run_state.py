from __future__ import annotations

import contextlib
import logging
from typing import Any

from asgiref.sync import sync_to_async as _s2a
from channels.layers import get_channel_layer

from core_ui.activity import log_user_activity_async
from studio.models import PipelineRun

from .pipeline_context import pipeline_actor_context
from .pipeline_routing import serialize_routing_state
from .pipeline_secrets import serialize_pipeline_node_state

logger = logging.getLogger(__name__)


def _s2a_fn(func, thread_sensitive=False):
    return _s2a(func, thread_sensitive=thread_sensitive)


def make_run_event_callback(run: PipelineRun, node_id: str):
    """Returns an async callback that forwards agent events to the pipeline run channel group."""

    async def callback(event_type: str, data: dict):
        layer = get_channel_layer()
        if layer:
            with contextlib.suppress(Exception):
                await layer.group_send(
                    f"pipeline_run_{run.pk}",
                    {
                        "type": "pipeline.node.event",
                        "node_id": node_id,
                        "event_type": event_type,
                        "data": data,
                    },
                )

    return callback


async def update_node_state(run: PipelineRun, node_id: str, state: dict):
    """Persist node state and notify WS clients."""
    run.node_states[node_id] = state
    logger.info(
        "pipeline run %s node %s state -> %s",
        run.pk,
        node_id,
        state.get("status", "unknown"),
    )

    await _s2a_fn(lambda: PipelineRun.objects.filter(pk=run.pk).update(node_states=run.node_states))()

    actor_ctx = pipeline_actor_context(run)
    await log_user_activity_async(
        user_id=actor_ctx.get("user_id"),
        username_snapshot=str(actor_ctx.get("username_snapshot") or ""),
        category="pipeline",
        action="pipeline_node_state",
        status="error" if state.get("status") == "failed" else "success",
        description=f"Node {node_id} -> {state.get('status', 'unknown')}",
        entity_type="pipeline_run",
        entity_id=str(run.pk),
        entity_name=actor_ctx.get("entity_name") or "",
        metadata={
            "node_id": node_id,
            "node_status": state.get("status", "unknown"),
            "started_at": state.get("started_at"),
            "finished_at": state.get("finished_at"),
            "error": str(state.get("error") or "")[:4000],
        },
    )

    layer = get_channel_layer()
    if layer:
        with contextlib.suppress(Exception):
            await layer.group_send(
                f"pipeline_run_{run.pk}",
                {
                    "type": "pipeline.node.state",
                    "node_id": node_id,
                    "state": serialize_pipeline_node_state(state),
                },
            )


async def update_routing_state(run: PipelineRun, routing_state: dict[str, Any]) -> None:
    run.routing_state = routing_state
    await _s2a_fn(lambda: PipelineRun.objects.filter(pk=run.pk).update(routing_state=run.routing_state))()


async def persist_routing_state(
    run: PipelineRun,
    *,
    entry_node_id: str,
    activated_nodes: set[str],
    completed_nodes: set[str],
    ready_nodes: set[str],
    pending_merges: dict[str, dict[str, Any]],
) -> None:
    await update_routing_state(
        run,
        serialize_routing_state(
            entry_node_id=entry_node_id,
            activated_nodes=activated_nodes,
            completed_nodes=completed_nodes,
            queued_nodes=ready_nodes,
            pending_merges=pending_merges,
        ),
    )


async def update_run_status(run: PipelineRun, status: str, **extra):
    run.status = status
    update_fields = ["status"]
    for key, value in extra.items():
        setattr(run, key, value)
        update_fields.append(key)
    logger.info(
        "pipeline run %s status -> %s%s",
        run.pk,
        status,
        f" extra={list(extra.keys())}" if extra else "",
    )
    await _s2a_fn(run.save)(update_fields=list(dict.fromkeys(update_fields)))

    actor_ctx = pipeline_actor_context(run)
    await log_user_activity_async(
        user_id=actor_ctx.get("user_id"),
        username_snapshot=str(actor_ctx.get("username_snapshot") or ""),
        category="pipeline",
        action="pipeline_run_status",
        status="error" if status == PipelineRun.STATUS_FAILED else "success",
        description=f"Pipeline run #{run.pk} -> {status}",
        entity_type="pipeline_run",
        entity_id=str(run.pk),
        entity_name=actor_ctx.get("entity_name") or "",
        metadata={
            "status": status,
            "extra": extra,
        },
    )

    layer = get_channel_layer()
    if layer:
        with contextlib.suppress(Exception):
            await layer.group_send(
                f"pipeline_run_{run.pk}",
                {"type": "pipeline.status", "status": status, **extra},
            )
