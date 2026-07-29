from __future__ import annotations

from servers.agent_background import launch_agent_run_background
from servers.models import AgentRun
from servers.run_events import record_run_event
from servers.services.server_query import CAPABILITY_EXECUTE_COMMAND, resolve_servers_for_user_capability


def launch_queued_agent_run(
    *,
    agent,
    user,
    accessible_servers_queryset,
    server_id: int | None = None,
) -> dict:
    """Queue mini/full/multi agent run for the dedicated execution-plane worker.

    HTTP/API callers return immediately with a pending run; the worker performs
    SSH + LLM so Daphne/runserver request threads never block on remote work.
    """
    if server_id is not None:
        server = accessible_servers_queryset.filter(id=int(server_id)).first()
        if not server:
            return {"ok": False, "status": 404, "error": "Server not found"}
        servers, denied = resolve_servers_for_user_capability(
            [server.id],
            user,
            CAPABILITY_EXECUTE_COMMAND,
            base_queryset=accessible_servers_queryset,
        )
        if denied:
            return {"ok": False, "status": 403, "error": "Missing server capability: execute_command"}
    else:
        server_ids = list(agent.servers.values_list("id", flat=True))
        if not server_ids:
            return {"ok": False, "status": 400, "error": "No servers assigned to agent"}
        accessible_servers = list(accessible_servers_queryset.filter(id__in=server_ids))
        if not accessible_servers:
            return {"ok": False, "status": 400, "error": "No accessible servers"}
        servers, denied = resolve_servers_for_user_capability(
            server_ids,
            user,
            CAPABILITY_EXECUTE_COMMAND,
            base_queryset=accessible_servers_queryset,
        )
        if denied:
            return {"ok": False, "status": 403, "error": "Missing server capability: execute_command"}

    already_running = AgentRun.objects.filter(
        agent=agent,
        status__in=[
            AgentRun.STATUS_PENDING,
            AgentRun.STATUS_RUNNING,
            AgentRun.STATUS_PAUSED,
            AgentRun.STATUS_WAITING,
            AgentRun.STATUS_PLAN_REVIEW,
        ],
    ).exists()
    if already_running:
        return {"ok": False, "status": 409, "error": "Agent is already running"}

    primary_server = servers[0]
    run_result = AgentRun.objects.create(
        agent=agent,
        server=primary_server,
        user=user,
        status=AgentRun.STATUS_PENDING,
    )
    record_run_event(
        run_result.id,
        "agent_run_created",
        {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "agent_mode": agent.mode,
            "server_ids": [server.id for server in servers],
            "plan_only": False,
            "status": AgentRun.STATUS_PENDING,
        },
    )

    launch_agent_run_background(
        run_id=run_result.id,
        agent_id=agent.id,
        server_ids=[server.id for server in servers],
        user_id=user.id,
        plan_only=False,
    )

    return {
        "ok": True,
        "run": run_result,
        "servers": servers,
    }


def launch_full_agent_run(*, agent, user, accessible_servers_queryset, server_id: int | None = None) -> dict:
    """Backward-compatible alias for queued agent launch (all modes)."""
    return launch_queued_agent_run(
        agent=agent,
        user=user,
        accessible_servers_queryset=accessible_servers_queryset,
        server_id=server_id,
    )
