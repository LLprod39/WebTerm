from __future__ import annotations

import contextlib

from django.db.models import Q
from django.utils import timezone

from app.runtime_limits import ACTIVE_AGENT_RUN_STATUSES, get_agent_run_limit_error
from servers.agent_background import launch_plan_execution_background
from servers.agent_cleanup_service import cleanup_stale_agent_runs_for_user as cleanup_stale_agent_runs_for_user
from servers.agent_dispatch import cancel_agent_dispatches_for_run, serialize_agent_dispatch
from servers.agent_execution_state import (
    get_agent_execution_readiness,
    get_agent_execution_readiness_for_mode,
)
from servers.agent_inputs import normalize_input_artifacts, normalize_report_delivery
from servers.agent_launch import launch_queued_agent_run
from servers.agent_run_lifecycle import mark_agent_run_stopped
from servers.agent_run_report import record_run_event_and_refresh_report, refresh_agent_run_report_payload
from servers.agent_runtime import get_engine_for_agent, get_engine_for_run, update_runtime_control
from servers.agent_runtime_overview import (
    get_agent_runtime_overview as get_agent_runtime_overview,
)
from servers.agent_runtime_overview import (
    get_agent_worker_states,
)
from servers.agent_schedule import compute_next_due_by_schedule, normalize_schedule_config
from servers.models import AgentRun, BackgroundWorkerState, ServerAgent, ServerWatcherDraft
from servers.run_events import record_run_event
from servers.scheduled_agents import dispatch_scheduled_agents, is_agent_due
from servers.services.server_query import CAPABILITY_EXECUTE_COMMAND, resolve_servers_for_user_capability
from servers.watcher_actions import ensure_watcher_agent, mark_watcher_draft_launched
from servers.worker_state import serialize_background_worker_state


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
        "schedule_config": normalize_schedule_config(
            agent.schedule_config, fallback_minutes=int(agent.schedule_minutes or 0)
        ),
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
        "active_run_status": active_run.status if active_run else None,
        "active_run_started_at": active_run.started_at.isoformat() if active_run and active_run.started_at else None,
        "active_run_iterations": int(active_run.total_iterations or 0) if active_run else 0,
        "active_run_server_name": (
            active_run.server.name if active_run and active_run.server_id and active_run.server else None
        ),
        "active_run_pending_question": (active_run.pending_question or "")[:200] if active_run else "",
        "execution_readiness": execution_readiness or get_agent_execution_readiness_for_mode(agent.mode),
        "schedule_state": compute_schedule_state(agent, current_time),
        "due_now": bool(next_due_at is not None and next_due_at <= current_time and agent.is_enabled),
        "next_due_at": next_due_at.isoformat() if next_due_at else None,
        "next_due_in_seconds": next_due_in_seconds,
    }


def _owned_agent_run_queryset(user):
    return AgentRun.objects.filter(Q(user=user) | Q(agent__user=user)).distinct()


def list_agents_for_user(user, *, mode_filter: str | None = None) -> list[dict]:
    queryset = ServerAgent.objects.filter(user=user).prefetch_related("servers")
    if mode_filter in {ServerAgent.MODE_MINI, ServerAgent.MODE_FULL, ServerAgent.MODE_MULTI}:
        queryset = queryset.filter(mode=mode_filter)

    current_time = timezone.now()
    execution_readiness = get_agent_execution_readiness()
    data: list[dict] = []
    for agent in queryset:
        last_run = AgentRun.objects.filter(agent=agent).select_related("server").first()
        active_run = (
            AgentRun.objects.filter(agent=agent, status__in=ACTIVE_AGENT_RUN_STATUSES).select_related("server").first()
        )
        data.append(
            serialize_agent_item(
                agent,
                now=current_time,
                last_run=last_run,
                active_run=active_run,
                execution_readiness=execution_readiness,
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
    execution_readiness = get_agent_execution_readiness()
    summary = {
        "total_scheduled": 0,
        "enabled": 0,
        "paused": 0,
        "due_now": 0,
        "active_runs": 0,
    }
    for agent in agents:
        last_run = AgentRun.objects.filter(agent=agent).select_related("server").first()
        active_run = (
            AgentRun.objects.filter(agent=agent, status__in=ACTIVE_AGENT_RUN_STATUSES).select_related("server").first()
        )
        item = serialize_agent_item(
            agent,
            now=current_time,
            last_run=last_run,
            active_run=active_run,
            execution_readiness=execution_readiness,
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
    """Queue any agent mode (mini/full/multi) for the execution-plane worker.

    Never runs SSH/LLM inside the HTTP request — that blocked Daphne threads and
    left orphan ``running`` rows when the client timed out or the worker hung.
    """
    limit_error = get_agent_run_limit_error(user)
    if limit_error:
        return {"ok": False, "status": 429, "payload": limit_error}

    launch_result = launch_queued_agent_run(
        agent=agent,
        user=user,
        accessible_servers_queryset=accessible_servers_queryset,
        server_id=int(server_id) if server_id is not None else None,
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
            extra_payload={
                "server_id": run_result.server_id,
                **(extra_event_payload or {}),
            },
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
    run = (
        _owned_agent_run_queryset(user)
        .filter(
            id=run_id,
            status=AgentRun.STATUS_WAITING,
        )
        .first()
    )
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
    run = (
        _owned_agent_run_queryset(user)
        .filter(
            id=run_id,
            status=AgentRun.STATUS_PLAN_REVIEW,
        )
        .select_related("agent", "server")
        .first()
    )
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
    servers, denied_server_ids = resolve_servers_for_user_capability(
        server_ids,
        user,
        CAPABILITY_EXECUTE_COMMAND,
        base_queryset=accessible_servers_queryset,
    )
    if denied_server_ids:
        return {
            "ok": False,
            "status": 403,
            "payload": {"success": False, "error": "Missing server capability: execute_command"},
        }
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
