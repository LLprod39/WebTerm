from __future__ import annotations

import contextlib
from datetime import timedelta

from asgiref.sync import async_to_sync
from django.utils import timezone

from app.runtime_limits import ACTIVE_AGENT_RUN_STATUSES, get_agent_run_limit_error
from servers.agent_background import launch_plan_execution_background
from servers.agent_dispatch import cancel_agent_dispatches_for_run, serialize_agent_dispatch
from servers.agent_launch import launch_full_agent_run
from servers.agent_runtime import get_engine_for_agent, get_engine_for_run, update_runtime_control
from servers.agents import run_agent, run_agent_on_all_servers
from servers.models import AgentRun, ServerAgent, ServerWatcherDraft
from servers.run_events import record_run_event
from servers.scheduled_agents import dispatch_scheduled_agents, is_agent_due
from servers.watcher_actions import ensure_watcher_agent, mark_watcher_draft_launched
from servers.worker_state import serialize_background_worker_state


def compute_next_due_at(agent: ServerAgent, now=None):
    current_time = now or timezone.now()
    schedule_minutes = max(int(agent.schedule_minutes or 0), 0)
    if schedule_minutes <= 0:
        return None
    if agent.last_run_at is None:
        return current_time
    return agent.last_run_at + timedelta(minutes=schedule_minutes)


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


def serialize_agent_item(agent: ServerAgent, *, now=None, last_run: AgentRun | None = None, active_run: AgentRun | None = None) -> dict:
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
        "server_names": list(agent.servers.values_list("name", flat=True)),
        "schedule_minutes": int(agent.schedule_minutes or 0),
        "is_enabled": bool(agent.is_enabled),
        "commands": agent.commands,
        "ai_prompt": agent.ai_prompt,
        "goal": agent.goal,
        "system_prompt": agent.system_prompt,
        "max_iterations": agent.max_iterations,
        "allow_multi_server": agent.allow_multi_server,
        "last_run_at": agent.last_run_at.isoformat() if agent.last_run_at else None,
        "last_run_status": last_run.status if last_run else None,
        "last_run_id": last_run.id if last_run else None,
        "active_run_id": active_run.id if active_run else None,
        "schedule_state": compute_schedule_state(agent, current_time),
        "due_now": bool(next_due_at is not None and next_due_at <= current_time and agent.is_enabled),
        "next_due_at": next_due_at.isoformat() if next_due_at else None,
        "next_due_in_seconds": next_due_in_seconds,
    }


def list_agents_for_user(user, *, mode_filter: str | None = None) -> list[dict]:
    queryset = ServerAgent.objects.filter(user=user).prefetch_related("servers")
    if mode_filter in {ServerAgent.MODE_MINI, ServerAgent.MODE_FULL, ServerAgent.MODE_MULTI}:
        queryset = queryset.filter(mode=mode_filter)

    current_time = timezone.now()
    data: list[dict] = []
    for agent in queryset:
        last_run = AgentRun.objects.filter(agent=agent).first()
        active_run = AgentRun.objects.filter(agent=agent, status__in=ACTIVE_AGENT_RUN_STATUSES).first()
        data.append(serialize_agent_item(agent, now=current_time, last_run=last_run, active_run=active_run))
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
        item = serialize_agent_item(agent, now=current_time, last_run=last_run, active_run=active_run)
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
        "execution_plane": serialize_background_worker_state("agent_execution"),
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
        record_run_event(run_result.id, "agent_manual_dispatch", _manual_dispatch_payload(
            agent=agent,
            source=source,
            extra_payload=extra_event_payload,
        ))
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
        record_run_event(
            run.id,
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
    run_query = AgentRun.objects.filter(
        agent_id=agent_id,
        agent__user=user,
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

    run.status = AgentRun.STATUS_STOPPED
    run.completed_at = timezone.now()
    run.save(update_fields=["status", "completed_at"])
    record_run_event(
        run.id,
        "agent_control_stop_requested",
        {
            "agent_id": agent_id,
            "source": source,
            "message": "Run stopped by operator request",
        },
    )
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
    run = AgentRun.objects.filter(
        id=run_id,
        agent__user=user,
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
    return {"ok": True, "payload": {"success": True}}


def approve_agent_plan_for_user(*, run_id: int, user, accessible_servers_queryset, source: str = "http") -> dict:
    run = AgentRun.objects.filter(
        id=run_id,
        agent__user=user,
        status=AgentRun.STATUS_PLAN_REVIEW,
    ).select_related("agent", "server").first()
    if not run:
        return {
            "ok": False,
            "status": 404,
            "payload": {"success": False, "error": "Run not found or not awaiting plan approval"},
        }

    agent = run.agent
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
