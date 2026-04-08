from __future__ import annotations

from datetime import timedelta

from asgiref.sync import async_to_sync
from django.utils import timezone

from app.runtime_limits import ACTIVE_AGENT_RUN_STATUSES, get_agent_run_limit_error
from servers.agent_launch import launch_full_agent_run
from servers.agents import run_agent_on_all_servers
from servers.models import AgentRun, Server, ServerAgent
from servers.run_events import record_run_event


def is_agent_due(agent: ServerAgent, now=None) -> bool:
    current_time = now or timezone.now()
    if not agent.is_enabled:
        return False
    schedule_minutes = max(int(agent.schedule_minutes or 0), 0)
    if schedule_minutes <= 0:
        return False
    if agent.last_run_at is None:
        return True
    return agent.last_run_at <= current_time - timedelta(minutes=schedule_minutes)


def dispatch_scheduled_agents(*, now=None, limit: int = 50, agent_ids: list[int] | None = None, user_ids: list[int] | None = None) -> dict:
    current_time = now or timezone.now()
    queryset = (
        ServerAgent.objects.select_related("user")
        .prefetch_related("servers")
        .filter(is_enabled=True, schedule_minutes__gt=0, user__is_active=True)
        .order_by("id")
    )
    if agent_ids:
        queryset = queryset.filter(id__in=agent_ids)
    if user_ids:
        queryset = queryset.filter(user_id__in=user_ids)

    agents = list(queryset[: max(1, min(int(limit), 500))])
    summary = {
        "scanned": len(agents),
        "due": 0,
        "launched_agents": 0,
        "runs_created": 0,
        "background_runs": 0,
        "mini_runs": 0,
        "skipped": 0,
        "skip_reasons": {
            "not_due": 0,
            "no_servers": 0,
            "active_run": 0,
            "limit": 0,
            "launch_rejected": 0,
            "error": 0,
        },
        "errors": [],
    }

    for agent in agents:
        if not is_agent_due(agent, current_time):
            summary["skipped"] += 1
            summary["skip_reasons"]["not_due"] += 1
            continue

        summary["due"] += 1
        server_ids = list(agent.servers.values_list("id", flat=True))
        server_qs = Server.objects.filter(id__in=server_ids, is_active=True).order_by("id")
        if not server_ids or not server_qs.exists():
            summary["skipped"] += 1
            summary["skip_reasons"]["no_servers"] += 1
            continue

        if AgentRun.objects.filter(agent=agent, status__in=ACTIVE_AGENT_RUN_STATUSES).exists():
            summary["skipped"] += 1
            summary["skip_reasons"]["active_run"] += 1
            continue

        limit_error = get_agent_run_limit_error(agent.user)
        if limit_error:
            summary["skipped"] += 1
            summary["skip_reasons"]["limit"] += 1
            continue

        try:
            if agent.is_full or agent.is_multi:
                launch_result = launch_full_agent_run(
                    agent=agent,
                    user=agent.user,
                    accessible_servers_queryset=server_qs,
                )
                if not launch_result["ok"]:
                    summary["skipped"] += 1
                    summary["skip_reasons"]["launch_rejected"] += 1
                    summary["errors"].append(
                        {
                            "agent_id": agent.id,
                            "agent_name": agent.name,
                            "error": str(launch_result["error"]),
                        }
                    )
                    continue

                run = launch_result["run"]
                record_run_event(
                    run.id,
                    "agent_scheduled_dispatch",
                    {
                        "source": "schedule_minutes",
                        "schedule_minutes": int(agent.schedule_minutes or 0),
                        "agent_id": agent.id,
                        "agent_name": agent.name,
                        "agent_mode": agent.mode,
                    },
                )
                summary["launched_agents"] += 1
                summary["runs_created"] += 1
                summary["background_runs"] += 1
                continue

            runs = async_to_sync(run_agent_on_all_servers)(agent, agent.user)
            created_runs = 0
            for run in runs or []:
                record_run_event(
                    run.id,
                    "agent_scheduled_dispatch",
                    {
                        "source": "schedule_minutes",
                        "schedule_minutes": int(agent.schedule_minutes or 0),
                        "agent_id": agent.id,
                        "agent_name": agent.name,
                        "agent_mode": agent.mode,
                    },
                )
                created_runs += 1

            if created_runs:
                summary["launched_agents"] += 1
                summary["runs_created"] += created_runs
                summary["mini_runs"] += created_runs
            else:
                summary["skipped"] += 1
                summary["skip_reasons"]["launch_rejected"] += 1
        except Exception as exc:
            summary["skipped"] += 1
            summary["skip_reasons"]["error"] += 1
            summary["errors"].append(
                {
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "error": str(exc),
                }
            )

    return summary
