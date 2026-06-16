from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from django.utils import timezone

from .models import PipelineRun
from .pipeline_routing import result_routing_ports, route_from_node
from .pipeline_run_setup import PreparedPipelineRun
from .pipeline_run_state import persist_routing_state, update_node_state, update_run_status

logger = logging.getLogger(__name__)


async def execute_pipeline_run_loop(
    run: PipelineRun,
    prepared: PreparedPipelineRun,
    *,
    execute_node: Callable[[dict[str, Any], dict[str, Any], dict[str, dict]], Awaitable[dict[str, Any]]],
    sync_stop_state_from_db: Callable[[], Awaitable[bool]],
    request_stop: Callable[[], None],
    is_stop_requested: Callable[[], bool],
) -> PipelineRun:
    context = prepared.context
    entry_node_id = prepared.entry_node_id
    id_to_node = prepared.id_to_node
    outgoing_edges = prepared.outgoing_edges
    incoming_edges = prepared.incoming_edges

    node_outputs: dict[str, dict] = {}
    ready_queue: deque[str] = deque()
    ready_nodes: set[str] = set()
    activated_nodes: set[str] = {entry_node_id}
    completed_nodes: set[str] = {entry_node_id}
    pending_merges: dict[str, dict[str, Any]] = {}
    await route_from_node(
        source_node_id=entry_node_id,
        routing_ports={"out"},
        entry_node_id=entry_node_id,
        id_to_node=id_to_node,
        outgoing_edges=outgoing_edges,
        incoming_edges=incoming_edges,
        node_states=run.node_states,
        ready_queue=ready_queue,
        ready_nodes=ready_nodes,
        activated_nodes=activated_nodes,
        completed_nodes=completed_nodes,
        pending_merges=pending_merges,
    )
    await persist_routing_state(
        run,
        entry_node_id=entry_node_id,
        activated_nodes=activated_nodes,
        completed_nodes=completed_nodes,
        ready_nodes=ready_nodes,
        pending_merges=pending_merges,
    )

    try:
        batch_index = 0
        while ready_queue:
            if await sync_stop_state_from_db():
                break

            batch_index += 1
            batch_node_ids: list[str] = []
            while ready_queue:
                node_id = ready_queue.popleft()
                ready_nodes.discard(node_id)
                if node_id not in id_to_node or node_id in completed_nodes:
                    continue
                batch_node_ids.append(node_id)

            if not batch_node_ids:
                continue

            exec_nodes = [id_to_node[node_id] for node_id in batch_node_ids]
            logger.info(
                "pipeline run %s batch %s start: nodes=%s",
                run.pk,
                batch_index,
                [node.get("id") for node in exec_nodes],
            )

            started_at = timezone.now().isoformat()
            for node in exec_nodes:
                await update_node_state(
                    run,
                    str(node["id"]),
                    {"status": "running", "started_at": started_at},
                )

            results = await asyncio.gather(
                *(execute_node(node, context, node_outputs) for node in exec_nodes),
                return_exceptions=True,
            )

            resolved_states: list[tuple[dict[str, Any], dict[str, Any]]] = []
            abort_error: str | None = None
            stop_in_batch = False
            finished_at = timezone.now().isoformat()

            for node, result in zip(exec_nodes, results, strict=False):
                nid = str(node["id"])
                if isinstance(result, Exception):
                    logger.exception("pipeline run %s node %s raised exception", run.pk, nid, exc_info=result)
                    state: dict[str, Any] = {
                        "status": "failed",
                        "error": str(result),
                    }
                else:
                    state = dict(result)

                state.setdefault("started_at", started_at)
                state["finished_at"] = finished_at
                state["routing_ports"] = result_routing_ports(node, state)
                node_outputs[nid] = state
                completed_nodes.add(nid)
                activated_nodes.add(nid)
                resolved_states.append((node, state))
                await update_node_state(run, nid, state)

                logger.info(
                    "pipeline run %s node %s finished: type=%s status=%s ports=%s error=%s output_chars=%s",
                    run.pk,
                    nid,
                    node.get("type", ""),
                    state.get("status"),
                    state.get("routing_ports"),
                    (state.get("error") or "")[:300],
                    len(state.get("output") or ""),
                )

                if state.get("status") == "stopped":
                    stop_in_batch = True
                    request_stop()

                node_type = str(node.get("type") or "")
                on_fail = str((node.get("data") or {}).get("on_failure") or "continue").strip().lower()
                if (
                    abort_error is None
                    and state.get("status") == "failed"
                    and on_fail == "abort"
                    and (node_type.startswith("agent/") or node_type.startswith("output/"))
                ):
                    abort_error = f"Node {nid} failed: {state.get('error')}"

            if abort_error is None and not stop_in_batch and not is_stop_requested():
                for node, state in resolved_states:
                    await route_from_node(
                        source_node_id=str(node.get("id") or ""),
                        routing_ports=set(state.get("routing_ports") or []),
                        entry_node_id=entry_node_id,
                        id_to_node=id_to_node,
                        outgoing_edges=outgoing_edges,
                        incoming_edges=incoming_edges,
                        node_states=run.node_states,
                        ready_queue=ready_queue,
                        ready_nodes=ready_nodes,
                        activated_nodes=activated_nodes,
                        completed_nodes=completed_nodes,
                        pending_merges=pending_merges,
                    )

            await persist_routing_state(
                run,
                entry_node_id=entry_node_id,
                activated_nodes=activated_nodes,
                completed_nodes=completed_nodes,
                ready_nodes=ready_nodes,
                pending_merges=pending_merges,
            )

            if abort_error is not None:
                raise RuntimeError(abort_error)
            if stop_in_batch or is_stop_requested():
                break

    except Exception as exc:
        run.error = str(exc)
        logger.exception("pipeline run %s failed", run.pk)
        await update_run_status(run, PipelineRun.STATUS_FAILED, error=str(exc), finished_at=timezone.now())
        return run

    if is_stop_requested():
        await update_run_status(run, PipelineRun.STATUS_STOPPED, finished_at=timezone.now())
    else:
        await update_run_status(run, PipelineRun.STATUS_COMPLETED, finished_at=timezone.now())

    logger.info("pipeline run %s finished: status=%s", run.pk, run.status)
    return run
