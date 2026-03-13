"""
Background launch helpers for long-running agent executions.

These helpers move full agent execution out of the HTTP request thread while
preserving live websocket events and run ids for the frontend.
"""

from __future__ import annotations

import asyncio
import threading

from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.contrib.auth.models import User
from django.db import close_old_connections, connections
from django.utils import timezone
from loguru import logger

from servers.agent_engine import AgentEngine
from servers.agent_runtime import is_runtime_stop_requested
from servers.models import AgentRun, Server, ServerAgent
from servers.multi_agent_engine import MultiAgentEngine


def _make_event_callback(run_id: int):
    async def callback(event_type: str, data: dict):
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


def _spawn_background_worker(name: str, target) -> None:
    thread = threading.Thread(target=target, daemon=True, name=name)
    thread.start()


def launch_agent_run_background(run_id: int, agent_id: int, server_ids: list[int], user_id: int, *, plan_only: bool = False) -> None:
    """Launch a new full/multi agent run in a background thread."""

    def _target():
        close_old_connections()
        try:
            asyncio.run(_run_agent_background(run_id, agent_id, server_ids, user_id, plan_only=plan_only))
        except Exception as exc:
            logger.exception("Background agent run {} failed: {}", run_id, exc)
            AgentRun.objects.filter(pk=run_id).update(
                status=AgentRun.STATUS_FAILED,
                ai_analysis=f"Background launch failed: {exc}",
                completed_at=timezone.now(),
            )
        finally:
            connections.close_all()

    _spawn_background_worker(f"agent-run-{run_id}", _target)


async def _run_agent_background(run_id: int, agent_id: int, server_ids: list[int], user_id: int, *, plan_only: bool = False) -> None:
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


def launch_plan_execution_background(run_id: int, agent_id: int, server_ids: list[int], user_id: int) -> None:
    """Launch execution of an approved multi-agent plan in a background thread."""

    def _target():
        close_old_connections()
        try:
            asyncio.run(_run_plan_execution_background(run_id, agent_id, server_ids, user_id))
        except Exception as exc:
            logger.exception("Background plan execution {} failed: {}", run_id, exc)
            AgentRun.objects.filter(pk=run_id).update(
                status=AgentRun.STATUS_FAILED,
                ai_analysis=f"Background launch failed: {exc}",
                completed_at=timezone.now(),
            )
        finally:
            connections.close_all()

    _spawn_background_worker(f"agent-plan-{run_id}", _target)


async def _run_plan_execution_background(run_id: int, agent_id: int, server_ids: list[int], user_id: int) -> None:
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


def _load_servers_in_order(server_ids: list[int]) -> list[Server]:
    servers_by_id = {
        server.id: server
        for server in Server.objects.filter(id__in=server_ids)
    }
    return [servers_by_id[server_id] for server_id in server_ids if server_id in servers_by_id]
