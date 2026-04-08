from __future__ import annotations

from servers.agent_background import launch_agent_run_background
from servers.models import AgentRun
from servers.run_events import record_run_event


def launch_full_agent_run(*, agent, user, accessible_servers_queryset) -> dict:
    server_ids = list(agent.servers.values_list("id", flat=True))
    if not server_ids:
        return {"ok": False, "status": 400, "error": "No servers assigned to agent"}

    servers = list(accessible_servers_queryset.filter(id__in=server_ids))
    if not servers:
        return {"ok": False, "status": 400, "error": "No accessible servers"}

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
