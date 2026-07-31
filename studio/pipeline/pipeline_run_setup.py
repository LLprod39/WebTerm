from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from asgiref.sync import sync_to_async as _s2a
from django.utils import timezone

from studio.models import PipelineRun
from studio.policy.execution_policy import build_execution_policy_decisions, summarize_execution_policy_decisions

from .pipeline_routing import build_execution_graph, reachable_nodes_from_entry, serialize_routing_state
from .pipeline_run_state import update_run_status
from .pipeline_runtime_context import validate_pipeline_runtime_context
from .pipeline_validation import validate_pipeline_definition

logger = logging.getLogger(__name__)


def _s2a_fn(func, thread_sensitive=False):
    return _s2a(func, thread_sensitive=thread_sensitive)


@dataclass(slots=True)
class PreparedPipelineRun:
    context: dict[str, Any]
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    entry_node_id: str
    id_to_node: dict[str, dict[str, Any]]
    outgoing_edges: dict[str, list[dict[str, Any]]]
    incoming_edges: dict[str, list[dict[str, Any]]]
    resumed: bool = False


async def prepare_pipeline_run_start(
    run: PipelineRun,
    context: dict | None,
    *,
    resume: bool = False,
    non_idempotent_confirmed: bool = False,
) -> PreparedPipelineRun | None:
    if context is None:
        context = {}
    if not isinstance(context, dict):
        await update_run_status(
            run,
            PipelineRun.STATUS_FAILED,
            error="Pipeline run context must be a JSON object.",
            finished_at=timezone.now(),
        )
        return None

    context = dict(context)
    owner = await _s2a_fn(lambda: run.pipeline.owner)()
    nodes = list(run.nodes_snapshot or run.pipeline.nodes or [])
    edges = list(run.edges_snapshot or run.pipeline.edges or [])
    graph_version = getattr(run.pipeline, "graph_version", None)

    validation_errors = await _s2a_fn(
        lambda: validate_pipeline_definition(
            nodes=nodes,
            edges=edges,
            owner=owner,
            graph_version=graph_version,
        )
    )()
    if validation_errors:
        await update_run_status(
            run,
            PipelineRun.STATUS_FAILED,
            error=f"Pipeline validation failed: {'; '.join(validation_errors)}",
            finished_at=timezone.now(),
        )
        return None

    entry_node_id = str(run.entry_node_id or getattr(getattr(run, "trigger", None), "node_id", "") or "").strip()
    id_to_node, outgoing_edges, incoming_edges = build_execution_graph(nodes, edges)
    policy_summary = summarize_execution_policy_decisions(
        build_execution_policy_decisions(
            nodes=nodes,
            id_to_node=id_to_node,
            incoming_edges=incoming_edges,
        )
    )

    entry_node = id_to_node.get(entry_node_id)
    if not entry_node_id or entry_node is None:
        await update_run_status(
            run,
            PipelineRun.STATUS_FAILED,
            error="Pipeline run is missing a valid entry trigger node.",
            finished_at=timezone.now(),
        )
        return None
    if not str(entry_node.get("type") or "").startswith("trigger/"):
        await update_run_status(
            run,
            PipelineRun.STATUS_FAILED,
            error=f"Entry node '{entry_node_id}' is not a trigger node.",
            finished_at=timezone.now(),
        )
        return None

    context_errors = validate_pipeline_runtime_context(
        nodes,
        context,
        edges=edges,
        entry_node_id=entry_node_id,
    )
    if context_errors:
        await update_run_status(
            run,
            PipelineRun.STATUS_FAILED,
            error=f"Pipeline runtime context failed: {'; '.join(context_errors)}",
            finished_at=timezone.now(),
        )
        return None

    reachable_from_entry = reachable_nodes_from_entry(
        entry_node_id=entry_node_id,
        id_to_node=id_to_node,
        outgoing_edges=outgoing_edges,
        node_states={},
    )
    if not any(
        not str(id_to_node[node_id].get("type") or "").startswith("trigger/") for node_id in reachable_from_entry
    ):
        await update_run_status(
            run,
            PipelineRun.STATUS_FAILED,
            error=f"Selected trigger '{entry_node_id}' has no downstream executable nodes.",
            finished_at=timezone.now(),
        )
        return None

    if resume:
        from .pipeline_resume import build_resume_checkpoint

        checkpoint = build_resume_checkpoint(run)
        if checkpoint.confirmation_nodes and not non_idempotent_confirmed:
            trigger_data = run.trigger_data if isinstance(run.trigger_data, dict) else {}
            run.trigger_data = {
                **trigger_data,
                "resume_confirmation_required": checkpoint.confirmation_nodes,
            }
            await _s2a_fn(run.save)(update_fields=["trigger_data"])
            await update_run_status(
                run,
                PipelineRun.STATUS_FAILED,
                error="Operator confirmation is required before retrying non-idempotent nodes.",
                finished_at=timezone.now(),
            )
            return None

        trigger_data = run.trigger_data if isinstance(run.trigger_data, dict) else {}
        run.context = context
        run.node_states = checkpoint.node_states
        run.routing_state = checkpoint.routing_state
        run.trigger_data = {
            **trigger_data,
            "execution_policy": policy_summary,
            "resume_execution": {
                "resumed_at": timezone.now().isoformat(),
                "retry_node_ids": checkpoint.retry_node_ids,
                "confirmed_non_idempotent": bool(non_idempotent_confirmed),
            },
        }
        run.trigger_data.pop("resume_confirmation_required", None)
        run.error = ""
        run.finished_at = None
        if run.started_at is None:
            run.started_at = timezone.now()
        await _s2a_fn(run.save)()
        await update_run_status(run, PipelineRun.STATUS_RUNNING)
        logger.info(
            "pipeline run %s resume: entry=%s completed=%s queued=%s retry=%s",
            run.pk,
            entry_node_id,
            len(checkpoint.routing_state.get("completed_nodes") or []),
            len(checkpoint.routing_state.get("queued_nodes") or []),
            checkpoint.retry_node_ids,
        )
        return PreparedPipelineRun(
            context=context,
            nodes=nodes,
            edges=edges,
            entry_node_id=entry_node_id,
            id_to_node=id_to_node,
            outgoing_edges=outgoing_edges,
            incoming_edges=incoming_edges,
            resumed=True,
        )

    run.nodes_snapshot = nodes
    run.edges_snapshot = edges
    run.context = context
    trigger_data = run.trigger_data if isinstance(run.trigger_data, dict) else {}
    run.trigger_data = {**trigger_data, "execution_policy": policy_summary}
    run.entry_node_id = entry_node_id
    run.node_states = {}
    run.routing_state = serialize_routing_state(
        entry_node_id=entry_node_id,
        activated_nodes={entry_node_id},
        completed_nodes={entry_node_id},
        queued_nodes=set(),
        pending_merges={},
    )
    run.error = ""
    run.started_at = timezone.now()
    await _s2a_fn(run.save)()

    logger.info(
        "pipeline run %s start: pipeline=%s entry=%s context_keys=%s nodes=%s edges=%s",
        run.pk,
        run.pipeline.name,
        entry_node_id,
        sorted(context.keys()),
        len(run.nodes_snapshot or []),
        len(run.edges_snapshot or []),
    )
    await update_run_status(run, PipelineRun.STATUS_RUNNING)

    return PreparedPipelineRun(
        context=context,
        nodes=nodes,
        edges=edges,
        entry_node_id=entry_node_id,
        id_to_node=id_to_node,
        outgoing_edges=outgoing_edges,
        incoming_edges=incoming_edges,
        resumed=False,
    )
