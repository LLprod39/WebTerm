from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from app.runtime_limits import ACTIVE_AGENT_RUN_STATUSES
from servers.agents.agent_dispatch import serialize_agent_dispatch
from servers.agents.agent_execution_state import (
    AGENT_EXECUTION_COMMAND,
    AGENT_OPS_SUPERVISOR_COMMAND,
    SCHEDULED_AGENTS_COMMAND,
    get_agent_execution_readiness,
)
from servers.agents.agent_schedule import compute_next_due_by_schedule, normalize_schedule_config
from servers.agents.scheduled_agents import is_agent_due
from servers.models import AgentRun, AgentRunDispatch, BackgroundWorkerState, ServerAgent
from servers.worker_state import cleanup_stale_background_workers, serialize_background_worker_state


def get_agent_worker_states() -> dict[str, dict]:
    cleanup_stale_background_workers(BackgroundWorkerState.KIND_AGENT_EXECUTION)
    cleanup_stale_background_workers(BackgroundWorkerState.KIND_SCHEDULED_AGENTS)
    return {
        "agent_execution": serialize_background_worker_state(BackgroundWorkerState.KIND_AGENT_EXECUTION),
        "scheduled_agents": serialize_background_worker_state(BackgroundWorkerState.KIND_SCHEDULED_AGENTS),
    }


def _status_counts(queryset, statuses: list[str]) -> dict[str, int]:
    counts = dict.fromkeys(statuses, 0)
    for item in queryset.values("status").annotate(total=Count("id", distinct=True)):
        status = str(item.get("status") or "")
        if status in counts:
            counts[status] = int(item.get("total") or 0)
    return counts


def _age_seconds(current_time, value) -> int | None:
    if not value:
        return None
    return max(0, int((current_time - value).total_seconds()))


def _server_names_for_agent(agent: ServerAgent) -> list[str]:
    return [server.name for server in agent.servers.all()[:4]]


def _agent_run_stale_seconds_setting() -> int:
    return max(int(getattr(settings, "AGENT_RUN_STALE_SECONDS", 0) or 0), 0)


def _serialize_runtime_run_item(run: AgentRun, current_time, *, stale_seconds: int) -> dict:
    latest_dispatch = run.dispatches.order_by("-queued_at", "-id").first()
    age_seconds = _age_seconds(current_time, run.started_at)
    agent = run.agent if run.agent_id else None
    server = run.server if run.server_id else None
    return {
        "run_id": run.id,
        "agent_id": run.agent_id,
        "agent_name": agent.name if agent else "Agent",
        "agent_mode": agent.mode if agent else "",
        "server_id": run.server_id,
        "server_name": server.name if server else "",
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "age_seconds": age_seconds,
        "duration_ms": int(run.duration_ms or 0),
        "pending_question": run.pending_question or "",
        "is_stale_candidate": bool(
            stale_seconds
            and age_seconds is not None
            and age_seconds >= stale_seconds
            and run.completed_at is None
            and run.status in ACTIVE_AGENT_RUN_STATUSES
        ),
        "dispatch": serialize_agent_dispatch(latest_dispatch),
    }


def _serialize_runtime_dispatch_item(dispatch: AgentRunDispatch, current_time) -> dict:
    run = dispatch.run
    agent = dispatch.agent if dispatch.agent_id else None
    server = run.server if run and run.server_id else None
    lease_seconds_left = None
    if dispatch.lease_expires_at:
        lease_seconds_left = max(0, int((dispatch.lease_expires_at - current_time).total_seconds()))
    return {
        "dispatch_id": dispatch.id,
        "run_id": dispatch.run_id,
        "agent_id": dispatch.agent_id,
        "agent_name": agent.name if agent else "Agent",
        "agent_mode": agent.mode if agent else "",
        "server_id": run.server_id if run else None,
        "server_name": server.name if server else "",
        "dispatch_kind": dispatch.dispatch_kind,
        "status": dispatch.status,
        "server_ids": list(dispatch.server_ids or []),
        "queued_at": dispatch.queued_at.isoformat() if dispatch.queued_at else None,
        "claimed_at": dispatch.claimed_at.isoformat() if dispatch.claimed_at else None,
        "heartbeat_at": dispatch.heartbeat_at.isoformat() if dispatch.heartbeat_at else None,
        "lease_expires_at": dispatch.lease_expires_at.isoformat() if dispatch.lease_expires_at else None,
        "queued_age_seconds": _age_seconds(current_time, dispatch.queued_at),
        "lease_seconds_left": lease_seconds_left,
        "claimed_by": dispatch.claimed_by,
        "attempt_count": int(dispatch.attempt_count or 0),
        "error": dispatch.error or "",
    }


def _serialize_runtime_scheduled_item(
    agent: ServerAgent,
    current_time,
    *,
    active_run: AgentRun | None,
) -> dict:
    next_due_at = compute_next_due_by_schedule(agent, current_time)
    last_run_at = agent.last_run_at
    return {
        "agent_id": agent.id,
        "agent_name": agent.name,
        "agent_mode": agent.mode,
        "server_count": agent.servers.count(),
        "server_names": _server_names_for_agent(agent),
        "schedule_minutes": int(agent.schedule_minutes or 0),
        "schedule_config": normalize_schedule_config(
            agent.schedule_config,
            fallback_minutes=int(agent.schedule_minutes or 0),
        ),
        "last_run_at": last_run_at.isoformat() if last_run_at else None,
        "next_due_at": next_due_at.isoformat() if next_due_at else None,
        "due_age_seconds": _age_seconds(current_time, next_due_at)
        if next_due_at and next_due_at <= current_time
        else 0,
        "active_run_id": active_run.id if active_run else None,
        "active_run_status": active_run.status if active_run else "",
    }


def get_agent_runtime_overview(user) -> dict:
    current_time = timezone.now()
    worker_states = get_agent_worker_states()
    execution_readiness = get_agent_execution_readiness()
    scheduled_worker = worker_states["scheduled_agents"]
    stale_seconds = _agent_run_stale_seconds_setting()

    run_qs = AgentRun.objects.filter(Q(user=user) | Q(agent__user=user)).distinct()
    run_statuses = [choice[0] for choice in AgentRun.STATUS_CHOICES]
    run_counts = _status_counts(run_qs, run_statuses)
    active_runs = sum(run_counts.get(status, 0) for status in ACTIVE_AGENT_RUN_STATUSES)

    dispatch_qs = AgentRunDispatch.objects.filter(user=user)
    dispatch_statuses = [choice[0] for choice in AgentRunDispatch.STATUS_CHOICES]
    dispatch_counts = _status_counts(dispatch_qs, dispatch_statuses)
    queued_dispatches = dispatch_counts.get(AgentRunDispatch.STATUS_QUEUED, 0)
    claimed_dispatches = dispatch_counts.get(AgentRunDispatch.STATUS_CLAIMED, 0)

    scheduled_agents = list(ServerAgent.objects.filter(user=user, schedule_minutes__gt=0).prefetch_related("servers"))
    enabled_scheduled = [agent for agent in scheduled_agents if agent.is_enabled]
    due_agents = [agent for agent in enabled_scheduled if is_agent_due(agent, current_time)]
    due_now = len(due_agents)

    active_run_rows = list(
        run_qs.filter(status__in=ACTIVE_AGENT_RUN_STATUSES)
        .select_related("agent", "server")
        .order_by("-started_at", "-id")[:6]
    )
    dispatch_rows = list(
        dispatch_qs.filter(status__in=[AgentRunDispatch.STATUS_QUEUED, AgentRunDispatch.STATUS_CLAIMED])
        .select_related("agent", "run", "run__server")
        .order_by("queued_at", "id")[:6]
    )
    stale_run_rows: list[AgentRun] = []
    if stale_seconds > 0:
        stale_cutoff = current_time - timedelta(seconds=stale_seconds)
        stale_run_rows = list(
            run_qs.filter(
                status__in=ACTIVE_AGENT_RUN_STATUSES,
                completed_at__isnull=True,
                started_at__lt=stale_cutoff,
            )
            .select_related("agent", "server")
            .order_by("started_at", "id")[:6]
        )

    active_runs_by_agent: dict[int, AgentRun] = {}
    due_agent_ids = [agent.id for agent in due_agents[:8]]
    if due_agent_ids:
        for run in (
            run_qs.filter(agent_id__in=due_agent_ids, status__in=ACTIVE_AGENT_RUN_STATUSES)
            .select_related("agent", "server")
            .order_by("-started_at", "-id")
        ):
            if run.agent_id and run.agent_id not in active_runs_by_agent:
                active_runs_by_agent[run.agent_id] = run

    issues = _runtime_issues(
        queued_dispatches=queued_dispatches,
        claimed_dispatches=claimed_dispatches,
        pending_runs=run_counts.get(AgentRun.STATUS_PENDING, 0),
        execution_readiness=execution_readiness,
        due_now=due_now,
        scheduled_worker=scheduled_worker,
    )
    status = "idle"
    severity = "info"
    if active_runs or queued_dispatches or claimed_dispatches:
        status = "active"
        severity = "success"
    if issues:
        status = "needs_attention"
        severity = "warning"

    return {
        "status": status,
        "severity": severity,
        "summary": {
            "configured_agents": ServerAgent.objects.filter(user=user).count(),
            "active_runs": active_runs,
            "pending_runs": run_counts.get(AgentRun.STATUS_PENDING, 0),
            "running_runs": run_counts.get(AgentRun.STATUS_RUNNING, 0),
            "waiting_runs": run_counts.get(AgentRun.STATUS_WAITING, 0),
            "queued_dispatches": queued_dispatches,
            "claimed_dispatches": claimed_dispatches,
            "scheduled_agents": len(scheduled_agents),
            "scheduled_due_now": due_now,
            "issues": len(issues),
        },
        "queue": {"runs": run_counts, "dispatches": dispatch_counts},
        "schedule": {
            "total_scheduled": len(scheduled_agents),
            "enabled": len(enabled_scheduled),
            "paused": len(scheduled_agents) - len(enabled_scheduled),
            "due_now": due_now,
            "worker_ready": scheduled_worker.get("status") == BackgroundWorkerState.STATUS_RUNNING
            and not scheduled_worker.get("is_stale"),
        },
        "workers": worker_states,
        "execution_readiness": execution_readiness,
        "items": {
            "active_runs": [
                _serialize_runtime_run_item(run, current_time, stale_seconds=stale_seconds) for run in active_run_rows
            ],
            "queued_dispatches": [
                _serialize_runtime_dispatch_item(dispatch, current_time) for dispatch in dispatch_rows
            ],
            "scheduled_due": [
                _serialize_runtime_scheduled_item(agent, current_time, active_run=active_runs_by_agent.get(agent.id))
                for agent in due_agents[:8]
            ],
            "stale_candidates": [
                _serialize_runtime_run_item(run, current_time, stale_seconds=stale_seconds) for run in stale_run_rows
            ],
        },
        "issues": issues,
        "commands": {
            "execution_worker": AGENT_EXECUTION_COMMAND,
            "scheduled_agents_worker": SCHEDULED_AGENTS_COMMAND,
            "ops_supervisor": AGENT_OPS_SUPERVISOR_COMMAND,
        },
        "generated_at": current_time.isoformat(),
    }


def _runtime_issues(
    *,
    queued_dispatches: int,
    claimed_dispatches: int,
    pending_runs: int,
    execution_readiness: dict,
    due_now: int,
    scheduled_worker: dict,
) -> list[dict]:
    issues = []
    if (queued_dispatches or claimed_dispatches or pending_runs) and not execution_readiness.get("ready"):
        issues.append(
            {
                "id": "execution_worker_not_ready",
                "severity": "warning",
                "title": "Execution worker не активен",
                "description": "Full/multi-запуски есть в очереди, но worker не подтверждён.",
                "next_action": AGENT_EXECUTION_COMMAND,
            }
        )
    scheduled_worker_running = scheduled_worker.get(
        "status"
    ) == BackgroundWorkerState.STATUS_RUNNING and not scheduled_worker.get("is_stale")
    if due_now and not scheduled_worker_running:
        issues.append(
            {
                "id": "scheduled_agents_worker_not_ready",
                "severity": "warning",
                "title": "Schedule worker не активен",
                "description": "Есть due-агенты, но автозапуск по расписанию не подтверждён.",
                "next_action": SCHEDULED_AGENTS_COMMAND,
            }
        )
    if scheduled_worker.get("last_error"):
        issues.append(
            {
                "id": "scheduled_agents_worker_error",
                "severity": "warning",
                "title": "Schedule worker сообщил ошибку",
                "description": str(scheduled_worker.get("last_error") or "")[:500],
                "next_action": SCHEDULED_AGENTS_COMMAND,
            }
        )
    return issues
