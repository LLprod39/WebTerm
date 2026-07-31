from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from asgiref.sync import sync_to_async
from django.utils import timezone

from studio.models import PipelineRun

from .pipeline_dead_letter import record_node_dead_letter
from .pipeline_retry import node_retry_policy
from .pipeline_routing import result_routing_ports, route_from_node
from .pipeline_run_setup import PreparedPipelineRun
from .pipeline_run_state import persist_routing_state, update_node_state, update_run_status

logger = logging.getLogger(__name__)


async def _execute_node_with_retries(
    *,
    run: PipelineRun,
    node: dict[str, Any],
    context: dict[str, Any],
    node_outputs: dict[str, dict],
    execute_node: Callable[[dict[str, Any], dict[str, Any], dict[str, dict]], Awaitable[dict[str, Any]]],
    sync_stop_state_from_db: Callable[[], Awaitable[bool]],
) -> dict[str, Any]:
    node_id = str(node.get("id") or "")
    policy = node_retry_policy(node)
    retry_history: list[dict[str, Any]] = []
    for attempt in range(1, policy.max_attempts + 1):
        try:
            result = await execute_node(node, context, node_outputs)
            state = dict(result)
        except Exception as exc:
            logger.exception("pipeline run %s node %s attempt %s raised exception", run.pk, node_id, attempt)
            state = {"status": "failed", "error": str(exc)}

        state["attempt_count"] = attempt
        state["max_attempts"] = policy.max_attempts
        if policy.retry_suppressed_reason:
            state["retry_suppressed_reason"] = policy.retry_suppressed_reason
        if str(state.get("status") or "") != "failed":
            if retry_history:
                state["retry_history"] = retry_history
            return state

        if attempt >= policy.max_attempts:
            if retry_history:
                state["retry_history"] = retry_history
            dead_letter = await sync_to_async(record_node_dead_letter, thread_sensitive=True)(
                run=run,
                node=node,
                state=state,
                attempt_count=attempt,
                max_attempts=policy.max_attempts,
            )
            state["dead_letter_id"] = dead_letter.pk
            return state

        delay = policy.delay_after_attempt(attempt)
        retry_at = timezone.now() + timedelta(seconds=delay)
        retry_history.append(
            {
                "attempt": attempt,
                "error": str(state.get("error") or "")[:1000],
                "delay_seconds": delay,
                "retry_at": retry_at.isoformat(),
            }
        )
        await update_node_state(
            run,
            node_id,
            {
                **state,
                "status": "retrying",
                "retry_history": retry_history,
                "next_retry_at": retry_at.isoformat(),
            },
        )
        if await sync_stop_state_from_db():
            return {
                "status": "stopped",
                "attempt_count": attempt,
                "max_attempts": policy.max_attempts,
                "retry_history": retry_history,
            }
        if delay:
            await asyncio.sleep(delay)

    raise AssertionError("node retry loop must return a terminal state")


def _restored_pending_merges(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    restored: dict[str, dict[str, Any]] = {}
    for node_id, item in raw.items():
        if not isinstance(item, dict):
            continue
        restored[str(node_id)] = {
            "mode": str(item.get("mode") or "all"),
            "arrived_sources": {str(value) for value in (item.get("arrived_sources") or [])},
            "possible_sources": {str(value) for value in (item.get("possible_sources") or [])},
            "released": bool(item.get("released")),
        }
    return restored


async def _restore_resume_loop_state(
    run: PipelineRun,
    prepared: PreparedPipelineRun,
) -> tuple[dict[str, dict], deque[str], set[str], set[str], set[str], dict[str, dict[str, Any]]]:
    routing = run.routing_state if isinstance(run.routing_state, dict) else {}
    completed_nodes = {
        str(node_id) for node_id in (routing.get("completed_nodes") or []) if str(node_id) in prepared.id_to_node
    }
    activated_nodes = {
        str(node_id) for node_id in (routing.get("activated_nodes") or []) if str(node_id) in prepared.id_to_node
    }
    queued = [str(node_id) for node_id in (routing.get("queued_nodes") or []) if str(node_id) in prepared.id_to_node]
    ready_queue: deque[str] = deque(dict.fromkeys(queued))
    ready_nodes = set(ready_queue)
    pending_merges = _restored_pending_merges(routing.get("pending_merges"))
    node_outputs = {
        node_id: dict(state)
        for node_id, state in (run.node_states or {}).items()
        if node_id in completed_nodes and isinstance(state, dict)
    }

    executable_queue: deque[str] = deque()
    executable_nodes: set[str] = set()
    while ready_queue:
        node_id = ready_queue.popleft()
        ready_nodes.discard(node_id)
        if node_id in completed_nodes:
            continue
        state = (run.node_states or {}).get(node_id)
        if isinstance(state, dict) and str(state.get("status") or "").lower() == "completed":
            completed_nodes.add(node_id)
            activated_nodes.add(node_id)
            node_outputs[node_id] = dict(state)
            await route_from_node(
                source_node_id=node_id,
                routing_ports=set(
                    state.get("routing_ports") or result_routing_ports(prepared.id_to_node[node_id], state)
                ),
                entry_node_id=prepared.entry_node_id,
                id_to_node=prepared.id_to_node,
                outgoing_edges=prepared.outgoing_edges,
                incoming_edges=prepared.incoming_edges,
                node_states=run.node_states,
                ready_queue=ready_queue,
                ready_nodes=ready_nodes,
                activated_nodes=activated_nodes,
                completed_nodes=completed_nodes,
                pending_merges=pending_merges,
            )
            continue
        if node_id not in executable_nodes:
            executable_queue.append(node_id)
            executable_nodes.add(node_id)

    await persist_routing_state(
        run,
        entry_node_id=prepared.entry_node_id,
        activated_nodes=activated_nodes,
        completed_nodes=completed_nodes,
        ready_nodes=executable_nodes,
        pending_merges=pending_merges,
    )
    return (
        node_outputs,
        executable_queue,
        executable_nodes,
        activated_nodes,
        completed_nodes,
        pending_merges,
    )


async def _initialize_loop_state(
    run: PipelineRun,
    prepared: PreparedPipelineRun,
) -> tuple[dict[str, dict], deque[str], set[str], set[str], set[str], dict[str, dict[str, Any]]]:
    if prepared.resumed:
        return await _restore_resume_loop_state(run, prepared)

    entry_node_id = prepared.entry_node_id
    ready_queue: deque[str] = deque()
    ready_nodes: set[str] = set()
    activated_nodes = {entry_node_id}
    completed_nodes = {entry_node_id}
    pending_merges: dict[str, dict[str, Any]] = {}
    await route_from_node(
        source_node_id=entry_node_id,
        routing_ports={"out"},
        entry_node_id=entry_node_id,
        id_to_node=prepared.id_to_node,
        outgoing_edges=prepared.outgoing_edges,
        incoming_edges=prepared.incoming_edges,
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
    return {}, ready_queue, ready_nodes, activated_nodes, completed_nodes, pending_merges


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

    (
        node_outputs,
        ready_queue,
        ready_nodes,
        activated_nodes,
        completed_nodes,
        pending_merges,
    ) = await _initialize_loop_state(run, prepared)

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
                *(
                    _execute_node_with_retries(
                        run=run,
                        node=node,
                        context=context,
                        node_outputs=node_outputs,
                        execute_node=execute_node,
                        sync_stop_state_from_db=sync_stop_state_from_db,
                    )
                    for node in exec_nodes
                ),
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
