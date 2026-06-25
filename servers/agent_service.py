from __future__ import annotations

import contextlib
from datetime import timedelta

from asgiref.sync import async_to_sync
from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from app.runtime_limits import ACTIVE_AGENT_RUN_STATUSES, get_agent_run_limit_error
from servers.agent_background import launch_plan_execution_background
from servers.agent_dispatch import cancel_agent_dispatches_for_run, serialize_agent_dispatch
from servers.agent_execution_state import (
    AGENT_EXECUTION_COMMAND,
    AGENT_OPS_SUPERVISOR_COMMAND,
    SCHEDULED_AGENTS_COMMAND,
    get_agent_execution_readiness,
    get_agent_execution_readiness_for_mode,
)
from servers.agent_inputs import normalize_input_artifacts, normalize_report_delivery
from servers.agent_launch import launch_full_agent_run
from servers.agent_run_lifecycle import mark_agent_run_stopped
from servers.agent_run_report import record_run_event_and_refresh_report, refresh_agent_run_report_payload
from servers.agent_runtime import get_engine_for_agent, get_engine_for_run, update_runtime_control
from servers.agent_schedule import compute_next_due_by_schedule, normalize_schedule_config
from servers.agents import run_agent, run_agent_on_all_servers
from servers.models import AgentRun, AgentRunDispatch, BackgroundWorkerState, ServerAgent, ServerWatcherDraft
from servers.run_events import record_run_event
from servers.scheduled_agents import dispatch_scheduled_agents, is_agent_due
from servers.watcher_actions import ensure_watcher_agent, mark_watcher_draft_launched
from servers.worker_state import cleanup_stale_background_workers, serialize_background_worker_state


def compute_next_due_at(agent: ServerAgent, now=None):
    return compute_next_due_by_schedule(agent, now)


def compute_schedule_state(agent: ServerAgent, now=None) -> str:
    current_time = now or timezone.now()
    schedule_minutes = max(int(agent.schedule_minutes or 0), 0)
    if schedule_minutes <= 0:
        return "manual"
    if not agent.is_enabled:
        return "paused"
    if is_agent_due(agent, current_time):
        return "due"
    return "scheduled"


def serialize_run_result(run: AgentRun) -> dict:
    latest_dispatch = run.dispatches.order_by("-queued_at", "-id").first()
    return {
        "run_id": run.id,
        "server_name": run.server.name if run.server_id and run.server else "?",
        "status": run.status,
        "ai_analysis": run.ai_analysis,
        "duration_ms": run.duration_ms,
        "commands_output": run.commands_output,
        "total_iterations": run.total_iterations,
        "final_report": run.final_report,
        "dispatch": serialize_agent_dispatch(latest_dispatch),
    }


def serialize_agent_item(
    agent: ServerAgent,
    *,
    now=None,
    last_run: AgentRun | None = None,
    active_run: AgentRun | None = None,
    execution_readiness: dict | None = None,
) -> dict:
    current_time = now or timezone.now()
    next_due_at = compute_next_due_at(agent, current_time)
    next_due_in_seconds = None
    if next_due_at is not None:
        next_due_in_seconds = max(0, int((next_due_at - current_time).total_seconds()))

    return {
        "id": agent.id,
        "name": agent.name,
        "mode": agent.mode,
        "mode_display": agent.get_mode_display(),
        "agent_type": agent.agent_type,
        "agent_type_display": agent.get_agent_type_display(),
        "server_count": agent.servers.count(),
        "server_ids": list(agent.servers.values_list("id", flat=True)),
        "server_names": list(agent.servers.values_list("name", flat=True)),
        "schedule_minutes": int(agent.schedule_minutes or 0),
        "schedule_config": normalize_schedule_config(agent.schedule_config, fallback_minutes=int(agent.schedule_minutes or 0)),
        "is_enabled": bool(agent.is_enabled),
        "commands": agent.commands,
        "ai_prompt": agent.ai_prompt,
        "goal": agent.goal,
        "system_prompt": agent.system_prompt,
        "max_iterations": agent.max_iterations,
        "allow_multi_server": agent.allow_multi_server,
        "tools_config": agent.tools_config,
        "sudo_policy": agent.sudo_policy,
        "stop_conditions": agent.stop_conditions,
        "skill_slugs": list(agent.skill_slugs or []),
        "input_artifacts": normalize_input_artifacts(agent.input_artifacts),
        "report_delivery": normalize_report_delivery(agent.report_delivery),
        "session_timeout_seconds": agent.session_timeout_seconds,
        "max_connections": agent.max_connections,
        "last_run_at": agent.last_run_at.isoformat() if agent.last_run_at else None,
        "last_run_status": last_run.status if last_run else None,
        "last_run_id": last_run.id if last_run else None,
        "active_run_id": active_run.id if active_run else None,
        "execution_readiness": execution_readiness or get_agent_execution_readiness_for_mode(agent.mode),
        "schedule_state": compute_schedule_state(agent, current_time),
        "due_now": bool(next_due_at is not None and next_due_at <= current_time and agent.is_enabled),
        "next_due_at": next_due_at.isoformat() if next_due_at else None,
        "next_due_in_seconds": next_due_in_seconds,
    }


def get_agent_worker_states() -> dict[str, dict]:
    cleanup_stale_background_workers(BackgroundWorkerState.KIND_AGENT_EXECUTION)
    cleanup_stale_background_workers(BackgroundWorkerState.KIND_SCHEDULED_AGENTS)
    return {
        "agent_execution": serialize_background_worker_state(BackgroundWorkerState.KIND_AGENT_EXECUTION),
        "scheduled_agents": serialize_background_worker_state(BackgroundWorkerState.KIND_SCHEDULED_AGENTS),
    }


def _status_counts(queryset, statuses: list[str]) -> dict[str, int]:
    counts = {status: 0 for status in statuses}
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


def _owned_agent_run_queryset(user):
    return AgentRun.objects.filter(Q(user=user) | Q(agent__user=user)).distinct()


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
    next_due_at = compute_next_due_at(agent, current_time)
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
        "due_age_seconds": _age_seconds(current_time, next_due_at) if next_due_at and next_due_at <= current_time else 0,
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

    issues = []
    if (queued_dispatches or claimed_dispatches or run_counts.get(AgentRun.STATUS_PENDING, 0)) and not execution_readiness.get("ready"):
        issues.append(
            {
                "id": "execution_worker_not_ready",
                "severity": "warning",
                "title": "Execution worker не активен",
                "description": "Full/multi-запуски есть в очереди, но worker не подтверждён.",
                "next_action": AGENT_EXECUTION_COMMAND,
            }
        )
    scheduled_worker_running = scheduled_worker.get("status") == BackgroundWorkerState.STATUS_RUNNING and not scheduled_worker.get("is_stale")
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
        "queue": {
            "runs": run_counts,
            "dispatches": dispatch_counts,
        },
        "schedule": {
            "total_scheduled": len(scheduled_agents),
            "enabled": len(enabled_scheduled),
            "paused": len(scheduled_agents) - len(enabled_scheduled),
            "due_now": due_now,
            "worker_ready": scheduled_worker_running,
        },
        "workers": worker_states,
        "execution_readiness": execution_readiness,
        "items": {
            "active_runs": [
                _serialize_runtime_run_item(run, current_time, stale_seconds=stale_seconds)
                for run in active_run_rows
            ],
            "queued_dispatches": [
                _serialize_runtime_dispatch_item(dispatch, current_time)
                for dispatch in dispatch_rows
            ],
            "scheduled_due": [
                _serialize_runtime_scheduled_item(
                    agent,
                    current_time,
                    active_run=active_runs_by_agent.get(agent.id),
                )
                for agent in due_agents[:8]
            ],
            "stale_candidates": [
                _serialize_runtime_run_item(run, current_time, stale_seconds=stale_seconds)
                for run in stale_run_rows
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


def list_agents_for_user(user, *, mode_filter: str | None = None) -> list[dict]:
    queryset = ServerAgent.objects.filter(user=user).prefetch_related("servers")
    if mode_filter in {ServerAgent.MODE_MINI, ServerAgent.MODE_FULL, ServerAgent.MODE_MULTI}:
        queryset = queryset.filter(mode=mode_filter)

    current_time = timezone.now()
    full_multi_readiness = get_agent_execution_readiness()
    data: list[dict] = []
    for agent in queryset:
        last_run = AgentRun.objects.filter(agent=agent).first()
        active_run = AgentRun.objects.filter(agent=agent, status__in=ACTIVE_AGENT_RUN_STATUSES).first()
        readiness = get_agent_execution_readiness_for_mode(agent.mode) if agent.mode == ServerAgent.MODE_MINI else full_multi_readiness
        data.append(
            serialize_agent_item(
                agent,
                now=current_time,
                last_run=last_run,
                active_run=active_run,
                execution_readiness=readiness,
            )
        )
    return data


def list_scheduled_agents_for_user(user, *, limit: int = 50) -> dict:
    current_time = timezone.now()
    agents = list(
        ServerAgent.objects.filter(user=user)
        .prefetch_related("servers")
        .filter(schedule_minutes__gt=0)
        .order_by("name")[: max(1, min(int(limit), 200))]
    )

    items = []
    full_multi_readiness = get_agent_execution_readiness()
    summary = {
        "total_scheduled": 0,
        "enabled": 0,
        "paused": 0,
        "due_now": 0,
        "active_runs": 0,
    }
    for agent in agents:
        last_run = AgentRun.objects.filter(agent=agent).first()
        active_run = AgentRun.objects.filter(agent=agent, status__in=ACTIVE_AGENT_RUN_STATUSES).first()
        readiness = get_agent_execution_readiness_for_mode(agent.mode) if agent.mode == ServerAgent.MODE_MINI else full_multi_readiness
        item = serialize_agent_item(
            agent,
            now=current_time,
            last_run=last_run,
            active_run=active_run,
            execution_readiness=readiness,
        )
        items.append(item)
        summary["total_scheduled"] += 1
        if item["is_enabled"]:
            summary["enabled"] += 1
        else:
            summary["paused"] += 1
        if item["due_now"]:
            summary["due_now"] += 1
        if item["active_run_id"]:
            summary["active_runs"] += 1

    return {
        "summary": summary,
        "scheduled_agents": items,
        "execution_plane": serialize_background_worker_state(BackgroundWorkerState.KIND_AGENT_EXECUTION),
        "scheduled_agents_worker": serialize_background_worker_state(BackgroundWorkerState.KIND_SCHEDULED_AGENTS),
        "worker_states": get_agent_worker_states(),
        "execution_readiness": get_agent_execution_readiness(),
        "generated_at": current_time.isoformat(),
    }


def dispatch_scheduled_agents_for_user(user, *, limit: int = 100, agent_ids: list[int] | None = None) -> dict:
    summary = dispatch_scheduled_agents(limit=limit, agent_ids=agent_ids, user_ids=[int(user.id)])
    return {
        "summary": summary,
        "generated_at": timezone.now().isoformat(),
    }


def cleanup_stale_agent_runs_for_user(user, *, limit: int = 100) -> dict:
    stale_seconds = _agent_run_stale_seconds_setting()
    current_time = timezone.now()
    if stale_seconds <= 0:
        return {
            "stale_seconds": stale_seconds,
            "scanned": 0,
            "cleaned": 0,
            "canceled_dispatches": 0,
            "runs": [],
            "generated_at": current_time.isoformat(),
        }

    cutoff = current_time - timedelta(seconds=stale_seconds)
    queryset = (
        AgentRun.objects.filter(
            Q(user=user) | Q(agent__user=user),
            status__in=ACTIVE_AGENT_RUN_STATUSES,
            completed_at__isnull=True,
            started_at__lt=cutoff,
        )
        .select_related("agent", "server")
        .order_by("started_at", "id")
    )
    runs = list(queryset[: max(1, min(int(limit or 100), 200))])
    items = []
    canceled_total = 0
    for run in runs:
        age_seconds = _age_seconds(current_time, run.started_at)
        message = f"Agent run exceeded stale runtime threshold ({stale_seconds}s) and was marked failed by operator cleanup."
        record_run_event(
            run.id,
            "agent_stale_cleanup",
            {
                "stale_seconds": stale_seconds,
                "age_seconds": age_seconds,
                "source": "http",
                "message": message,
                "severity": "warning",
            },
        )
        canceled = cancel_agent_dispatches_for_run(run.id, reason="operator_stale_cleanup")
        canceled_total += int(canceled or 0)
        run.status = AgentRun.STATUS_FAILED
        run.ai_analysis = message
        run.completed_at = current_time
        if run.started_at:
            run.duration_ms = max(0, int((current_time - run.started_at).total_seconds() * 1000))
        run.save(update_fields=["status", "ai_analysis", "completed_at", "duration_ms"])
        refresh_agent_run_report_payload(run)
        items.append(
            {
                "run_id": run.id,
                "agent_id": run.agent_id,
                "agent_name": run.agent.name if run.agent_id and run.agent else "Agent",
                "status": run.status,
                "age_seconds": age_seconds,
                "canceled_dispatches": int(canceled or 0),
            }
        )

    return {
        "stale_seconds": stale_seconds,
        "scanned": len(runs),
        "cleaned": len(items),
        "canceled_dispatches": canceled_total,
        "runs": items,
        "generated_at": current_time.isoformat(),
    }


def _manual_dispatch_payload(*, agent: ServerAgent, source: str, extra_payload: dict | None = None) -> dict:
    payload = {
        "source": source,
        "agent_id": agent.id,
        "agent_name": agent.name,
        "agent_mode": agent.mode,
        "message": f"Run launched from {source}",
    }
    if extra_payload:
        payload.update(extra_payload)
    return payload


def start_agent_run_for_user(
    *,
    agent: ServerAgent,
    user,
    accessible_servers_queryset,
    server_id: int | None = None,
    source: str = "http",
    extra_event_payload: dict | None = None,
) -> dict:
    if agent.is_full or agent.is_multi:
        limit_error = get_agent_run_limit_error(user)
        if limit_error:
            return {"ok": False, "status": 429, "payload": limit_error}

        launch_result = launch_full_agent_run(
            agent=agent,
            user=user,
            accessible_servers_queryset=accessible_servers_queryset,
        )
        if not launch_result["ok"]:
            return {
                "ok": False,
                "status": int(launch_result["status"]),
                "payload": {"success": False, "error": launch_result["error"]},
            }

        run_result = launch_result["run"]
        record_run_event_and_refresh_report(
            run_result,
            "agent_manual_dispatch",
            _manual_dispatch_payload(
                agent=agent,
                source=source,
                extra_payload=extra_event_payload,
            ),
        )
        return {
            "ok": True,
            "payload": {
                "success": True,
                "run_id": run_result.id,
                "status": run_result.status,
                "runs": [serialize_run_result(run_result)],
            },
        }

    if server_id:
        server = accessible_servers_queryset.filter(id=server_id).first()
        if not server:
            return {"ok": False, "status": 404, "payload": {"success": False, "error": "Server not found"}}
        runs = [async_to_sync(run_agent)(agent, server, user)]
    else:
        runs = async_to_sync(run_agent_on_all_servers)(agent, user)

    results = []
    for run in runs:
        record_run_event_and_refresh_report(
            run,
            "agent_manual_dispatch",
            _manual_dispatch_payload(
                agent=agent,
                source=source,
                extra_payload={"server_id": run.server_id, **(extra_event_payload or {})},
            ),
        )
        results.append(serialize_run_result(run))

    return {
        "ok": True,
        "payload": {
            "success": True,
            "runs": results,
        },
    }


def stop_agent_run_for_user(*, agent_id: int, user, run_id: int | None = None, source: str = "http") -> dict:
    run_query = _owned_agent_run_queryset(user).filter(
        agent_id=agent_id,
        status__in=ACTIVE_AGENT_RUN_STATUSES,
    )
    if run_id is not None:
        run_query = run_query.filter(id=run_id)
    run = run_query.first()
    if not run:
        return {"ok": False, "status": 404, "payload": {"success": False, "error": "No active run found"}}

    live_engine = get_engine_for_run(run.id) or get_engine_for_agent(agent_id)
    update_runtime_control(run, live_engine=live_engine, stop_requested=True, pause_requested=False)
    canceled_dispatches = cancel_agent_dispatches_for_run(run.id, reason="operator_stop_requested")

    mark_agent_run_stopped(run)
    record_run_event(
        run.id,
        "agent_control_stop_requested",
        {
            "agent_id": agent_id,
            "source": source,
            "message": "Run stopped by operator request",
        },
    )
    refresh_agent_run_report_payload(run)
    return {
        "ok": True,
        "payload": {
            "success": True,
            "run_id": run.id,
            "stop_signal_sent": bool(live_engine),
            "canceled_dispatches": int(canceled_dispatches or 0),
        },
    }


def reply_to_agent_run_for_user(*, run_id: int, user, answer: str, source: str = "http") -> dict:
    run = _owned_agent_run_queryset(user).filter(
        id=run_id,
        status=AgentRun.STATUS_WAITING,
    ).first()
    if not run:
        return {"ok": False, "status": 404, "payload": {"success": False, "error": "Run not found or not waiting"}}

    answer = str(answer or "").strip()
    if not answer:
        return {"ok": False, "status": 400, "payload": {"success": False, "error": "Answer required"}}

    live_engine = get_engine_for_run(run.id)
    update_runtime_control(run, live_engine=live_engine, reply_text=answer, pause_requested=False)

    run.pending_question = ""
    run.status = AgentRun.STATUS_RUNNING
    run.save(update_fields=["pending_question", "status"])
    record_run_event(
        run.id,
        "agent_user_reply",
        {
            "source": source,
            "answer": answer,
            "message": "Operator replied to pending agent question",
        },
    )
    refresh_agent_run_report_payload(run)
    return {"ok": True, "payload": {"success": True}}


def approve_agent_plan_for_user(*, run_id: int, user, accessible_servers_queryset, source: str = "http") -> dict:
    run = _owned_agent_run_queryset(user).filter(
        id=run_id,
        status=AgentRun.STATUS_PLAN_REVIEW,
    ).select_related("agent", "server").first()
    if not run:
        return {
            "ok": False,
            "status": 404,
            "payload": {"success": False, "error": "Run not found or not awaiting plan approval"},
        }

    agent = run.agent
    if agent is None:
        return {
            "ok": False,
            "status": 400,
            "payload": {"success": False, "error": "Run has no agent plan to approve"},
        }
    server_ids = list(agent.servers.values_list("id", flat=True))
    servers = list(accessible_servers_queryset.filter(id__in=server_ids))
    if not servers:
        return {"ok": False, "status": 400, "payload": {"success": False, "error": "No accessible servers"}}

    run.status = AgentRun.STATUS_PENDING
    run.pending_question = ""
    run.completed_at = None
    run.save(update_fields=["status", "pending_question", "completed_at"])
    record_run_event(
        run.id,
        "agent_plan_approved",
        {
            "source": source,
            "message": "Operator approved pipeline plan",
        },
    )
    refresh_agent_run_report_payload(run)

    launch_plan_execution_background(
        run_id=run.id,
        agent_id=agent.id,
        server_ids=[server.id for server in servers],
        user_id=user.id,
    )

    return {
        "ok": True,
        "payload": {
            "success": True,
            "run_id": run.id,
            "status": run.status,
            "runs": [serialize_run_result(run)],
        },
    }


def launch_watcher_draft_for_user(*, draft_id: int, user, accessible_servers_queryset) -> dict:
    draft = (
        ServerWatcherDraft.objects.select_related("server", "acknowledged_by")
        .filter(id=draft_id, server_id__in=accessible_servers_queryset.values("id"))
        .first()
    )
    if draft is None:
        return {"ok": False, "status": 404, "payload": {"success": False, "error": "Watcher draft not found"}}

    agent = ensure_watcher_agent(user=user, draft=draft)
    launch_result = start_agent_run_for_user(
        agent=agent,
        user=user,
        accessible_servers_queryset=accessible_servers_queryset,
        source="watcher_draft",
        extra_event_payload={"draft_id": draft.id, "severity": draft.severity},
    )
    if not launch_result["ok"]:
        return launch_result

    payload = dict(launch_result["payload"] or {})
    run_id = payload.get("run_id")
    if not run_id:
        return {
            "ok": False,
            "status": 500,
            "payload": {"success": False, "error": "Watcher launch did not create a run"},
        }

    run = AgentRun.objects.filter(id=run_id).first()
    if run is None:
        return {
            "ok": False,
            "status": 404,
            "payload": {"success": False, "error": "Watcher run not found"},
        }

    mark_watcher_draft_launched(draft=draft, user=user, agent=agent, run=run)
    with contextlib.suppress(Exception):
        draft.refresh_from_db()
    from servers.watcher_service import WatcherService

    payload.update(
        {
            "draft": WatcherService._serialize_record(draft),
            "agent_id": agent.id,
            "run_id": run.id,
            "status": run.status,
        }
    )
    return {"ok": True, "payload": payload}
