"""
Background launch helpers and worker execution for long-running agent runs.

Full/multi-agent launches are now queued for a dedicated execution-plane worker
process. This module still owns the shared execution routine and live event
delivery used by that worker.
"""

from __future__ import annotations

import asyncio
import contextlib

from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.contrib.auth.models import User
from django.db import close_old_connections, connections
from django.utils import timezone
from loguru import logger

from servers.agent_dispatch import (
    complete_agent_dispatch,
    enqueue_agent_run_dispatch,
    fail_agent_dispatch,
    heartbeat_agent_dispatch,
)
from servers.agent_engine import AgentEngine
from servers.agent_runtime import is_runtime_stop_requested
from servers.models import AgentRun, AgentRunDispatch, Server, ServerAgent
from servers.multi_agent_engine import MultiAgentEngine
from servers.run_events import record_run_event, record_run_event_async
from servers.worker_state import heartbeat_background_worker


def _make_event_callback(run_id: int):
    async def callback(event_type: str, data: dict):
        await record_run_event_async(run_id, event_type, data or {})
        layer = get_channel_layer()
        if not layer:
            return
        try:
            await layer.group_send(
                f"agent_run_{run_id}",
                {
                    "type": event_type,
                    "run_id": run_id,
                    **(data or {}),
                },
            )
        except Exception as exc:
            logger.debug("Agent live event delivery failed for run {}: {}", run_id, exc)

    return callback

def _mark_background_failure(run_id: int, exc: Exception, *, phase: str) -> None:
    message = f"Background {phase} failed: {exc}"
    record_run_event(
        run_id,
        "agent_background_failed",
        {
            "phase": phase,
            "error": str(exc),
            "message": message,
        },
    )
    AgentRun.objects.filter(pk=run_id).update(
        status=AgentRun.STATUS_FAILED,
        ai_analysis=message,
        completed_at=timezone.now(),
    )


def launch_agent_run_background(run_id: int, agent_id: int, server_ids: list[int], user_id: int, *, plan_only: bool = False) -> AgentRunDispatch:
    """Queue a new full/multi agent run for the dedicated execution worker."""
    run = AgentRun.objects.get(pk=run_id)
    return enqueue_agent_run_dispatch(
        run=run,
        agent_id=agent_id,
        user_id=user_id,
        server_ids=server_ids,
        plan_only=plan_only,
        dispatch_kind=AgentRunDispatch.KIND_LAUNCH,
    )


async def _run_agent_background(run_id: int, agent_id: int, server_ids: list[int], user_id: int, *, plan_only: bool = False) -> None:
    await record_run_event_async(run_id, "agent_background_started", {"plan_only": bool(plan_only), "server_ids": list(server_ids)})
    run = await sync_to_async(
        lambda: AgentRun.objects.select_related("agent", "server", "user").get(pk=run_id),
        thread_sensitive=True,
    )()
    if run.status == AgentRun.STATUS_STOPPED or is_runtime_stop_requested(run):
        return

    agent = await sync_to_async(
        lambda: ServerAgent.objects.get(pk=agent_id, user_id=user_id),
        thread_sensitive=True,
    )()
    user = await sync_to_async(lambda: User.objects.get(pk=user_id), thread_sensitive=True)()
    servers = await sync_to_async(
        lambda: _load_servers_in_order(server_ids),
        thread_sensitive=True,
    )()

    callback = _make_event_callback(run_id)
    if agent.is_multi:
        engine = MultiAgentEngine(agent, servers, user, event_callback=callback)
        await engine.run(plan_only=plan_only, run_record=run)
    else:
        engine = AgentEngine(agent, servers, user, event_callback=callback)
        await engine.run(run_record=run)


def launch_plan_execution_background(run_id: int, agent_id: int, server_ids: list[int], user_id: int) -> AgentRunDispatch:
    """Queue execution of an approved multi-agent plan for the execution worker."""
    run = AgentRun.objects.get(pk=run_id)
    return enqueue_agent_run_dispatch(
        run=run,
        agent_id=agent_id,
        user_id=user_id,
        server_ids=server_ids,
        plan_only=False,
        dispatch_kind=AgentRunDispatch.KIND_PLAN_EXECUTION,
    )


async def _run_plan_execution_background(run_id: int, agent_id: int, server_ids: list[int], user_id: int) -> None:
    await record_run_event_async(run_id, "agent_plan_execution_started", {"server_ids": list(server_ids)})
    run = await sync_to_async(
        lambda: AgentRun.objects.select_related("agent", "server", "user").get(pk=run_id),
        thread_sensitive=True,
    )()
    if run.status == AgentRun.STATUS_STOPPED or is_runtime_stop_requested(run):
        return

    agent = await sync_to_async(
        lambda: ServerAgent.objects.get(pk=agent_id, user_id=user_id),
        thread_sensitive=True,
    )()
    user = await sync_to_async(lambda: User.objects.get(pk=user_id), thread_sensitive=True)()
    servers = await sync_to_async(
        lambda: _load_servers_in_order(server_ids),
        thread_sensitive=True,
    )()

    callback = _make_event_callback(run_id)
    engine = MultiAgentEngine(agent, servers, user, event_callback=callback)
    await engine.execute_existing_plan(run)


async def execute_agent_dispatch(
    dispatch_id: int,
    *,
    worker_key: str = "default",
    lease_seconds: int = 180,
) -> None:
    await sync_to_async(close_old_connections, thread_sensitive=True)()
    dispatch = await sync_to_async(
        lambda: AgentRunDispatch.objects.select_related("run", "agent", "user").get(pk=dispatch_id),
        thread_sensitive=True,
    )()
    run_id = int(dispatch.run_id)
    await record_run_event_async(
        run_id,
        "agent_worker_claimed",
        {
            "dispatch_id": dispatch.id,
            "dispatch_kind": dispatch.dispatch_kind,
            "worker_key": worker_key,
            "message": f"Execution worker claimed {dispatch.dispatch_kind.replace('_', ' ')} dispatch",
        },
    )

    stop_heartbeat = asyncio.Event()

    async def _heartbeat_loop() -> None:
        interval = max(15, min(int(lease_seconds // 3), 60))
        while not stop_heartbeat.is_set():
            await sync_to_async(heartbeat_agent_dispatch, thread_sensitive=True)(
                dispatch.id,
                worker_name=worker_key,
                lease_seconds=lease_seconds,
            )
            await sync_to_async(heartbeat_background_worker, thread_sensitive=True)(
                "agent_execution",
                worker_key=worker_key,
                lease_seconds=lease_seconds,
                summary={"active_dispatch_id": dispatch.id, "run_id": run_id},
            )
            try:
                await asyncio.wait_for(stop_heartbeat.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    heartbeat_task = asyncio.create_task(_heartbeat_loop())
    try:
        if dispatch.dispatch_kind == AgentRunDispatch.KIND_PLAN_EXECUTION:
            await _run_plan_execution_background(run_id, dispatch.agent_id, list(dispatch.server_ids or []), dispatch.user_id)
        else:
            await _run_agent_background(
                run_id,
                dispatch.agent_id,
                list(dispatch.server_ids or []),
                dispatch.user_id,
                plan_only=bool(dispatch.plan_only),
            )
        await sync_to_async(complete_agent_dispatch, thread_sensitive=True)(
            dispatch.id,
            summary={"run_id": run_id, "dispatch_kind": dispatch.dispatch_kind},
        )
    except Exception as exc:
        await sync_to_async(fail_agent_dispatch, thread_sensitive=True)(dispatch.id, error=str(exc))
        await sync_to_async(_mark_background_failure, thread_sensitive=True)(
            run_id,
            exc,
            phase=dispatch.dispatch_kind,
        )
        raise
    finally:
        stop_heartbeat.set()
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task
        await sync_to_async(connections.close_all, thread_sensitive=True)()


def _load_servers_in_order(server_ids: list[int]) -> list[Server]:
    servers_by_id = {
        server.id: server
        for server in Server.objects.filter(id__in=server_ids)
    }
    return [servers_by_id[server_id] for server_id in server_ids if server_id in servers_by_id]
